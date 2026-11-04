# TinyCoder Weight Lab

A beginner-friendly experiment for **running, inspecting and directly editing weights in a very small coding AI**. The repository contains the software and examples; it intentionally **does not commit full pretrained model weights**.

**Current direction (Session 002 onward): DIRECT WEIGHT EDITING, with no training.** The earlier LoRA session is preserved as historical research, not our active approach. Directly editing tensor values is real and reversible, but it is not a shortcut to the general intelligence of a larger model.

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

**Measured Session 002 trial:** The first hosted direct edit raised token `def`'s next-token logit from 14.921803 to 16.921801 without changing any of the four generated responses. The workflow now tests a stronger but bounded +5 logit intervention, reports token rank, and saves `direct-002-results`. This can change the model's opening token, but does not establish better general coding ability.

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
| 001 | Same toy training examples | LoRA r=8 on attention q/v projections | Re-run held-out tests | **Not yet run** |

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
- This lab does not run generated programs. AST validity **is not correctness**.
- Keep evaluation examples separate from training. Build a much larger, independent benchmark before drawing conclusions.
- Running inference is feasible on modest PCs, especially via quantization; local fine-tuning may need a GPU/cloud environment.
- Do not commit `.env`, model weights, private data, or large checkpoints.
- See the upstream model cards for license terms; the StarCoder license differs from Qwen's.

