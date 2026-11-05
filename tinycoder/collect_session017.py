"""Publish only verified Session017 benchmark results from Docker artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session017 import metrics
from .session017_contracts import MODULES, contract_sha256, contracts


def collect(output: Path, out: Path, readme: Path):
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    predictions = json.loads((output / "predictions.json").read_text(encoding="utf-8"))
    tasks = contracts()
    ids = [t["task_id"] for t in tasks]
    if (report.get("status") != "completed" or report.get("model") != MODEL_ID
        or report.get("parameter_count") != MODEL_PARAMETER_COUNT
        or report.get("training_steps") != 0
        or report["dataset"]["manifest_sha256"] != contract_sha256(tasks)
        or report["dataset"]["task_ids"] != ids
        or report["selection"]["holdout_used_during_search"] is not False):
        raise ValueError("Session017 provenance / isolation verification failed")
    for track in ("baseline", "guided"):
        if set(predictions[track]) != set(ids):
            raise ValueError(f"Missing or duplicated generated {track} projects")
        for app in predictions[track].values():
            if set(app) != set(MODULES) or any(not isinstance(app[k], str) for k in MODULES):
                raise ValueError("Incomplete or invalid three-language source bundle")
        for scope in ("public", "holdout"):
            records = report[track]["task_results"] if scope == "holdout" else None
            if records is not None:
                if [r["task_id"] for r in records] != ids:
                    raise ValueError("Incorrect final task ordering")
                if metrics(records) != report[track][scope]:
                    raise ValueError(f"Inconsistent {track} {scope} metrics")

    out.mkdir(parents=True, exist_ok=True)
    save_json(out / "session017_fullstack_report.json", report)
    save_json(out / "session017_fullstack_predictions.json", predictions)
    original = readme.read_text(encoding="utf-8")
    begin, end = "<!-- SESSION017-PENDING-START -->", "<!-- SESSION017-PENDING-END -->"
    if original.count(begin) != 1 or original.count(end) != 1:
        raise ValueError("README missing unique Session017 pending section")
    b = report["baseline"]["holdout"]
    g = report["guided"]["holdout"]
    generation = report["compute"]
    section = f"""## Session 017 — contract-first full-stack vertical slices (measured)

**Frozen model:** `{MODEL_ID}`, {MODEL_PARAMETER_COUNT:,} parameters; no
fine-tuning, gradients, static weight modification, or parameter scaling.
Ten **newly authored mini-app specifications** require Python transformation,
an Express POST endpoint, React JSX rendering, and the integrated request-to-UI
path. Public cases steer up to one sampled continuation and one localized
repair for failed modules; **two separate holdout inputs per app** are evaluated
only after final candidates have been frozen. All code executes in restricted,
network-disabled Docker.

| System | Fully integrated apps on holdout | Python modules | Express modules | React modules | Valid three-module syntax |
| --- | ---: | ---: | ---: | ---: | ---: |
| Untouched greedy | {b['full_app_passes']}/10 | {b['module_passes']['logic']}/10 | {b['module_passes']['api']}/10 | {b['module_passes']['ui']}/10 | {b['all_three_syntax_valid']}/10 |
| Contract-guided search | {g['full_app_passes']}/10 | {g['module_passes']['logic']}/10 | {g['module_passes']['api']}/10 | {g['module_passes']['ui']}/10 | {g['all_three_syntax_valid']}/10 |

**Compute:** {generation['total_output_tokens']} generated output tokens in all,
including {generation['extra_sample_output_tokens']} sampled alternatives and
{generation['extra_repair_output_tokens']} repair tokens; {generation['wall_seconds']}s
wall-time. The guided score is a **system-level** result after extra inference.

This is a **controlled proof of concept, not evidence of production-ready
autonomous development or parity with frontier models**. The ten specifications
are authored, not an independently curated third-party benchmark; test cases
may be similar to public examples even though holdout values were withheld from
candidate selection. Browser-level accessibility, security, deployment and
multi-page workflows are outside this session's scope. Archived candidate
project files are untrusted; do not run them outside a sandbox.

[Full verified report](experiments/session017_fullstack_report.json) ·
[Generated modules and acceptances](experiments/session017_fullstack_predictions.json).
The workflow also retains the ten candidate app directories as artifacts.

"""
    prefix, tail = original.split(begin, 1)
    _, suffix = tail.split(end, 1)
    readme.write_text(prefix + section + suffix.lstrip("\n"), encoding="utf-8")
    print(json.dumps({"baseline_integrated": b["full_app_passes"],
                      "guided_integrated": g["full_app_passes"],
                      "generated_tokens": generation["total_output_tokens"]}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/session017"))
    parser.add_argument("--publish-to", type=Path, default=Path("experiments"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    args = parser.parse_args()
    collect(args.output_dir, args.publish_to, args.readme)


if __name__ == "__main__":
    main()
