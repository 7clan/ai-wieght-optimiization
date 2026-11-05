# Weight-Space Programming Agent

## Objective

Explore reversible, directly computed edits to local open-model tensor weights.
**Do not use gradients, backpropagation, optimizers, training loops, or LoRA for new experiments.** The older LoRA workflow is preserved solely as historical context.

## Procedure

1. **Inspect:** Call `get_layer_weights(model, layer_idx, matrix_name)` from `tinycoder.weight_space` to obtain a detached tensor copy and size/norm/sample-SVD statistics. For prompt-dependent work, use `capture_io` to read the last-token key/value at the target linear layer.
2. **Derive:** Select a dimensionally valid closed-form rank-one or null-space edit. Rank-one uses `ΔW = α (y-Wk) (C^-1 k)^T / (k^T C^-1 k)` with a regularized diagonal covariance approximation. Null-space input dampening uses `ΔW = -α (Wv) v^T` for normalized `v`.
3. **Bound and apply:** Use `cap_factors` to limit the update norm relative to the matrix, then `apply_weight_edit(model, layer_idx, matrix_name, left, right)` to modify the selected `torch.nn.Linear.weight` tensor in RAM. Never patch arbitrary parameter names supplied by untrusted prompts; use the allowlist.
4. **Verify:** Check finite values, tensor dimensions, weight norms and before/after outputs on both target and unrelated prompts. Save small factor files and a JSON report. Omit `--weight-edit` to restore the untouched base model.
5. **Report:** Distinguish changes in logits or activation distances from proven improvements in programming correctness. This code is ROME-*inspired* but is not an implementation of the ROME/MEMIT algorithms.

## HumanEval 20-failure experiment

- `tinycoder/rome20.py` uses the **base** `Qwen/Qwen2.5-Coder-0.5B` for code completion, distinct from the default Instruct checkpoint.
- The 20 failure-conditioned examples come from an official pinned HumanEval dataset. Successful reference completions are the dataset's canonical code solutions, each executed successfully in the isolated container before inclusion.
- Causal patching replaces last-token `mlp.down_proj` outputs from reference completions and measures the correct first token's log probability. All 24 layers are scanned across all 20 pairs; the highest-mean layer is selected.
- The rank-one projection uses a ridge-plus-empirical covariance inverse computed with Woodbury, and targets the centroid of 20 pairs. One rank-one matrix **cannot generally satisfy 20 independent mappings exactly**.
- Report **two** scores: the selected 20 baseline failures (biased by selection), and a completely separate 20-task holdout for meaningful pass@1 comparisons.
- Model-generated Python is executed only in short-lived, network-disabled, read-only, unprivileged Docker containers with resource limits. Never silently remove the sandbox.

## CPU-approved batch-edit follow-up

- The user explicitly authorized the **CPU fallback** on a standard GitHub `ubuntu-latest` runner. `tinycoder/rome_batch.py` supports `--device cpu` and sets `torch.set_num_threads(4)` for the hosted run; GPU remains optional but is not needed. Docker remains mandatory.
- The two candidate layers are 8 and 12, but all 24 MLP layers are causally scanned first. Report each candidate's actual score and rank even if the evidence is negative.
- Use the same 20 verified failure/reference pairs as the previous experiment and keep HumanEval tasks 44 through 93 untouched until the **50-task independent holdout evaluation**. Do not reuse either evaluation set to pick later edits.
- Batch updates use a Woodbury-based regularized covariance inverse, sequential residual splitting, and directly applied low-rank factors. Cap the **observed**, not merely proposed, Frobenius delta on each `mlp.down_proj` to **<= 1.5%**; save `experiments/rome_batch_factors.safetensors` and a JSON report.
- Only after the actual CPU run completes should the pending README results area be replaced with measured pass@1 and passed/failed IDs. A pending report must have null scores, never speculative improvement claims.

## Session 007: four explicitly authorized high-risk branches

