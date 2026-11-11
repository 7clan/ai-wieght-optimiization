"""Session 041B — Stage-1 LoRA SFT (bounded, disclosed, resumable single run).

Executes SESSION040 TRAINING_PROPOSAL.md §2 Stage 1 under the explicit
user authorization of session 041B (supersedes the no-training rule on
this branch only):

  * base: the frozen Qwen2.5-Coder-0.5B (sha aff8914e…a47f80, verified
    on load: 494,032,768 params / 24 layers / 896 hidden);
  * LoRA r=16, alpha=32, dropout 0.05, targets q/k/v/o + MLP up/down
    (040 proposal), bf16 trunk + fp32 adapters (038A Plan-1; dtype
    chosen by the measured bench_dtype probe — bf16 4.9 s/micro-step,
    fp32 not measurable on this 3.9 GiB box);
  * lr 2e-4 cosine (inside the proposal's declared 1e-4..2e-4 range),
    no warmup, AdamW, micro-batch 1, grad-accum 8 (effective batch 8);
  * family-weighted sampling plan from the dataset builder (seed 4141,
    300 draws over 9 families, auditable draw counts);
  * loss on completion tokens + one supervised EOS only (labels for
    prompt positions are masked to -100);
  * memory-safe chunked lm_head+CE (the full fp32 logit tensor over the
    151,936-token vocab at seq≈980 would need ~1.5 GiB; chunks of 128
    shift-positions keep peak RAM bounded);
  * HARD BUDGET CAPS: (a) cumulative TRAINING time 2,400 s (40 min),
    (b) 296 micro-steps / 37 optimizer steps, (c) per-invocation time
    budget with clean checkpoint+exit (the sandbox reaps detached
    processes and tool calls cap at 10 min, so the run resumes across
    invocations; the resume bundle is written after EVERY optimizer
    step — adapter + optimizer + scheduler + rng + position + log tail).
  * seed pinned (4141); every optimizer step logged to train-log.jsonl.

Disclosed amendments to the frozen proposal (pre-registered before the
run, recorded in train-config.json): epochs 3 -> 12 (038A Plan-1 used
20; 12 stays inside the 038A-measured time envelope), +EOS supervision
(teaches termination), grad-accum tail draws dropped (296 of 300),
resumable-invocation execution (identical math, chunked in time).
"""
from __future__ import annotations

import argparse
import json
import os
import resource
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.utils.checkpoint import checkpoint as ckpt

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "experiments/z041-coding-finetune/train"
RESUME_DIR = OUT_DIR / "resume"
DATASET = ROOT / "experiments/z041-coding-finetune/dataset/sft-25.jsonl"
STATS = ROOT / "experiments/z041-coding-finetune/dataset/dataset-stats.json"

EXPECTED_PARAMS = 494_032_768
SEED = 4141
LR = 2e-4
ACCUM = 8
TRAIN_TIME_CAP_S = 2400  # cumulative 40-minute training budget cap
INVOCATION_CAP_S = 420   # clean exit margin under the 10-min tool call
CHUNK = 128


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def chunked_ce(h: torch.Tensor, labels: torch.Tensor, lm_head, n_sup: int):
    """Sum CE over shift positions in CHUNK-sized pieces; each piece's
    logits are recomputed in backward (checkpoint), so the peak holds at
    most one chunk's fp32 logits (128 x 151,936 x 4 B ~= 78 MiB)."""
    total = None
    L = h.shape[1]
    for a in range(0, L - 1, CHUNK):
        b = min(a + CHUNK, L - 1)
        hc = h[:, a:b, :]
        lc = labels[:, a + 1:b + 1]

        def piece(hh, ll):
            logits = lm_head(hh).float()
            return F.cross_entropy(
                logits.reshape(-1, logits.shape[-1]), ll.reshape(-1),
                ignore_index=-100, reduction="sum")

        s = ckpt(piece, hc, lc, use_reentrant=False)
        total = s if total is None else total + s
    return total / max(int(n_sup), 1)


def build_draws(examples: list[dict], n_draws: int) -> list[int]:
    import random
    rng = random.Random(SEED)
    fam_counts = {}
    for ex in examples:
        fam_counts[ex["family"]] = fam_counts.get(ex["family"], 0) + 1
    cum, acc = [], 0.0
    total_w = sum(1.0 / fam_counts[e["family"]] for e in examples)
    for e in examples:
        acc += (1.0 / fam_counts[e["family"]]) / total_w
        cum.append(acc)
    cum[-1] = 1.0
    draws = []
    for _ in range(n_draws):
        x = rng.random()
        draws.append(next(i for i, c in enumerate(cum) if x <= c))
    return draws


