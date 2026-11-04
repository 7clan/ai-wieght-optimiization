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

## Boundaries

- We cannot inspect or copy ChatGPT's underlying proprietary weights.
- Do not suggest that a few edits make a small model generally equivalent to a frontier model.
- Do not run model-generated code on an unsandboxed machine.
- Do not commit model checkpoints, private prompts, credentials, or experiment artifacts with sensitive data.
- Keep original model files unmodified; save only reversible edit factors.

