# TinyCoder Weight Lab

A beginner-friendly experiment for **running, inspecting and directly editing weights in a very small coding AI**. The repository contains the software and examples; it intentionally **does not commit full pretrained model weights**.

**Current direction (Session 002 onward): DIRECT WEIGHT EDITING, with no training.** The earlier LoRA session is preserved as historical research, not our active approach. Directly editing tensor values is real and reversible, but it is not a shortcut to the general intelligence of a larger model.

### Internal weight-space programming (current research track)

The original `edit` command adjusts one output-token weight row. The new `weight-inspect` and `weight-edit` commands operate on **internal attention or MLP linear matrices** (for example, `model.layers[12].mlp.down_proj`). They use tensor reads and closed-form matrix algebra only:

```powershell
python -m tinycoder weight-inspect --layer 12 --matrix mlp.down_proj
python -m tinycoder weight-edit "Write only Python code defining max_of_three(a, b, c), returning the greatest argument." --reference-prompt "Return only the bare Python function definition of max_of_three(a, b, c), with no explanation." --method rank-one --layer 12 --matrix mlp.down_proj --alpha 0.5 --max-relative-change 0.002 --output edits/internal-001
python -m tinycoder eval --weight-edit edits/internal-001 --report outputs/internal-after.json
```

The `rank-one` method captures the chosen matrix's last-token input vector `k` for the target prompt and its output `y` for a reference prompt. It calculates:

`ΔW = α (y - Wk) (C^-1 k)^T / (k^T C^-1 k)`

Here `C` is approximated by a regularized diagonal of key squared activations from `data/calibration.jsonl`; no trained covariance model is used. The factors are capped by a maximum relative matrix-norm change (default 0.2%) and saved as `factors.safetensors` and `weight_edit.json`. This **does not guarantee a more accurate answer**: a reference prompt is not a teacher's hidden state, and copying its activation can distort other behavior.

Null-space input dampening is also available with `--method nullspace`, using `ΔW = -α (Wv)v^T` for normalized `v`. It can reduce one internal direction but may erase useful information. Use small bounds and compare multiple outputs.

See [AGENTS.md](AGENTS.md) for the full inspect → derive → apply → verify protocol. The `.github/workflows/internal-weight-session.yml` workflow runs the initial internal-matrix experiment in GitHub Actions and saves a downloadable `internal-001-results` artifact. The method is a **simplified algebraic demonstration inspired by ROME/MEMIT, not their complete algorithms**.

### HumanEval 20-failure causal-patching experiment

