"""Session 040 Phase-5 application generation driver (GearHut).

Applies the validated Track-B contract-first recipe (prompts.py, reused
verbatim) to a NEW domain frozen in APP_SPEC.json BEFORE any generation.
Each piece is generated greedily with a deterministic seed, extracted with
L-TRIM, gated inside the restricted tier, and given <= 2 execution-feedback
repair attempts. Every prompt, raw generation, usage record, candidate and
verdict is archived to experiments/z040-autonomous-fullstack/app/evidence/.

Gates (frozen in APP_SPEC.json generation_protocol.gates):
  schema          restricted-tier schema_runner with the app task spec
  state-invariant restricted-tier s039 runner with the app case table
  others          restricted-tier parse gate (esbuild transform; behavior is
                  verified by the Phase-6 app-level test suite)

No training, no weight edits; the holdout stays sealed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.s040 import exec as s040exec  # noqa: E402
from archagent.s040 import prompts, schema_probes  # noqa: E402
from archagent.s040.experiments import extract_construct  # noqa: E402

APP_DIR = ROOT / "experiments/z040-autonomous-fullstack/app"
SPEC_PATH = APP_DIR / "APP_SPEC.json"
EVIDENCE_DIR = APP_DIR / "evidence"
GENERATED_DIR = APP_DIR / "generated"

TRUSTED_SCAFFOLD_PRISMA = """datasource db {
  provider = "sqlite"
  url      = env("DATABASE_URL")
}

