# SESSION 042 — GLM→Qwen Weight-Transfer Feasibility: NO-GO

**Date:** 2026-11-11
**Branch:** `exp/zai-042-glm-weight-transfer` (from `561de13`, which carries the
041A memorial on top of the SESSION040 final `84dbc39`)
**Question:** can knowledge encoded in Z.ai's GLM weights be transferred
directly into Qwen2.5-Coder-0.5B without increasing its CPU inference cost?

**Verdict: NO-GO.** Direct GLM→Qwen weight transfer is technically infeasible
in this environment for four independent, individually sufficient reasons
(dimension/geometry incompatibility, representation-space incompatibility —
measured, not assumed; resource limits on every code-capable donor; and the
absence of any valid non-training transfer mechanism). No experimental
checkpoint was created, per the session brief's instruction to stop at the
feasibility check when the answer is negative. Sessions 040–041, the original
Qwen checkpoint, and the sealed 24-task holdout are untouched.

---

## 1. What "the GLM donor" actually is (availability audit)

| candidate | access path | size | usable here? |
|---|---|---|---|
| Z.ai production GLM (the model behind `z-ai-web-dev-sdk`) | chat/images/video/ASR/TTS **inference API only** — the SDK's entire type surface was inspected (`dist/index.d.ts`): `chat.completions.create`, `images.generations`, …; no weight download/export exists | n/a | **no weights exist client-side to transfer** |
| `zai-org/glm-edge-1.5b-chat` | open weights, single 3.05GB safetensors | 1.5B | the **only** donor within disk (3.2GB free) and RAM (4GB) — but it is a general *chat/edge* model, not code-specialized |
| `THUDM/codegeex4-all-9b` (GLM-family code model) | open weights, 4 shards | ~18GB | exceeds disk and RAM — cannot even be loaded |
| `THUDM/glm-4-9b-chat` | 10 shards | ~18GB | same |
| `THUDM/chatglm3-6b` | 7 shards | ~12GB | same |
| GLM at Qwen-0.5B scale | does not exist publicly (repo probe: `zai-org/GLM-4-0.5B` missing) | — | — |

No GLM model exists anywhere on local disk (filesystem search of HF cache
and model directories); the only GLM "presence" in this sandbox is the
SDK's inference endpoint, which cannot donate weights by construction.

## 2. Architecture and dimension comparison (from pinned configs)

| property | Qwen2.5-Coder-0.5B (recipient) | GLM-Edge-1.5B-Chat (only feasible donor) | implication |
|---|---|---|---|
| class | `Qwen2ForCausalLM` | `GlmForCausalLM` | different module trees |
| layers | 24 | 28 | no depth correspondence |
| hidden | 896 | 2048 | every per-layer tensor's IO dims mismatch (2.29×) |
| attention | 14 heads × 64 | 16 heads × 128 | head_dim mismatch blocks even head-wise surgery |
| KV heads (GQA) | 2 | 4 | different compression geometry |
| intermediate (MLP) | 4,864 | 6,144 | mismatched |
| vocab | 151,936 | 59,264 | different tokenizers; only 13,773 shared printable-ASCII token strings |
| RoPE theta | 1,000,000 | 10,000 | different positional frequency geometry |
| RMSNorm eps | 1e-6 | 1e-5 | different activation-scale statistics |
| params | 494M | 1.5B | donor 3× recipient |
| tied embeddings | yes | yes | (the one structural similarity — exploited by the probe) |
| on-disk dtype | bf16 | bf16 | — |

## 3. The measured feasibility probe (the heart of this session)

Weight transfer without fine-tuning requires some correspondence between
the two models' representation spaces. The one place that correspondence is
*measurable without loading the full donor* is the embedding matrix — and
because both models tie embeddings to the LM head, it is simultaneously the
output head: the single most consequential tensor for "knowledge". A 231MB
HTTP-range fetch of `model.embed_tokens.weight` from the donor's 3.05GB
safetensors (offsets parsed from the live file header, verified) was all
that was needed; **the full donor model was never downloaded**.

**Protocol** (`archagent/s042/probe_alignment.py`, no gradients anywhere):
13,777 shared printable-ASCII byte-level-BPE token strings as anchors
(both tokenizers use the GPT-2 unicode byte convention, so string identity
is exact); deterministic 50/50 train/held-out split; closed-form orthogonal
Procrustes `P = argmin ||A P − B||` on the train half (2048→896);
held-out evaluation against two nulls (shuffled pairing; random orthogonal
projection); plus a semantic kNN probe on code tokens.

**Results** (`experiments/z042-glm-transfer/embedding-alignment-probe.json`):

| metric | value | meaning |
|---|---|---|
| train cosine | 0.484 | the fit can memorize its own anchors |
| **held-out cosine** | **0.086** | vs **0.077** shuffled-pairing null → **+0.009** of actual signal |
| held-out explained variance | **−1.52** | the projection is *worse than predicting zero* |
| cross-correlation spectrum | s₁=205, s₂=7.7, then flat ~2.6 | one shared mean-direction and nothing else |
| centered variant (means removed) | held-out cos **0.0094**, EV −1.69 | removing the mean direction leaves zero structure |

