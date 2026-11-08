# Exploratory frozen-Qwen protocol pilot

Two deliberately small function-implementation tasks, one Python and one
JavaScript. This is **not** a full-stack benchmark or independent proof of
transferable learning. Both tracks use the same frozen 0.5B Instruct model.

## First measured run (2026-11-08)

[GitHub Actions run 42467678175](https://github.com/7clan/ai-wieght-optimiization/actions/runs/42467678175)

- Runner succeeded; model inference and sandbox were real.
- Solo public passes: **0/2**; controller-assisted public passes: **0/2**.
- Both solo outputs were JSON-valid, but their artifacts did not expose the
  required Python/JavaScript module paths. The resulting errors were
  `ModuleNotFoundError` and Node `MODULE_NOT_FOUND`.
- Controller on Python: 3 proposals, 1 evaluation, blocked for lack of
  progress. Controller on JavaScript: 2 proposals, 2 evaluations, exhausted.
- 2 CPU threads, 400-token generation cap, approximately 3.25 GiB peak RSS.
- Teacher repairs: zero; docs search: off; weight changes: zero.
- An artifact containing the exact JSON report is attached to the run.

## v2 correction (subsequent run; do not combine scores across versions)

1. Each task now provides an **explicit required file path** to both solo
   and controller tracks. This is contract scaffolding, not intrinsic model
   learning; it modifies the prompt and may change both tracks' results.
2. Missing required paths are rejected *before* Docker evaluation, and the
   controller receives targeted file-contract feedback.
3. Controller proposals record paths, checks, diagnostic previews and source
   hashes. This allows independent audits of what Qwen actually proposed.
4. When no candidate passes public tests, holdout evaluation uses the best
   candidate selected **only by public checks**; private tests remain sealed
   until both tracks finish generation.

The next CI run will report v2 results. A score difference from v1 measures
the **protocol/contract change**, not an increase in model intelligence.

## Reproduce

On a Docker-capable environment with CPU PyTorch, Transformers and the frozen
Qwen checkpoint accessible:

```bash
python -m experiments.adaptive.pilot --output experiments/adaptive/pilot_report.json --max-new-tokens 400
```

Real model outputs execute only inside the `DockerSandbox`; no host fallback.