- Maintain four separate `exp/` branches (`01-transplant`, `02-svd-zeroing`, `03-norm-break`, `04-memit-single-layer`) from a shared base. Run exactly four independent, parallel CPU jobs; never merge experiments into `main` automatically.
- Reuse only the 20 previously verified *failure/reference* pairs for deriving edits. Reserve fresh **HumanEval/94–143** (50 tasks) for identical before/after execution scoring across branches. Previous evaluations consumed all IDs through 93. Reserve 144–163 for later, independent confirmation; do not train/retarget on the 94–143 comparative holdout.
- `01`: copy reference MLP values from layer 18 onto layer 8 keys; only layer 8 `mlp.down_proj` may change and its observed norm delta must remain <= 1.5%. Treat cross-layer values as unvalidated proxies.
- `02`: use full singular-value decomposition on layer 8 `self_attn.o_proj` and `mlp.down_proj`. Select exactly two directions among the top singular spectrum using activation separation on *syntax-invalid* prior completions versus canonical reference continuations. This is **correlational association**, not evidence of causal syntax circuits. Save subtraction factors.
- `03`: the user expressly approved stress edits of **3%, 5%, 10%** of layer 8 `mlp.down_proj` Frobenius norm, exceeding the prior 1.5% limit **only in this isolated, in-memory branch**. Each level must restart from the same original weights, save reversible factors, and report execution/syntax breakdown. Three tests cannot establish an exact continuous breakdown threshold.
- `04`: use a multi-key Woodbury covariance inverse with a direct batch update only on layer 8 `mlp.down_proj` (<= 1.5%). Never edit layer 12.
- All experiments run Docker-isolated HumanEval assertions and save task-level before/after outcomes. The collector compares their reports only after every branch actually completes; no fabricated metrics or silent unsandboxed evaluation.

## Session 008: final reserved holdout and SVD/MEMIT hybrid

- Independently confirm the preselected **10% layer 8 MLP** candidate on HumanEval/144–163 **before constructing/evaluating** the hybrid. Freeze all editing factors first; never use its 20 results to derive the hybrid edit.
- Reuse the exact archived factors from commit `b48673a`: the **two** removed singular modes in layer 8 `self_attn.o_proj` (exclude the old SVD `mlp.down_proj` erasure) and the **10%** layer 8 `mlp.down_proj` MEMIT-style batch direction.
- Keep the new `exp/05-svd-norm-fusion` branch independent and the base checkpoint unmodified. No gradients, optimizers, LoRA, or unsandboxed execution.
- Benchmark the hybrid on HumanEval/94–163, labeling 94–143 previously compared and 144–163 now consumed by 10% independent confirmation; the hybrid's 70-task score is exploratory, **not** independent generalization evidence.
- To compare all three interventions fairly, combine previously recorded 50-task measurements for 1.5%/10% with a newly measured 20-task validation for both. Require identical task lists and baseline pass IDs before publishing the 70-task comparison.
- Report syntax validity (`ast.parse`) separately from sandboxed HumanEval pass@1, and archive raw passed/failed IDs and reversible factors.

## Session 009: causal head mediation and rank-one attention surgery

- Use only the original 20 pre-94 failure/reference pairs to select attention layers and heads. Measure actual last-token `self_attn.o_proj` counterfactual interventions in layers 10–18 using change in reference-token log probability.
- Restrict the *edited* matrices to the top two causally ranked candidates within layers 12–16, while preserving the full nine-layer scan, including negative scores. Within each selected matrix, identify head-indexed projection input blocks. Assign one loop-state and one variable-tracking source-AST proxy; these are heuristic categories, **not proven causal semantics**.
- Use teacher-forced reference activation keys, a regularized Woodbury covariance inverse and a **rank-one update confined to the selected head columns** of each o_proj. Cap the observed Frobenius change of each attention matrix at **1.5%**.
- Combine the resulting two attention factors with **exactly the archived 10% layer 8 `mlp.down_proj` factors** from commit `e100c62`; verify the original factor Git blob against that commit. Keep the base checkpoint unchanged.
- Run the already-consumed HumanEval/94–163 70-task suite in isolated Docker containers; report pass@1 and separately `ast.parse` validity. **Never call this an independent generalization test.** Save per-task predictions and reversible factors.

