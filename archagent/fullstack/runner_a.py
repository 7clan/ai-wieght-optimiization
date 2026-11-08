"""Track A — unassisted monolithic baseline (Session 035).

The frozen model receives the whole StockPilot spec in ONE prompt and
must produce the complete application (schema + two API route files +
the page).  No staging, no feedback.  Up to 7 candidates (greedy
first, then sampled; frozen seed list).  Each candidate is installed
MECHANICALLY (marker-based file extraction only), gated, and tested
with the frozen acceptance suites.  Nothing the harness does here
adds or fixes application bytes.

Two-phase design (RAM constraint): phase `gen` stops the dev server,
loads the model once, generates all candidates, exits (freeing RAM);
phase `test` restarts the dev server and installs/gates/tests each
candidate in order.

All raw completions are archived with full prompt + seed + token
counts + sha256 under experiments/zai-fullstack/generations/.
"""
from __future__ import annotations

import hashlib
import json
import re
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.fullstack import devserver, install  # noqa: E402
from archagent.fullstack.prompts import track_a_prompt  # noqa: E402

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


def run_suite(script: str, timeout: int = 480) -> dict:
    try:
        r = subprocess.run(["node", str(EXP / script)],
                           capture_output=True, text=True, timeout=timeout,
                           env=NODE_ENV, cwd=str(EXP))
        tail = (r.stdout + r.stderr).strip().splitlines()
        return {"exit": r.returncode, "tail": tail[-8:]}
    except subprocess.TimeoutExpired:
        return {"exit": 124, "tail": ["TIMEOUT"]}


def phase_gen() -> None:
    from archagent.model import FrozenModel
    GEN.mkdir(parents=True, exist_ok=True)
    prompt, anchor = track_a_prompt(spec_sections())
    print(f"prompt: {len(prompt)} chars; anchor: {anchor.splitlines()[0]!r}")
    devserver.stop_dev()
    time.sleep(2)
    model = FrozenModel(threads=2)
    t_start = time.time()
    meta = []
    for idx, seed in enumerate(SEEDS):
        stochastic = idx != 0
        cand_id = f"trackA_{idx + 1:03d}"
        print(f"\n=== candidate {idx + 1}/7 seed={seed} "
              f"({'greedy' if not stochastic else 'sampled'}) ===", flush=True)
        text, usage = model.generate(prompt, max_tokens=MAX_TOKENS,
                                     seed=seed, stochastic=stochastic)
        files = install.extract_files(text)
        rec = dict(id=cand_id, seed=seed, stochastic=stochastic, usage=usage,
                   completion_chars=len(text),
                   completion_lines=len(text.splitlines()),
                   markers_found=sorted(files.keys()),
                   first_line=text.splitlines()[0] if text.splitlines() else "",
                   sha256=hashlib.sha256(text.encode()).hexdigest()[:16])
        (GEN / f"{cand_id}.json").write_text(json.dumps(dict(
            track="A", id=cand_id, prompt=prompt, anchor=anchor,
            completion=text, usage=usage, seed=seed,
            stochastic=stochastic), ensure_ascii=False, indent=1))
        meta.append(rec)
        print(json.dumps(rec, indent=1), flush=True)
    ru = resource.getrusage(resource.RUSAGE_SELF)
    out = dict(track="A-gen", wall_seconds=round(time.time() - t_start, 1),
               model_usage=model.usage(),
               cpu_seconds=round(ru.ru_utime + ru.ru_stime, 1),
               peak_rss_mb=round(ru.ru_maxrss / 1024, 1),
               candidates=meta)
    (REPORTS / "trackA_gen.json").write_text(json.dumps(out, indent=1))
    print("\nGEN PHASE DONE", json.dumps(
        {k: out[k] for k in ("wall_seconds", "model_usage", "cpu_seconds",
                             "peak_rss_mb")}, indent=1))
    devserver.start_dev()  # bring the preview back up


def phase_test() -> None:
    devserver.start_dev()
    install.backup_workspace()
    gen_meta = json.loads((REPORTS / "trackA_gen.json").read_text())
    results = []
    t_start = time.time()
    for rec in gen_meta["candidates"]:
        cand_id = rec["id"]
        raw = json.loads((GEN / f"{cand_id}.json").read_text())
        files = install.extract_files(raw["completion"])
        tr = dict(id=cand_id, seed=rec["seed"], usage=rec["usage"],
                  completion_lines=rec["completion_lines"],
                  markers_found=rec["markers_found"],
                  installed=[], gates={})
        print(f"\n=== testing {cand_id}: {sorted(files)} ===", flush=True)
        if files:
            install.restore_workspace()
            written = install.install_files(files)
            tr["installed"] = written
            schema_written = [w for w in written if "schema.prisma" in w]
            if schema_written:
                block = files[schema_written[0]]
                if "model InventoryItem" in block:
                    install.merge_schema_block(block)
                    ok, out = install.db_push()
                    tr["gates"]["db_push"] = {"ok": ok, "tail": out[-200:]}
            time.sleep(2)
            lint = install.run_cmd(["node_modules/.bin/eslint", "src"],
                                   install.APP, timeout=300)
            tr["gates"]["lint_exit"] = lint["exit"]
            tr["gates"]["lint_tail"] = lint["out"][-300:]
            tsc = install.run_cmd(
                ["node_modules/.bin/tsc", "--noEmit", "-p",
                 "tsconfig.gate.json"], install.APP, timeout=300)
            tr["gates"]["tsc_exit"] = tsc["exit"]
            tr["gates"]["tsc_tail"] = tsc["out"][-400:]
            page_ok, page_state = wait_dev("/")
            tr["gates"]["page_load"] = page_state
            api_ok, api_state = wait_dev("/api/items", want=200, timeout=60)
            tr["gates"]["api_items"] = api_state
            if api_ok:
                tr["gates"]["apitest"] = run_suite("apitest.mjs")
                if tr["gates"]["apitest"]["exit"] == 0:
                    tr["gates"]["uitest"] = run_suite("uitest.mjs", timeout=600)
        results.append(tr)
        print(json.dumps({k: tr[k] for k in
                          ("id", "installed", "gates")}, indent=1)[-1500:],
              flush=True)
        if tr.get("gates", {}).get("uitest", {}).get("exit") == 0:
            print("Track A candidate PASSED everything — keeping it "
                  "installed and stopping early")
            break
    else:
        install.restore_workspace()
        install.db_push()
    final = dict(track="A-test", wall_seconds=round(time.time() - t_start, 1),
                 candidates=results)
    (REPORTS / "trackA_test.json").write_text(json.dumps(final, indent=1))
    print("\nTEST PHASE DONE — see trackA_test.json")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else "gen"
    if phase == "gen":
        phase_gen()
    elif phase == "test":
        phase_test()
    else:
        raise SystemExit(f"unknown phase {phase}")
