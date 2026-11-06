"""Driver: run the full TaskFlow development sequence (Stages B-F).

Sequential single-model process (the sandbox fits exactly one model in
RAM).  Stages:
  A  (run separately)  architectural plan
  B/C store  -> D api (with store + logic)  -> E ui, css
Each stage checkpoints into experiments/zai-taskflow/state.json, so the
driver can be resumed after interruption.

Budgets are explicit and bounded (mission section 15).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXP = ROOT / "experiments" / "zai-taskflow"

ORDER = ["logic", "store", "api", "ui", "css"]
WALL = {"logic": 1500, "store": 2700, "api": 2700, "ui": 3300, "css": 1200}
MAX_ROUNDS = {"logic": 6, "store": 8, "api": 8, "ui": 8, "css": 5}


def run_stage(role: str, docs: bool) -> dict:
    cmd = [sys.executable, "-m", "archagent.runner", "develop",
           "--role", role, "--wall", str(WALL[role]),
           "--max-rounds", str(MAX_ROUNDS[role])]
    if docs:
        cmd.append("--docs")
    env = dict(os.environ)
    env.setdefault("ARCHAGENT_MODEL_DIR", "/home/z/models/qwen25-coder-0.5b")
    print(f"=== develop {role} (docs={docs}) ===", flush=True)
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=ROOT, env=env)
    return {"role": role, "rc": proc.returncode,
            "wall": round(time.time() - t0, 1)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", action="store_true", default=True)
    ap.add_argument("--no-docs", dest="docs", action="store_false")
    ap.add_argument("--only", help="comma-separated roles to run")
    args = ap.parse_args()

    order = args.only.split(",") if args.only else ORDER
    state_path = EXP / "state.json"
    done: set[str] = set()
    if state_path.exists():
        done = set(json.loads(state_path.read_text()).get("selected", {}))

    results = []
    for role in order:
        if role in done:
            print(f"=== {role} already selected; skipping (resume) ===")
            continue
        results.append(run_stage(role, args.docs))
        if results[-1]["rc"] != 0:
            print(f"stage {role} failed rc={results[-1]['rc']}; stopping")
            break
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
