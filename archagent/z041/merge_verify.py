"""Session 041B — merge the trained LoRA adapter into the frozen base and verify.

Steps (user-mandated):
  1. load the frozen base in fp32 (sha-verified safetensors, architecture
     check 494,032,768 params / 24 layers / 896 hidden);
  2. snapshot the base weights as bf16 — EXACT, because the on-disk
     checkpoint is bf16 (fp32 load is an exact upcast; bf16 snapshot is
     a lossless round-trip) and it halves the diff-snapshot RAM (the
     fp32 variant OOMs on this 3.9 GiB box — measured, disclosed);
  3. load the 041B adapter onto it (fp32 LoRA) and merge with
     merge_and_unload() — a REAL in-weight merge (in place, no adapter
     modules left in the result);
  4. verify: merged module type is the plain Qwen2ForCausalLM, parameter
     count and architecture identical to the original, no NaN/Inf;
  5. weight-diff audit vs the exact bf16 snapshot: exactly the 24x6
     LoRA-target matrices changed, with per-matrix max|ΔW| statistics;
  6. save the merged checkpoint (bf16 — the original checkpoint's
     on-disk format) + tokenizer + generation_config + sha256 manifest.

The merged weights are NOT committed to git (repo convention: *.safetensors
ignored; GitHub 100 MB/file limit). The adapter and this script ARE
committed, so the merge is reproducible from branch artifacts.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

import torch

ROOT = Path(__file__).resolve().parents[2]
TRAIN = ROOT / "experiments/z041-coding-finetune/train"
ADAPTER = TRAIN / "adapter"
MERGED_DIR = ROOT / "experiments/z041-coding-finetune/merged-checkpoint"

EXPECTED_PARAMS = 494_032_768
FROZEN_SHA = "aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer, Qwen2ForCausalLM

    model_dir = Path(os.environ["ARCHAGENT_MODEL_DIR"])
    assert sha256_file(model_dir / "model.safetensors") == FROZEN_SHA, \
        "base safetensors sha mismatch"

    # 1. frozen base in fp32 ---------------------------------------------------
    t0 = time.time()
    base = AutoModelForCausalLM.from_pretrained(model_dir, dtype=torch.float32)
    load_s = round(time.time() - t0, 1)
    n_params = sum(p.numel() for p in base.parameters())
    assert n_params == EXPECTED_PARAMS, n_params
    assert len(base.model.layers) == 24 and base.config.hidden_size == 896

    # 2. adapter + real in-place merge ------------------------------------------
    # (no in-RAM weight snapshot: the diff in step 5 reads the on-disk base
    # safetensors memory-mapped, one tensor at a time — an in-RAM snapshot
    # OOMs on this 3.9 GiB box, measured twice, disclosed)
    model = PeftModel.from_pretrained(base, str(ADAPTER))
    assert any("lora" in n for n, _ in model.named_parameters()), "no LoRA tensors"
    t0 = time.time()
    merged = model.merge_and_unload()
    merge_s = round(time.time() - t0, 1)

    # 4. verification ----------------------------------------------------------
    assert type(merged) is Qwen2ForCausalLM, type(merged)
    assert not any("lora" in n for n, _ in merged.named_parameters()), \
        "adapter modules left after merge_and_unload"
    n_params_m = sum(p.numel() for p in merged.parameters())
    assert n_params_m == EXPECTED_PARAMS, n_params_m
    assert len(merged.model.layers) == 24
    assert merged.config.hidden_size == 896
    assert merged.config.vocab_size == base.config.vocab_size
    for p in merged.parameters():
        assert torch.isfinite(p).all(), "non-finite merged weight"
    cfg_equal = merged.config.to_dict() == base.config.to_dict()  # same object tree

    # 5. weight-diff audit vs the on-disk base (memory-mapped, exact) -----------
    from safetensors import safe_open
    merged_sd = merged.state_dict()
    changed = []
    checked = 0
    with safe_open(model_dir / "model.safetensors", framework="pt") as f:
        disk_keys = set(f.keys())
        assert disk_keys <= set(merged_sd), \
            f"on-disk keys missing from merged: {sorted(disk_keys - set(merged_sd))[:5]}"
        for k in sorted(disk_keys):
            base_t = f.get_tensor(k)  # bf16, exact on-disk bytes
            d = merged_sd[k].float() - base_t.float()
            mx = float(d.abs().max())
            checked += 1
            if mx != 0.0:
                changed.append({"param": k, "max_abs_diff": mx,
                                "mean_abs_diff": float(d.abs().mean()),
                                "rel_to_weight_norm": float(
                                    d.norm() / base_t.float().norm())})
            del d, base_t
    lora_targets = {"q_proj", "k_proj", "v_proj", "o_proj", "up_proj", "down_proj"}
    bad = [c for c in changed if not any(t in c["param"] for t in lora_targets)]
    assert not bad, f"weights changed outside LoRA targets: {[c['param'] for c in bad][:5]}"
    assert len(changed) == 24 * 6, len(changed)  # 24 layers x 6 targets
    n_unchanged = checked - len(changed)

    # 6. save (bf16 = the original checkpoint's on-disk format) -----------------
    merged.to(torch.bfloat16)
    if MERGED_DIR.exists():
        import shutil
        shutil.rmtree(MERGED_DIR)
    MERGED_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    merged.save_pretrained(MERGED_DIR, safe_serialization=True)
    save_s = round(time.time() - t0, 1)
    # tokenizer + config files are copied VERBATIM from the frozen base
    # (a transformers 4.57 re-save changes tokenizer.json bytes, rewrites
    # config keys — sliding_window None, dtype vs torch_dtype — and
    # triggers a pre-tokenizer regex warning; measured. Training never
    # touched tokenizer or config, so byte-identical copies are the only
    # correct form: the merged dir differs from the base dir ONLY in
    # model.safetensors bytes)
    import shutil
    for name in ("tokenizer.json", "tokenizer_config.json", "vocab.json",
                 "merges.txt", "generation_config.json", "config.json"):
        shutil.copyfile(model_dir / name, MERGED_DIR / name)
    for extra in ("added_tokens.json", "special_tokens_map.json",
                  "chat_template.jinja"):
        p = MERGED_DIR / extra
        if p.exists():
            p.unlink()
    # tokenization-equality proof on a fixed string (both dirs byte-identical
    # files -> identical ids by construction; assert anyway)
    probe = "model Spot {\n  id String @id\n}\nexport async function POST(request: Request) {\n"
    ids_base = AutoTokenizer.from_pretrained(model_dir)(probe, add_special_tokens=False)["input_ids"]
    ids_merged = AutoTokenizer.from_pretrained(MERGED_DIR)(probe, add_special_tokens=False)["input_ids"]
    assert ids_base == ids_merged, "tokenization drift between base and merged"

    manifest = {
        "merged_dir": str(MERGED_DIR),
        "merge_method": "peft merge_and_unload() on the fp32 base, saved bf16 "
                        "(the original checkpoint's on-disk dtype; fp32->bf16 "
                        "rounding on save is the standard merge convention)",
        "base_model_sha256": FROZEN_SHA,
        "adapter_dir": str(ADAPTER),
        "adapter_files_sha256": {p.name: sha256_file(p)
                                 for p in sorted(ADAPTER.iterdir()) if p.is_file()},
        "architecture": {"params": n_params_m, "layers": 24, "hidden": 896,
                         "class": type(merged).__name__,
                         "config_identical_to_base": cfg_equal},
        "changed_matrices": len(changed),
        "unchanged_matrices": n_unchanged,
        "matrices_checked": checked,
        "max_abs_diff_overall": max(c["max_abs_diff"] for c in changed),
        "largest_relative_change": max(c["rel_to_weight_norm"] for c in changed),
        "changed_matrix_examples": sorted(changed,
                                          key=lambda c: -c["max_abs_diff"])[:8],
        "timing_s": {"base_load_fp32": load_s, "merge": merge_s, "save_bf16": save_s},
        "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha256_file(p)}
                  for p in sorted(MERGED_DIR.iterdir()) if p.is_file()},
    }
    (MERGED_DIR / "merge-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items()
                      if k not in ("files", "adapter_files_sha256",
                                   "changed_matrix_examples")}, indent=1))
    print("files:", {k: v["bytes"] for k, v in manifest["files"].items()})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
