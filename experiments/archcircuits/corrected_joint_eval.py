"""Session 011 corrected re-evaluation of the joint CON+XCOM factor set.

The independent audit found that the Session 010 joint edit was applied in
RAM at the capped scale (0.6943985003096566) but the saved factors were the
UNCAPPED proposal, so every reload-based evaluation of `joint_L16`
(eval_joint_L16_dev, eval_joint_val, holdout_joint_L16) actually measured an
edit of ~2.16% relative Frobenius norm — above the 1.5% repository limit.

This script:
  1. rebuilds the intended bounded edit (saved factors x recorded scale),
     saved as factors/joint_L16_corrected with full verification metadata;
  2. verifies the corrected set (norm bound + reversibility within float32
     tolerance) with the new verify_factor_set tooling;
  3. re-runs the dev / val / holdout evaluations with the corrected factors;
  4. publishes paired comparisons against the recorded baseline under
     reports/corrected/ WITHOUT modifying any historical file.

Historical results are never edited; corrected results are published
separately and both versions are referenced in the report.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
torch.set_num_threads(2)

from archcircuits.benchmark import tasks_for  # noqa: E402
from archcircuits.runner import (load_model, evaluate_tasks, save_report,  # noqa: E402
                                 paired_comparison, resolve_model_path, repro_info)
from archcircuits import edits  # noqa: E402

ROOT = Path(__file__).resolve().parents[0]
FACTORS = ROOT / "factors"
REPORTS = ROOT / "reports"
LEGACY = FACTORS / "joint_L16"
CORRECTED = FACTORS / "joint_L16_corrected"
BASELINE = REPORTS / "baseline.json"


def build_corrected_factors() -> dict:
    """Scale the legacy saved proposal by its recorded applied_scale."""
    from safetensors.torch import load_file, save_file

    meta = json.loads((LEGACY / "meta.json").read_text(encoding="utf8"))
    scale = meta["applied"]["applied_scale"]
    if not (0 < scale < 1.0):
        raise ValueError(f"unexpected applied_scale {scale}; set was not capped?")
    factors = load_file(str(LEGACY / "factors.safetensors"))
    left = factors["left"].float() * scale
    right = factors["right"].float()
    CORRECTED.mkdir(parents=True, exist_ok=True)
    save_file({"left": left.contiguous().cpu(),
               "right": right.contiguous().cpu()},
              str(CORRECTED / "factors.safetensors"))
    corrected_meta = {
        **{k: v for k, v in meta.items() if k not in ("applied",)},
        "applied": meta["applied"],
        "correction": {
            "reason": "Session 011 audit: legacy factors were the uncapped "
                      "proposal; applied edit used in-RAM scaling that was "
                      "not persisted",
            "legacy_directory": str(LEGACY),
            "rescale_factor": scale,
            "legacy_relative_delta_frob_unscaled": 0.021586,
            "corrected_relative_delta_frob_expected": meta["applied"]["relative_delta_frob"],
        },
    }
    (CORRECTED / "meta.json").write_text(
        json.dumps(corrected_meta, indent=2) + "\n", encoding="utf8")
    return corrected_meta


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--partition", choices=["dev", "val", "holdout", "all"],
                    default="all")
    args = ap.parse_args()
    model_path = resolve_model_path()
    meta = build_corrected_factors()

    model, tok, _ = load_model(edit_dirs=None, model_path=model_path)
    verification = edits.verify_factor_set(model, str(CORRECTED))
    print("corrected factor verification:", json.dumps(verification, indent=1))
    if not verification["within_limit"]:
        raise SystemExit("corrected factors still exceed the cap")

    base = json.loads(BASELINE.read_text())
    base_records = {r["id"]: r for r in base["records"]}

    out_dir = REPORTS / "corrected"
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "correction_note": ("joint_L16 was historically evaluated with the "
                            "uncapped saved proposal (~2.16% relative Frobenius); "
                            "these runs use the intended bounded edit "
                            "(<= 1.5%). Historical files are unchanged."),
        "factor_verification": verification,
        "repro": repro_info(model_path),
        "partitions": {},
    }
    partitions = (["dev", "val", "holdout"] if args.partition == "all"
                  else [args.partition])
    for partition in partitions:
        out_file = out_dir / f"eval_joint_L16_corrected_{partition}.json"
        if out_file.is_file():
            print(f"[{partition}] already evaluated; skipping")
            continue
        tasks = tasks_for(partition)
        t0 = time.time()
        rep = evaluate_tasks(model, tok, tasks, tag=f"joint_L16_corrected_{partition}")
        rep["edits_applied"] = ["JOINT_CON_XCOM_CORRECTED"]
        rep["edits_meta"] = [meta]
        part_records = [base_records[r["id"]] for r in rep["records"]]
        pc = paired_comparison(part_records, rep["records"],
                               "baseline", f"joint_corrected_{partition}")
        rep["paired_vs_baseline"] = pc
        save_report(rep, str(out_dir / f"eval_joint_L16_corrected_{partition}.json"))
        summary["partitions"][partition] = {
            "accuracy": rep["accuracy"],
            "by_category": rep["by_category"],
            "baseline_accuracy": round(
                sum(r["correct"] for r in part_records) / len(part_records), 4),
            "gained": pc["gained"], "lost": pc["lost"],
            "mcnemar_p": pc["mcnemar_p"],
            "wall_seconds": round(time.time() - t0, 1),
        }
        print(f"[{partition}] corrected={rep['accuracy']} "
              f"baseline={summary['partitions'][partition]['baseline_accuracy']} "
              f"gained={pc['gained']} lost={pc['lost']}", flush=True)
    save_report(summary, str(out_dir / "joint_correction_summary.json"))
    print("done")


if __name__ == "__main__":
    main()
