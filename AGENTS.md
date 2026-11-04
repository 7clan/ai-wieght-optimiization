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

## Boundaries

- We cannot inspect or copy ChatGPT's underlying proprietary weights.
- Do not suggest that a few edits make a small model generally equivalent to a frontier model.
- Do not run model-generated code on an unsandboxed machine.
- Do not commit model checkpoints, private prompts, credentials, or experiment artifacts with sensitive data.
- Keep original model files unmodified; save only reversible edit factors.

