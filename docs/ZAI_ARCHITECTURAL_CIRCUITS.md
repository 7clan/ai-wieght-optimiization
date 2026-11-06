# ZAI Architectural Circuits — Session 010 Research Report

**Branch:** `exp/zai-architectural-circuits`
**Base commit:** `1868a8d` (main, Session 009 launch state)
**Model:** `Qwen/Qwen2.5-Coder-0.5B` (base checkpoint, untouched on disk; all edits applied in RAM only)
**Compute:** 2 vCPU, 4 GB RAM, CPU-only PyTorch 2.15 (fp32), no GPU, no local Docker
**Duration:** single research session; every number below comes from an executed run archived in
`experiments/archcircuits/reports/`.

---

## 1. Mission and hypotheses

The assignment asked whether specific architectural coding behaviors — variable
tracking, interface-contract compliance, JavaScript reasoning, cross-component
consistency — can be **causally localized** in Qwen2.5-Coder-0.5B and
**improved through direct, reversible weight-space programming**, and whether
any improvement **generalizes** beyond the tasks used to construct the edits.

Working hypotheses:

* **H1 (localization).** Distinct architectural-reasoning behaviors are
  carried by identifiable, causally testable sites (layers/components/heads).
* **H2 (steering).** A contrastive "correct-vs-incorrect continuation"
  direction at a causally validated site, installed as a bounded low-rank
  weight edit, strengthens the targeted behavior.
* **H3 (composition).** Independently derived edits can coexist if their
  factor subspaces are sufficiently separated.
* **H4 (generalization).** Effects transfer to unseen identifiers, domains,
  and structures.

**H1 and H3 were supported. H2 was supported only on the construction set.
H4 was rejected.** The remainder of this document is the evidence.

## 2. Constraints honored

* No backpropagation, gradients, optimizers, LoRA, or fine-tuning anywhere;
  every intervention is a closed-form tensor edit (rank-one ridge projection,
  Woodbury multi-key least squares, joint multi-category subspace solve).
* Parameter count unchanged (0.49B); no larger model involved.
* Per-matrix observed Frobenius change capped at **≤ 1.5%** (repository norm
  limit); every applied edit's exact relative norm is recorded in its factor
  metadata. The base checkpoint file was never modified.
* All edits are exactly reversible: `W ±= left @ right`; reversibility was
  verified to 0.0 max-abs difference after apply+revert.
* **Zero HumanEval usage** — all 164 HumanEval IDs were consumed by Sessions
  001–009, so every task here was authored fresh (contamination risk:
  the model may have seen similar *kinds* of problems in pretraining, which
  applies equally to baseline and edited conditions).
* Model-generated code was **never executed**. Primary metrics are
  short-answer exact-match against gold values that were themselves verified
  by executing *our own reference snippets* (28 Python, 28 Node, 56
  structural checks) — see `archcircuits/verify_gold.py`. The benchmark
  deliberately avoids executing Qwen's outputs, so the local absence of
  Docker (see §9) does not weaken any reported score.

## 3. Phase A — ArchBench benchmark

`archcircuits/benchmark.py` defines **112 short-answer tasks** in four
categories with three difficulty levels each:

| Category | Skills | Example task |
| --- | --- | --- |
| **VAR** (28) | reassignment chains, aliasing vs copying, closures, cross-call state | `a=[1,2]; b=a; b.append(3)` → value of `a`? |
| **CON** (28) | exact signatures, returned JSON shapes, binding to contracted names, error contracts | which function name fills the blank given the import contract? |
| **JSR** (28) | array/object transforms, promise/async ordering, express status/method | logged order of sync/microtask/timeout `console.log`s |
| **XCOM** (28) | storage↔API↔frontend field/method binding, rename propagation | which key keeps two files consistent after an update? |

