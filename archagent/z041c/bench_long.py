"""Session 041C — longer code generation benchmark: original vs merged.

The 041B CPU benchmark measured 128 tokens on one fixed neutral prompt.
The user asked to benchmark LONGER code generation (no additional
training). Protocol, kept identical to archagent/z041/bench_cpu.py wherever
it applies:

  * fp32 load (the harness path), threads=2, greedy decoding, seed 20261111;
  * one-shot isolated subprocess per run (cold module state; peak RSS via
    resource.getrusage inside the child);
  * the frozen base vs the LoRA-merged checkpoint rebuilt byte-identically
    from the committed adapter (sha-verified in the aggregate step).

What is NEW (this is the "longer" part):

  * four trusted teacher-authored longer-form coding prompts (neutral
    domains, not from any suite/curriculum/holdout split; archived with
    their sha256 in bench/prompts.json) spanning four shapes the project
    cares about: a React client component, an Express/Node API router
    module, a Python logic module, and a Prisma schema + seed + CRUD
    client file;
  * budgets of 512 and 1024 new tokens per prompt;
  * a continuity control: the exact bench_cpu 128-token prompt, 3 trials
    per model, so the 041B 6.95 tok/s anchor and this session's numbers are
    directly comparable;
  * per-run structural signals computed on the RAW output: natural-EOS vs
    truncation, brace/paren balance, distinct-3 repetition share.

Resumability: every run writes one JSON under bench/runs/; completed runs
are skipped, so the driver can be invoked repeatedly across tool-call
windows. ``--max-seconds`` bounds each invocation (exit 75 = runs remain;
0 = complete). ``--aggregate`` builds bench/long-gen-bench.json and prints
the comparison. The 24-task holdout is never read by anything here.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BENCH = ROOT / "experiments/z041c-evaluator-correction/bench"
RUNS = BENCH / "runs"
BASE_DIR = Path("/home/z/my-project/models/qwen25-coder-05b")
MERGED_DIR = ROOT / "experiments/z041-coding-finetune/merged-checkpoint"
SEED = 20261111

MODELS = {"base": BASE_DIR, "merged": MERGED_DIR}

# The exact 041B bench_cpu prompt (continuity control; 128-token budget).
CONTINUITY_PROMPT = (
    "// utility helpers for a small booking tool\n"
    "export function nights(checkIn, checkOut) {\n"
    "  const msPerDay = 24 * 60 * 60 * 1000;\n"
    "  return Math.round((Date.parse(checkOut) - Date.parse(checkIn)) / msPerDay);\n"
    "}\n\n"
    "export function totalPrice(nights, ratePerNight) {\n"
)

LONG_PROMPTS: dict[str, str] = {
    "react-parcel-pickup": (
        "Write a complete React client component file (TypeScript, no server "
        "actions) for a parcel pickup point desk. The page shows: a text search "
        "box filtering parcels by recipient name, a status filter with the three "
        "states waiting/picked-up/returned, the full parcel list with sender, "
        "recipient and shelf code columns, an add-parcel form (recipient, shelf "
        "code, weight in grams 1..30000) with inline validation, and an error "
        "banner that appears only after failed submissions. Keep component state "
        "in hooks; no external UI library; only the global fetch API.\n\n"
        "Write the complete file now. The first line is already written; "
        "continue from it:\n"
        "\"use client\";\n\n"
        "import { useEffect, useMemo, useState } from \"react\";\n"
    ),
    "express-garage-sessions": (
        "Write a complete Express router module (JavaScript, CommonJS) for a "
        "parking garage session API on an existing express Router. Implement: "
        "GET /sessions returning a JSON envelope { sessions: [...], total } "
        "with optional query filters level (integer) and paid (true/false); "
        "POST /sessions creating a session from a body with plate (non-empty "
        "string), level (integer 0..5), validating everything and answering "
        "400 with a machine-readable code on any violation, 409 if an open "
        "session for the plate already exists, 201 with the created record "
        "otherwise; PATCH /sessions/:id/pay marking a session paid (400 when "
        "already paid, 404 when unknown id); DELETE /sessions/:id closing a "
        "session (404 when unknown). Use a small in-memory store module passed "
        "in via router-level dependency injection.\n\n"
        "Write the complete file now. The first line is already written; "
        "continue from it:\n"
        "\"use strict\";\n\n"
        "const express = require(\"express\");\n"
    ),
    "python-readingroom-holds": (
        "Write a complete Python module (standard library only) implementing "
        "the hold logic for a library reading room: a frozen Seat dataclass "
        "(id, capacity 1..6), a Hold dataclass (id, seat_id, patron, state "
        "with exactly the states placed/claimed/cancelled), a HoldBook class "
        "with place_hold/claim/cancel/list_holds methods enforcing: no two "
        "open holds on the same seat, unknown ids raise LookupError, invalid "
        "state transitions raise ValueError, and a module-level validate_"
        "patron(name) helper rejecting empty or non-string names. Include "
        "type hints and docstrings.\n\n"
        "Write the complete file now. The first line is already written; "
        "continue from it:\n"
        "\"\"\"Reading-room seat hold logic (pure, standard library only).\"\"\"\n\n"
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass, field\n"
    ),
    "prisma-repairshop-orders": (
        "Write a complete file for a repair shop work-order backend: first a "
        "Prisma schema block as a comment string (datasource sqlite, two "
        "models — Technician with id and name, WorkOrder with id, title, "
        "notes, status with default intake, and a required relation to "
        "Technician with onDelete Restrict), then a TypeScript client script "
        "that imports PrismaClient from \"@prisma/client\", exports async "
        "functions list_open_orders(), create_order(title, notes, "
        "technician_id) with input validation, and assign_status(order_id, "
        "status) validating the status transition chain intake->diagnosed->"
        "repaired->delivered. No default export.\n\n"
        "Write the complete file now. The first line is already written; "
        "continue from it:\n"
        "// repair shop work-orders: schema + typed client\n"
    ),
}

BUDGETS = (512, 1024)


def stage_prompts() -> dict[str, Path]:
    """Archive prompts (with sha256) and return per-id prompt file paths."""
    import hashlib
    BENCH.mkdir(parents=True, exist_ok=True)
    RUNS.mkdir(parents=True, exist_ok=True)
    archive = {"seed": SEED, "prompts": {}}
    files: dict[str, Path] = {}
    entries = {"continuity-128": CONTINUITY_PROMPT, **LONG_PROMPTS}
    for name, text in entries.items():
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        archive["prompts"][name] = {"sha256": digest, "chars": len(text), "text": text}
        path = BENCH / f"prompt-{name}.txt"
        path.write_text(text, encoding="utf-8")
        files[name] = path
    (BENCH / "prompts.json").write_text(
        json.dumps(archive, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return files


def planned_runs() -> list[dict]:
    runs = [dict(model=m, prompt=p, budget=b)
            for m in MODELS for p in LONG_PROMPTS for b in BUDGETS]
    runs += [dict(model=m, prompt="continuity-128", budget=128) for m in MODELS]
    return runs


def run_path(run: dict, trial: int) -> Path:
    return RUNS / f"{run['model']}__{run['prompt']}__{run['budget']}__t{trial}.json"


def all_run_slots() -> list[dict]:
    slots = []
    for run in planned_runs():
        trials = 3 if run["prompt"] == "continuity-128" else 1
        for t in range(trials):
            slots.append({**run, "trial": t})
    return slots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-seconds", type=float, default=300.0,
                        help="wall-clock budget for this invocation")
    parser.add_argument("--aggregate", action="store_true")
    args = parser.parse_args()

    files = stage_prompts()
    slots = all_run_slots()
    t0 = time.time()
    pending = []
    for slot in slots:
        out = run_path(slot, slot["trial"])
        if out.is_file() and json.loads(out.read_text(encoding="utf-8")).get("gen_tokens") is not None:
            continue
        pending.append((slot, out))

    if not args.aggregate:
        for slot, out in pending:
            if time.time() - t0 > args.max_seconds:
                print(f"TIME_BUDGET reached; {len(pending)} runs were pending at start, "
                      f"rerun to continue", flush=True)
                return 75
            elapsed = slot["budget"] / 6.5 + 60  # generous per-run estimate
            if time.time() - t0 + elapsed > args.max_seconds + 120:
                print(f"NEXT-RUN OVERHEAD guard; rerun to continue "
                      f"({len(pending)} pending at start)", flush=True)
                return 75
            print(f"run {out.name} ...", flush=True)
            proc = subprocess.run(
                [sys.executable, "-m", "archagent.z041c.bench_long_child",
                 str(MODELS[slot["model"]]), str(files[slot["prompt"]]),
                 str(slot["budget"]), str(out), str(SEED)],
                cwd=str(ROOT), text=True, capture_output=True, timeout=560)
            if proc.returncode != 0:
                print(f"  child failed rc={proc.returncode}: "
                      f"{proc.stderr.strip()[-300:]}", flush=True)
                return 1
            summary = json.loads(proc.stdout.strip().splitlines()[-1])
            print(f"  ok: {summary['gen_tokens']} tokens in {summary['gen_s']}s "
                  f"({summary['tokens_per_s']} tok/s) eos={summary['natural_eos']} "
                  f"rss={summary['peak_rss_mb']}MB", flush=True)
        print(f"DONE this invocation (all {len(slots)} slots complete: "
              f"{len(slots) - len(pending)} were already present)", flush=True)
        return 0

    # ---- aggregate ----------------------------------------------------------
    import hashlib
    records = [json.loads(run_path(s, s["trial"]).read_text(encoding="utf-8"))
               for s in all_run_slots()]
    prompt_names = {hashlib.sha256(files[k].read_text(encoding="utf-8").encode("utf-8")).hexdigest(): k
                    for k in files}
    def sha_of(model: str) -> str:
        h = hashlib.sha256()
        with open(MODELS[model] / "model.safetensors", "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                h.update(block)
        return h.hexdigest()
    result = {"session": "041C", "protocol": {
        "dtype": "fp32 load", "threads": 2, "decoding": "greedy", "seed": SEED,
        "one_shot_subprocess": True, "continuity_with": "041B bench_cpu (128-token prompt, 3 trials)"},
        "models": {m: {"dir": str(MODELS[m]), "safetensors_sha256": sha_of(m)} for m in MODELS},
        "n_runs": len(records)}
    for model in MODELS:
        rows = [r for r in records if r["model_dir"] == str(MODELS[model])]
        cont = [r for r in rows if r["budget"] == 128]
        out = {"continuity_128": {
            "trials": len(cont),
            "tokens_per_s_mean": round(sum(r["tokens_per_s"] for r in cont) / len(cont), 3),
            "model_load_s_mean": round(sum(r["model_load_s"] for r in cont) / len(cont), 3),
            "peak_rss_mb_max": max(r["peak_rss_mb"] for r in cont)}}
        by_budget = {}
        for b in BUDGETS:
            rs = [r for r in rows if r["budget"] == b]
            by_budget[str(b)] = {
                "runs": len(rs),
                "tokens_total": sum(r["gen_tokens"] for r in rs),
                "natural_eos_runs": sum(1 for r in rs if r["natural_eos"]),
                "truncated_runs": sum(1 for r in rs if not r["natural_eos"]),
                "tokens_per_s_mean": round(sum(r["tokens_per_s"] for r in rs) / len(rs), 3),
                "gen_s_mean": round(sum(r["gen_s"] for r in rs) / len(rs), 2),
                "peak_rss_mb_max": max(r["peak_rss_mb"] for r in rs),
                "balanced_braces_runs": sum(1 for r in rs if r["brace_balance"] == 0),
                "distinct_3_mean": round(sum(r["distinct_3"] for r in rs) / len(rs), 4),
                "per_prompt": {k: {
                    "gen_tokens": r["gen_tokens"], "natural_eos": r["natural_eos"],
                    "tokens_per_s": r["tokens_per_s"], "gen_s": r["gen_s"],
                    "chars": r["chars"], "lines": r["lines"],
                    "brace_balance": r["brace_balance"], "distinct_3": r["distinct_3"]}
                    for r in rs for k in [prompt_names[r["prompt_sha256"]]]}}
        out["long_budgets"] = by_budget
        result[model] = out
    out_path = BENCH / "long-gen-bench.json"
    out_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps({
        m: {"128 tok/s": result[m]["continuity_128"]["tokens_per_s_mean"],
            **{b: {"tok/s": result[m]["long_budgets"][b]["tokens_per_s_mean"],
                   "eos": f"{result[m]['long_budgets'][b]['natural_eos_runs']}/4",
                   "balanced": result[m]["long_budgets"][b]["balanced_braces_runs"],
                   "d3": result[m]["long_budgets"][b]["distinct_3_mean"]}
             for b in map(str, BUDGETS)}}
        for m in MODELS}, indent=1))
    print(f"written {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