**Leakage audit** (the result initially *looked* half-successful — some
code tokens projected to rank-1 same-string neighbors at cos ≈ 0.5): a
split audit showed **every** rank-1 token (`def`, `class`, `return`,
`const`, `await`, `if`, `true`, `None`, `print`, `request`, `error`,
`status`, `route`) was in the Procrustes *train* half, and **every**
failed token (`import`, `function`, `async`, `for`, `while`, `false`,
`export`, `data`, `schema`, `model`, `state`) was held-out. The apparent
alignment was train-set memorization, not shared structure.

**Machinery sanity**: the identical pipeline run Qwen-to-Qwen (self
alignment, held-out) returns cosine **1.0000** — the probe is exact; the
GLM result is real, not an artifact.

**Interpretation.** The two embedding spaces share (i) a mean direction
and (ii) nothing else linearly. Independent training runs do not produce
interoperable representation codes — consistent with the model-stitching
literature (alignment across independently trained networks recovers only
trivial structure absent a learned realignment). Any transfer built on a
2048→896 projection would be built on a correspondence measured at +0.009
cosine over null.

## 4. The four candidate methods, analyzed

1. **Layer slicing** (take 896 of the donor's 2048 coordinates): coordinate
   systems of independently trained networks carry no cross-run semantics —
   they do not even align up to permutation (the Git Re-Basin result), and a
   coordinate *subset* is strictly worse. Slicing also rescales per-layer
   Frobenius norms by ≈ √(896/2048), shattering the recipient's RMSNorm
   statistics (different eps values compound this).
2. **Weight pruning** (prune the 1.5B donor down to ~0.5B, then
   transplant): pruning removes capacity but preserves the donor's internal
   representational code — the very thing that does not correspond (§3).
   It addresses donor size, not compatibility; and pruning a general chat
   model to donate to a code-specialized recipient inverts the knowledge
   gradient.
3. **Selective tensor transplantation**: embeddings/lm_head are blocked by
   the vocab mismatch (59,264 vs 151,936; 13,773 shared strings) *and* by
   the measured absence of a token-space correspondence. Per-layer tensors
   all have mismatched IO dimensions (896/2048, 4864/6144, head_dim 64/128,
   KV 2/4); there is no layer-index correspondence (28 vs 24) and the
   rotary bases differ by 100×. No tensor family survives.
4. **Projection-based weight transfer**: the only variant compatible with
   the no-fine-tuning constraint is a *closed-form* cross-space map.
   §3 measures the best case of exactly that, at the most favorable site,
   and finds no generalizable linear structure (held-out +0.009 over null;
   EV negative). A learned projection (the only alternative) is by
   definition gradient-based alignment — i.e. fine-tuning, which this
   session forbids and which would also require paired activations that
   cannot even be constructed across different tokenizations (token
   sequences and positions do not correspond).

## 5. Resource ceiling on every better donor

The GLM family's code-capable open models (CodeGeeX-4-9B, GLM-4-9B; the
larger GLM-4.x are far beyond) require ~18GB of weights against this
sandbox's 3.2GB free disk and 4GB RAM — they cannot be loaded, and no
streaming tensor surgery changes the representation-compatibility result
of §3 (it would only relocate the same incompatibility). The instruction
to report rather than burn hours was applied here: the strongest feasible
donor was probed for ~30 minutes of wall time, total.

## 6. Why no experimental checkpoint was created

Instruction 5 gates checkpoint creation on "a technically justified,
CPU-feasible weight-transfer method". The probe falsifies the necessary
condition for every gradient-free method (§4), the remaining method class
requires training (forbidden, and separately unauthorized), and no
code-specialized donor fits the machine (§5). Creating a checkpoint anyway
would mean injecting a measured-to-be-meaningless perturbation into a
working model and calling it transfer — precisely the substitution the
session brief forbids. Correspondingly, no dev-set before/after comparison
was run (nothing valid exists to compare; the brief's step 6 presupposes a
created checkpoint).

## 7. Integrity

- Branch isolation: all work on `exp/zai-042-glm-weight-transfer`; no other
  branch touched; Sessions 040–041 fully preserved on their branches.
- The original Qwen checkpoint was **read only** (memory-mapped) and its
  pin `aff8914e…a47f80` remains verified; the 041B merged checkpoint
  recovered last session is untouched.
- The sealed 24-task holdout was not accessed (the s039 loader's refusal
  remains in force; nothing holdout-adjacent entered any prompt or
  artifact).
- No fine-tuning, no cloud resources, no destructive modifications; the
  donor contributed 231MB of range-fetched embedding bytes and nothing
  else; no model-generated code was executed this session.
- Zero-budget honesty: the session consumed ~45 minutes of wall time, one
  231MB network fetch, and minutes of CPU — the stop discipline for
  infeasible paths was honored.

## 8. Honest recommendation

**NO-GO, and it is not close.** For a real coding improvement on this
checkpoint, the evidence across Sessions 037–041 points at supervised
fine-tuning on verified candidates (041B: pipeline proven, one cross-domain
family gain, +Track-B 1/6 with crashes halved) and, if authorized, the
pre-declared Stage-2 contrastive step on task-noun binding — not weight
transfer from an incompatible donor family. If GLM assistance is desired
for *data* (not weights), that is a separate, explicitly-authorized
conversation — and it would be fine-tuning/teacher-data work, which this
session deliberately did not substitute.

*Every number above traces to an archived artifact on this branch
(`experiments/z042-glm-transfer/`, `archagent/s042/`); nothing is simulated
or extrapolated.*
