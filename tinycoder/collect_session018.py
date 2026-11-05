"""Verify and publish completed Session018 Python-only search measurements."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session017 import metrics
from .session017_contracts import contract_sha256, contracts


TRACKS = ("control", "typed_ast", "search4", "search8_repair2")


def collect(output: Path, destination: Path, readme: Path):
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    predictions = json.loads((output / "predictions.json").read_text(encoding="utf-8"))
    archive = json.loads((output / "candidate_public_archive.json").read_text(encoding="utf-8"))
    ids = [t["task_id"] for t in contracts()]
    selection = report.get("selection", {})
    if (report.get("status") != "completed" or report.get("session") != "018"
        or report.get("model") != MODEL_ID
        or report.get("parameter_count") != MODEL_PARAMETER_COUNT
        or report.get("training_steps") != 0
        or report.get("manifest_sha256") != contract_sha256(contracts())
        or report.get("task_ids") != ids
        or selection.get("holdout_used_during_selection") is not False
        or selection.get("react_express_source_unchanged") is not True
        or selection.get("extra_public_distinguishing_probes_per_app") != 2
        or set(report["tracks"]) != set(TRACKS)
        or set(predictions) != set(TRACKS)
        or set(archive) != set(ids)):
        raise ValueError("Session018 provenance, parameter count or task identity invalid")
    for name in TRACKS:
        source = predictions[name]
        observed = report["tracks"][name]
        if (set(source) != set(ids)
            or [row["task_id"] for row in observed["task_results"]] != ids
            or metrics(observed["task_results"]) != observed["holdout"]):
            raise ValueError(f"Session018 score did not reproduce: {name}")
        if any(set(source[tid]) != {"logic", "api", "ui"} or
               not all(isinstance(source[tid][role], str) for role in ("logic", "api", "ui"))
               for tid in ids):
            raise ValueError(f"Incomplete source archive: {name}")
        if name != "control":
            if any(source[tid][role] != predictions["control"][tid][role]
                   for tid in ids for role in ("api", "ui")):
                raise ValueError("Unscoped Express or React edit in Session018")
    if (report["tracks"]["control"]["holdout"]["full_app_passes"] != 5
        or report["tracks"]["control"]["holdout"]["module_passes"]
        != {"logic": 5, "api": 9, "ui": 10}
        or report["compute"]["sample_draws_max"] != 8
        or report["compute"]["repair_rounds_max"] != 2):
        raise ValueError("Session017b frozen baseline or search budget unexpectedly changed")
    if any(not isinstance(archive[tid], list) or not archive[tid] or
           any(candidate["public_result"]["cases_total"] != 4
               for candidate in archive[tid]) for tid in ids):
        raise ValueError("Missing public candidate diagnostics")

    destination.mkdir(parents=True, exist_ok=True)
    save_json(destination / "session018_extreme_report.json", report)
    save_json(destination / "session018_extreme_predictions.json", predictions)
    save_json(destination / "session018_extreme_public_candidates.json", archive)

    raw = readme.read_text(encoding="utf-8")
    begin, end = "<!-- SESSION018-PENDING-START -->", "<!-- SESSION018-PENDING-END -->"
    if raw.count(begin) != 1 or raw.count(end) != 1:
        raise ValueError("Expected unique Session018 README staging markers")
    a = report["tracks"]
    def row(name, label):
        s = a[name]["holdout"]
        return (f"| {label} | {s['full_app_passes']}/10 | "
                f"{s['module_passes']['logic']}/10 | "
                f"{s['module_passes']['api']}/10 | "
                f"{s['module_passes']['ui']}/10 | "
                f"{s['all_three_syntax_valid']}/10 |")
    block = f"""## Session 018 — extreme, bounded Python search (measured)

The **unchanged Qwen2.5-Coder-0.5B** base model and frozen Session017b
scaffold were re-used. This ablation tests whether repairing Python dictionary
access and increasing *test-time* sampling/feedback improves complete mini-app
execution. React and Express source bytes are identical in all four tracks.
No model parameters were edited or trained.

| Track | Integrated holdout | Python | Express | React | Valid three-module syntax |
| --- | ---: | ---: | ---: | ---: | ---: |
{row('control', 'Session017b frozen control')}
{row('typed_ast', 'Public-schema AST repair')}
{row('search4', 'AST + up to 4 extra samples')}
{row('search8_repair2', 'AST + up to 8 samples + 2 repairs')}

Additional inference: **{report['compute']['new_output_tokens']} generated
output tokens** ({report['compute']['sample_output_tokens']} samples,
{report['compute']['repair_output_tokens']} repairs),
**{report['compute']['wall_seconds']} seconds** total wall time.
Candidate selection saw two original public examples and two additional
PUBLIC edge-case probes per app; **two distinct holdout inputs** were evaluated
only after code selection was frozen.

**Interpretation:** These are ten custom, small, authored vertical slices, not
production-ready applications, independently sourced benchmarks, or proof of
parity with a larger coding model. The best-of-search result uses more compute
and trusted compiler/scaffold assistance; it is a *system-level selected@1*,
NOT the underlying model's single-sample pass@1. Generated code was evaluated
only inside Docker with network and privilege restrictions.

[Verified report](experiments/session018_extreme_report.json) ·
[Exact source per ablation](experiments/session018_extreme_predictions.json) ·
[Public search failures and selections](experiments/session018_extreme_public_candidates.json).

"""
    prefix, rest = raw.split(begin, 1)
    _, suffix = rest.split(end, 1)
    readme.write_text(prefix + block + suffix.lstrip("\n"), encoding="utf-8")
    print(json.dumps({name: a[name]["holdout"]["full_app_passes"]
                      for name in TRACKS}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/session018"))
    parser.add_argument("--publish-to", type=Path, default=Path("experiments"))
    parser.add_argument("--readme", type=Path, default=Path("README.md"))
    args = parser.parse_args()
    collect(args.output_dir, args.publish_to, args.readme)


if __name__ == "__main__":
    main()