Partitions were fixed before any intervention was constructed:
**dev 48 / val 32 / holdout 32** (12/8/8 per category). The holdout was
authored with deliberately different identifier names (crew/roster/silo
domains vs cart/user/storage), different structures, and harder variants.
46 of 48 dev tasks carry a **counterfactual variant** (a modified critical
value with its own gold answer) used only for causal patching; two
documented exceptions (`XCOM-010`, initially `JSR-003`) had answers
invariant under their counterfactual edit.

Scoring (`archcircuits/scoring.py`) normalizes numeric, list, dict
(Python and JS-style), string, identifier, signature (type-hint-stripped)
and log-order answer forms, then exact-matches. Generation is greedy,
24 new tokens, identical prompts across every condition.

**Baseline (untouched model):** 54.9% overall — VAR 46%, CON 39%, JSR 66%,
XCOM 66%. Syntax/structure validity of code-line answers: 96%. Full records:
`reports/baseline.json`. The short-answer format avoids the 2–4% HumanEval
floor effect of prior sessions and gives measurable headroom.

## 4. Phase B — causal localization (supported H1)

For each patchable dev task we ran **value-swap counterfactual patching**:
patch activations from the counterfactual run into the original run at the
critical span's token positions, across 11 layers × {attn, mlp}, and measured
the shift of `log p(cf answer token) − log p(orig answer token)` at the
commitment position (the position predicting the first token where gold and
counterfactual answers diverge; numeric answers tokenize digit-by-digit, so
the bare leading space must be skipped — see `archcircuits/tracing.py`).

Aggregated mean mediation (46 tasks, `reports/trace_merged.json`):

| Category | Top site | Mean mediation | Tasks with positive effect |
| --- | --- | ---: | ---: |
| VAR | **L14 / mlp** | 0.530 | 8/12 |
| CON | **L16 / mlp** | 0.724 | 8/12 |
| JSR | L6 / mlp | 0.153 | 6/11 |
| XCOM | **L16 / mlp** | 1.342 | **11/11** |

Per-head refinement (`reports/heads_L16.json`): **layer 16, head 10** is a
near-monomediatory contract head — patching only its 64-dim slice of the
`o_proj` input moves the XCOM-005 answer with mediation 1.43, XCOM-001 0.29,
CON-001 0.08, while all other heads stay ≈ 0. Variable tracking shows no
single-head structure (MLP-carried), and JS reasoning is weakly and
distributedly localized.

**Interpretation caution:** mediation scores show these sites *carry* the
task-relevant information at the patched positions; they do not prove the
sites *implement* an abstract "contract-following skill". Early layers
(L2/L4 mlp, mediation 0.2–0.4 everywhere) most likely carry token-identity
information about the changed values themselves.

## 5. Phase C — weight-space interventions (H2: construction-set only)

