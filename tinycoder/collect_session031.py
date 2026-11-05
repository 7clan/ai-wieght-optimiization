"""Publish only faithfully archived Qwen-generated Session031 repairs."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session015 import MODEL_PARAMETER_COUNT
from .session027 import ROLE_PATHS
from .session030_contract import PREFIX, ROLES


def collect(root: Path):
    report = json.loads((root / "report.json").read_text(encoding="utf8"))
    data = json.loads((root / "predictions.json").read_text(encoding="utf8"))
    if (report.get("session") != "031" or report.get("status") != "completed"
            or report.get("parameter_count") != MODEL_PARAMETER_COUNT
            or report.get("training_steps") != 0 or report.get("weight_edits") != 0
            or report.get("independent_generalization") is not False
            or report.get("teacher_target_code_used") is not False):
        raise ValueError("Invalid experiment provenance")
    original, selected, attempts = data["initial"], data["selected"], data["attempts"]
    if set(original) != set(ROLES) or set(selected) != set(ROLES):
        raise ValueError("Incomplete sources")
    if len(attempts) != report["search"]["candidates"]:
        raise ValueError("Candidate count mismatch")
    if len({a["role"] for a in attempts}) != len(attempts):
        raise ValueError("Duplicate candidate role")
    for role in ROLES:
        candidate = next((a for a in attempts if a["role"] == role), None)
        expected = (PREFIX[role] + candidate["raw"] if candidate and candidate["accepted"]
                    else original[role])
        if selected[role] != expected:
            raise ValueError("Unattributed replacement: " + role)
        if candidate and candidate["candidate_source"] != PREFIX[role] + candidate["raw"]:
            raise ValueError("Unattributed model generation")
        if data["source_sha256"][role] != hashlib.sha256(selected[role].encode()).hexdigest():
            raise ValueError("Source hash mismatch")
        if (root / "generated" / ROLE_PATHS[role]).read_text(encoding="utf8") != selected[role]:
            raise ValueError("Published source mismatch")
    for phase in (report["before"], report["after"]):
        if phase["phase"] != "holdout" or set(phase["modules"]) != set(ROLES):
            raise ValueError("Missing repeated holdout results")
    page = (root / "preview/index.html").read_text(encoding="utf8").lower()
    if any(x in page for x in ("<script", "<iframe", "<form")):
        raise ValueError("Unsafe static preview")
    output = Path("docs/previews/session031")
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Refusing to overwrite earlier preview")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(root / "preview/index.html", output / "index.html")
    for role, path in ROLE_PATHS.items():
        target = output / "generated" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / "generated" / path, target)
    save_json(Path("experiments/session031_contract_report.json"), report)
    save_json(Path("experiments/session031_contract_predictions.json"), data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs/session031", type=Path)
    collect(parser.parse_args().output_dir)
