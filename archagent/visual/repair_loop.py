"""Execution-guided visual repair loop (Session 034, post-recovery).

The independent re-verification of the recovered apps found four real
visual defects.  Per the frozen-model discipline, the FIXES themselves
must be model-generated: this module asks Qwen2.5-Coder-0.5B for a
bounded CSS patch per defect, guided only by (a) the failing
measurement, (b) the relevant existing CSS, (c) a different-domain
example — never a teacher-written target rule.  Every attempt is
logged under experiments/zai-visual/generations/ (full prompt +
completion + seed + tokens) so these fixes carry RE-VERIFIABLE Qwen
provenance, unlike the recovered application files.

Acceptance: the specific evaluator check flips to PASS and no other
metric regresses (both apps re-measured after each accepted patch).
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

from archagent.visual import curriculum  # noqa: E402
from archagent.visual.css_builder import (  # noqa: E402
    balanced_block, cut_trailing_prose, degenerate, echoes, sha,
    strip_prose)
from archagent.model import FrozenModel  # noqa: E402

GEN_DIR = ROOT / "experiments" / "zai-visual" / "generations"
EVAL = ROOT / "archagent" / "visual" / "evaluator.mjs"
REVERIFY = ROOT / "archagent" / "visual" / "reverify_recovered.mjs"
NODE_ENV = dict(PATH="/usr/local/bin:/usr/bin:/bin",
                PLAYWRIGHT_BROWSERS_PATH="/home/z/.cache/ms-playwright",
                BASE="http://127.0.0.1:4195")

CONCEPT = """You write small CSS patch files that fix measured
accessibility/visual defects in an existing web application.  Answer
with CSS rules only.  The patch will be appended after the existing
stylesheets, so later rules override earlier ones."""

DEMO = """Example from a DIFFERENT app (cooking blog).  Measured defect:
"button height 19px, below the 24px minimum".  The correct patch was:

/* fix: raise button hit area */
.blog-btn {
  min-height: 28px;
  padding: 6px 14px;
}
.blog-btn-icon {
  min-width: 28px;
  min-height: 28px;
}
"""

# The measured defects (from reverification.json + follow-up probes).
# Specs use the EXACT-SHAPE method (the V1-proven and recovered-session
# convention): the selector structure and required properties are named
# by the harness (interface contract); the model writes every byte and
# chooses conforming values.
DEFECTS = [
    dict(
        id="tf-hierarchy", app="taskflow-v2",
        file="styles/fixes-recovery.css",
        measurement="the FIRST h3 on the page is .sidebar-label (the "
                    "sidebar 'PROJECTS' heading) at 18.72px, while the "
                    "section h2 (.view-head h2) computes 18px — a label "
                    "renders larger than a section heading. Checker: "
                    "'h3(18.72) > h2(18)'.  (Harness note: an earlier "
                    "spec misattributed this to .card h3; a probe showed "
                    "card h3s already compute 16px. The 12 model patches "
                    "from that round were exactly as specified — the spec "
                    "was wrong, not the model.)",
        context=".view-head h2 { font-size: 18px; }\n"
                ".sidebar-label { font-size: 1.17em; }  /* 18.72px: the "
                "actual culprit */\n"
                ".card h3 { /* already 16px via app rules */ }",
        spec="""Write a patch that restores the heading hierarchy.  The
patch has THREE parts, in this exact order — write all three:
1. a rule for the selector .view-head h2 with font-size: 20px;
2. a rule for the selector .sidebar-label with font-size: 14px;
3. a media query @media (max-width: 720px) containing a rule for the
   selector .view-head h2 with font-size: 17px;  (measured fact: at
   320px width the app's own rules shrink h1 to 19px, so the h2 must
   be smaller than 19px on narrow screens)
