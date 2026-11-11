# SESSION 041C — RECOVERY VERIFICATION RECORD

**Date:** 2026-11-11 (recovery session, immediately after both Z-environment
resets)
**Mode:** RECOVERY ONLY — no retraining, no benchmark re-runs, no evaluator
re-execution beyond the unit suite, holdout never touched.
**Branch:** `exp/zai-041-coding-finetune` (recovery work confined to it;
`main` and every other branch untouched).

## 1. Situation

Session 041B (LoRA Stage-1) was complete and pushed: the remote branch stood
at `adf668f` (041B final). Session 041C completed experimentally in a second
environment, but that environment reset **before the two 041C commits were
pushed**; its ledger row 16 wrote "branch pushed" prematurely — the push
never reached the remote. The user recovered artifacts out-of-band; this
record documents their verification and the restore of the branch.

## 2. Recovery sources (all under the recovered `download/` area)

| source | what it is |
|---|---|
| `session041c-commits.bundle` | git bundle carrying both unpushed 041C commits |
| `0001-SESSION041C-duplicate-title-evaluator-corrected-039B.patch` | PATCH 1/2 as a standalone file |
| `0002-SESSION041C-longer-code-generation-benchmark-report-.patch` | PATCH 2/2 as a standalone file |
| `ZAI_SESSION041C_EVALUATOR_CORRECTION_LONGBENCH.md` | 041C report copy |
| `session041c-experiment-README.md` | 041C experiment README copy |
| `session041b/` | 041B checkpoint recovery set (adapter tarball, manifests, train/bench/eval artifacts, 041B report) |

## 3. Verification performed (fresh sandbox; nothing re-executed)

1. **Bundle integrity:** `git bundle verify` = okay; the bundle *requires*
   `adf668f9802c…d7bc1265` — exactly the remote head at recovery time — and
   contributes exactly two commits on top:
   `a874d9b71b9d…915c88c` (evaluator correction) and
   `550a337400dc…f10253` (long-benchmark + report + ledger).
2. **PATCH 1/2 was NOT missing after all — it is fully recoverable:**
   - it exists as commit `a874d9b` inside the bundle, with intact original
     history, author and message; and
   - the standalone `0001-…patch` file is **byte-identical** to
     `git format-patch` of `a874d9b` (numbered-series form); likewise
     `0002-…patch` == commit `550a337`. No reconstruction was needed.
3. **Report copies:** recovered 041C report and experiment README are
   byte-identical to `docs/ZAI_SESSION041C_EVALUATOR_CORRECTION_LONGBENCH.md`
   and `experiments/z041c-evaluator-correction/README.md` at `550a337`.
4. **041B checkpoint restore (hash-parity, all byte-identical to the
   committed repo state):**
   - `session041b/lora-adapter.tar.gz` → all 10 adapter files match
     `experiments/z041-coding-finetune/train/adapter/` AND the
     `merged-checkpoint/merge-manifest.json` per-file SHA-256 manifest
     (adapter_model.safetensors
     `7d272330b830…ed58c32`);
   - frozen base model safetensors re-hashed
     `aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80`
     (== manifest `base_model_sha256`, both recovered copies);
   - `train-config.json`, `train-log.jsonl`, `train-summary.json`,
     `cpu-bench.json`, `eval/base/summary.json`, `eval/merged/summary.json`,
     `merge-manifest.json` — every one byte-identical to the committed
     041B artifacts;
   - recovered `ZAI_SESSION041B_REPORT.md` == the `adf668f` version; the
     `550a337` version differs only by the 041C ERRATUM addendum (original
     publication preserved unmodified, by design).
5. **Security scan of the two recovered commits:** zero PAT/token patterns
   (`ghp_…`, `github_pat_…`, `gho_…`, `ghs_…`, `x-access-token`) in the
   combined diff; no credential-like files anywhere in the tree at `550a337`;
   no holdout paths touched by either commit.
6. **Essential verification run (unit suite, pytest 9.0.2, no torch in the
   fresh sandbox):**
   - 041C-touched test files: `tests/test_z041c.py` +
     `tests/test_s039_route_eval.py` = **28/28 passed**, including
     `test_corrected_post_plan_is_a_strict_superset_of_the_frozen_plan`,
     the rescore provenance flip, the amendment disclosure and the
     holdout-seal tests;
   - whole suite excluding the 7 torch/transformers-dependent legacy files:
     **180 passed, 10 skipped, 13 subtests passed** (0.56 s);
   - honest limitation: those 7 legacy files (`test_archcircuits_corrections`,
     `test_attention_steering`, `test_branch_experiments`,
     `test_fusion_validation`, `test_rome_batch`, `test_session015`,
     `test_weight_space`) are **byte-unchanged by the 041C commits** (tests/
     diff touches only `test_s039_route_eval.py` and adds `test_z041c.py`);
     they were last verified in the pinned 041C environment as part of the
     archived "231 passed / 10 skipped / 17 subtests" run. Re-installing the
     torch pin merely to repeat them was judged against the recovery
     priority ("stop wasting computation on repeated experiments"); their
     pass state is unaffected by recovery because their bytes are identical.

## 4. Action taken

The branch was fast-forwarded to the bundle head — the ORIGINAL commits were
restored, nothing was re-applied or cherry-picked:

```
adf668f (remote, 041B final)
   └── a874d9b  SESSION041C: duplicate-title evaluator corrected   (= PATCH 1/2)
        └── 550a337  SESSION041C: longer code generation benchmark  (= PATCH 2/2)
             └── (this recovery-record commit)
```

Then this record + ledger row 17 were committed and the branch pushed to
`origin/exp/zai-041-coding-finetune`.

## 5. Explicitly not done (recovery constraints)

- No retraining or fine-tuning of any kind (041B checkpoint preserved as-is).
- No re-run of the long-generation benchmarks or the control matrices
  (archived evidence stands; the unit suite re-validated the correction
  logic).
- No holdout access of any kind — the 24-task holdout stays sealed.
- No Docker, GPU, cloud or billable resources.