For each category we captured, at the causally selected layer's
`mlp.down_proj`, the gold-forced and wrong-forced outputs at the divergence
token, computed the contrastive direction
`d = mean(v_gold) − mean(v_wrong)` over the 12 dev tasks (wrong answers =
the baseline model's own errors, with deterministic distractor fallback),
and solved either a rank-one ridge projection
`ΔW = α d (C⁻¹k̄)ᵀ/(k̄ᵀC⁻¹k̄)` or a multi-key Woodbury least-squares update
that pushes every error-conditioned key's output toward `Wk + αd`. All
factors: `experiments/archcircuits/factors/`.

| Factor set | Site | Rel. ‖ΔW‖/‖W‖ | Contrast quality (cos gold↔wrong) |
| --- | --- | ---: | ---: |
| `con_L16` | L16 mlp.down_proj | 1.38% | 0.34 |
| `xcom_L16` | L16 mlp.down_proj | 0.99% | 0.45 |
| `var_L14` | L14 mlp.down_proj | 0.92% | 0.61 |
| `jsr_L6` | L6 mlp.down_proj | 1.38% | 0.46 |
| `joint_L16` (CON+XCOM keys, per-category directions) | L16 | 1.50% | — |
| `contract_v2_L16` (refinement: unit-norm per-task contrast, both-side keys) | L16 | 0.82% | — |

Because the 1.5% cap dominates the applied magnitude, α is effectively
absorbed by the cap; the edit *shape* (direction + key geometry + ridge) is
what differs across candidates.

**Construction-set (dev) results:**

| Condition | VAR | CON | JSR | XCOM | Overall |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 5/12 | 6/12 | 7/12 | 7/12 | 25/48 |
| `con_L16` | 5/12 | **8/12** | 8/12 | 7/12 | 28/48 |
| `var_L14` | **4/12 ↓** | 6/12 | 7/12 | 7/12 | 24/48 |
| `jsr_L6` | 5/12 | 7/12 | 7/12 | 7/12 | 26/48 |
| `joint_L16` | 5/12 | **8/12** | 7/12 | 7/12 | 27/48 |
| sequential `con+xcom` | 5/12 | **8/12** | 8/12 | **8/12** | **29/48** |

Task-level: `con_L16` gained exactly the two contract tasks whose error keys
were construction inputs (CON-009, CON-012) plus one JS spillover, with zero
losses. `var_L14` **regressed its own target category** (VAR-007 lost) — an
honest negative result. The v2 refinement (unit-normalized contrast, wider
key manifold) was *weaker* than v1 (+1 CON task) and was abandoned.

## 6. Phase D — interference (supported H3)

* **Geometry** (`reports/factor_geometry.json`): principal angles between the
  `con_L16` and `xcom_L16` factor subspaces are 24°/51°/76°/78° (output) —
  overlapping but not collinear, leaving room for additive composition.
* **Behavior**: sequential `con_L16`+`xcom_L16` at the *same matrix* was
  strictly additive on dev (both families' gains preserved, +1 XCOM task,
  zero losses) and indistinguishable from baseline-plus-one-task on val
  (XCOM-101 gained, no losses). Cross-layer `con`+`var` preserved the CON
  gains but inherited var_L14's VAR regression.
* **Regression probe** (`reports/regression_probe.json`): mean token NLL on
  7 unrelated real source files (the repository's own `tinycoder/` modules)
  changed by ≤ 0.004 nats for every condition including the four-edit
  sequential stack — no detectable damage to general code modeling.

## 7. Phase E — frozen-holdout generalization (H4 rejected)

The holdout was consumed once, after all candidates and combinations were
fixed. Paired task-level outcomes versus baseline (18/32 = 56.2%):

| Condition | Holdout score | Gained | Lost | Exact McNemar p |
| --- | ---: | --- | --- | ---: |
| `con_L16` | 18/32 | — | — | 1.0 |
| `xcom_L16` | 17/32 | — | XCOM-202 | 1.0 |
| `joint_L16` | 18/32 | — | — | 1.0 |
| sequential `con+xcom` | 18/32 | — | — | 1.0 |
| `var_L14` | 16/32 | — | JSR-201, XCOM-202 | 0.5 |

Teacher-forced gold-answer log-probabilities moved by only ±0.01–0.06 nats
per category (noise level); 2–5 of 32 generations changed text at all, and
none changed correctness class upward. **No intervention improved the
frozen holdout.** The v2 refinement was deliberately *not* run on the
holdout because it was dominated on the construction set and the holdout
had already served its one confirmatory use.

The effect-size gradient is diagnostic:

construction set (dev, +16.7 pp on CON) → selection set (val, +3.1 pp) →
frozen holdout (0 pp).

The edits strengthened behavior specifically on the error-conditioned keys
they were built from — a construction-set effect, not a transferable skill.

## 8. What worked, what failed

**Worked (reproducible evidence):**
1. A contamination-free architectural-reasoning benchmark with verified gold
   answers and a baseline far above the HumanEval floor.
2. Causal localization of contract/cross-component information to L16 MLP
   (11/11 task consistency) with a remarkably specific head (L16 H10).
3. Bounded, exactly reversible weight edits that improve the targeted
   construction-set behavior with zero interference and zero code-NLL cost.

**Failed:**
1. Generalization of every candidate to renamed/re-domained tasks.
2. The variable-tracking edit outright hurt its own category.
3. The unit-normalized/both-side-keys refinement (weaker than v1).

## 9. Limitations

* Single 0.5B base model, one seed, greedy decoding, 32-task holdout —
  small; only effects larger than ~±2 tasks would be detectable, and none
  approached that.
* Short-answer scoring measures architectural *understanding* cheaply but is
  not execution-tested code generation; the mission's execution criterion is
  therefore addressed only in the negative direction (no claimed improvement
  exists that would need execution confirmation).
* No local Docker: model-generated code was never executed at all, and gold
  verification ran our own reference snippets in plain subprocesses. A
  GitHub Actions workflow (`archcircuits-cpu.yml`) reproduces the baseline
  and verification pipeline on a hosted runner.
* Contrast directions were built from 12 tasks per category with
  distractor fallbacks for correctly-answered tasks; more diverse anchors
  might change the picture, but the v2 attempt argues against it.
* Causal claims are limited to information flow at the patched positions;
  "L16 H10 implements contract-following" remains an interpretive gloss.

## 10. Conclusions and next steps

1. **Localizable ≠ editable-for-transfer.** Strong, replicated causal
   mediation did not convert into generalizable behavioral gains via
   contrastive low-rank steering at the 1.5% norm budget.
2. The most defensible integration from this session is **infrastructure**:
   the benchmark, tracing tools, and factor machinery — not any weight edit.
3. Hypotheses to revise or abandon: abandon "contrastive answer-time
   steering at the top mediation site generalizes" (twice falsified here);
   revise toward (a) *question-side* edits that change how contracts are
   read rather than answer-side steering, (b) head-scoped o_proj edits
   targeting L16 H10 specifically, or (c) accepting that 0.5B-scale models
   may lack the redundant circuit capacity for lossless behavioral grafting.
4. Next experiment: an L16-H10-scoped o_proj rank-one edit (the strongest
   single mechanism found) evaluated on a freshly authored second holdout,
   since this branch's holdout is now consumed.

## Reproduction index

* Benchmark + golds: `archcircuits/benchmark.py`, `archcircuits/verify_gold.py`,
  manifest `experiments/archcircuits/manifests/benchmark_manifest.json`
* Baseline: `python3 -m archcircuits.cli baseline --output ...`
* Tracing: `python3 -m archcircuits.cli trace --category ...` (results in
  `reports/trace_*.json`, `reports/heads_*.json`, `reports/trace_merged.json`)
* Edits: `python3 -m archcircuits.cli edit ...`, `experiments/archcircuits/build_joint.py`
* Evaluations: `reports/eval_*.json`, `reports/holdout_*.json`
* Interference: `reports/factor_geometry.json`, `reports/regression_probe.json`
* Factors: `experiments/archcircuits/factors/*/` (safetensors + meta.json)

## 11. Publication status

**PUBLISHED.** The branch `exp/zai-architectural-circuits` is live at
`https://github.com/7clan/ai-wieght-optimiization/tree/exp/zai-architectural-circuits`
(remote head `ddb971b` + publication commit, verified via the GitHub API).

Publication history: the original PAT was accepted for the initial clone but
was revoked before the first push attempt (GitHub returned 401 Bad
credentials; secret-scanning revocation of an exposed token is the likely
cause). All work was committed locally and archived as a complete-history
bundle at `/home/z/architectural-circuits-branch.bundle`. A replacement PAT
was later supplied and the branch was pushed successfully with:

```bash
cd /home/z/research-repo
git push https://<NEW_PAT>@github.com/7clan/ai-wieght-optimiization.git \
  exp/zai-architectural-circuits:exp/zai-architectural-circuits
```

The bundle remains as an offline fallback:

```bash
git clone /home/z/architectural-circuits-branch.bundle -b exp/zai-architectural-circuits
```