generator client {
  provider = "prisma-client-js"
}
"""

MAX_REPAIRS = 2

# The frozen app entry, in the exact shape prompts.py expects of a v2 task.
APP_ENTRY_BASE = {
    "domain": "gearhut",
    "entities": {"parent": "GearLocker", "child": "GearItem",
                 "foreign_key": "lockerId", "foreign_key_mode": "required"},
    "fields": {"label": "label", "amount": "usageHours",
               "min_inclusive": 0, "max_inclusive": 2000},
    "workflow": ["stashed", "inspected", "retired"],
    "user_story": "Manage GearItem records linked to GearLocker in the GearHut maintenance service.",
}

PIECES = ("schema-relationship", "state-invariant", "api-get-filter",
          "api-post-validation", "react-interaction", "fullstack-integration")

FILE_FOR_SKILL = {
    "schema-relationship": "output.prisma",
    "state-invariant": "output.ts",
    "api-get-filter": "output.ts",
    "api-post-validation": "output.ts",
    "react-interaction": "output.tsx",
    "fullstack-integration": "output.tsx",
}

SPECS = json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def app_entry(skill: str) -> dict:
    entry = dict(APP_ENTRY_BASE)
    entry["skill"] = skill
    entry["id"] = f"gearhut:{skill}"
    if skill == "schema-relationship":
        entry["requirements"] = SPECS["schema_contract"]["requirements"]
    elif skill == "state-invariant":
        entry["requirements"] = SPECS["invariant_contract"]["requirements"]
    elif skill == "api-get-filter":
        entry["requirements"] = SPECS["route_contract"]["get_requirements"]
    elif skill == "api-post-validation":
        entry["requirements"] = SPECS["route_contract"]["post_requirements"]
    elif skill == "react-interaction":
        entry["requirements"] = SPECS["ui_contract"]["react_requirements"]
    elif skill == "fullstack-integration":
        entry["requirements"] = SPECS["ui_contract"]["integration_requirements"]
    else:
        raise ValueError(skill)
    return entry


def anchor_for(skill: str) -> str:
    if skill == "fullstack-integration":
        # app-specific: the manager receives the lockers prop (frozen spec)
        return ("import { useEffect, useState } from 'react';\n\n"
                "export default function GearItemManager({ lockers }) {\n")
    return prompts.anchor_for(app_entry(skill))


def forced_anchor(skill: str) -> str:
    base = anchor_for(skill)
    if skill == "schema-relationship":
        return base + "  id String @id @default(cuid())\n"
    return base + "  const "


# ------------------------------------------------------------------ gates

def _stage_candidate(candidate_text: str, filename: str, stage_root: Path) -> Path:
    cand = stage_root / "candidate"
    if cand.exists():
        shutil.rmtree(cand)
    cand.mkdir(parents=True)
    (cand / filename).write_text(candidate_text, encoding="utf-8")
    return cand


def gate_schema(repo: Path, models_text: str, backend: str) -> dict:
    """Restricted-tier schema probes; trusted scaffold prepended before staging."""
    spec = {
        "task_id": "gearhut:schema-relationship",
        "skill": "schema-relationship",
        "entities": {
            "parent": APP_ENTRY_BASE["entities"]["parent"],
            "child": APP_ENTRY_BASE["entities"]["child"],
            "foreign_key": APP_ENTRY_BASE["entities"]["foreign_key"],
            "foreign_key_optional": False,
        },
        "fields": dict(APP_ENTRY_BASE["fields"]),
        "workflow": list(APP_ENTRY_BASE["workflow"]),
        "requirements": SPECS["schema_contract"]["requirements"],
        "probes": SPECS["schema_contract"]["probe_plan"],
    }
    with tempfile.TemporaryDirectory(prefix="s040-app-schema-") as temp:
        harness = Path(temp)
        shutil.copyfile(Path(__file__).resolve().parent / "harness" / "schema_runner.mjs",
                        harness / "schema_runner.mjs")
        (harness / "task.json").write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
        (harness / "probe.mjs").write_text(schema_probes.probe_mjs(), encoding="utf-8")
        for staged in sorted(harness.iterdir()):
            os.chmod(staged, 0o644)
        os.chmod(harness, 0o755)
        staged_text = TRUSTED_SCAFFOLD_PRISMA + "\n" + models_text
        with tempfile.TemporaryDirectory(prefix="s040-app-cand-") as ctemp:
            cand = _stage_candidate(staged_text, "output.prisma", Path(ctemp))
            result = s040exec.run(cand, harness, s040exec.DEFAULT_EVAL_DEPS,
                                  runner="schema_runner.mjs", tier="schema",
                                  backend=backend)
    return {"task_id": spec["task_id"], "gate": "schema-probes",
            "probe_count": len(spec["probes"]), "model_weight_change": False, **result}


def gate_invariant(repo: Path, candidate_text: str, backend: str) -> dict:
    """Restricted-tier case-table evaluation via the trusted s039 runner."""
    fixture = {
        "task_id": "gearhut:state-invariant",
        "export_name": "canAdvanceGearItem",
        "cases": SPECS["invariant_contract"]["cases"],
    }
    from archagent.s039 import invariant_eval  # trusted runner source only
    with tempfile.TemporaryDirectory(prefix="s040-app-inv-") as temp:
        harness = Path(temp)
        shutil.copyfile(Path(invariant_eval.__file__).parent / "harness" / "runner.mjs",
                        harness / "runner.mjs")
        (harness / "task.json").write_text(json.dumps(fixture, sort_keys=True), encoding="utf-8")
        for staged in sorted(harness.iterdir()):
            os.chmod(staged, 0o644)
        os.chmod(harness, 0o755)
        with tempfile.TemporaryDirectory(prefix="s040-app-cand-") as ctemp:
            cand = _stage_candidate(candidate_text, "output.ts", Path(ctemp))
            result = s040exec.run(cand, harness, s040exec.DEFAULT_EVAL_DEPS,
                                  runner="runner.mjs", tier="invariant",
                                  backend=backend)
    return {"task_id": fixture["task_id"], "gate": "invariant-cases",
            "case_count": len(fixture["cases"]), "model_weight_change": False, **result}


def gate_parse(repo: Path, candidate_text: str, skill: str, backend: str) -> dict:
    """Restricted-tier syntax gate (esbuild transform; candidate never runs)."""
    filename = FILE_FOR_SKILL[skill]
    loader = "tsx" if filename.endswith(".tsx") else "ts"
    spec = {"candidate_file": filename, "loader": loader}
    with tempfile.TemporaryDirectory(prefix="s040-app-parse-") as temp:
        harness = Path(temp)
        shutil.copyfile(Path(__file__).resolve().parent / "harness" / "parse_gate.mjs",
                        harness / "parse_gate.mjs")
        (harness / "task.json").write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
        for staged in sorted(harness.iterdir()):
            os.chmod(staged, 0o644)
        os.chmod(harness, 0o755)
        with tempfile.TemporaryDirectory(prefix="s040-app-cand-") as ctemp:
            cand = _stage_candidate(candidate_text, filename, Path(ctemp))
            result = s040exec.run(cand, harness, s040exec.DEFAULT_EVAL_DEPS,
                                  runner="parse_gate.mjs", tier="invariant",
                                  backend=backend)
    return {"task_id": f"gearhut:{skill}", "gate": "parse",
            "model_weight_change": False, **result}


def run_gate(repo: Path, skill: str, candidate_text: str, backend: str) -> dict:
    if skill == "schema-relationship":
        return gate_schema(repo, candidate_text, backend)
    if skill == "state-invariant":
        return gate_invariant(repo, candidate_text, backend)
    return gate_parse(repo, candidate_text, skill, backend)


def _failing_checks(verdict: dict) -> list[dict]:
    checks = verdict.get("checks")
    if not isinstance(checks, list):
        return []
    return [c for c in checks if isinstance(c, dict) and c.get("passed") is not True]


# ------------------------------------------------------------------ driver

def run_piece(repo: Path, model, skill: str, backend: str) -> dict:
    entry = app_entry(skill)
    t_start = time.time()
    record = {
        "task_id": entry["id"], "skill": skill, "domain": "gearhut", "split": "app",
        "decoding": "greedy", "attempts": [], "repairs_used": 0,
        "spec_sha256": sha256_text(SPEC_PATH.read_text(encoding="utf-8")),
    }

    def attempt(prompt: str, seed: int, max_tokens: int, note: str,
                anchor: str) -> dict:
        raw, usage = model.generate(prompt, max_tokens=max_tokens, seed=seed, stochastic=False)
        candidate, balanced = extract_construct(anchor, raw, skill)
        att = {"note": note, "prompt_sha256": sha256_text(prompt), "prompt": prompt,
               "raw_generation": raw, "usage": usage, "anchor": anchor,
               "candidate": candidate, "brace_balanced": balanced,
               "near_empty": len(candidate.strip()) < 100}
        record["attempts"].append(att)
        return att

    # The Track-B template is reused verbatim except for the anchor override
    # frozen in the app spec (fullstack-integration receives a lockers prop).
    base_anchor = prompts.anchor_for(entry)
    app_anchor = anchor_for(skill)
    prompt = prompts.build_track_b(entry)
    if app_anchor != base_anchor:
        prompt = prompt.replace(base_anchor, app_anchor)
    seed = prompts.seed_for("APP", entry["id"])
    att = attempt(prompt, seed, prompts.max_tokens_for(entry), "single-shot", app_anchor)
    if att["near_empty"]:
        forced = forced_anchor(skill)
        retry_prompt = prompt.replace(app_anchor, forced)
        att = attempt(retry_prompt, seed + 1, prompts.max_tokens_for(entry),
                      "forced-continuation-retry", forced)
    candidate = att["candidate"]
    verdict = run_gate(repo, skill, candidate, backend)
    record.setdefault("gate_verdicts", []).append(
        {"attempt": "initial", "verdict": verdict, "candidate_sha256": sha256_text(candidate)})

    repairs = 0
    while verdict.get("passed") is not True and repairs < MAX_REPAIRS:
        repairs += 1
        repair_prompt = prompts.build_track_c_repair(entry, repairs, _failing_checks(verdict))
        repair_prompt = repair_prompt.replace(base_anchor, app_anchor)
        att = attempt(repair_prompt, prompts.seed_for("APPR", entry["id"]) + repairs,
                      prompts.max_tokens_for(entry), f"repair-{repairs}", app_anchor)
        candidate = att["candidate"]
        verdict = run_gate(repo, skill, candidate, backend)
        record["gate_verdicts"].append(
            {"attempt": f"repair-{repairs}", "verdict": verdict,
             "candidate_sha256": sha256_text(candidate)})

    record["repairs_used"] = repairs
    record["verdict"] = verdict
    record["candidate_final"] = candidate
    record["candidate_final_sha256"] = sha256_text(candidate)
    record["attribution"] = ("QWEN_GENERATED" if verdict.get("passed") is True and repairs == 0
                             else "QWEN-REPAIRED" if verdict.get("passed") is True
                             else "TEACHER-CORRECTED-pending")
    record["wall_seconds"] = round(time.time() - t_start, 1)
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=["auto", "docker", "unshare"], default="auto")
    parser.add_argument("--pieces", nargs="*", default=list(PIECES))
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    repo = ROOT
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    from archagent.model import FrozenModel
    model = FrozenModel(threads=2)
    completed = 0
    for skill in args.pieces:
        out_path = EVIDENCE_DIR / f"gearhut__{skill}.json"
        if out_path.is_file():
            print(f"SKIP {skill}: evidence exists")
            continue
        if args.limit and completed >= args.limit:
            continue
        record = run_piece(repo, model, skill, args.backend)
        out_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        (GENERATED_DIR / FILE_FOR_SKILL[skill]).write_text(
            record["candidate_final"], encoding="utf-8")
        completed += 1
        print(f"APP {skill}: {record['verdict'].get('status')} "
              f"repairs={record['repairs_used']} [{record['wall_seconds']}s]")
    print(json.dumps(model.usage()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
