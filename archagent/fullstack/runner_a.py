"""Track A — unassisted monolithic baseline (Session 035).

The frozen model receives the whole StockPilot spec in ONE prompt and
must produce the complete application (schema + two API route files +
the page).  No staging, no feedback.  Up to 7 candidates (greedy
first, then sampled; frozen seed list).  Each candidate is installed
MECHANICALLY (marker-based file extraction only), gated, and tested
with the frozen acceptance suites.  Nothing the harness does here
adds or fixes application bytes.

All raw completions are archived with full prompt + seed + token
counts + sha256 under experiments/zai-fullstack/generations/.
"""
from __future__ import annotations

import json
import re
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import install  # noqa: E402
from archagent.fullstack.prompts import track_a_prompt  # noqa: E402
from archagent.model import FrozenModel  # noqa: E402

EXP = ROOT / "experiments/zai-fullstack"
GEN = EXP / "generations"
REPORTS = EXP / "reports"
NODE_ENV = dict(
    PATH="/home/z/.npm-global/bin:/usr/local/bin:/usr/bin:/bin",
    NODE_PATH="/home/z/.npm-global/lib/node_modules",
    BASE="http://127.0.0.1:3000",
)
SEEDS = [0, 1013, 2026, 3039, 4052, 5165, 6278]  # frozen
MAX_TOKENS = 1200


def spec_sections() -> str:
    """§1–§3 of the frozen SPEC.md, verbatim."""
    text = (EXP / "SPEC.md").read_text()
    m = re.search(r"(## 1\. Data model.*?)\n## 4\.", text, re.DOTALL)
    if not m:
        raise RuntimeError("cannot extract SPEC sections 1-3")
    return m.group(1).strip()


def wait_dev(path: str = "/", want: int = 200, timeout: float = 90) -> tuple[bool, str]:
    import urllib.request
    import urllib.error
    t0 = time.time()
    last = ""
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:3000{path}",
                                        timeout=20) as r:
                last = f"HTTP {r.status}"
                if r.status == want:
                    return True, last
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code == want:
                return True, last
        except Exception as e:  # noqa: BLE001
            last = str(e)[:120]
        time.sleep(2.5)
    return False, last


def run_suite(script: str, timeout: int = 420) -> dict:
    r = subprocess.run(["node", str(EXP / script)],
                       capture_output=True, text=True, timeout=timeout,
                       env=NODE_ENV, cwd=str(EXP))
    tail = (r.stdout + r.stderr).strip().splitlines()
    return {"exit": r.returncode, "tail": tail[-6:]}


def main() -> None:
    GEN.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)

    prompt, anchor = track_a_prompt(spec_sections())
    print(f"prompt: {len(prompt)} chars; anchor: {anchor.splitlines()[0]!r}")

    install.backup_workspace()
    results = []
    model = FrozenModel(threads=2)
    t_start = time.time()

    for idx, seed in enumerate(SEEDS):
        stochastic = idx != 0
        cand_id = f"trackA_{idx + 1:03d}"
        print(f"\n=== candidate {idx + 1}/7 seed={seed} "
              f"({'greedy' if not stochastic else 'sampled'}) ===")
        text, usage = model.generate(prompt, max_tokens=MAX_TOKENS,
                                     seed=seed, stochastic=stochastic)
        files = install.extract_files(text)
        rec = dict(
            id=cand_id, seed=seed, stochastic=stochastic, usage=usage,
            completion_chars=len(text),
            completion_lines=len(text.splitlines()),
            markers_found=sorted(files.keys()),
            first_line=text.splitlines()[0] if text.splitlines() else "",
            ended_cleanly=text.rstrip().endswith("}") or "===" in text[-80:],
        )
        (GEN / f"{cand_id}.json").write_text(json.dumps(dict(
            track="A", id=cand_id, prompt=prompt, anchor=anchor,
            completion=text, usage=usage, seed=seed,
            stochastic=stochastic), ensure_ascii=False, indent=1))

        if files:
            install.restore_workspace()
            written = install.install_files(files)
            rec["installed"] = written
            if any("schema.prisma" in w for w in written):
                block = files[[k for k in files if "schema.prisma" in k][0]]
                if "model InventoryItem" in block:
                    install.merge_schema_block(block)
                    ok, out = install.db_push()
                    rec["db_push"] = {"ok": ok, "tail": out[-200:]}
            # gates (scoped to src/ — pre-existing repo errors elsewhere
            # are excluded; tsconfig.gate.json is TRUSTED-SCAFFOLD)
            time.sleep(2)
            lint = install.run_cmd(
                ["node_modules/.bin/eslint", "src"], install.APP,
                timeout=300)
            rec["lint_exit"] = lint["exit"]
            tsc = install.run_cmd(
                ["node_modules/.bin/tsc", "--noEmit",
                 "-p", "tsconfig.gate.json"],
                install.APP, timeout=300)
            rec["tsc_exit"] = tsc["exit"]
            rec["tsc_tail"] = tsc["out"][-400:]
            page_ok, page_state = wait_dev("/")
            rec["page_load"] = page_state
            api = wait_dev("/api/items", want=200, timeout=45)
            rec["api_items"] = api[1]
            if page_ok and api[0]:
                api_res = run_suite("apitest.mjs")
                rec["apitest"] = api_res
                ui_res = run_suite("uitest.mjs", timeout=600)
                rec["uitest"] = ui_res
        else:
            rec["installed"] = []
        results.append(rec)
        print(json.dumps({k: rec[k] for k in
                          ('id', 'completion_lines', 'markers_found',
                           'installed', 'lint_exit', 'tsc_exit',
                           'page_load', 'api_items') if k in rec},
                         indent=1))
        # stop early if a candidate fully passes (frozen rule)
        if rec.get("apitest", {}).get("exit") == 0 and \
           rec.get("uitest", {}).get("exit") == 0:
            print("Track A candidate PASSED everything — stopping early")
            break

    install.restore_workspace()
    usage = model.usage()
    ru = resource.getrusage(resource.RUSAGE_SELF)
    report = dict(
        track="A", wall_seconds=round(time.time() - t_start, 1),
        model_usage=usage,
        cpu_seconds=round(ru.ru_utime + ru.ru_stime, 1),
        peak_rss_mb=round(ru.ru_maxrss / 1024, 1),
        candidates=results,
    )
    (REPORTS / "trackA.json").write_text(json.dumps(report, indent=1))
    print("\n==== Track A summary ====")
    print(json.dumps({k: report[k] for k in
                      ('wall_seconds', 'model_usage', 'cpu_seconds',
                       'peak_rss_mb')}, indent=1))
    for r in results:
        print(f"- {r['id']}: {r['completion_lines']} lines, "
              f"files={r['markers_found']}, installed={r.get('installed')}")


if __name__ == "__main__":
    main()
