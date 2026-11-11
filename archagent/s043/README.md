# Session 043: Qwen Instruct first real app

This branch tests the **unmodified** `Qwen/Qwen2.5-Coder-0.5B-Instruct` checkpoint,
not the prior base or LoRA-trained checkpoint. No weight edits, training, or
holdout access. The first target is a self-contained offline FocusBoard app.

From the repository root, in an environment with CPU PyTorch and Transformers:

```bash
python -m archagent.s043.generate_instruct_app --output-dir experiments/z043-instruct-app
```

The driver archives the exact unedited model output, extracted HTML, hash
manifest, and basic structural checks. Session 043 also ran exactly one
public-feedback revision, saved under `experiments/z043-instruct-app/revision2`.
It **does not run model-generated code**;
the latter must be checked inside a network-disabled, unprivileged Docker
container with resource limits. Do not call an HTML preview a verified app.

The session is successful only if the generated app passes actual CRUD,
filtering, and persistence interactions. Both outputs currently fail
source-level correctness review. The GitHub Actions behavior job executes the
revision inside Docker to independently confirm failure or success; its status
must not be described as passing until measured. No generated checkpoint is added.
