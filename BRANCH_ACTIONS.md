# Branch Action Ledger — `exp/zai-042-glm-weight-transfer`

This file is the per-branch action ledger. It exists **only on the
branch named in the title**, so its very presence identifies the
branch you are looking at:

    git show exp/zai-042-glm-weight-transfer:BRANCH_ACTIONS.md   # exists (this file)
    git show main:BRANCH_ACTIONS.md                               # errors

Every commit created from an action in this ledger also carries the
prefix `[exp/zai-042-glm-weight-transfer]` in its subject.

## Branch facts

- Branch: `exp/zai-042-glm-weight-transfer`
- Forked from: `561de13` (041A memorial on top of SESSION040 final
  `84dbc39`) on 2026-11-11
- Scope guarantee: no action in this ledger writes to any other branch
  or to `main`; every push goes to
  `origin/exp/zai-042-glm-weight-transfer` only
- Work: SESSION 042 — final weight-transfer feasibility experiment:
  can GLM-family weights be transferred into Qwen2.5-Coder-0.5B without
  training and without CPU-inference cost? **Verdict: NO-GO** (see
  `docs/ZAI_SESSION042_GLM_TRANSFER_FEASIBILITY.md`). No experimental
  checkpoint was created; the original model was read-only throughout.

## Ledger

Rows are append-only. The "Commit" column records the commit that
contains the action; a row is filled in by the next ledger update, so
the newest row may still say "this commit".

| # | UTC time | Action | Outcome | Commit |
|---|----------|--------|---------|--------|
| 1 | 2026-11-11T13:30Z | Branch created from `561de13` and pushed; duplicate 041B merged checkpoint in the `/tmp/z041b` worktree removed to free 1GB (the repo-path copy kept) | Branch on origin | this commit |
| 2 | 2026-11-11T13:35Z | Donor availability audit: filesystem search (no local GLM; HF cache holds only the pinned Qwen); `z-ai-web-dev-sdk` type surface inspected — inference API only (chat/images/video/ASR/TTS), no weight access; HF enumeration of the GLM family: only `zai-org/glm-edge-1.5b-chat` (3.05GB, single shard) fits disk/RAM; CodeGeeX-4-9B / GLM-4-9B (~18GB) and ChatGLM3-6B (~12GB) cannot load; no 0.5B-scale GLM exists | Donor identified: GLM-Edge-1.5B-Chat (general chat model, not code-specialized) | this commit |
| 3 | 2026-11-11T13:40Z | Architecture/dimension comparison from pinned configs (donor config.json downloaded, 2KB): hidden 896/2048, heads 14×64/16×128, KV 2/4, layers 24/28, intermediate 4864/6144, vocab 151,936/59,264, RoPE theta 1e6/1e4, RMSNorm eps 1e-6/1e-5 — every per-layer tensor family dimensionally incompatible; both models tie embeddings to lm_head | Full mismatch table recorded in the report | this commit |
| 4 | 2026-11-11T13:45–14:10Z | Measured feasibility probe (`archagent/s042/probe_alignment.py`): parsed the live donor safetensors header and HTTP-range-fetched ONLY the 231MB `model.embed_tokens.weight` (full 3.05GB model never downloaded); 13,777 shared printable-ASCII byte-level-BPE anchors; closed-form orthogonal Procrustes (2048→896) with deterministic 50/50 split, two null baselines, semantic kNN on code tokens, cross-correlation spectrum | Held-out cosine 0.086 vs 0.077 shuffled-null (+0.009 signal); EV −1.52; spectrum s₁=205 then flat ~2.6 → one shared mean direction, nothing else | this commit |
| 5 | 2026-11-11T14:10–14:20Z | Verification pass: (a) kNN split audit — every rank-1 "aligned" code token is a TRAIN anchor, every failure held-out (memorization, not structure); (b) probe machinery sanity — Qwen-to-Qwen self-alignment returns held-out cosine 1.0000 exactly; (c) centered variant — held-out cos 0.0094, EV −1.69 (removing the mean direction leaves zero). Artifacts: `experiments/z042-glm-transfer/{embedding-alignment-probe,alignment-verification}.json` | Probe verdict confirmed airtight | this commit |
| 6 | 2026-11-11T14:20–14:35Z | Four-method feasibility analysis (layer slicing / weight pruning / selective tensor transplantation / projection-based transfer — all blocked by §2 dimensions + §3 measurement + no-gradient constraint); resource ceiling documented for every code-capable donor; NO-GO report written (`docs/ZAI_SESSION042_GLM_TRANSFER_FEASIBILITY.md`); gitignore rule for the 231MB probe cache; **no checkpoint created** per the brief's step-5 gate (no technically justified method exists); original Qwen read-only, holdout sealed, no fine-tuning, no cloud | **NO-GO with evidence**; session cost ~45 min wall / 231MB fetch / minutes of CPU | this commit |
