"""Small, *exploratory* frozen Qwen solo-vs-controller pilot.

Both tracks use the exact same loaded checkpoint. Private test fixtures are
evaluated only after generation for BOTH tracks has finished. No gradients.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import resource
import time

from adaptive_agent import AgentController, Budget, ControllerError, ModelContext, Task
from adaptive_agent.controller import _validate_proposal
from adaptive_agent.docker_sandbox import DockerSandbox, PublicFixture, require_docker
from adaptive_agent.qwen_adapter import (QwenCommonJSScaffoldAdapter, QwenFunctionBodyAdapter,
                                         QwenSingleFileAdapter, load_local_qwen)


MODEL_ID = "Qwen/Qwen2.5-Coder-0.5B-Instruct"


@dataclass(frozen=True)
class PilotTask:
    contract: Task
    public: PublicFixture
    private: PublicFixture
    commonjs_export: str | None = None
    commonjs_parameters: tuple[str, ...] = ()


PILOT_TASKS = (
    PilotTask(
        Task("py-nonempty", (
            "Write solution.py defining count_nonempty(items), returning the number of "
            "nonempty or non-whitespace strings. Input is a list of strings."
        ), ("count_nonempty([' a ', '', 'b']) == 2",), ("solution.py",)),
        PublicFixture("python", (
            "import sys\nsys.path.insert(0,'/app')\nfrom solution import count_nonempty\n"
            "assert count_nonempty([' a ', '', 'b']) == 2\n"
        )),
        PublicFixture("python", (
            "import sys\nsys.path.insert(0,'/app')\nfrom solution import count_nonempty\n"
            "assert count_nonempty([]) == 0\nassert count_nonempty([' ', '\\t', 'x']) == 1\n"
        )),
    ),
    PilotTask(
        Task("js-normalizetags", (
            "Write solution.cjs exporting a function normalizeTags(items). Given a JavaScript "
            "array of strings, trim and lowercase each, drop empty strings, keep first occurrence "
            "of each unique normalized string, preserving order."
        ), ("normalizeTags([' A ','a','B']) returns ['a','b']",), ("solution.cjs",)),
        PublicFixture("javascript", (
            "const assert=require('node:assert/strict');\n"
            "const {normalizeTags}=require('/app/solution.cjs');\n"
            "assert.deepEqual(normalizeTags([' A ', 'a', 'B']), ['a','b']);\n"
        )),
        PublicFixture("javascript", (
            "const assert=require('node:assert/strict');\n"
            "const {normalizeTags}=require('/app/solution.cjs');\n"
            "assert.deepEqual(normalizeTags([]), []);\n"
            "assert.deepEqual(normalizeTags(['  ', 'X', ' x ', 'Y']), ['x','y']);\n"
        )),
        "normalizeTags",
        ("items",),
    ),
)


class NoWebResearch:
    """No hidden internet or teacher assistance in this protocol smoke."""
    def lookup(self, query):
        return None


def solo_attempt(model, spec: PilotTask, sandbox: DockerSandbox) -> dict:
    started = time.monotonic()
    output = {"public_pass": False, "proposal_valid": False, "files": None, "error": None}
    try:
        candidate = model.propose(ModelContext(
            spec.contract, 1, (), (),
            "Split contracts; change one hypothesis at a time; verify public checks.",
        ))
        _validate_proposal(candidate.files, max_file_bytes=60_000,
                           required_files=spec.contract.required_files)
        output["proposal_valid"] = True
        output["files"] = dict(candidate.files)
        result = sandbox.evaluate(spec.contract, candidate.files)
        output["public_pass"] = result.passed
        if not result.passed:
            output["error"] = result.feedback[:600]
    except ControllerError as exc:
        output["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
    output["seconds"] = round(time.monotonic() - started, 3)
    return output


def private_score(spec: PilotTask, files: dict[str, str] | None) -> bool | None:
    if not files:
        return None
    evaluator = DockerSandbox({spec.contract.task_id: spec.private})
    return evaluator.evaluate(spec.contract, files).passed


def run(output_path: Path, max_new_tokens: int = 400) -> dict:
    require_docker()  # Don't download a model if execution cannot be scored.
    import torch
    torch.set_num_threads(2)
    setup = time.monotonic()
    model = load_local_qwen(MODEL_ID, max_new_tokens=max_new_tokens)
    loading_s = round(time.monotonic() - setup, 3)
    records = []
    direct_adapter = QwenSingleFileAdapter(model.generate_text)

    # The same model instance is reused, but generation is stateless/deterministic.
    for spec in PILOT_TASKS:
        public_evaluator = DockerSandbox({spec.contract.task_id: spec.public})
        solo = solo_attempt(model, spec, public_evaluator)
        start = time.monotonic()
        assisted = AgentController(Budget(max_attempts=2, max_proposals=3,
                                          max_research=0)).run(
            spec.contract, model, public_evaluator, NoWebResearch(),
        )
        assisted_seconds = round(time.monotonic() - start, 3)
        start = time.monotonic()
        direct = AgentController(Budget(max_attempts=3, max_proposals=4,
                                        max_research=0)).run(
            spec.contract, direct_adapter, public_evaluator, NoWebResearch(),
        )
        direct_seconds = round(time.monotonic() - start, 3)
        scaffold = None
        scaffold_seconds = None
        body_track = None
        body_seconds = None
        if spec.commonjs_export:
            start = time.monotonic()
            scaffold = AgentController(Budget(max_attempts=3, max_proposals=4,
                                              max_research=0)).run(
                spec.contract,
                QwenCommonJSScaffoldAdapter(model.generate_text, spec.commonjs_export),
                public_evaluator, NoWebResearch(),
            )
            scaffold_seconds = round(time.monotonic() - start, 3)
            start = time.monotonic()
            body_track = AgentController(Budget(max_attempts=3, max_proposals=4,
                                                max_research=0)).run(
                spec.contract,
                QwenFunctionBodyAdapter(model.generate_text, spec.commonjs_export,
                                        spec.commonjs_parameters),
                public_evaluator, NoWebResearch(),
            )
            body_seconds = round(time.monotonic() - start, 3)
        records.append((spec, solo, assisted, assisted_seconds, direct,
                        direct_seconds, scaffold, scaffold_seconds,
                        body_track, body_seconds))

    # The private oracle runs ONLY once all solo and controller generation is over.
    rows = []
    for (spec, solo, assisted, assisted_seconds, direct, direct_seconds,
         scaffold, scaffold_seconds, body_track, body_seconds) in records:
        glue = f"\nmodule.exports = {{ {spec.commonjs_export} }};\n" if spec.commonjs_export else ""
        path = spec.contract.required_files[0]
        scaffold_file = scaffold.selected_files.get(path, "") if scaffold else ""
        direct_file = direct.selected_files.get(path, "")
        rows.append({
            "task_id": spec.contract.task_id,
            "public_spec_hash": sha256(spec.public.test_source.encode()).hexdigest(),
            "private_spec_hash": sha256(spec.private.test_source.encode()).hexdigest(),
            "solo": {"valid": solo["proposal_valid"],
                     "file_paths": sorted(solo["files"] or {}),
                     "public_pass": solo["public_pass"],
                     "private_pass": private_score(spec, solo["files"]),
                     "seconds": solo["seconds"], "error": solo["error"]},
            "controller": {"status": assisted.status,
                           "public_pass": assisted.status == "public_checks_passed",
                           "private_pass": private_score(spec, assisted.selected_files),
                           "seconds": assisted_seconds,
                           "proposals": assisted.proposals,
                           "evaluations": assisted.evaluations,
                           "invalid_proposals": assisted.invalid_proposals,
                           "research_calls": assisted.research_calls,
                           "messages": assisted.messages,
                           "proposal_trace": assisted.proposal_trace},
            "single_file_controller": {
                "status": direct.status,
                "public_pass": direct.status == "public_checks_passed",
                "private_pass": private_score(spec, direct.selected_files),
                "seconds": direct_seconds,
                "proposals": direct.proposals,
                "evaluations": direct.evaluations,
                "invalid_proposals": direct.invalid_proposals,
                "research_calls": direct.research_calls,
                "messages": direct.messages,
                "proposal_trace": direct.proposal_trace,
            },
            "commonjs_scaffold_controller": None if scaffold is None else {
                "status": scaffold.status,
                "public_pass": scaffold.status == "public_checks_passed",
                "private_pass": private_score(spec, scaffold.selected_files),
                "seconds": scaffold_seconds,
                "proposals": scaffold.proposals,
                "evaluations": scaffold.evaluations,
                "invalid_proposals": scaffold.invalid_proposals,
                "mechanical_export_only": glue.strip(),
                "model_source_same_as_direct_first_candidate": (
                    scaffold_file.endswith(glue) and
                    scaffold_file[:-len(glue)].strip() == direct_file.strip()
                ),
                "proposal_trace": scaffold.proposal_trace,
            },
            "function_body_controller": None if body_track is None else {
                "status": body_track.status,
                "public_pass": body_track.status == "public_checks_passed",
                "private_pass": private_score(spec, body_track.selected_files),
                "seconds": body_seconds,
                "proposals": body_track.proposals,
                "evaluations": body_track.evaluations,
                "invalid_proposals": body_track.invalid_proposals,
                "mechanical_function_declaration": (
                    f"function {spec.commonjs_export}({', '.join(spec.commonjs_parameters)}) {{ ... }}"
                ),
                "mechanical_module_export": glue.strip(),
                "proposal_trace": body_track.proposal_trace,
            },
        })
    report = {
        "description": "Exploratory two-task frozen Qwen0.5B protocol smoke; NOT fullstack generalization",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "model": MODEL_ID, "weights_updated": False, "training": False,
        "teacher_repairs": 0, "docs_search_enabled": False,
        "protocols": ["json_solo", "json_controller", "single_file_controller",
                       "commonjs_scaffold_controller_js_only",
                       "function_body_controller_js_only"],
        "host_cpu_threads": 2, "max_new_tokens": max_new_tokens,
        "loading_seconds": loading_s,
        "peak_host_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        "tasks": rows,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("experiments/adaptive/pilot_report.json"))
    parser.add_argument("--max-new-tokens", type=int, default=400)
    args = parser.parse_args()
    report = run(args.output, args.max_new_tokens)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