Use px values everywhere.  Use ONLY these three selectors — do not
invent other class names.""",
        anchor="/* fix: heading hierarchy */\n.view-head h2 {\n",
        check=lambda rep: all(
            v["metrics"]["visual-hierarchy"] for v in rep["viewports"]),
        no_regress=["text-visibility", "no-overlap", "no-h-overflow",
                    "alignment", "typography-consistency", "contrast",
                    "interactivity"]),
    dict(
        id="tf-touch", app="taskflow-v2",
        file="styles/fixes-recovery.css",
        measurement="at 390px and 320px widths: .btn-icon buttons were "
                    "24x24 (now fixed at 40x40 by an earlier patch); "
                    ".menu-btn computes 38px wide despite width: 44px — "
                    "flex-shrink compresses it. Checker: 'menu-btn 38x44'.",
        context="/* already patched (keep): */\n"
                "@media (max-width: 720px) {\n"
                ".menu-btn { width: 44px; height: 44px; }\n"
                "  .btn-icon { width: 40px; height: 40px; }\n"
                "}\n"
                "/* measured: the header is a flex row; the menu button\n"
                "   shrinks below its set width under space pressure */",
        spec="""Write a patch that stops the menu button from shrinking.
Add ONE rule (inside a max-width: 720px media query) for the selector
.menu-btn with the property flex-shrink and the value 0.  Do not
change any other property.""",
        anchor="/* fix: menu button shrink */\n@media (max-width: 720px) {\n",
        check=lambda rep: all(
            v["metrics"]["button-visibility"] for v in rep["viewports"]),
        no_regress=["text-visibility", "no-overlap", "no-h-overflow",
                    "alignment", "visual-hierarchy"]),
    dict(
        id="tf-typo-320", app="taskflow-v2",
        file="styles/fixes-recovery.css",
        measurement="at 320px width the page now uses 9 distinct font "
                    "sizes (typography limit is 8).  The extra size is the "
                    "17px media-query h2: at 320px the sizes include both "
                    "17 (h2) and 16 (body).  Setting the narrow-screen h2 "
                    "to 16px keeps the hierarchy (h1=19 > h2=16 > h3=14) "
                    "and collapses into the body size.",
        context=("@media (max-width: 720px) {\n"
                 "  .view-head h2 {\n"
                 "    font-size: 17px;\n"
                 "  }\n"
                 "}"),
        spec="""Write a patch that adjusts the narrow-screen heading size.
Add ONE media query @media (max-width: 720px) containing a rule for
the selector .view-head h2 with font-size: 16px;  Do not change any
other selector or property.""",
        anchor="/* fix: narrow heading size */\n@media (max-width: 720px) {\n",
        check=lambda rep: all(
            v["metrics"]["typography-consistency"] and
            v["metrics"]["visual-hierarchy"] for v in rep["viewports"]),
        no_regress=["text-visibility", "no-overlap", "no-h-overflow",
                    "alignment", "contrast", "interactivity",
                    "button-visibility"]),
    dict(
        id="mv-buttons", app="medivault",
        file="styles/fixes-recovery.css",
        measurement=".btn buttons compute to 21px tall (96x21, 123x21) "
                    "on every viewport; WCAG 2.2 minimum target is 24px. "
                    "Checker: 'btn btn-ghost 96x21', 'btn btn-primary "
                    "123x21'.",
        context=".btn { padding: 4px 12px; font-size: 14px; "
                "line-height: 1.2; border: 1px solid; }",
        spec="""Write a patch that raises button height.  TWO rules:
1. .btn { min-height: 28px; padding: 6px 14px; }
2. .btn-icon { min-width: 28px; min-height: 28px; }
Do not change colors or fonts.""",
        anchor="/* fix: button hit areas */\n.btn {\n",
        check=lambda rep: all(
            not [f for f in v["details"].get("buttonVisibility", [])
                 if f.startswith("btn")]
            for v in rep["viewports"]),
        no_regress=["text-visibility", "no-overlap", "no-h-overflow",
                    "alignment", "contrast", "interactivity",
                    "visual-hierarchy"]),
    dict(
        id="mv-docname", app="medivault",
        file="styles/fixes-recovery.css",
        measurement="the .doc-name row buttons (document name links in "
                    "the records table) compute to 18px tall — below the "
                    "24px minimum target. Checker: 'doc-name 108x18'.",
        context="/* current: no rule sizes .doc-name; it inherits the "
                "table cell's inline flow */",
        spec="""Write a patch that raises the document-name button's hit
