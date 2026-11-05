"""Fast Session017b ablation: contract-derived UI fallback, zero model inference.

Reuses the EXACT frozen Session017 generated modules and score manifest. The
only intervention is a trusted, deterministic React shell for UI modules that
fail PUBLIC checks. No tests, Python/Express modules, or model weights change.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session017 import check_apps, metrics
from .session017_contracts import MODULES, contract_sha256, contracts, holdout_cases
from .session017_scaffold import export_project
from .session017_ui_templates import contract_ui


FROZEN_REPORT = Path("experiments/session017_fullstack_report.json")
FROZEN_PREDICTIONS = Path("experiments/session017_fullstack_predictions.json")


def run(out: Path):
    require_sandbox()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Refusing to overwrite Session017b outputs")
    out.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    tasks = contracts()
    ids = [t["task_id"] for t in tasks]
    public = {t["task_id"]: t["public_cases"] for t in tasks}
    frozen = json.loads(FROZEN_PREDICTIONS.read_text(encoding="utf-8"))
    if any(set(frozen[name]) != set(ids) or any(set(app) != set(MODULES)
           for app in frozen[name].values()) for name in ("baseline", "guided")):
        raise ValueError("Archived model completions are incomplete")

    # A: frozen model-generated source, scored on PUBLIC inputs only.
    generated_public = {name: check_apps(tasks, frozen[name], public)
                        for name in ("baseline", "guided")}
    fallback = {}
    fallback_ids = {}
    for track in ("baseline", "guided"):
        source = {task_id: dict(modules) for task_id, modules in frozen[track].items()}
        chosen = []
        for task, previous in zip(tasks, generated_public[track], strict=True):
            if not previous["modules"]["ui"]["passed"]:
                source[task["task_id"]]["ui"] = contract_ui(task)
                chosen.append(task["task_id"])
        fallback[track] = source
        fallback_ids[track] = chosen
    print({"public_ui_fallback_ids": fallback_ids}, flush=True)

    # B: separately verify the contract-only scaffold on public inputs.
    scaffold_public = {name: check_apps(tasks, fallback[name], public)
                       for name in ("baseline", "guided")}
    if any(not row["modules"]["ui"]["passed"]
           for records in scaffold_public.values() for row in records):
        raise RuntimeError("Deterministic UI shell failed public integration contract")

    # C: heldout inputs only appear AFTER final fallback decisions are frozen.
    hidden = holdout_cases()
    base_final = check_apps(tasks, frozen["baseline"], hidden)
    guided_final = check_apps(tasks, frozen["guided"], hidden)
    scaffold_final = {name: check_apps(tasks, fallback[name], hidden)
                      for name in ("baseline", "guided")}

    # D: verify previous final results exactly, before reporting any new scores.
    previous = json.loads(FROZEN_REPORT.read_text(encoding="utf-8"))
    if (previous.get("status") != "completed" or previous.get("model") != MODEL_ID
        or previous.get("parameter_count") != MODEL_PARAMETER_COUNT
        or previous["dataset"]["manifest_sha256"] != contract_sha256(tasks)
        or previous["dataset"]["task_ids"] != ids
        or metrics(base_final) != previous["baseline"]["holdout"]
        or metrics(guided_final) != previous["guided"]["holdout"]):
        raise ValueError("Frozen original Session017 results were not reproduced")
    report = {
        "status": "completed", "session": "017b", "model": MODEL_ID,
        "parameter_count": MODEL_PARAMETER_COUNT, "training_steps": 0,
        "manifest_sha256": contract_sha256(tasks), "task_ids": ids,
        "baseline": metrics(base_final), "guided": metrics(guided_final),
        "baseline_scaffold": metrics(scaffold_final["baseline"]),
        "guided_scaffold": metrics(scaffold_final["guided"]),
        "public_scores": {name: {"original": metrics(generated_public[name]),
                                 "scaffold": metrics(scaffold_public[name])}
                          for name in ("baseline", "guided")},
        "selection": {"mode": "replace_UI_if_and_only_if_public_UI_checks_fail",
                      "public_fallback_ids": fallback_ids,
                      "number_of_generated_modules_reused": 60,
                      "number_of_new_model_inference_calls": 0,
                      "holdout_used_for_selection": False},
        "compute": {"additional_generated_output_tokens": 0,
                    "wall_seconds": round(time.monotonic()-start, 2)},
        "caveats": "A system-level ablation, NOT a model-only pass@1 improvement. Fallback UIs are generated deterministically from explicit authored contracts; the model does not independently author those replacement components. Ten small authored examples, not independent production-grade application tasks. Docker restrictions are defense-in-depth, not a guarantee of safety.",
        "task_results": {name: scaffold_final[name] for name in ("baseline", "guided")},
    }
    save_json(out / "report.json", report)
    save_json(out / "predictions.json", {"baseline_scaffold": fallback["baseline"],
                                        "guided_scaffold": fallback["guided"],
                                        "fallback_ids": fallback_ids})
    for task, record in zip(tasks, scaffold_final["guided"], strict=True):
        export_project(out / "projects", task, fallback["guided"][task["task_id"]],
                       holdout_passed=bool(record["passed"]))
    print({name:report[name]["full_app_passes"] for name in
           ("baseline", "guided", "baseline_scaffold", "guided_scaffold")}, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/session017b"))
    args = parser.parse_args()
    run(args.output_dir)


if __name__ == "__main__":
    main()
