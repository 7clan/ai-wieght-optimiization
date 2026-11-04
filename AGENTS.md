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

## Boundaries

- We cannot inspect or copy ChatGPT's underlying proprietary weights.
- Do not suggest that a few edits make a small model generally equivalent to a frontier model.
- Do not run model-generated code on an unsandboxed machine.
- Do not commit model checkpoints, private prompts, credentials, or experiment artifacts with sensitive data.
- Keep original model files unmodified; save only reversible edit factors.