## Session 015 — gated 0.5B low-rank subspaces

- All new work takes place on `exp/13-context-gated-subspaces`, created from `main`. The original base model remains 24 layers with exactly 494,032,768 parameters. No gradients, training, LoRA adapters or increased model capacity.
- Read the exact Session014 rank32 factor file using a SHA-256 verification before running any track. Use only Layer8 UI and Layer16 backend factors, no new learned target vectors.
- In the gated tracks, pair `register_forward_pre_hook` with an output hook on the selected `mlp.down_proj`. Compute `(Left @ Right) @ X` with two sequential low-rank matmuls and add it to `W_base @ X`; never mutate the stored weight or hidden model state outside these modules.
- Classify context strictly from original prompt lexical cues; default to baseline for ordinary Python/math. Ambiguous cues are baseline. A verified task manifest must contain 50 baseline-mode Python, 25 UI, and 25 backend tasks.
- Evaluate six tracks: untouched baseline, ungated static Layer8+16 edits, gated 0.0/0.5/1.0, and a labeled UI-only ablation at 1.0. The explicit backend gate still activates Layer16 in the standard gated tracks; **do not assume this preserves API correctness**.
- Select 50 MBPP+ test-split IDs disjoint from all 150 scored in Sessions013/014 and 50 newly numbered custom web template variants. Use identical prompts and scoring settings across all tracks. The old numerical 27/7/1 thresholds are exploratory success targets on a different task sample, not prior scores on these prompts.
- Require Docker for all model-generated Python/JS execution. The collector must prove exact prediction equality on Python for every gated variant, and exact API equality for the UI-only variant. Never publish fabricated counts or partial scores as completed measurements.

## Session 016 — adaptive runtime execution guidance

- Work exclusively on `exp/14-execution-guided-search`, retaining original
  Qwen2.5-Coder-0.5B base parameters. No gradients, optimizers, training,
  weight edits, LoRA, or model-size changes.
- Reuse the exact Session015 baseline `experiments/session015_gated_predictions.json`
  as candidate zero on the same 100 task prompts. Do not waste CPU
  regenerating the baseline or interpret earlier pass counts on other tasks.
- Public candidate tests may come only from original MBPP `test_list` or
  custom web smoke inputs derived from task specifications. The collector's
  private EvalPlus `plus_input` must not enter any generation, selection,
  candidate ranking, or feedback prompts. The original MBPP `test_list`
  is public; overlap with EvalPlus base tests must be disclosed.
- Generate up to two or four candidates adaptively, and only one
  feedback-conditioned repair for unresolved tasks. Record all candidate
  public feedback and exactly how much inference and time each track uses.
- Execute *all* model-generated Python/JavaScript solely inside isolated
  CPU Docker images with network disabled, read-only root and resource
  restrictions. Keep final expanded tests separate from public checks.
- Publish metrics only after measured full-run artifacts pass exact
  manifest and metric reproduction tests. The reported final selected
  solve@1 uses extra compute and is NOT a single-sample model pass@1.

## Session 017 — contract-first full-stack vertical slices

- Work on `exp/15-contract-first-fullstack`; keep original base
  `Qwen/Qwen2.5-Coder-0.5B` exactly 494,032,768 parameters. No gradients,
  fine-tuning, LoRA, scaling, or changing model weights.
- Freeze ten authored mini-app contracts before evaluating. Each requires a
  generated Python transformation, Express API, and React UI. The shared
  contract and inter-language adapters are trusted deterministic scaffolds.
- Public contract checks may select one sampled alternative and one repaired
  continuation only for failing modules. Do not load `holdout_cases()` until
  all generation/selection is complete; never leak hidden values in prompts.
- Generated code is untrusted. Execute Python and JavaScript only in the
  network-disabled, read-only, resource-restricted, unprivileged Docker image,
  one bounded container per candidate. Saved project directories are archives,
  NOT permission to run them outside Docker.
