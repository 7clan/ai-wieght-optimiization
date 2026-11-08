"""SESSION 036 — RoomReserve Track A: unassisted monolithic baseline.

The frozen model receives the whole RoomReserve API spec in ONE prompt
and must produce the core application (schema model block + types + four
route files + page).  No staging, no feedback, no repairs, no teacher
bytes.  Up to 7 candidates (greedy first, then frozen seeds).

Two-phase RAM design: `gen` (dev stopped, model loaded once, all
candidates generated, everything archived) then `test` (model unloaded,
dev restarted, each candidate installed mechanically, structurally
gated, tsc-gated and scored with the frozen apitest).

Usage:
  ARCHAGENT_MODEL_DIR=... python -m archagent.fullstack.rr_track_a gen
  python -m archagent.fullstack.rr_track_a test
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

EXP = ROOT / "experiments" / "z036-roomreserve"
GEN = EXP / "generations"
REPORTS = EXP / "reports"
WS = Path("/home/z/my-project")
NODE_ENV = dict(
    PATH="/home/z/.npm-global/bin:/usr/local/bin:/usr/bin:/bin",
    NODE_PATH="/home/z/my-project/node_modules",
    BASE="http://127.0.0.1:3000",
)
SEEDS = [0, 1013, 2026, 3039, 4052, 5165, 6278]  # frozen
MAX_TOKENS = 1500

FILES = [
    ("prisma/schema.prisma", "model block only"),
    ("src/lib/roomreserve/types.ts", ""),
    ("src/app/api/rooms/route.ts", ""),
    ("src/app/api/rooms/[id]/route.ts", ""),
    ("src/app/api/reservations/route.ts", ""),
    ("src/app/api/reservations/[id]/route.ts", ""),
    ("src/app/page.tsx", ""),
]

CONCEPT = ("You are writing RoomReserve, a Next.js 16 meeting-room "
           "reservation app. TypeScript, Prisma + SQLite, NextResponse "
           "JSON APIs. Dates are plain ISO strings 'YYYY-MM-DDTHH:mm' "
           "compared lexicographically.")

DEMO = """// a hotel spa treatment route (different domain, for shape)
import { NextRequest, NextResponse } from 'next/server'
import { db } from '@/lib/db'

