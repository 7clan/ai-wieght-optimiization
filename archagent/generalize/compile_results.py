"""SESSION037 — compile the four-track comparison + resource accounting
from the committed artifacts (no model needed).

Usage: python -m archagent.generalize.compile_results
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TR = ROOT / "experiments" / "z037-generalization" / "tracks"
CH = ROOT / "experiments" / "z037-generalization" / "challenge"
CU = ROOT / "experiments" / "z037-generalization" / "curricula"
DG = ROOT / "experiments" / "z037-generalization" / "docgate"


def load(t: str):
    p = TR / t / "summary.json"
    return json.loads(p.read_text()) if p.exists() else None


def per_piece(s: dict) -> dict:
    out = {}
    for dom in s["domains"]:
        for pid, rec in dom["per_piece"].items():
            out[pid] = rec
    return out


def main() -> None:
    summaries = {t: load(t) for t in "ABCD"}
    if not all(summaries.values()):
        missing = [t for t, v in summaries.items() if not v]
        print(f"missing track summaries: {missing} — aborting")
        return

    print("=" * 72)
    print("FOUR-TRACK COMPARISON (final independent scoring, n=15 pieces)")
    print("=" * 72)
    rows = []
    for t in "ABCD":
        s = summaries[t]
        label = {"A": "unassisted", "B": "036 baseline",
                 "C": "engine structural", "D": "engine full"}[t]
        rows.append((t, label, s["final_resolved_total"],
                     s["total_pieces"], s["loop_tokens"]))
        print(f"  {t} ({label:17s}): {s['final_resolved_total']:2d}/"
              f"{s['total_pieces']}  loop_tokens={s['loop_tokens']:6d}  "
              f"schema_ok="
              f"{all(d['schema_validates'] for d in s['domains'])}")

    base = summaries["B"]["final_resolved_total"]
    for t, label, n, tot, tok in rows:
        if t == "B":
            continue
        rel = ((n - base) / base * 100) if base else float("nan")
        print(f"  B->{t}: {rel:+.1f}% relative "
              f"({'target >=+20%' if t == 'D' else ''})")

    # paired piece-level table
    pp = {t: per_piece(summaries[t]) for t in "ABCD"}
    pids = sorted(pp["B"].keys())
    print("\nper-piece (A/B/C/D, x=correct, .=not, ?=harness-None):")
    for pid in pids:
        cells = []
        for t in "ABCD":
            r = pp[t].get(pid, {})
            cells.append("x" if r.get("resolved") else
                         ("?" if r.get("behavioral") is None else "."))
        dom = pid.split("-")[0]
        print(f"  {pid:18s} {' '.join(cells)}  ({dom})")

    # per-domain totals
    print("\nper-domain final resolved:")
    for t in "ABCD":
        drow = []
        for dom in summaries[t]["domains"]:
            drow.append(f"{dom['domain'][:10]}:{dom['final_resolved']}"
                        f"/{dom['total']}")
        print(f"  {t}: " + "  ".join(drow))

    # McNemar-style pairing D vs B
    b_win = d_win = tie = 0
    for pid in pids:
        b = pp["B"][pid].get("resolved", False)
        d = pp["D"][pid].get("resolved", False)
        if d and not b:
            d_win += 1
        elif b and not d:
            b_win += 1
        else:
            tie += 1
    print(f"\npaired D-vs-B: D-only wins={d_win}  B-only wins={b_win}  "
          f"ties={tie}  (binomial p on discordant pairs, report with "
          f"n=15 caveat)")

    # resource accounting
    print("\n" + "=" * 72)
    print("RESOURCE ACCOUNTING")
    print("=" * 72)
    total_tok = 0
    for t in "ABCD":
        s = summaries[t]
        u = s.get("model_usage", {})
        print(f"  track {t}: loop_tokens={s['loop_tokens']:6d} "
              f"model_usage={u}")
        total_tok += s.get("loop_tokens", 0)
    print(f"  four-track loop tokens total: {total_tok}")

    for c in ("a", "b"):
        p = CU / c / "summary.json"
        if p.exists():
            s = json.loads(p.read_text())
            d = s["dev"]
            print(f"  curriculum {c.upper()}: base {d['baseline_tokens']} "
                  f"tok / eng {d['engine_tokens']} tok")

    dg = DG / "decision.json"
    if dg.exists():
        s = json.loads(dg.read_text())
        print(f"  docgate A/B: without {s['without_doc']['resolved']}/"
              f"{len(s['without_doc']['detail'])} ({s['without_doc']['tokens']} tok) "
              f"vs with {s['with_doc']['resolved']}/"
              f"{len(s['with_doc']['detail'])} ({s['with_doc']['tokens']} tok) "
              f"-> default={s['becomes_default']}")

    ch = CH / "results.json"
    if ch.exists():
        s = json.loads(ch.read_text())
        e = s["engine_only"]
        print(f"  challenge: engine-only {e['resolved']}/{e['total']} "
              f"pieces, {e['tokens']} tok, "
              f"schema_valid={s['schema_validates'].get('pass')}")


if __name__ == "__main__":
    main()
