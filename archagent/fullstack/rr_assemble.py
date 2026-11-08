"""SESSION 036 — RoomReserve assembly verification (post-track).

With the model UNLOADED and the dev server UP: run tsc gate, reseed,
then the frozen suites (apitest pre, restart, apitest post-restart,
uitest, heldout) against the current workspace state.  Emits one JSON
report.  Used for Track A/B/C final states — identical scoring for all.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import devserver  # noqa: E402

EXP = ROOT / "experiments" / "z036-roomreserve"
WS = Path("/home/z/my-project")
NODE_ENV = dict(
    PATH="/home/z/.npm-global/bin:/usr/local/bin:/usr/bin:/bin",
    NODE_PATH="/home/z/my-project/node_modules",
    BASE="http://127.0.0.1:3000",
)


def run(cmd: list[str], cwd=WS, timeout: int = 480) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True,
                          text=True, timeout=timeout, env=NODE_ENV)


def suite(script: str) -> dict:
    r = run(["node", str(EXP / script)])
    out = r.stdout
    m = re.search(r"(?:API|UI|HELD-OUT): (\d+)/(\d+) checks passed", out)
    page_err = re.search(r"pageErrors: (\d+)", out)
    return {
        "exit": r.returncode,
        "passed": int(m.group(1)) if m else 0,
        "total": int(m.group(2)) if m else 0,
        "page_errors": int(page_err.group(1)) if page_err else None,
        "tail": out[-400:] if r.returncode else "",
    }


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    report: dict = {"label": label}

    # 1. tsc gate
    r = run(["node_modules/.bin/tsc", "--noEmit", "-p",
             "tsconfig.gate.json"], timeout=300)
    errs = [l for l in (r.stdout + r.stderr).splitlines()
            if "error TS" in l]
    report["tsc_errors"] = len(errs)
    report["tsc_first"] = errs[:3]

    # 2. dev up + reseed
    devserver.restart_dev()
    rr = run(["bun", "run", "db:reseed-roomreserve"], timeout=120)
    report["reseed"] = rr.returncode == 0

    # 3. apitest pre
    report["apitest_pre"] = suite("apitest.mjs")
    # note: apitest itself reseeds at start; --phase pre

    # 4. restart + persistence
    devserver.restart_dev()
    r = run(["node", str(EXP / "apitest.mjs"), "--phase", "post-restart"])
    m = re.search(r"API: (\d+)/(\d+) checks passed", r.stdout)
    report["apitest_post"] = {
        "passed": int(m.group(1)) if m else 0,
        "total": int(m.group(2)) if m else 0,
        "tail": r.stdout[-300:] if r.returncode else "",
    }

    # 5. uitest
    report["uitest"] = suite("uitest.mjs")

    # 6. held-out
    report["heldout"] = suite("heldout.mjs")

    out = EXP / "reports" / f"assembly-{label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items()
                      if k != "tsc_first"}, indent=1)[:1200])
    print("report ->", out)


if __name__ == "__main__":
    main()