export async function POST(req: NextRequest) {
  const body = await req.json()
  const title = String(body.title ?? '').trim()
  if (!title) {
    return NextResponse.json({ error: 'Title is required' }, { status: 400 })
  }
  const clash = await db.treatment.findFirst({
    where: { suiteId: body.suiteId, status: 'booked',
             start: { lt: body.end }, end: { gt: body.start } },
  })
  if (clash) {
    return NextResponse.json(
      { error: 'Time conflict with an existing treatment' },
      { status: 409 })
  }
  const created = await db.treatment.create({
    data: { suiteId: body.suiteId, title, start: body.start, end: body.end },
  })
  return NextResponse.json({ treatment: created }, { status: 201 })
}
"""


def build_prompt() -> tuple[str, str]:
    spec = (EXP / "SPEC.md").read_text()
    m = re.search(r"(## 1\. Data model.*?)\n## 4\. UI contract", spec,
                  re.DOTALL)
    core = m.group(1).strip()
    parts = [CONCEPT, "", DEMO, ""]
    parts.append("Now YOUR task.  Build this application's backend + page.")
    parts.append("")
    parts.append(core)
    parts.append("")
    parts.append("Page: single page with header title RoomReserve, a New "
                 "Reservation button, a rooms panel, a date filter, a "
                 "reservation table with Edit and Cancel buttons, loading, "
                 "error and empty states.")
    parts.append("")
    parts.append("OUTPUT FORMAT — write these seven files, complete, in "
                 "this exact order, each introduced by its marker line:")
    parts.append("")
    for path, note in FILES:
        parts.append(f"=== FILE: {path}"
                     + (f" ({note})" if note else "") + " ===")
    parts.append("")
    parts.append("prisma/schema.prisma contains ONLY the model blocks "
                 "(datasource is already configured).  Start writing now, "
                 "beginning with the marker line:")
    anchor = f"=== FILE: {FILES[0][0]} ({FILES[0][1]}) ==="
    parts.append(anchor)
    return "\n".join(parts), anchor


def extract_files(text: str) -> dict[str, str]:
    """Mechanical marker-based extraction only."""
    files: dict[str, str] = {}
    marker_re = re.compile(r"^=== FILE: (.+?) ===\s*$", re.MULTILINE)
    hits = list(marker_re.finditer(text))
    for i, h in enumerate(hits):
        path = h.group(1).strip()
        # strip a trailing "(note)" from the path if echoed
        path = re.sub(r"\s+\([^)]*\)$", "", path)
        start = h.end()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        body = text[start:end].strip()
        if body:
            files[path] = body
    return files


def phase_gen() -> None:
    from archagent.model import FrozenModel
    from archagent.fullstack import devserver
    devserver.stop_dev()
    model = FrozenModel(threads=2)
    prompt, anchor = build_prompt()
    GEN.mkdir(parents=True, exist_ok=True)
    (GEN / "trackA_prompt.txt").write_text(prompt)
    for i, seed in enumerate(SEEDS):
        t0 = time.time()
        out, usage = model.generate(prompt, max_tokens=MAX_TOKENS,
                                    seed=seed, stochastic=(i > 0))
        files = extract_files(out)
        rec = {
            "kind": "trackA", "round": 0, "k": i, "seed": seed,
            "usage": usage, "stochastic": i > 0,
            "n_files_extracted": len(files),
            "files": sorted(files.keys()),
            "completion": out,
        }
        (GEN / f"trackA_k{i}.json").write_text(json.dumps(rec, indent=1))
        print(f"  k{i} seed={seed}: {len(files)} files, "
              f"{usage['tokens']} tokens, {time.time()-t0:.0f}s")
    print("model usage:", model.usage())


def wait_dev(timeout: float = 90) -> bool:
    import urllib.request
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen("http://127.0.0.1:3000/",
                                        timeout=10) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(2.5)
    return False


def structural_gate(files: dict[str, str]) -> list[str]:
    """Run the Phase-1 gates on each extracted file (stdin mode)."""
    from archagent.repair.controller import RepairController
    gate_contracts = {
        "src/app/api/rooms/route.ts": {
            "kind": "route", "handlers": ["GET"],
            "calls": ["NextResponse.json"]},
        "src/app/api/rooms/[id]/route.ts": {
            "kind": "route", "handlers": ["GET"],
            "calls": ["NextResponse.json"]},
        "src/app/api/reservations/route.ts": {
            "kind": "route", "handlers": ["GET", "POST"],
            "calls": ["NextResponse.json"]},
        "src/app/api/reservations/[id]/route.ts": {
            "kind": "route", "handlers": ["PUT", "DELETE"],
            "calls": ["NextResponse.json"]},
        "src/lib/roomreserve/types.ts": {
            "kind": "types", "interfaces": [
                {"name": "Room", "members": {"name": "string"}},
                {"name": "Reservation", "members": {"title": "string"}}]},
        "src/app/page.tsx": {"kind": "page", "exports": ["default"]},
    }
    failures = []
    ctrl = RepairController(None, str(WS), "/tmp/rr-a-gate.jsonl")
    for path, contract in gate_contracts.items():
        code = files.get(path)
        if code is None:
            failures.append(f"{path}: not extracted")
            continue
        v = ctrl.structural_gate(code, contract)
        if not v["pass"]:
            failures.append(f"{path}: " + "; ".join(v["failures"][:2]))
    return failures


def phase_test() -> None:
    from archagent.fullstack import devserver
    results = []
    # baseline snapshot of the workspace to restore after each candidate
    for i in range(len(SEEDS)):
        rec = json.loads((GEN / f"trackA_k{i}.json").read_text())
        files = extract_files(rec["completion"])
        entry = {"k": i, "seed": rec["seed"],
                 "n_files": rec["n_files_extracted"]}
        if not files:
            entry["verdict"] = "no files extracted"
            results.append(entry)
            continue
        sg = structural_gate(files)
        entry["structural_failures"] = sg[:6]
        entry["structural_pass"] = not sg
        # mechanical install: schema model-block merge, others as-is
        try:
            installed = mechanical_install(files)
            entry["installed"] = installed
        except Exception as e:
            entry["verdict"] = f"install error: {str(e)[:120]}"
            results.append(entry)
            continue
        # tsc gate (model unloaded by now)
        r = subprocess.run(["node_modules/.bin/tsc", "--noEmit", "-p",
                            "tsconfig.gate.json"], cwd=str(WS),
                           capture_output=True, text=True, timeout=300)
        errs = [l for l in (r.stdout + r.stderr).splitlines()
                if "error TS" in l]
        entry["tsc_errors"] = len(errs)
        entry["tsc_first"] = errs[:2]
        # frozen apitest
        if not errs:
            devserver.restart_dev()
            subprocess.run(["bun", "run", "db:reseed-roomreserve"],
                           cwd=str(WS), capture_output=True, timeout=120)
            if wait_dev():
                ap = subprocess.run(["node", str(EXP / "apitest.mjs")],
                                    env={**NODE_ENV}, capture_output=True,
                                    text=True, timeout=480)
                m = re.search(r"API: (\d+)/(\d+) checks passed", ap.stdout)
                entry["apitest"] = (m.group(0) if m
                                    else ap.stdout[-200:])
            else:
                entry["apitest"] = "dev server did not start"
        results.append(entry)
        print(f"  k{i}: files={entry.get('n_files')} "
              f"struct={'PASS' if entry.get('structural_pass') else 'FAIL'} "
              f"tsc={entry.get('tsc_errors')} api={entry.get('apitest','-')}")
    (REPORTS).mkdir(parents=True, exist_ok=True)
    (REPORTS / "trackA.json").write_text(json.dumps(results, indent=1))
    print("results ->", REPORTS / "trackA.json")


def mechanical_install(files: dict[str, str]) -> list[str]:
    """Install candidate files mechanically (no edits beyond merging)."""
    installed = []
    for path, body in files.items():
        if path.endswith("schema.prisma"):
            # merge model blocks into the existing scaffold schema
            schema = (WS / "prisma/schema.prisma").read_text()
            keep = schema.split("model User")[0]
            new = keep + body + "\n"
            (WS / "prisma/schema.prisma").write_text(new)
        else:
            dest = WS / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(body)
        installed.append(path)
    subprocess.run(["bun", "run", "db:push"], cwd=str(WS),
                   capture_output=True, timeout=240)
    return installed


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "gen"
    if mode == "gen":
        phase_gen()
    elif mode == "test":
        phase_test()
    else:
        raise SystemExit(f"unknown mode {mode}")


if __name__ == "__main__":
    main()