def save_resume(model, opt, sched, state: dict):
    RESUME_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(RESUME_DIR / "adapter")
    torch.save({"opt": opt.state_dict(), "sched": sched.state_dict(),
                "rng": torch.get_rng_state()}, RESUME_DIR / "state.pt")
    (RESUME_DIR / "state.json").write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dtype", choices=["bf16", "fp32"], default="bf16")
    parser.add_argument("--finalize", action="store_true",
                        help="force final save even if the plan is incomplete")
    args = parser.parse_args()

    t_invocation = time.time()
    torch.manual_seed(SEED)
    torch.set_num_threads(2)

    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_dir = Path(os.environ["ARCHAGENT_MODEL_DIR"])
    tok = AutoTokenizer.from_pretrained(model_dir)
    dtype = torch.bfloat16 if args.dtype == "bf16" else torch.float32
    causal = AutoModelForCausalLM.from_pretrained(model_dir, dtype=dtype)
    n_params = sum(p.numel() for p in causal.parameters())
    assert n_params == EXPECTED_PARAMS, n_params
    assert len(causal.model.layers) == 24 and causal.config.hidden_size == 896
    causal.config.use_cache = False

    lcfg = LoraConfig(
        r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "up_proj", "down_proj"])
    # ---- resume or fresh model construction ----------------------------------
    # (peft>=0.21 wraps adapter params in ModuleDict('default'); the
    # canonical resume path is PeftModel.from_pretrained, which handles
    # the saved-key remapping — never hand-remap state-dict keys)
    state_path = RESUME_DIR / "state.json"
    if state_path.is_file():
        from peft import PeftModel
        state = json.loads(state_path.read_text(encoding="utf-8"))
        model = PeftModel.from_pretrained(causal, str(RESUME_DIR / "adapter"),
                                          is_trainable=True)
    else:
        model = get_peft_model(causal, lcfg)  # fp32 adapters (autocast_adapter_dtype)
        state = {"micro_done": 0, "opt_step": 0, "train_elapsed_s": 0.0,
                 "log_entries": []}
    for n, p in model.named_parameters():
        if p.requires_grad:
            assert p.dtype == torch.float32, f"adapter not fp32: {n}"
    n_trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    base = model.get_base_model()
    base.gradient_checkpointing_enable()
    base.enable_input_require_grads()
    trunk, lm_head = base.model, base.lm_head
    opt = torch.optim.AdamW(
        [p for p in model.parameters() if p.requires_grad],
        lr=LR, weight_decay=0.0)

    examples = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines()]
    stats = json.loads(STATS.read_text(encoding="utf-8"))
    plan = stats["sampling"]
    assert plan["seed"] == SEED and len(examples) == 25
    draws = build_draws(examples, plan["draws"])
    n_micro = (len(draws) // ACCUM) * ACCUM  # 296 of 300 (tail disclosed)
    n_opt = n_micro // ACCUM
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=n_opt)

    # ---- restore optimizer/scheduler/rng on resume ----------------------------
    if state_path.is_file():
        bundle = torch.load(RESUME_DIR / "state.pt", map_location="cpu",
                            weights_only=False)
        opt.load_state_dict(bundle["opt"])
        sched.load_state_dict(bundle["sched"])
        torch.set_rng_state(bundle["rng"])
        print(f"RESUMED at micro {state['micro_done']} "
              f"(opt step {state['opt_step']}, "
              f"train {state['train_elapsed_s']:.0f}s)", flush=True)

    if not (OUT_DIR / "train-config.json").is_file():
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        config = {
            "session": "041B", "seed": SEED, "dtype_trunk": args.dtype,
            "dtype_choice": "bf16 per bench_dtype probe (fp32 not measurable "
                            "on this 3.9 GiB box); 038A Plan-1 intent",
            "lora": {"r": 16, "alpha": 32, "dropout": 0.05, "bias": "none",
                     "targets": sorted(lcfg.target_modules)},
            "n_trainable_params": n_trainable,
            "lr": LR, "schedule": "cosine", "warmup": 0,
            "micro_batch": 1, "grad_accum": ACCUM, "effective_batch": ACCUM,
            "epochs_plan": plan["epochs"], "draws_total": plan["draws"],
            "micro_steps": n_micro, "optimizer_steps": n_opt,
            "loss": "CE on completion tokens + 1 EOS (prompt masked -100)",
            "chunked_ce_chunk": CHUNK,
            "train_time_cap_s": TRAIN_TIME_CAP_S,
            "invocation_cap_s": INVOCATION_CAP_S,
            "execution": "resumable across sandbox invocations; identical "
                         "math (adapter+optimizer+scheduler+rng checkpointed "
                         "after every optimizer step)",
            "amendments": [
                "epochs 3 -> 12 (038A Plan-1 used 20; within its envelope)",
                "one supervised EOS token after each completion",
                "grad-accum tail: 296 of 300 draws used",
                "bf16 trunk per measured probe (038A plan's own choice)",
            ],
            "model_pin_sha256": stats["model_pin_sha256"],
        }
        (OUT_DIR / "train-config.json").write_text(
            json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    log_fh = open(OUT_DIR / "train-log.jsonl", "a", encoding="utf-8")
    model.train()
    opt.zero_grad(set_to_none=True)
    run_loss_sum, run_loss_n = 0.0, 0
    group_micro, stopped_reason = 0, None

    while state["micro_done"] + group_micro < n_micro:
        if state["train_elapsed_s"] + (time.time() - t_invocation) > TRAIN_TIME_CAP_S:
            stopped_reason = (f"train-time cap {TRAIN_TIME_CAP_S}s at micro "
                              f"{state['micro_done'] + group_micro}")
            break
        if time.time() - t_invocation > INVOCATION_CAP_S:
            stopped_reason = "invocation-budget exit (resume to continue)"
            break
        micro = state["micro_done"] + group_micro
        ex = examples[draws[micro]]
        ids_p = tok(ex["prompt"], add_special_tokens=False)["input_ids"]
        ids_c = tok(ex["prompt"] + ex["completion"], add_special_tokens=False)["input_ids"]
        assert ids_c[: len(ids_p)] == ids_p, ex["id"]
        ids = ids_c + [ex["eos_token_id"]]
        n_prompt = len(ids_p)
        input_ids = torch.tensor([ids], dtype=torch.long)
        labels = input_ids.clone()
        labels[0, :n_prompt] = -100
        n_sup = int((labels != -100).sum())

        h = trunk(input_ids=input_ids).last_hidden_state
        loss = chunked_ce(h, labels, lm_head, n_sup)
        (loss / ACCUM).backward()
        run_loss_sum += float(loss.detach())
        run_loss_n += 1
        group_micro += 1

        if group_micro == ACCUM:
            # optimizer steps ONLY on complete 8-micro groups; an
            # interrupted group is discarded and re-run on resume
            opt.step()
            sched.step()
            opt.zero_grad(set_to_none=True)
            state["micro_done"] += ACCUM
            state["opt_step"] += 1
            entry = {
                "optimizer_step": state["opt_step"],
                "micro": state["micro_done"],
                "example": ex["id"], "family": ex["family"],
                "batch_mean_loss": round(run_loss_sum / max(run_loss_n, 1), 6),
                "lr": sched.get_last_lr()[0],
                "train_elapsed_s": round(state["train_elapsed_s"]
                                         + (time.time() - t_invocation), 1),
                "peak_rss_mb": round(peak_rss_mb(), 1),
            }
            log_fh.write(json.dumps(entry) + "\n")
            log_fh.flush()
            print(json.dumps(entry), flush=True)
            state["log_entries"].append(entry)
            run_loss_sum, run_loss_n = 0.0, 0
            group_micro = 0
            state["train_elapsed_s"] += time.time() - t_invocation
            save_resume(model, opt, sched, state)
            t_invocation = time.time()
    else:
        stopped_reason = stopped_reason or "plan-complete"

    # ---- finalize (always: adapter saved, summary written) --------------------
    state["train_elapsed_s"] += time.time() - t_invocation
    done = state["micro_done"] >= n_micro
    model.save_pretrained(OUT_DIR / "adapter")
    tok.save_pretrained(OUT_DIR / "adapter")
    if done:
        import shutil
        if RESUME_DIR.exists():
            shutil.rmtree(RESUME_DIR)
    summary = {
        "stopped_reason": stopped_reason,
        "complete": done,
        "micro_steps_done": state["micro_done"],
        "optimizer_steps_done": state["opt_step"],
        "planned": {"micro_steps": n_micro, "optimizer_steps": n_opt},
        "train_seconds_cumulative": round(state["train_elapsed_s"], 1),
        "train_time_cap_s": TRAIN_TIME_CAP_S,
        "peak_rss_mb": round(peak_rss_mb(), 1),
        "adapter_dir": str(OUT_DIR / "adapter"),
        "trainable_params": n_trainable,
        "log_entries": len(state["log_entries"]),
    }
    (OUT_DIR / "train-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    log_fh.close()
    print(json.dumps(summary, indent=1), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