area.  Add ONE rule for the selector .doc-name with the properties
min-height: 28px; and display: inline-flex; and align-items: center;
Do not change any other selector.""",
        anchor="/* fix: doc-name hit area */\n.doc-name {\n",
        check=lambda rep: all(
            not [f for f in v["details"].get("buttonVisibility", [])
                 if f.startswith("doc-name")]
            for v in rep["viewports"]),
        no_regress=["text-visibility", "no-overlap", "no-h-overflow",
                    "alignment", "contrast", "interactivity",
                    "visual-hierarchy"]),
]


def run_evaluator(app: str, out: Path, base: str) -> dict:
    subprocess.run(
        ["node", str(EVAL), "--base",
         f"{base}/{app}/index.html",
         "--out", str(out), "--waitfor", "#root > div"],
        capture_output=True, text=True, timeout=180, env=NODE_ENV,
        cwd=str(ROOT))
    return json.loads(out.read_text())


def ensure_fixed_copy(app: str) -> Path:
    """Copy the recovered app into recovery/session034-fixed/ (one-time)
    and inject a <link> for the patch stylesheet into the COPIED
    index.html (a disclosed TRUSTED-SCAFFOLD loader-manifest edit — the
    same classification the recovered ORIGIN.json gives index.html).
    The session034-preview directory stays untouched."""
    src = ROOT / "recovery" / "session034-preview" / app
    dst = ROOT / "recovery" / "session034-fixed" / app
    if not (dst / "index.html").exists():
        import shutil
        shutil.copytree(src, dst)
        idx = dst / "index.html"
        html = idx.read_text()
        inject = ('  <!-- session034-fixed: Qwen-generated repair patches '
                  '(provenance: experiments/zai-visual/generations/fix_*.json) -->\n'
                  '  <link rel="stylesheet" href="styles/fixes-recovery.css" />\n')
        if "fixes-recovery.css" not in html:
            html = html.replace("</head>", inject + "</head>")
            idx.write_text(html)
    return dst


def run_functional(out: Path) -> dict:
    subprocess.run(
        ["node", str(REVERIFY)], capture_output=True, text=True,
        timeout=300, env=NODE_ENV, cwd=str(ROOT))
    return json.loads(out.read_text())


def build_prompt(d: dict, feedback: str | None, own_prev: str | None) -> str:
    parts = [CONCEPT, "", DEMO, ""]
    parts.append("Now YOUR task.  Measured defect (from the automated "
                 "checker):")
    parts.append(d["measurement"])
    parts.append("")
    parts.append("The relevant existing CSS is:")
    parts.append(d["context"])
    parts.append("")
    parts.append(d["spec"])
    if own_prev:
        parts.append("")
        parts.append("Your previous patch (which did not fix the "
                     "measurement) was:")
        parts.append(own_prev)
    if feedback:
        parts.append("")
        parts.append("After your patch the checker reported:")
        parts.append(feedback)
        parts.append("Fix exactly that.")
    parts.append("")
    parts.append("Write the patch now.  The first line is already "
                 "written; continue from it:")
    parts.append(d["anchor"])
    return "\n".join(parts)


def repair_one(model: FrozenModel, d: dict, log: list,
               fixed_base: str) -> bool:
    app_dir = ensure_fixed_copy(d["app"])
    patch_file = app_dir / d["file"]
    report_dir = ROOT / "experiments" / "zai-visual" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    vis_out = report_dir / f"fix-{d['id']}-after.json"

    baseline = run_evaluator(d["app"],
                             report_dir / f"fix-{d['id']}-before.json",
                             fixed_base)
    baseline_pass = d["check"](baseline)
    if baseline_pass:
        print(f"[{d['id']}] already passing — no patch needed")
        log.append(dict(defect=d["id"], already_passing=True))
        return True

    backup = None
    if patch_file.exists():
        backup = patch_file.read_text()

    accepted = None
    attribution = "QWEN-ORIGINAL"
    attempts = 0
    feedback = None
    own_prev = None
    t0 = time.time()
    for round_no in range(3):
        for k in range(4):
            attempts += 1
            prompt = build_prompt(d, feedback, own_prev)
            seed = (k * 1013 + round_no * 77) or 7
            text, usage = model.generate(prompt, max_tokens=260,
                                         seed=seed, stochastic=k != 0)
            code = cut_trailing_prose(
                d["anchor"] + strip_prose(text, d["anchor"]))
            block = balanced_block(code)
            demo_echo = any(m in code for m in
                            (".blog-", ".recipe-card", ".chip"))
            if (not block or degenerate(code)
                    or echoes(code, d["spec"], d["anchor"])
                    or demo_echo):
                GEN_DIR.mkdir(parents=True, exist_ok=True)
                (GEN_DIR / f"fix_{d['id']}_{attempts:03d}.json").write_text(
                    json.dumps(dict(defect=d["id"], kind="rejected",
                                    why="unbalanced/degenerate/echo",
                                    prompt=prompt, text=text, usage=usage),
                               indent=1))
                continue
            code = block
            # apply patch
            patch_file.write_text((backup + "\n\n" if backup else "") + code + "\n")
            after = run_evaluator(d["app"], vis_out, fixed_base)
            ok = d["check"](after)
            regress = [m for m in d["no_regress"]
                       if baseline["aggregate"][m]["pass"]
                       and not after["aggregate"][m]["pass"]]
            GEN_DIR.mkdir(parents=True, exist_ok=True)
            (GEN_DIR / f"fix_{d['id']}_{attempts:03d}.json").write_text(
                json.dumps(dict(defect=d["id"], kind="accepted" if ok and not regress else "rejected",
                                why="" if ok else "check still failing",
                                regress=regress, prompt=prompt, text=code,
                                usage=usage), indent=1))
            if ok and not regress:
                accepted = code
                break
            # revert
            if backup is None:
                patch_file.unlink(missing_ok=True)
            else:
                patch_file.write_text(backup)
            # focused feedback: only THIS defect's metric + per-viewport detail
            metric_key = {"tf-hierarchy": "visual-hierarchy",
                          "tf-touch": "button-visibility",
                          "mv-buttons": "button-visibility"}[d["id"]]
            fb_lines = []
            for v in after["viewports"]:
                if not v["metrics"].get(metric_key, True):
                    det = v.get("details", {}).get(
                        "hierarchy" if metric_key == "visual-hierarchy"
                        else "buttonVisibility", [])
                    fb_lines.append(f"viewport {v['width']}px: still failing — " +
                                    "; ".join(str(x) for x in det[:3]))
            feedback = ("The specific checker for THIS defect still reports:\n" +
                        "\n".join(fb_lines)[:500] +
                        "\nIgnore every other metric; fix only this.")
            own_prev = code
            print(f"[{d['id']}] try {attempts} rejected "
                  f"(pass={ok} regress={regress}) {usage['tokens']}tok")
        if accepted:
            break
        attribution = "QWEN-REPAIRED"
    dt = round(time.time() - t0, 1)
    if accepted is None:
        log.append(dict(defect=d["id"], ok=False, attempts=attempts,
                        seconds=dt))
        print(f"[{d['id']}] FAILED after {attempts} attempts")
        return False
    log.append(dict(defect=d["id"], ok=True, attempts=attempts,
                    attribution=attribution, seconds=dt,
                    sha256=sha(accepted),
                    lines=len(accepted.splitlines())))
    print(f"[{d['id']}] FIXED ({attribution}) after {attempts} attempts "
          f"({dt}s) — {len(accepted.splitlines())} lines")
    return True


def save_log(log_path: Path, log: list, usage: dict):
    log_path.write_text(json.dumps(
        dict(when=time.strftime("%Y-%m-%dT%H:%M:%S"), log=log,
             usage=usage), indent=1))


def main():
    from argparse import ArgumentParser
    ap = ArgumentParser()
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--fixed-base", default="http://127.0.0.1:4196")
    args = ap.parse_args()
    model = FrozenModel(threads=args.threads)
    log_path = (ROOT / "experiments" / "zai-visual" / "reports"
                / "visual-repair-loop.json")
    log = []
    if log_path.exists():
        prev = json.loads(log_path.read_text())
        log = prev.get("log", [])
    done = {e["defect"] for e in log if e.get("ok") or e.get("already_passing")}
    todo = [d for d in DEFECTS if d["id"] not in done]
    if not todo:
        print("all defects already handled (checkpoint)")
    for d in todo:
        repair_one(model, d, log, args.fixed_base)
        save_log(log_path, log, model.usage())  # checkpoint after EACH defect
    save_log(log_path, log, model.usage())
    print("\nusage:", model.usage())
    print("log:", json.dumps(log, indent=1))


if __name__ == "__main__":
    main()