- Score both untouched greedy and guided variants on identical frozen holdout
  cases. Report module pass counts, *integrated* end-to-end passes, syntax,
  generated output tokens and elapsed wall time. The tasks are custom
  vertical slices, NOT external production-grade web app benchmarks.
- Publish measured report to `experiments/session017_fullstack_report.json`
  only after collector checks every task identity and reported score.

## Session 017b — no-inference UI scaffold ablation

- Reuse exact published Session017 base/guided completions from the completed
  benchmark. No additional model inference, training or weight edits.
- Select a deterministic `ResultView` from the public application contract
  only if the original generated React module fails PUBLIC checks; preserve
  original Python and Express source bytes exactly.
- Freeze all fallback decisions before `holdout_cases()` is loaded. Evaluate
  both original source sets and scaffold-assisted sets on the same independent
  holdout values with all execution inside restricted Docker. Verify the
  original published Session017 holdout metrics before publishing the ablation.
- Explicitly distinguish model-generated-only from scaffold-assisted app
  results. The latter must never be called a 0.5B model-only pass@1 gain.

## Session 018 — extreme bounded Python search

- Branch `exp/16-extreme-python-search` is based on completed Session017b results. Freeze exact `guided_scaffold` React/Express bytes; modify only Python `logic` source.
- Keep untouched Qwen2.5-Coder-0.5B (494,032,768 parameters); no backpropagation, training, LoRA, or weight edits.
- Select using only two original plus two additional authored PUBLIC distinguishing inputs per app, generic type-directed AST normalization, up to 8 samples and 2 feedback repairs. Load independent holdout values only after all candidate selection finishes.
- Execute all generated code exclusively inside network-disabled, read-only, unprivileged Docker. Preserve public candidate diagnostics, selected source, extra inference and wall time.
- The collector must reproduce all task-level holdout metrics and the frozen 5/10 Session017b control; reject any React/Express changes. These are ten custom mini-apps, not independent production benchmarks.

## Session 019 — published visual previews for generated applications

- Reuse the complete measured Session018 source, scores and frozen holdout, with zero new inference or changes to model weights.
- Render each actual generated React `ResultView` exclusively inside disposable read-only, unprivileged, network-disabled Docker using only PUBLIC fixture outputs; all published HTML is sanitized against executable markup, styles, external fetches and events.
- Provide a static visual gallery plus an individual preview link per app, including failed apps, showing API/Python/React scores and exact source. Previews are not live deployed Express backends.
- Pin external CDN previews to an immutable public Git commit SHA. Preserve safe generated snapshots and offer GitHub Pages as an alternative if enabled.
- Every subsequent experiment that emits application sources MUST run the preview stage after candidate selection: `python -m tinycoder.session019_previews --predictions <file> --report <file> --track <name> --output-dir docs/previews/<session>`. Publish one preview link for every app and surface links alongside pass/fail scores; treat missing previews as incomplete reporting.

## Session 020 — real interactive full-stack reference application

- Branch `exp/18-real-project-manager` carries a **trusted, hand-authored reference**, not a generated benchmark sample. Do not attribute its code or passing tests to Qwen2.5-Coder-0.5B.
- The reference app in `apps/real-project-manager` includes a React UI, Express API, Python SQLite bridge, Docker Compose, Codespaces configuration, and a unit/integration workflow. Keep persistence tests and HTTP CRUD tests enabled.
- Running trusted reference infrastructure outside the model-generated-code Docker sandbox does not authorize executing any new model output on the host. Future model-generated candidate code must stay in an isolated, network-disabled, unprivileged, resource-restricted Docker environment.
- Never state that a Codespaces link is a permanent hosted app. Codespaces starts a server inside a user-created environment; port visibility should remain private. No public SaaS deployment or front-end/backend parity claim is made.

## Session 021 — actual model-written full-stack source

