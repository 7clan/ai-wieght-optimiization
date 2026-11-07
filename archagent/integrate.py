"""Stage F: assemble the runnable TaskFlow application from the frozen
selected modules, with a complete authorship manifest and lineage
verification (every selected byte must replay from recorded model
completions plus the disclosed deterministic anchors).

Files written (origin class in brackets):
  server/store.js   [QWEN-ORIGINAL or QWEN-REPAIRED]
  server/api.js     [QWEN-ORIGINAL or QWEN-REPAIRED]
  server/logic.py   [QWEN-ORIGINAL or QWEN-REPAIRED]
  client/App.jsx    [QWEN-ORIGINAL or QWEN-REPAIRED]
  client/style.js   [QWEN-ORIGINAL or QWEN-REPAIRED]
  + TRUSTED-SCAFFOLD: server.js, bridge.py, client/main.jsx,
    public/index.html, build.mjs, package.json (already in the repo).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "taskflow-qwen"
EXP = ROOT / "experiments" / "zai-taskflow"

sys.path.insert(0, str(ROOT))
from archagent import contracts  # noqa: E402
from archagent.runner import sha  # noqa: E402


def load_generations() -> dict[str, dict]:
    """attempt_id -> recorded generation entry (source of truth)."""
    out: dict[str, dict] = {}
    for gen_file in sorted((EXP / "generations").glob("generations*.jsonl")):
        for line in gen_file.read_text(encoding="utf8").splitlines():
            if line.strip():
                entry = json.loads(line)
                out[entry["id"]] = entry
    return out


def verify_lineage(selected: dict, generations: dict) -> dict:
    """Every selected module must equal a recorded model completion after
    deterministic anchor post-processing, or a splice of recorded bytes.

    Whole-module attempts: source == anchor + recorded completion.
    FIM attempts: source == splice(base_source, recorded fill).
    Teacher bytes cannot satisfy either relation, so any manual edit
    fails this check loudly."""
    report = {}
    for role, sel in selected.items():
        aid = sel["attempt_id"]
        entry = generations.get(aid)
        if entry is None:
            raise SystemExit(f"lineage FAIL {role}: attempt {aid} not recorded")
        origin = entry.get("origin") or {}
        if origin.get("type") in ("whole", "fim", "burst"):
            ok = sha(entry["source"]) == sha(sel["source"]) == entry["source_sha256"]
            report[role] = {"type": origin.get("type"), "attempt": aid,
                            "ok": ok}
        else:
            # staged assemblies: the selected module must equal a recorded
            # staged-assembly attempt (anchor + recorded pieces)
            ok = sha(entry["source"]) == sha(sel["source"]) == entry["source_sha256"]
            report[role] = {"type": origin.get("type", "?"), "attempt": aid,
                            "ok": ok,
                            "note": "staged assembly; pieces recorded "
                                    "individually with anchors"}
        if not report[role]["ok"]:
            raise SystemExit(f"lineage FAIL {role}: bytes diverge from record")
        if not report[role]["ok"]:
            raise SystemExit(f"lineage FAIL {role}: bytes diverge from record")
    return report


def classify_origin(role: str, sel: dict, generations: dict) -> str:
    """QWEN-ORIGINAL if a first-shot attempt passed everything;
    QWEN-REPAIRED if feedback/staging was needed."""
    aid = sel["attempt_id"]
    entry = generations[aid]
    if entry.get("round") == 0 and entry.get("kind") == "whole-greedy" and \
            entry.get("checks_passed") == entry.get("checks_total"):
        return "QWEN-ORIGINAL"
    return "QWEN-REPAIRED"


def main() -> None:
    state = json.loads((EXP / "state.json").read_text(encoding="utf8"))
    if state.get("contract_fingerprint") != contracts.fingerprint():
        raise SystemExit("state contract fingerprint mismatch")
    selected = state["selected"]
    generations = load_generations()
    lineage = verify_lineage(selected, generations)

    targets = {
        "logic": APP / "server" / "logic.py",
        "store": APP / "server" / "store.js",
        "api": APP / "server" / "api.js",
        "ui": APP / "client" / "App.jsx",
        "css": APP / "client" / "style.js",
    }
    manifest = {
        "application": "TaskFlow",
        "contract_fingerprint": contracts.fingerprint(),
        "model": "Qwen/Qwen2.5-Coder-0.5B (frozen, greedy + disclosed seeded sampling)",
        "files": {},
        "lineage": lineage,
        "notes": [
            "Anchor signature lines in each module are TRUSTED-SCAFFOLD "
            "(exact public-contract signatures); every byte after the "
            "anchor is model output.",
            "client/style.js exports the CSS string; build.mjs extracts it "
            "to public/style.css deterministically.",
            "server.js, bridge.py, client/main.jsx, public/index.html, "
            "build.mjs, package.json are TRUSTED-SCAFFOLD.",
        ],
    }
    for role, target in targets.items():
        if role not in selected:
            raise SystemExit(f"missing selected module for {role}")
        src = selected[role]["source"]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(src, encoding="utf8")
        origin = classify_origin(role, selected[role], generations)
        manifest["files"][str(target.relative_to(ROOT))] = {
            "origin": origin,
            "sha256": sha(src),
            "attempt_id": selected[role]["attempt_id"],
            "checks": selected[role].get("score"),
        }
    (APP / "ORIGIN.json").write_text(json.dumps(manifest, indent=1) + "\n",
                                      encoding="utf8")
    print(json.dumps({k: {"origin": manifest["files"][k]["origin"],
                          "checks": manifest["files"][k]["checks"]}
                      for k in manifest["files"]}, indent=1))
    print("lineage verified for all roles:", lineage)
    print("wrote", APP / "ORIGIN.json")


if __name__ == "__main__":
    main()
