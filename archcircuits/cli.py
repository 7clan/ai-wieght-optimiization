"""Architectural-circuits research CLI.

Subcommands map to the research phases:

  baseline   Phase A: untouched-model evaluation on any partition
  trace      Phase B: causal mediation scans over dev counterfactuals
  heads      Phase B: per-head refinement at chosen layers
  edit       Phase C: build contrastive steering factors for one category
  eval       Phase C/D/E: evaluate the model with factor sets applied
  interfere  Phase D: interference study between factor sets
  holdout    Phase E: frozen-holdout comparison (baseline vs factor sets)

All runs share identical prompts, greedy decoding and scoring paths.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

REPORTS = Path("experiments/archcircuits/reports")
FACTORS = Path("experiments/archcircuits/factors")
SCAN_LAYERS = [2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]


def _load(args):
    import torch
    from archcircuits.runner import load_model
    from archcircuits.benchmark import tasks_for
    torch.set_num_threads(args.threads)
    edit_dirs = args.edits or None
    model, tok, applied = load_model(edit_dirs=edit_dirs)
    return model, tok, applied


def cmd_baseline(args):
    from archcircuits.runner import evaluate_tasks, save_report
    from archcircuits.benchmark import tasks_for
    model, tok, _ = _load(args)
    tasks = tasks_for(args.partition, args.category)
    t0 = time.time()
    report = evaluate_tasks(model, tok, tasks, tag=args.tag)
    report["model"] = "Qwen/Qwen2.5-Coder-0.5B (base, fp32, CPU)"
    report["decode"] = "greedy, max_new_tokens=24"
    report["edits_applied"] = [str(d) for d in (args.edits or [])]
    report["wall_seconds"] = round(time.time() - t0, 1)
    save_report(report, args.output)


def cmd_trace(args):
    import torch
    from archcircuits.benchmark import tasks_for
    from archcircuits.tracing import mediation_scan
    torch.set_num_threads(args.threads)
    from archcircuits.runner import load_model
    model, tok, _ = load_model()
    tasks = [t for t in tasks_for("dev", args.category) if t.get("cf")]
    tasks = tasks[args.skip: args.skip + args.limit]
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results = []
    t0 = time.time()
    for i, task in enumerate(tasks):
        res = mediation_scan(model, tok, task, layers=SCAN_LAYERS)
        results.append(res)
        print(f"[{i+1}/{len(tasks)}] {task['id']} done ({time.time()-t0:.0f}s)", flush=True)
        out_path.write_text(json.dumps({"tasks": results,
                                        "layers": SCAN_LAYERS}, indent=2))
    # aggregate ranking
    agg = {}
    for res in results:
        for site, score in res.get("scores", {}).items():
            agg.setdefault(site, []).append(score)
    ranking = sorted(((site, round(sum(v) / len(v), 4)) for site, v in agg.items()),
                     key=lambda x: -x[1])
    summary = {"ranking": ranking, "per_task": results, "layers": SCAN_LAYERS}
    out_path.write_text(json.dumps(summary, indent=2))
    print("top mediation sites:", ranking[:8])


def cmd_heads(args):
    import torch
    from archcircuits.benchmark import tasks_for, task_by_id
    from archcircuits.tracing import head_scan
    from archcircuits.runner import load_model
    torch.set_num_threads(args.threads)
    model, tok, _ = load_model()
    out_path = Path(args.output)
    tasks = [task_by_id(t) for t in args.tasks]
    results = []
    for task in tasks:
        for layer in args.layers:
            res = head_scan(model, tok, task, layer=layer)
            results.append(res)
            print(f"{task['id']} L{layer}:", res.get("scores"), flush=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"results": results}, indent=2))


def cmd_edit(args):
    """Build a contrastive steering factor set for one category."""
    import torch
    from archcircuits.benchmark import tasks_for, build_prompt
    from archcircuits.runner import load_model, answer_logprobs
    from archcircuits import edits
    torch.set_num_threads(args.threads)
    model, tok, _ = load_model()

    # wrong answers: prefer the baseline model's own errors; fall back to a
    # simple deterministic distractor recorded in the baseline report
    base = json.loads((REPORTS / "baseline.json").read_text())
    wrongs = {r["id"]: r["prediction_extracted"] for r in base["records"]}

    def distractor(task):
        w = (wrongs.get(task["id"]) or "").strip()
        if w and w.lower() != task["gold"].strip().lower():
            return w
        g = task["gold"]
        try:
            n = int(g)
            return str(n + 1)
        except ValueError:
            return "unknown"

    tasks = [t for t in tasks_for("dev", args.category)]
    pairs = []
    for t in tasks:
        prompt = build_prompt(t["category"], t["question"])
        pairs.append({"prompt": prompt, "gold": t["gold"], "wrong": distractor(t)})

    matrix = args.matrix  # e.g. "mlp.down_proj" or "self_attn.o_proj"
    con = edits.collect_contrast(model, tok, pairs, layer=args.layer, matrix=matrix)
    print(f"contrast: d_norm={con['d_norm']:.3f} cos={con['cos_gold_wrong']:.3f} pairs={con['n_pairs']}")

    W = edits._resolve(model, args.layer, matrix).weight.detach().float()
    if args.method == "rank-one":
        left, right, info = edits.rank_one_factors(W, con["keys_wrong"], con["d"], alpha=args.alpha)
        left, right = left.unsqueeze(1), right.unsqueeze(0)
    else:
        left, right, info = edits.multi_key_factors(W, con["keys_wrong"], con["d"], alpha=args.alpha)

    out_dir = FACTORS / args.name
    if out_dir.exists() and not args.force:
        raise SystemExit(f"{out_dir} already exists (use --force)")
    meta = {
        "category": args.category,
        "method": args.method,
        "alpha": args.alpha,
        "construction": {
            "d_norm": con["d_norm"],
            "cos_gold_wrong": con["cos_gold_wrong"],
            "n_pairs": con["n_pairs"],
            **info,
        },
        "norm_limit": 0.015,
        "note": "contrastive steering edit; behavioral effect must be measured",
    }
    stats, left, right = edits.cap_and_apply(model, args.layer, matrix, left, right)
    meta["applied"] = stats
    # Session 011 audit fix: persist the SCALED factors so reload == applied.
    edits.save_factors(str(out_dir), args.layer, matrix, left, right, meta)
    verification = edits.verify_factor_set(model, str(out_dir))
    meta["verification"] = verification
    edits.save_factors(str(out_dir), args.layer, matrix, left, right, meta)
    print("saved", out_dir, "stats:", stats)


def cmd_eval(args):
    from archcircuits.runner import evaluate_tasks, save_report
    from archcircuits.benchmark import tasks_for
    model, tok, applied = _load(args)
    tasks = tasks_for(args.partition, args.category)
    report = evaluate_tasks(model, tok, tasks, tag=args.tag)
    report["edits_applied"] = [m.get("category", str(d)) for m, d in zip(applied, args.edits or [])]
    report["edits_meta"] = applied
    save_report(report, args.output)


def cmd_interfere(args):
    """Geometry + behavior interference between two factor sets."""
    import torch
    from safetensors.torch import load_file
    from archcircuits import edits
    from archcircuits.runner import evaluate_tasks, save_report, paired_comparison
    from archcircuits.benchmark import tasks_for
    torch.set_num_threads(args.threads)

    metas = []
    for d in [args.a, args.b]:
        metas.append(json.loads((Path(d) / "meta.json").read_text()))

    fa = load_file(str(Path(args.a) / "factors.safetensors"))
    fb = load_file(str(Path(args.b) / "factors.safetensors"))
    angles_out = edits.principal_angles(fa["left"].float(), fb["left"].float())
    angles_in = edits.principal_angles(fa["right"].float().T, fb["right"].float().T)
    print("principal angles (output space):", angles_out)
    print("principal angles (input space):", angles_in)

    results = {"geometry": {"output_angles": angles_out, "input_angles": angles_in},
               "conditions": {}}
    from archcircuits.runner import load_model
    for tag, dirs in [("baseline", []), (args.a, [args.a]), (args.b, [args.b]),
                      ("sequential", [args.a, args.b])]:
        model, tok, _ = load_model(edit_dirs=dirs)
        rep = evaluate_tasks(model, tok, tasks_for(args.partition), tag=tag)
        results["conditions"][tag] = {k: v for k, v in rep.items() if k != "records"}
        results["conditions"][tag]["records"] = rep["records"]
        print(tag, rep["by_category"], flush=True)
    # paired comparisons vs baseline
    base_rec = results["conditions"]["baseline"]["records"]
    for tag in (args.a, args.b, "sequential"):
        pc = paired_comparison(base_rec, results["conditions"][tag]["records"],
                               "baseline", tag)
        results["paired"] = results.get("paired", {})
        results["paired"][tag] = pc
        print("paired vs baseline:", tag, pc["gained"], pc["lost"], "p=", pc["mcnemar_p"])
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2))
    print("saved", out)


def cmd_holdout(args):
    """Frozen holdout: baseline vs factor sets, one shot, paired analysis."""
    from archcircuits.runner import evaluate_tasks, paired_comparison, load_model
    from archcircuits.benchmark import tasks_for
    import torch
    torch.set_num_threads(args.threads)
    conditions = {"baseline": []}
    for spec in args.condition:
        name, _, path = spec.partition("=")
        conditions[name] = [path] if path else []
    results = {}
    for name, dirs in conditions.items():
        model, tok, _ = load_model(edit_dirs=dirs)
        rep = evaluate_tasks(model, tok, tasks_for("holdout"), tag=name)
        results[name] = rep
        print(name, "overall:", rep["accuracy"], rep["by_category"], flush=True)
    out = {"conditions": {k: {kk: vv for kk, vv in v.items() if kk != "records"} for k, v in results.items()},
           "records": {k: v["records"] for k, v in results.items()},
           "paired": {}}
    for name in list(conditions)[1:]:
        out["paired"][name] = paired_comparison(results["baseline"]["records"],
                                                results[name]["records"], "baseline", name)
        print("paired:", name, out["paired"][name]["gained"], out["paired"][name]["lost"],
              "p=", out["paired"][name]["mcnemar_p"])
    outp = Path(args.output)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, indent=2))
    print("saved", outp)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp):
        sp.add_argument("--threads", type=int, default=2)

    sp = sub.add_parser("baseline"); common(sp)
    sp.add_argument("--partition", default=None)
    sp.add_argument("--category", default=None)
    sp.add_argument("--tag", default="run")
    sp.add_argument("--output", default=str(REPORTS / "eval.json"))
    sp.add_argument("--edits", nargs="*", default=None)
    sp.set_defaults(func=cmd_baseline)

    sp = sub.add_parser("trace"); common(sp)
    sp.add_argument("--category", default=None)
    sp.add_argument("--skip", type=int, default=0)
    sp.add_argument("--limit", type=int, default=1000)
    sp.add_argument("--output", default=str(REPORTS / "trace.json"))
    sp.set_defaults(func=cmd_trace)

    sp = sub.add_parser("heads"); common(sp)
    sp.add_argument("--tasks", nargs="+", required=True)
    sp.add_argument("--layers", nargs="+", type=int, required=True)
    sp.add_argument("--output", default=str(REPORTS / "heads.json"))
    sp.set_defaults(func=cmd_heads)

    sp = sub.add_parser("edit"); common(sp)
    sp.add_argument("--category", required=True)
    sp.add_argument("--layer", type=int, required=True)
    sp.add_argument("--matrix", required=True)
    sp.add_argument("--method", choices=["rank-one", "multi-key"], default="multi-key")
    sp.add_argument("--alpha", type=float, default=1.0)
    sp.add_argument("--name", required=True)
    sp.add_argument("--force", action="store_true")
    sp.set_defaults(func=cmd_edit)

    sp = sub.add_parser("eval"); common(sp)
    sp.add_argument("--partition", default=None)
    sp.add_argument("--category", default=None)
    sp.add_argument("--tag", default="edited")
    sp.add_argument("--output", default=str(REPORTS / "eval_edited.json"))
    sp.add_argument("--edits", nargs="*", default=None)
    sp.set_defaults(func=cmd_eval)

    sp = sub.add_parser("interfere"); common(sp)
    sp.add_argument("--a", required=True)
    sp.add_argument("--b", required=True)
    sp.add_argument("--partition", default="val")
    sp.add_argument("--output", default=str(REPORTS / "interference.json"))
    sp.set_defaults(func=cmd_interfere)

    sp = sub.add_parser("holdout"); common(sp)
    sp.add_argument("--condition", nargs="+", required=True,
                    help="name=factor_dir (or plain name for baseline)")
    sp.add_argument("--output", default=str(REPORTS / "holdout.json"))
    sp.set_defaults(func=cmd_holdout)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