For a more demanding evaluation, `python -m tinycoder.rome20` runs a **base-model** experiment with [`Qwen/Qwen2.5-Coder-0.5B`](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B), *not* the Instruct variant. It uses the official, MIT-licensed [OpenAI HumanEval](https://github.com/openai/human-eval) dataset pinned to a specific commit, containing coding prompts, reference solutions and unit tests.

The experiment:

1. Greedily generates code until it has 20 sandbox-verified failures with corresponding passing canonical reference solutions.
2. Reserves the next 20 HumanEval tasks as an untouched holdout set, regardless of their baseline results.
3. Captures all 24 `mlp.down_proj` key/value activations on each failing prompt and teacher-forced correct completion.
4. Patches success-side activations into failure-side forward passes to rank layers by change in first-reference-token log probability.
5. Computes a single bounded, closed-form rank-one update at the selected layer from the **centroid** of 20 key/value pairs, using a regularized empirical covariance inverse via Woodbury algebra. One rank-one update generally cannot satisfy 20 independent targets.
6. Runs one generated completion per task through a restricted, network-disabled, read-only **Docker** container with resource and time limits, then reports both failure-conditioned and independent holdout `pass@1` before/after deltas.

Launch from **GitHub Actions → HumanEval 20-failure ROME-style experiment** or run on a machine with Docker, Python, sufficient memory, and internet access:

```powershell
python -m tinycoder.rome20 --edit-count 20 --holdout-count 20 --max-new-tokens 160
```

Results are saved to `outputs/rome20/` locally or as the `humaneval-rome20-results` Actions artifact. The output includes `progress.json`, `rome_factors.safetensors`, `rome20_report.json` and per-task `predictions.json`. The selected-failure set has pass@1=0 by construction, so **the independent holdout delta is the primary generalization signal**. This is **ROME-style** closed-form editing, not a reproduction of original ROME's optimized target-value computation, and a positive result would require replication on multiple unseen seeds and tasks.

**Measured 20-failure ROME-style run — November 4, 2026:** [GitHub Actions run #1](https://github.com/7clan/ai-wieght-optimiization/actions/runs/41746688416) completed successfully on the base `Qwen/Qwen2.5-Coder-0.5B` model. The best patching layer was **8 of 24** (mean first-reference-token log-probability gain **+0.00341** across 20 patches). One rank-one update was applied to layer 8's `mlp.down_proj` with a **1% relative Frobenius-norm cap**. The centroid activation target distance decreased from **5.3785 to 3.2088**. The precise factors are retained alongside the full report and per-task predictions in [`experiments/2026-11-04-rome20/`](experiments/2026-11-04-rome20/).

| Execution-tested set | Before pass@1 | After pass@1 | Delta |
| --- | ---: | ---: | ---: |
| 20 deliberately selected failures | 0/20 (0%) | 1/20 (5%) | **+5 percentage points** |
| 20 subsequent, independent holdout tasks | 3/20 (15%) | 5/20 (25%) | **+10 percentage points** |

The repaired edit-set task was `HumanEval/7`. The holdout gained passes on `HumanEval/29` and `HumanEval/43`, with **no formerly passing holdout task regressing**. On the holdout, eight generated answers changed and twelve remained identical. These are verified one-generation-per-task execution results, **not proof of general coding-skill improvement**: a 20-task holdout has high statistical uncertainty, and the gain needs replication on a broader, untouched benchmark. Neither the selected 20 failures nor the 20 holdout tasks should be reused to choose future edits.

### Session 006: CPU two-layer batch-edit experiment

`python -m tinycoder.rome_batch --device cpu --threads 4` is a **CPU-approved** follow-up. It loads the original `Qwen/Qwen2.5-Coder-0.5B` base weights, reuses the 20 previously verified failure/reference pairs, and patches all 24 layer outputs to trace how strongly they affect the first reference token. It reports the causal ranks of candidate layers **8 and 12** before applying a sequential, **multi-key** ridge-regularized closed-form update to each layer's `mlp.down_proj`.

The two low-rank factor pairs are exported to `experiments/rome_batch_factors.safetensors` with a maximum **1.5% per-layer Frobenius norm change** and checked for finite values. No gradients, backpropagation, optimizer steps, or adapter training are used. Key-value capture and batched generation run on the selected device (CPU in the free hosted workflow; CUDA remains optional). Execution tests run in up to four parallel, restricted Docker containers, using **50 fresh HumanEval tasks `HumanEval/44`–`HumanEval/93`** never used in the earlier 20-failure experiment or its 20-task holdout. Evaluation uses deterministic greedy generation (one output per task), checks the original HumanEval assertions, and logs passed/failed IDs before and after.

The method uses a batch Woodbury projection, with the requested two target layers and residual splitting. This is **MEMIT-inspired**; it does *not* reproduce the original MEMIT's optimized target representations or demonstrate general capability transfer. Read the [MEMIT paper](https://openreview.net/forum?id=MkbcAHIYgyS) for the underlying editing research.

**CPU run:** The [standard `ubuntu-latest` workflow](.github/workflows/rome-batch-cpu.yml) installs CPU-only PyTorch, sets `torch.set_num_threads(4)`, runs the full batch experiment and automatically commits verified results and factor tensors if the job succeeds. The earlier [manual GPU workflow](.github/workflows/rome-batch-gpu.yml) remains available for an explicitly configured CUDA runner. The [unit-test workflow](.github/workflows/rome-batch-checks.yml) checks algebra independently. No paid GPU is required for the CPU route.

<!-- ROME-BATCH-RESULTS-START -->
**Batch experiment:** completed on CPU / 4 PyTorch threads (cpu). A direct two-layer (8, 12) MEMIT-style update, at most 1.5% of the original Frobenius norm per layer, changed independent HumanEval pass@1 **4/50 → 3/50** (**-2.0 percentage points**). New passes: None; regressions: HumanEval/55.

| Independent 50-task HumanEval holdout | Baseline | After two-layer edit |
| --- | ---: | ---: |
| Passing tasks | 4/50 | 3/50 |
| Failing tasks | 46/50 | 47/50 |
| pass@1 | 8.0% | 6.0% |

**Passed IDs before:** HumanEval/54, HumanEval/55, HumanEval/60, HumanEval/66.

**Passed IDs after:** HumanEval/54, HumanEval/60, HumanEval/66.

**Failed IDs before:** HumanEval/44, HumanEval/45, HumanEval/46, HumanEval/47, HumanEval/48, HumanEval/49, HumanEval/50, HumanEval/51, HumanEval/52, HumanEval/53, HumanEval/56, HumanEval/57, HumanEval/58, HumanEval/59, HumanEval/61, HumanEval/62, HumanEval/63, HumanEval/64, HumanEval/65, HumanEval/67, HumanEval/68, HumanEval/69, HumanEval/70, HumanEval/71, HumanEval/72, HumanEval/73, HumanEval/74, HumanEval/75, HumanEval/76, HumanEval/77, HumanEval/78, HumanEval/79, HumanEval/80, HumanEval/81, HumanEval/82, HumanEval/83, HumanEval/84, HumanEval/85, HumanEval/86, HumanEval/87, HumanEval/88, HumanEval/89, HumanEval/90, HumanEval/91, HumanEval/92, HumanEval/93.

**Failed IDs after:** HumanEval/44, HumanEval/45, HumanEval/46, HumanEval/47, HumanEval/48, HumanEval/49, HumanEval/50, HumanEval/51, HumanEval/52, HumanEval/53, HumanEval/55, HumanEval/56, HumanEval/57, HumanEval/58, HumanEval/59, HumanEval/61, HumanEval/62, HumanEval/63, HumanEval/64, HumanEval/65, HumanEval/67, HumanEval/68, HumanEval/69, HumanEval/70, HumanEval/71, HumanEval/72, HumanEval/73, HumanEval/74, HumanEval/75, HumanEval/76, HumanEval/77, HumanEval/78, HumanEval/79, HumanEval/80, HumanEval/81, HumanEval/82, HumanEval/83, HumanEval/84, HumanEval/85, HumanEval/86, HumanEval/87, HumanEval/88, HumanEval/89, HumanEval/90, HumanEval/91, HumanEval/92, HumanEval/93.

See [`experiments/rome_batch_report.json`](experiments/rome_batch_report.json), [`experiments/rome_batch_predictions.json`](experiments/rome_batch_predictions.json), and [`experiments/rome_batch_factors.safetensors`](experiments/rome_batch_factors.safetensors). This limited holdout alone does not prove general improvement.
<!-- ROME-BATCH-RESULTS-END -->

On a CPU host with 4 available cores, Docker and CPU PyTorch installed:

```powershell
python -m tinycoder.rome_batch --device cpu --threads 4 --holdout-start 44 --holdout-count 50 --max-relative-change 0.015 --batch-size 4 --workers 4
```

This process edits only the in-memory model, not the downloaded base checkpoint. The factor file permits later reconstruction or reversal of both low-rank updates. **The CPU fallback is explicitly authorized for this session; its numeric results must still be measured.**

**Safety:** Do not run generated code outside a sandbox. `tinycoder/sandbox_eval.py` refuses execution when Docker is unavailable. The Docker container has no network, uses an unprivileged user, read-only filesystem, dropped capabilities and strict resource limits. No sandbox is a guarantee against all attacks.

**First internal-matrix result:** [GitHub Actions run](https://github.com/7clan/ai-wieght-optimiization/actions/runs/41744954761) succeeded. A rank-one edit to layer 12's `mlp.down_proj` was bounded to **0.2% of the original matrix Frobenius norm**, and all matrix values remained finite. The targeted last-token output moved closer to the selected reference activation (Euclidean distance **3.1938 → 2.9704**, about 7% smaller). However, **all four generated answers remained identical**, and the simple static checks stayed **2/4 before and after**. This is a successful numerical intervention, **not an accuracy improvement**. Download `internal-001-results` from that run for the exact factor tensors and responses.

## Which AI are we starting with?

| Model | Size | Purpose |
| --- | ---: | --- |
| [Qwen2.5-Coder-0.5B-Instruct](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct) | ~0.5B parameters | Default: small instruction-following coding assistant; our LoRA training target (Apache 2.0) |
| [Tiny StarCoder Python](https://huggingface.co/bigcode/tiny_starcoder_py) | 164M parameters | Smaller comparison model for **Python completion**, not a strong assistant (BigCode OpenRAIL-M) |

These are **small practical research candidates**, not a verified claim about the world's smallest neural network. Their coding capabilities are limited. A small model cannot acquire a frontier model's complete general intelligence just through a few fine-tuning sessions, and OpenAI's proprietary model weights are not available for copying. Instead, we can train on carefully reviewed example answers and measure changes.

## First run (Windows PowerShell)

Requirements: **Python 3.10+** and sufficient free RAM/disk space to download and load a model. The default model's half-precision weights are roughly 1 GB, but inference and training use more RAM. CPU is supported for inference; training on CPU can be extremely slow. A CUDA GPU or cloud notebook is recommended for training.

```powershell
git clone https://github.com/7clan/ai-wieght-optimiization.git
cd ai-wieght-optimiization
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python -m tinycoder train --dry-run
```

The first real model command downloads weights from Hugging Face into the local cache (internet required). Nothing is sent to a hosted chatbot API.

### 1. Ask the baseline model to code

```powershell
python -m tinycoder chat "Write a Python function to find prime numbers"
```

### Direct edit: change one weight row yourself (our active method)

This is a simple **gradient-free, single-token** edit to the model's output-weight matrix. It uses the final hidden vector for a specific prompt to calculate an additive row update that increases the target token's logit. It changes actual base-model weights in memory, then saves a small reversible delta — no backpropagation, optimizer, fine-tuning or new adapter.

```powershell
python -m tinycoder edit "Write only Python code defining max_of_three(a, b, c), returning the greatest argument." --target-token def --boost 2 --output edits/direct-001
python -m tinycoder chat "Write only Python code defining max_of_three(a, b, c), returning the greatest argument." --edit edits/direct-001
python -m tinycoder eval --edit edits/direct-001 --report outputs/direct-after.json
```

See `edits/direct-001/edit.json` for the exact targeted token, weight-delta size and before/after logits. Remove `--edit` to return to the untouched model. The original weight checkpoint remains intact. One token being more probable **does not mean better code**, so inspect generated answers on multiple prompts and check for regressions. This is a teaching demonstration, **not an implementation of ROME or MEMIT**.

You can run the same direct-edit demonstration in GitHub-hosted compute using **Actions → Direct weight edits - no training**. Previous runs preserve their own artifacts. A push changing that workflow file starts a new experiment; future runs can also be started manually.

**Measured direct-edit trials:**

| Trial | Edit | Target-token rank | Generated answers changed | AST static checks |
| --- | --- | --- | --- | --- |
| [Direct 001](https://github.com/7clan/ai-wieght-optimiization/actions/runs/41742984583) | +2 next-token logit | Still below top | 0/4 | 2/4 before → 2/4 after |
| [Direct 002](https://github.com/7clan/ai-wieght-optimiization/actions/runs/41743605402) | +5 next-token logit | 6th → 1st (`def`) | 2/4 | 2/4 before → 2/4 after |

In Direct 002, `max_of_three` began with `def` instead of an introductory sentence; this better matches the "only code" instruction for that prompt. Another prompt (`gcd`) changed too, but its output contained stray Markdown, showing why stronger edits need regression checks. **These are format and next-token effects; neither trial proves improved coding correctness or general intelligence.** Download the artifact ZIP from the linked workflow page to inspect the exact saved delta and per-prompt outputs.

For more sophisticated targeted weight edits, read the original research on [ROME](https://papers.nips.cc/paper_files/paper/2022/hash/6f1d43d5a82a37e89b0665b33bf3a182-Abstract-Conference.html) and [MEMIT](https://openreview.net/forum?id=MkbcAHIYgyS). Those methods primarily edit *specific factual associations*, not broad coding competence.

Or inspect the smaller **completion-only** model:

```powershell
python -m tinycoder chat "def fibonacci(n):" --model bigcode/tiny_starcoder_py
```

For **lower-memory inference**, the author also publishes a 4-bit GGUF build that works with llama.cpp. This is a separate inference format, *not* the trainable Transformers checkpoint used by the commands above:

```powershell
winget install llama.cpp
llama cli -hf Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF:Q4_K_M
```

Reference: [official Qwen GGUF model card](https://huggingface.co/Qwen/Qwen2.5-Coder-0.5B-Instruct-GGUF).

### 2. Establish a baseline before tuning

```powershell
python -m tinycoder eval --report outputs/before.json
```

The four held-out challenges live in `data/eval.jsonl`. **This first benchmark checks only Python syntax and the expected top-level function name**, not whether the function actually works. Keep and manually review the generated answers. We will add isolated functional tests in later sessions; do not execute untrusted AI-generated code directly on your laptop.

### Archived approach: LoRA training (not used for new sessions)

Edit or add carefully reviewed prompt/answer examples in `data/train.jsonl`. The 12 included examples are only a **smoke-test dataset**, too small to support claims of improved general coding ability. Do not include secrets, proprietary code, or evaluation prompts in training data.

```powershell
python -m tinycoder train --output checkpoints/session-001
```

This uses [LoRA](https://huggingface.co/docs/peft/quicktour): the base model is frozen and small extra weight matrices are learned. This is real fine-tuning, but it doesn't directly rewrite every original base-model weight. To use the trained model, load the original checkpoint together with the adapter:

```powershell
python -m tinycoder chat "Write a Python function to find prime numbers" --adapter checkpoints/session-001
python -m tinycoder eval --adapter checkpoints/session-001 --report outputs/after.json
```

Compare `outputs/before.json` and `outputs/after.json`, inspect the responses and record what improved **and what regressed**. No improvement is claimed until an independent evaluation supports it.

### 4. Look inside the weights

```powershell
python -m tinycoder inspect --filter q_proj --limit 5
python -m tinycoder inspect --adapter checkpoints/session-001 --filter lora_ --limit 10
```

The statistics show layer names, tensor shapes, means, standard deviations, and which weights are trainable. A single weight does not correspond to a single concept like "Python skill"; blind manual edits tend to harm behavior.

## Session log

| Session | Dataset | Intervention | Evaluation | Result |
| --- | --- | --- | --- | --- |
| 000 | 12 toy examples / 4 held-out prompts | Baseline only | AST checks + manual review | **Not yet run** |
| 001 | Same toy training examples | LoRA r=8 on attention q/v projections (archived) | Held-out static checks | Workflow succeeded; not part of current editing method |
| 002 | 4 prompts | Direct output-row edit (+2 logit) | Rank and AST checks | Changed weight, no answers changed |
| 003 | 4 prompts | Direct output-row edit (+5 logit) | Rank and AST checks | `def` rank 6→1; 2 answers changed; AST stayed 2/4 |
| 004 | 4 prompts | Internal layer 12 `mlp.down_proj` rank-one update (0.2% cap) | Activation distance + AST checks | Distance 3.1938→2.9704; no answers changed; AST stayed 2/4 |
| 005 | 20 selected HumanEval failures + 20 untouched holdouts | Causal-scan-selected layer 8 `mlp.down_proj` rank-one update (1% cap) | Restricted Docker execution, greedy pass@1 | Selected 0/20→1/20; holdout 3/20→5/20; preliminary +10 pp holdout |
| 006 | Same 20 failure/reference pairs; independent HumanEval/44–93 holdout | CPU causal scan + layers 8/12 multi-key ridge updates (1.5% cap per layer) | 50 Docker-executed tasks, greedy pass@1 | 4/50 → 3/50 (8% → 6%); **−2 percentage points**, one regression |

### Historical first experiment in GitHub Actions

The `.github/workflows/model-session.yml` workflow records the earlier LoRA experiment. **Do not re-run it for our new direct-edit plan.** Our active workflow is `direct-edit-session.yml`. The older reports remain useful as a comparison, but no improvement is assumed.

## Project layout

- `tinycoder/model.py`: model loading and local generation
- `tinycoder/data.py`: JSONL validation and answer-only training labels
- `tinycoder/__main__.py`: `chat`, `train`, `eval`, `inspect` commands
- `tinycoder/evaluation.py`: non-executing static checks
- `tinycoder/direct_edit.py`: direct, reversible row-level weight editing without training
- `data/train.jsonl`: starter demonstrations (not a serious training corpus)
- `data/eval.jsonl`: held-out prompts
- `tests/`: offline unit tests; `.github/workflows/`: CI
- `checkpoints/`, `outputs/`: created locally and excluded from git

## Limitations and research hygiene

- Tiny models may generate wrong or insecure code. Always review their output.
- The earlier `eval` command checks AST structure only; the newer HumanEval experiment **does execute generated code, exclusively in a restricted Docker sandbox**. AST validity alone **is not correctness**; a sandbox is not a perfect security boundary.
- Keep evaluation examples separate from training. Build a much larger, independent benchmark before drawing conclusions.
- Running inference is feasible on modest PCs, especially via quantization; local fine-tuning may need a GPU/cloud environment.
- Do not commit `.env`, model weights, private data, or large checkpoints.
- See the upstream model cards for license terms; the StarCoder license differs from Qwen's.


## Session 007 — Four parallel, isolated direct-weight experiments

Four independent branches use the same pristine 50-task HumanEval comparison set (`HumanEval/94` through `HumanEval/143`). All generated code is execution-tested only in restricted Docker containers. The base model remains unmodified on disk.

- [`exp/01-transplant`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/01-transplant): Layer 18 reference outputs projected into layer 8, max 1.5% norm edit.
- [`exp/02-svd-zeroing`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/02-svd-zeroing): remove two syntax-associated SVD components each from layer 8 `self_attn.o_proj` and `mlp.down_proj`.
- [`exp/03-norm-break`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/03-norm-break): layer 8 stress trials at 3%, 5%, and 10%, restarted from base weights each time.
- [`exp/04-memit-single-layer`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/04-memit-single-layer): layer 8-only regularized multi-key edit, max 1.5% norm edit.

<!-- HIGH-RISK-EXPERIMENTS-START -->
### Session 007: four independent high-risk CPU branches

Every branch used the untouched **HumanEval/94–143** comparison set (50 tasks) and the original base Qwen2.5-Coder-0.5B checkpoint. The same holdout is now **used for model comparison**; future choices need a different final validation set.

| Isolated branch and method | Baseline pass@1 | Edited pass@1 | Change | New passes | Regressions |
| --- | ---: | ---: | ---: | ---: | ---: |
| [`01-transplant`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/01-transplant) | 2/50 (4%) | 2/50 (4%) | **+0.0 pp** | 0 | 0 |
| [`02-svd-zeroing`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/02-svd-zeroing) | 2/50 (4%) | 2/50 (4%) | **+0.0 pp** | 0 | 0 |
| [`03-norm-break`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/03-norm-break) (3%) | 2/50 (4%) | 2/50 (4%) | **+0.0 pp** | 0 | 0 |
| [`03-norm-break`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/03-norm-break) (5%) | 2/50 (4%) | 2/50 (4%) | **+0.0 pp** | 0 | 0 |
| [`03-norm-break`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/03-norm-break) (10%) | 2/50 (4%) | 3/50 (6%) | **+2.0 pp** | 1 | 0 |
| [`04-memit-single-layer`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/04-memit-single-layer) | 2/50 (4%) | 2/50 (4%) | **+0.0 pp** | 0 | 0 |

Each branch's exact passed/failed task IDs, activation measurements, tensor changes, and predictions are archived in `experiments/exp0*_report.json`, `experiments/exp0*_predictions.json`, and reversible `experiments/exp0*_factors.safetensors`.

**Caution:** SVD projection gaps are only *associated* with syntax-invalid examples. Cross-layer transplantation is not established as a way to transfer skills. The 3%, 5%, and 10% stress trials can locate only the first *tested* failure threshold, not an exact continuous breakdown point. Results do not prove general coding improvements.
<!-- HIGH-RISK-EXPERIMENTS-END -->

## Session 008 — Out-of-sample confirmation and SVD/MEMIT fusion

The original 10% Layer 8 `mlp.down_proj` factors are pinned to commit
[`b48673a`](https://github.com/7clan/ai-wieght-optimiization/commit/b48673a26e7ef6a6220aca331dfc8c0024944aa8).
The new workflow first evaluates the preselected candidate on the never-used
HumanEval/144–163 block, then combines the original syntax-associated layer 8
`self_attn.o_proj` SVD subtraction factors with the archived 10% MLP edit on
[`exp/05-svd-norm-fusion`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/05-svd-norm-fusion).
No training is performed. Results are populated only by a completed sandboxed
GitHub Actions run; the fusion comparison is not another independent holdout.

<!-- FUSION-VALIDATION-START -->
### Session 008: out-of-sample confirmation and Layer 8 hybrid fusion

**Final unused holdout:** the preselected 10% Layer 8 edit was evaluated first on HumanEval/144–163 (20 tasks), before constructing or scoring the hybrid.

| Fresh 20-task validation | Baseline pass@1 | Edited pass@1 | Change | AST valid before | AST valid after | New passes | Regressions |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| Preselected 10% Layer 8 MEMIT | 0/20 (0.0%) | 0/20 (0.0%) | **+0.00 pp** | 0/20 | 5/20 | None | None |
| Archived 1.5% Layer 8 MEMIT comparator | 0/20 (0.0%) | 0/20 (0.0%) | **+0.00 pp** | 0/20 | 1/20 | None | None |

**70-task comparison (HumanEval/94–163):** previously recorded results on 94–143 were combined with the 20-task validation results for each MEMIT candidate. The new SVD-hybrid was executed on all 70 tasks. All rows use identical task IDs.

| Intervention | Baseline pass@1 | Edited pass@1 | Change | AST valid before | AST valid after | New passes | Regressions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |
| 1.5% Layer 8 MEMIT | 2/70 (2.9%) | 2/70 (2.9%) | **+0.00 pp** | 7/70 | 9/70 | None | None |
| 10% Layer 8 MEMIT | 2/70 (2.9%) | 3/70 (4.3%) | **+1.43 pp** | 7/70 | 18/70 | HumanEval/122 | None |
| [SVD + 10% hybrid](https://github.com/7clan/ai-wieght-optimiization/tree/exp/05-svd-norm-fusion) | 2/70 (2.9%) | 3/70 (4.3%) | **+1.43 pp** | 7/70 | 22/70 | HumanEval/122 | None |

The hybrid removes the two previously identified singular components from layer 8 `self_attn.o_proj`, then applies the archived 10% multi-key Layer 8 `mlp.down_proj` edit. No layer 12 change, gradients, optimizer steps, or training.

**Interpretation:** AST syntax validity only means `ast.parse(prompt + completion)` succeeded; it is not execution correctness. pass@1 means all official HumanEval assertions passed inside restricted Docker containers. The 70-task hybrid comparison is **not** an independent validation of the hybrid because these tasks have already been used for prior comparisons.

Evidence: [`final_holdout_validation.json`](experiments/final_holdout_validation.json), [`hybrid_fusion_report.json`](experiments/hybrid_fusion_report.json), [`hybrid_fusion_comparison.json`](experiments/hybrid_fusion_comparison.json), [`hybrid_fusion_predictions.json`](experiments/hybrid_fusion_predictions.json), and [reversible `hybrid_fusion_factors.safetensors`](experiments/hybrid_fusion_factors.safetensors).
<!-- FUSION-VALIDATION-END -->

## Session 009 — Attention causal tracing and logic-alignment

The new experiment will causally patch `self_attn.o_proj` outputs in layers 10–18
on the original 20 failure/reference examples, then identify two target heads
within layers 12–16 from loop-state and variable-reassignment code proxies.
It will apply capped rank-one `o_proj` updates alongside the **unchanged
archived 10% Layer 8 MLP** factors from
[commit `e100c62`](https://github.com/7clan/ai-wieght-optimiization/commit/e100c628cd8fcf3c500e5c39070168e213b208aa).
The separate branch is
[`exp/06-attn-steering`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/06-attn-steering).

All 70 HumanEval/94–163 tasks have already been used in previous comparisons.
The new results will be exploratory and scored only in isolated Docker containers.

<!-- ATTENTION-STEERING-START -->
*Session 009 causal head tracing and execution evaluation pending; no scores claimed yet.*
<!-- ATTENTION-STEERING-END -->

## Session 010 — Architectural-reasoning circuits (ArchBench)

A new dedicated branch [`exp/zai-architectural-circuits`](https://github.com/7clan/ai-wieght-optimiization/tree/exp/zai-architectural-circuits)
introduces **ArchBench**, a 112-task architectural-reasoning benchmark
(variable tracking, interface contracts, JavaScript reasoning, cross-component
consistency) with fixed dev/val/holdout partitions and execution-verified gold
answers. Zero HumanEval IDs are reused. Causal counterfactual patching
localizes contract/cross-component information to **layer 16 MLP** (11/11 task
consistency; head 10 of layer 16 alone carries most of the effect) and variable
tracking to **layer 14 MLP**. Bounded (≤1.5%) multi-key contrastive steering
edits at those sites improve the construction set (CON 6/12→8/12) with zero
losses and zero code-perplexity cost, and same-layer edits compose additively
(24°–51° principal angles). On the frozen holdout, **no candidate transfers**
(0 gained tasks; the variable-tracking edit loses 2). The full method,
evidence, and negative-result discussion live in
[`docs/ZAI_ARCHITECTURAL_CIRCUITS.md`](docs/ZAI_ARCHITECTURAL_CIRCUITS.md).

<!-- ARCHCIRCUITS-RESULTS-START -->
### Session 010 measured results (frozen holdout, 32 tasks, greedy)

| Intervention | Holdout score | Gained | Lost | Unrelated-code NLL change |
| --- | ---: | ---: | ---: | ---: |
| Untouched baseline | 18/32 (56.2%) | — | — | — |
| L16 contract steer (`con_L16`, 1.38%) | 18/32 (56.2%) | 0 | 0 | −0.0013 |
| L16 cross-component steer (`xcom_L16`) | 17/32 (53.1%) | 0 | 1 | −0.0009 |
| L16 joint CON+XCOM subspace | 18/32 (56.2%) | 0 | 0 | −0.0018 |
| Sequential con+xcom | 18/32 (56.2%) | 0 | 0 | −0.0025 |
| L14 variable-tracking steer (`var_L14`) | 16/32 (50.0%) | 0 | 2 | −0.0001 |

Construction-set effects did not generalize: CON improved 6/12→8/12 on the
dev tasks whose error keys built the edit, and the val/holdout gradient
(+3.1 pp → 0 pp) shows a construction-set effect rather than a transferable
skill. No claim of improved general coding ability is made.
<!-- ARCHCIRCUITS-RESULTS-END -->
