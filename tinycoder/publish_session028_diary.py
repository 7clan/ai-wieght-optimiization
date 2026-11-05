"""Create an immutable, script-free visual replay of Qwen's mentor rounds."""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path


def render(prediction:dict,report:dict)->str:
    h=html.escape
    parts=[]
    for i,entry in enumerate(prediction["attempts"],1):
        role=h(str(entry["role"]))
        ispass=bool(entry["public_result"]["passed"])
        verdict="PASS" if ispass else "FAIL"
        selected="kept for next round" if entry["accepted"] else "rejected"
        error=h(str(entry["public_result"]["error"] or "none"))
        parts.append(f'''<section class="attempt">
<header><span class="number">#{i:02d}</span>
<h2>{role.upper()} — mentor round {entry["teacher_stage"]+1}</h2>
<span class="status {'pass' if ispass else 'fail'}">{verdict}</span></header>
<p>Student result: <strong>{h(selected)}</strong>.
Output tokens: {entry["output_tokens"]}.</p>
<p>Public test feedback: <code>{error}</code></p>
<details><summary>What the teacher demonstrated (a different task)</summary><pre>{h(entry["analogy"])}</pre></details>
<details><summary>Exact student prompt</summary><pre>{h(entry["prompt"])}</pre></details>
<details><summary>Qwen's raw generated continuation</summary><pre>{h(entry["raw"])}</pre></details>
</section>''')
    hold=report["selected"]["holdout"]
    module_status=", ".join(f"{h(k)} {'PASS' if v['passed'] else 'FAIL'}"
                           for k,v in hold["modules"].items())
    return ('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'">
<title>Qwen0.5B teacher–student replay</title><style>
*{box-sizing:border-box}body{background:#0c1424;color:#e5ecfa;font:15px system-ui;margin:0}
main{max-width:1000px;margin:45px auto;padding:20px}h1{font-size:38px;letter-spacing:-.035em}
.lede{color:#b6c7df;line-height:1.6}.attempt{background:#18243a;border:1px solid #32425b;
padding:22px;border-radius:14px;margin:22px 0}header{display:flex;align-items:center;gap:15px;flex-wrap:wrap}
h2{font-size:22px;flex:1;margin:6px 0}.status{font-size:12px;font-weight:800;padding:7px 12px;border-radius:20px}
.pass{background:#17513e;color:#a7f6c2}.fail{background:#653044;color:#ffd4de}
.number{color:#95a7cb;font-weight:800}p{color:#c9d6e9}details{margin:12px 0;padding:14px;
background:#101b2f;border-radius:9px;border:1px solid #2c3953}
summary{cursor:pointer;font-weight:750}pre{white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5;
font-size:12px;color:#d7ecff}a{color:#8fe3f3}code{overflow-wrap:anywhere}</style></head>
<body><main><a href="index.html">← Back to the source and preview</a>
<h1>Watch how Qwen was taught</h1>
<p class="lede">Recorded teacher feedback, other-domain demonstrations, and the
exact code Qwen produced in each round. This is a replay of real CPU inference,
not real-time streaming. The model's weights were not updated.</p>
<p>Final independent holdout: <strong>'''+('PASS' if hold['integrated'] else 'FAIL')+'''</strong>.
'''+module_status+'''</p>'''+''.join(parts)+
'''<p class="lede">All generated code was evaluated only inside restricted,
network-disabled, read-only and nonroot Docker. A green check on static UI
heuristics is not proof of browser-click functionality.</p></main></body></html>''')


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--predictions",type=Path,
                   default=Path("experiments/session028_mentor_predictions.json"))
    p.add_argument("--report",type=Path,
                   default=Path("experiments/session028_mentor_report.json"))
    p.add_argument("--output",type=Path,
                   default=Path("docs/previews/session028/teaching.html"))
    args=p.parse_args()
    if args.output.exists():
        raise FileExistsError("Refusing to overwrite teaching replay")
    preds=json.loads(args.predictions.read_text(encoding="utf-8"))
    report=json.loads(args.report.read_text(encoding="utf-8"))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(render(preds,report),encoding="utf-8")
    print(f"Wrote {len(preds['attempts'])} replay records: {args.output}",flush=True)


if __name__=="__main__":
    main()