- Work only on `exp/19-qwen-autonomous-app`. Freeze the base 494,032,768-parameter Qwen2.5-Coder-0.5B. No backpropagation, adapters, gradients, static/dynamic edits, or model scaling.
- The hand-authored Orbit application is a separate trusted reference, and its source must NEVER be included in the Qwen generation prompts. Only `session021_contract.py` public specification, public checks, and error feedback may guide generation or candidate choice.
- Four real app files (Python, Express, React, CSS) must be generated by the 0.5B model and saved unaltered except for deterministic prompt prefix assembly. A supplied SQLite store, bridge, Vite build and tests are labeled trusted scaffolding.
- Sample and repair only against public checks. Load the three holdout cases for the first time AFTER all selections are frozen; report greedy and selected outcomes separately.
- Every potentially untrusted Python or JavaScript completion executes only in isolated network-disabled, read-only, nonroot, resource-limited Docker. Never start generated Express or browser JS unsandboxed in Codespaces or other environments.
- Publish all raw completions, failures, final source and a safe preview of the ACTUAL generated React server markup, sanitized through the Session019 allowlist. For this single larger app the dedicated `session021.preview_page` renderer replaces the Session019 ten-mini-app-only gallery command.
- The static preview is script-free and cannot be described as an interactive application or evidence of browser E2E functionality. Publish a live interaction link only after a separately verified, contained deployment; do not invent a URL.
- Treat failed or timed-out runs as pending and do not manufacture scores, model attributions or frontier-model parity claims.

## Session 022 — native FIM model-assisted assembly

- Work on `exp/20-execution-guided-app`; keep the 494,032,768-parameter base
  model frozen. No gradient updates, weights edits, adapters, or fine-tuning.
- Model generation uses Qwen2.5-Coder-0.5B native fill-in-middle, eight
  narrowly specified Python/Express/React/CSS slots. Preserve exact raw
  token completions, generic normalized insertions, and the full trusted
  source template hashes so model attribution is always auditable.
- The authored surrounding Python function structure, Express route wiring,
  React state/actions, and CSS base layout are trusted scaffolding. NEVER
  describe assembled passing code as a full application written independently
  by Qwen. This branch measures a model-assisted integration milestone.
- Select each slot using public checks only. Invoke independent holdout only
  after all model selections have finished. Both public and holdout execution
  must use read-only, network-disabled, nonroot Docker with resource caps.
- Before publishing, a separate authored positive control must pass inside
  Docker, and a collector must verify model count, candidate identity, exact
  assembled source, and every passing claim. Publish failures truthfully.
- Browser links are static sanitized model-source previews unless a live
  server deployment is independently verified; never call static HTML an
  operational full-stack application.

## Session 023 — observable teacher–student correction loop

- Work on `exp/21-live-mentor`. Begin from the archived **actual** Session022
  model completions and failure report. Keep Qwen2.5-Coder-0.5B's 494,032,768
  parameters frozen. There must be no gradients, optimizer, LoRA or fine-tuning.
- The teacher may rewrite the *trusted* route response-envelope scaffold and
  provide analogous, non-target Express code examples. Log every observed
  error, teacher correction, generalized explanation and student attempt.
- The student must independently generate each targeted API expression.
  It never receives the exact target corrected expression. Unit tests may
  insert separate trusted positive-control expressions for OTHER slots so an
  upstream failing route cannot mask a downstream candidate's correctness.
  Positive controls and holdout examples must not enter generation prompts.
- Reuse the original three *verified Qwen-written* logic/UI/CSS slots from
  Session022, not the authored positive-control versions. The public and
  private integration checks execute all assembled code only inside restricted
  unprivileged Docker. Collect all generated raw token candidates.
- Publish the full immutable teacher diary and source. Distinguish successful
  adaptation in the prompt context from permanent learning in the model
  weights, and explicitly disclose how much of the app remained scaffolding.
- Never describe a sanitized static preview as an interactive live application.

## Boundaries

- We cannot inspect or copy ChatGPT's underlying proprietary weights.
- Do not suggest that a few edits make a small model generally equivalent to a frontier model.
- Do not run model-generated code on an unsandboxed machine.
- Do not commit model checkpoints, private prompts, credentials, or experiment artifacts with sensitive data.
- Keep original model files unmodified; save only reversible edit factors.

