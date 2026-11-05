"""Verify Qwen-only authorship, then publish the live deployment gallery.

Strict rules enforced here:
- every deployed byte of the five app modules is raw Qwen2.5-Coder-0.5B output
  (prefix + recorded raw attempt), proven by exact string membership;
- zero teacher bytes, zero human corrections of model code;
- the browser React runtime is pinned vendored infrastructure, disclosed in
  every ledger; the Docker evaluator uses React 19.1.1 while the static
  gallery runs the common API subset on React 18.3.1 UMD;
- each scored round gets its own live, interactive deployed page plus a
  script-free static report card.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
from pathlib import Path
import shutil
import subprocess

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session027 import ROLE_PATHS
from .session031_contract import NAME, PREFIX, ROLES, fingerprint

VENDOR_FILES = {"react": "vendor/react.production.min.js",
                "react-dom": "vendor/react-dom.production.min.js"}
VENDOR_SHA = {
    "react": "d949f1c3687aedadcedac85261865f29b17cd273997e7f6b2bfc53b2f9d4c4dd",
    "react-dom": "35f4f974f4b2bcd44da73963347f8952e341f83909e4498227d4e26b98f66f0d",
}
GALLERY_DIR = Path("docs/gallery/session031")
APP_DIR = Path("apps/devmetrics-qwen-selfrepair")

STYLE = """*{box-sizing:border-box}body{background:#0d1527;color:#e3ecf8;
font:15px system-ui,sans-serif;margin:0}main{max-width:1080px;padding:34px 22px;
margin:0 auto}h1{font-size:34px;letter-spacing:-.03em;margin:6px 0 10px}
h2{font-size:20px;margin-top:34px}p{color:#b7c8e4;line-height:1.6}
a{color:#9be4ec}table{border-collapse:collapse;width:100%;margin:14px 0}
th,td{border:1px solid #33507a;padding:8px 11px;text-align:left;font-size:14px}
th{background:#182a46}.pass,.fail{font-size:12px;font-weight:750;padding:6px 11px;
border-radius:12px;display:inline-block;margin:3px}.pass{background:#165440;
color:#b5ffdd}.fail{background:#67354b;color:#ffd6e1}
section{background:#152442;border:1px solid #33507a;border-radius:12px;
padding:20px;margin:18px 0}details{background:#152442;border:1px solid #33507a;
border-radius:10px;padding:12px 16px;margin:10px 0}summary{cursor:pointer;
font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;
line-height:1.5;background:#0a1322;border-radius:8px;padding:14px}
iframe{width:100%;height:640px;border:1px solid #33507a;border-radius:12px;
background:white}.muted{color:#8fa3c4;font-size:13px}code{background:#0a1322;
padding:2px 6px;border-radius:6px;font-size:13px}"""


ESBUILD_ARGS = ("--loader=jsx", "--format=cjs", "--target=es2022")


def esbuild_binary():
    override = os.environ.get("ESBUILD_BIN")
    if override:
        return [override]
    return ["npx", "--yes", "esbuild@0.25.9"]


def transpile_ui(source: str) -> str:
    """Deterministic JSX->CJS compile, the exact transform the Docker
    evaluator applies before executing the same source. Adds no logic;
    both raw and compiled hashes are published in the ledger."""
    proc = subprocess.run(esbuild_binary() + list(ESBUILD_ARGS),
                          input=source + "\nmodule.exports = App;\n",
                          capture_output=True, text=True, timeout=90)
    if proc.returncode or not proc.stdout.strip():
        raise ValueError("esbuild transpile failed: " + proc.stderr[-300:])
    return proc.stdout


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def js_literal(source: str) -> str:
    """JSON string literal with every '<' escaped: no raw tag breakout, and
    JS decoding yields a byte-identical string to the archived module."""
    return json.dumps(source).replace("<", "\\u003c")


def attempt_origin(pred, role):
    """Locate the exact recorded raw attempt that produced selected[role]."""
    selected = pred["selected"][role]
    for index, attempt in enumerate(pred["attempts"]):
        if attempt["role"] != role:
            continue
        if PREFIX[role] + attempt["raw"] == selected:
            return {"attempt_index": index, "stage": attempt["stage"],
                    "round": attempt["round"]}
    raise ValueError("Selected module is not any recorded raw model output: " + role)


CHECK_REGISTRY = {"logic": (), "store": ("persistence", "store_delete",
                   "store_validation"),
                  "api": ("health", "get", "post", "post_invalid", "delete",
                          "projects", "summary"),
                  "ui": ("ui_wiring", "ui_offline"), "css": ()}


def _role_badge(role, passed, checks):
    cls = "pass" if passed else "fail"
    extra = ""
    if CHECK_REGISTRY.get(role):
        marks = " ".join("%s%s" % (c, "✓" if checks.get(c) else "✗")
                         for c in CHECK_REGISTRY[role])
        extra = '<div class="muted">%s</div>' % esc(marks)
    return '<span class="%s">%s: %s</span>%s' % (
        cls, esc(role), "PASS" if passed else "FAIL", extra)


def badges(result):
    """Worker-format evaluation result (final holdout panel)."""
    return " ".join(_role_badge(role, result["modules"][role]["passed"],
                                result["checks"]) for role in ROLES)


def badges_snapshot(snap_public):
    """Round-snapshot format: {passed: {role: bool}, checks: {...}}."""
    return " ".join(_role_badge(role, snap_public["passed"].get(role),
                                snap_public.get("checks", {})) for role in ROLES)


LIVE_TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DevMetrics round __ROUND__ — generated by Qwen2.5-Coder-0.5B</title>
<!--
  Authorship: the application code below is the round __ROUND__ output of the
  frozen Qwen/Qwen2.5-Coder-0.5B model. The App.jsx body is the model's exact
  bytes compiled 1:1 by pinned esbuild 0.25.9 (--loader=jsx --format=cjs),
  the same deterministic, logic-preserving transform the Docker evaluator
  applies; the style.css body is embedded verbatim. Original raw sha-256
  hashes are published in the session gallery ledger. The React/ReactDOM
  runtime and the loader/mount shim are trusted, disclosed infrastructure
  (see docs/vendor/README.md). No human or teacher corrections are applied to
  any model byte. Static hosting has no Express/Python backend, so the app
  runs in the offline demo mode the model was required to implement; the full
  stack is execution-verified in Docker by CI.
-->
<script src="../../../../vendor/react.production.min.js"></script>
<script src="../../../../vendor/react-dom.production.min.js"></script>
<style>
#infra-banner{position:fixed;left:0;right:0;bottom:0;z-index:99;display:none;
background:#67354b;color:#ffd6e1;font:13px system-ui;padding:10px 14px}
</style>
</head><body>
<div id="root"></div>
<div id="infra-banner"></div>
<script>
(function(){
  var banner=document.getElementById('infra-banner');
  function show(message){
    banner.textContent='This round\\u2019s Qwen-generated UI failed to run: '+message+
      ' (the round report card lists the failing checks)';
    banner.style.display='block';
  }
  window.addEventListener('error',function(e){show(e.message||'script error');});
  var APP_SRC=__APP_SRC__;
  var CSS_SRC=__CSS_SRC__;
  try{
    var style=document.createElement('style');
    style.textContent=CSS_SRC;
    document.head.appendChild(style);
    var moduleObj={exports:{}};
    var requireShim=function(id){
      if(id==='react')return window.React;
      throw new Error('module not available in the static gallery: '+id);
    };
    var run=new Function('module','exports','require',APP_SRC);
    run(moduleObj,moduleObj.exports,requireShim);
    var App=moduleObj.exports;
    if(typeof App!=='function')throw new Error('module.exports is not the App function');
    var root=window.ReactDOM.createRoot(document.getElementById('root'));
    root.render(window.React.createElement(App));
  }catch(error){show(error&&error.message?error.message:String(error));}
})();
</script>
</body></html>
"""


def live_app_page(round_no: int, modules: dict, ui_compiled: str) -> str:
    return (LIVE_TEMPLATE
            .replace("__ROUND__", str(round_no))
            .replace("__APP_SRC__", js_literal(ui_compiled))
            .replace("__CSS_SRC__", js_literal(modules["css"])))


def report_card(round_no: int, snap: dict, is_final: bool) -> str:
    sources = "".join(
        "<details><summary>%s</summary><pre>%s</pre></details>"
        % (esc(ROLE_PATHS[role]), esc(snap["modules"][role])) for role in ROLES)
    checks = " ".join("<code>%s%s</code>" % (esc(k), "✓" if v else "✗")
                      for k, v in sorted(snap["public"]["checks"].items()))
    failures = "".join("<li>%s</li>" % esc(r) for r in snap["public"].get(
        "failure_reasons", [])) or "<li>none recorded</li>"
    passed = sum(1 for v in snap["public"]["passed"].values() if v)
    label = "final self-repair round" if is_final else "self-repair round"
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>DevMetrics round {round} report — Qwen2.5-Coder-0.5B</title>
<style>{style}</style></head><body><main>
<h1>DevMetrics — round {round} <span class="muted">({label})</span></h1>
<p>Every module below is raw Qwen2.5-Coder-0.5B output from the Session031
self-repair loop: public-contract prompt, its own previous attempt, public
execution errors. Zero teacher bytes, zero human corrections.</p>
<p><strong>Public score: {passed}/5 modules, {completed} checks, integrated: {integrated}</strong></p>
<div>{badges}</div>
<h2>Execution checks</h2>
<p>{checks}</p>
<h2>Public failure reasons</h2>
<ul>{failures}</ul>
<h2>Model source (exact bytes)</h2>
{sources}
<p><a href="./index.html">Open this round&rsquo;s live app →</a> ·
<a href="../index.html">Back to the session gallery</a></p>
<p class="muted">Elapsed {elapsed}s · {tokens} output tokens so far ·
SHA-256 of every module is published in the session gallery ledger.</p>
</main></body></html>""".format(round=round_no, label=label, style=STYLE,
                                passed=passed,
                                completed=snap["public"]["completed_checks"],
                                integrated="yes" if snap["public"]["integrated"] else "no",
                                badges=badges_snapshot(snap["public"]),
                                checks=checks, failures=failures, sources=sources,
                                elapsed=snap["elapsed_seconds"],
                                tokens=snap["output_tokens"])


def ledger_table(pred, ui_compiled_sha):
    rows = []
    for role in ROLES:
        origin = attempt_origin(pred, role)
        source = pred["selected"][role]
        digest = pred["source_sha256"][role]
        if role == "ui" and ui_compiled_sha:
            digest = ("%s (raw) / %s (esbuild-compiled artifact deployed)"
                      % (digest[:16] + "…", ui_compiled_sha[:16] + "…"))
        else:
            digest = digest[:16] + "…"
        rows.append("<tr><td>%s</td><td>%s</td><td><code>%s</code></td>"
                    "<td>%d bytes</td></tr>"
                    % (esc(ROLE_PATHS[role]),
                       esc("Qwen raw attempt #%d (%s, round %d)"
                           % (origin["attempt_index"], origin["stage"],
                              origin["round"])),
                       esc(digest),
                       len(source.encode())))
    return ("<table><tr><th>module</th><th>origin</th><th>sha-256</th>"
            "<th>size</th></tr>%s</table>" % "".join(rows))


def session_gallery(report, pred, ui_compiled_sha):
    rows = []
    for snap in pred["rounds"]:
        round_no = snap["round"]
        passed = sum(1 for v in snap["public"]["passed"].values() if v)
        marks = "".join('<span class="%s">%s</span> ' % (
            "pass" if snap["public"]["passed"][r] else "fail", esc(r[0].upper() + r[1:]))
            for r in ROLES)
        rows.append("<tr><td>round %d</td><td>%s</td><td>%d/5</td><td>%d</td>"
                    "<td>%s</td><td><a href=\"rounds/%02d/index.html\">live app</a> · "
                    "<a href=\"rounds/%02d/report.html\">report</a></td></tr>"
                    % (round_no, marks, passed, snap["public"]["completed_checks"],
                       "yes" if snap["public"]["integrated"] else "no",
                       round_no, round_no))
    base_pass = sum(1 for v in report["baseline"]["holdout"]["modules"].values() if v["passed"])
    final_pass = sum(1 for v in report["final"]["holdout"]["modules"].values() if v["passed"])
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>DevMetrics — Qwen2.5-Coder-0.5B autonomous self-repair gallery</title>
<style>{style}</style></head><body><main>
<h1>DevMetrics — the 0.5B model builds a full-stack dashboard</h1>
<p>Frozen <strong>Qwen2.5-Coder-0.5B</strong> (494,032,768 parameters, no training,
no weight edits) wrote every application byte of a React + Express + Python
developer-analytics dashboard, then repaired its own failing modules using only
public execution feedback. Teacher bytes: <strong>0</strong>. Human corrections:
<strong>none</strong>. Every scored round below is deployed exactly as the model
wrote it.</p>
<h2>Score progression (public contract, Docker-verified)</h2>
<table><tr><th>round</th><th>modules</th><th>passes</th><th>checks</th>
<th>integrated</th><th>links</th></tr>{rows}</table>
<h2>Independent holdout (first opened after selection froze)</h2>
<p>Untouched greedy baseline: <strong>{base_pass}/5</strong> modules,
integrated {base_int}. After {rounds} self-repair round(s):
<strong>{final_pass}/5</strong> modules, integrated {final_int}.</p>
<div>{final_badges}</div>
<h2>Final deployed app (runs the model&rsquo;s required offline demo mode)</h2>
<iframe src="rounds/{final_round:02d}/index.html" sandbox="allow-scripts allow-forms" loading="lazy" title="Qwen-generated DevMetrics UI"></iframe>
<p><a href="rounds/{final_round:02d}/index.html">Open the live app standalone →</a></p>
<h2>Authorship ledger</h2>
{ledger}
<h2>Verification and disclosure</h2>
<p>Model code executed only inside network-disabled, read-only, unprivileged
Docker (Express routes via supertest, Python via a restricted subprocess, React
behavior in a jsdom realm with failing fetch). The static gallery serves the
same model bytes with vendored React 18.3.1 UMD
(<code>docs/vendor/</code>, sha-256 pinned); the evaluator itself runs React
19.1.1. The jsdom mount is a behavioral DOM check, not a real browser click
test. The Express/Python half cannot run on static hosting; CI verifies it
end-to-end in Docker and publishes the report JSON below.</p>
<p><a href="../../../../experiments/session031_selfrepair_report.json">report JSON</a> ·
<a href="../../../../experiments/session031_selfrepair_predictions.json">predictions JSON</a> ·
<a href="../../../index.html">mission dashboard</a></p>
<p class="muted">{candidates} model generations · {tokens} output tokens ·
{wall}s wall time · production_ready=false · no frontier-model parity claim.</p>
</main></body></html>""".format(style=STYLE, rows="".join(rows),
                               base_pass=base_pass,
                               base_int="yes" if report["baseline"]["holdout"]["integrated"] else "no",
                               rounds=report["self_repair_rounds"],
                               final_pass=final_pass,
                               final_int="yes" if report["final"]["holdout"]["integrated"] else "no",
                               final_badges=badges(report["final"]["holdout"]),
                               final_round=pred["rounds"][-1]["round"],
                               ledger=ledger_table(pred, ui_compiled_sha),
                               candidates=report["search"]["candidate_count"],
                               tokens=report["search"]["output_tokens"],
                               wall=report["search"]["wall_seconds"])


def dashboard(report, pred, prior_sessions):
    session_rows = []
    for entry in prior_sessions:
        session_rows.append(
            "<tr><td>%s</td><td>%s</td><td>%d/5</td><td>%s</td><td><a href=\"%s\">%s</a></td></tr>"
            % (esc(entry["session"]), esc(entry["app"]), entry["passes"],
               "yes" if entry["integrated"] else "no", esc(entry["link"]),
               esc(entry["link_label"])))
    final_pass = sum(1 for v in report["final"]["holdout"]["modules"].values() if v["passed"])
    session_rows.append(
        "<tr><td>031 (this branch)</td><td>DevMetrics — autonomous self-repair</td>"
        "<td>%d/5</td><td>%s</td><td><a href=\"gallery/session031/index.html\">live gallery</a></td></tr>"
        % (final_pass, "yes" if report["final"]["holdout"]["integrated"] else "no"))
    preview_links = []
    preview_root = Path("docs/previews")
    if preview_root.is_dir():
        for child in sorted(preview_root.iterdir()):
            if child.is_dir() and (child / "index.html").is_file():
                preview_links.append('<a href="previews/%s/index.html">%s</a>'
                                     % (child.name, child.name))
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>TinyCoder Weight Lab — live mission gallery</title>
<style>{style}</style></head><body><main>
<h1>TinyCoder Weight Lab — live mission gallery</h1>
<p>This page deploys from the <code>exp/29-selfrepair-deployment</code> branch.
It exists so that <strong>every measured score the frozen Qwen2.5-Coder-0.5B
model achieves is visible as an actual deployed site</strong>, built exactly
from the model&rsquo;s own bytes — never from human- or teacher-corrected code.</p>
<h2>Measured full-stack application sessions</h2>
<table><tr><th>session</th><th>app</th><th>holdout modules</th><th>integrated</th><th>visit</th></tr>{rows}</table>
<h2>Historical sanitized previews</h2>
<p>{previews}</p>
<p class="muted">Static hosting runs the model&rsquo;s required offline demo mode;
Express/Python halves are Docker-verified in CI. No production-readiness or
frontier-model parity claims.</p>
</main></body></html>""".format(style=STYLE, rows="".join(session_rows),
                               previews=" · ".join(preview_links) or "none yet")


def prior_session_entries():
    entries = []
    path = Path("experiments/session030_transfer_report.json")
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf8"))
        guided = data.get("guided", {}).get("holdout", {})
        passes = sum(1 for v in guided.get("modules", {}).values() if v.get("passed"))
        entries.append({"session": "030 (exp/28)", "app": "ShelfStock — teacher-example transfer",
                        "passes": passes, "integrated": guided.get("integrated", False),
                        "link": "previews/session030/index.html",
                        "link_label": "static preview"})
    return entries


def verify_vendored_runtime():
    for key, rel in VENDOR_FILES.items():
        path = Path("docs") / rel
        if not path.is_file():
            raise FileNotFoundError("Missing vendored runtime: " + str(path))
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != VENDOR_SHA[key]:
            raise ValueError("Vendored runtime hash mismatch: " + rel)


def verify_provenance(report, pred, root):
    if (report.get("session") != "031" or report.get("status") != "completed"
            or report.get("model") != MODEL_ID
            or report.get("parameter_count") != MODEL_PARAMETER_COUNT
            or report.get("training_steps") != 0 or report.get("weight_edits") != 0
            or report.get("contract_sha256") != fingerprint()
            or report.get("target_app_modules_from_qwen") != list(ROLES)
            or report.get("teacher_bytes") != 0
            or report.get("teacher_supplied_anything") is not False
            or report.get("self_repair_only") is not True
            or report["search"]["private_holdout_seen_during_selection"] is not False):
        raise ValueError("Invalid frozen-model experiment provenance")
    attempts = pred["attempts"]
    if report["search"]["candidate_count"] != len(attempts) or len(attempts) < len(ROLES):
        raise ValueError("Candidate count does not match raw generations")
    if [(x["stage"], x["role"]) for x in attempts[:5]] != [("baseline", r) for r in ROLES]:
        raise ValueError("Missing actual greedy baseline per role")
    if set(pred["selected"]) != set(ROLES) or set(pred["greedy"]) != set(ROLES):
        raise ValueError("Incomplete generated model sources")
    for role in ROLES:
        source = pred["selected"][role]
        options = [PREFIX[role] + x["raw"] for x in attempts
                   if x["role"] == role and (x["stage"] == "baseline" or x.get("accepted"))]
        if source not in options or not source.startswith(PREFIX[role]):
            raise ValueError("Non-model target code substituted: " + role)
        if (root / "generated" / ROLE_PATHS[role]).read_text(encoding="utf8") != source:
            raise ValueError("Saved file changed from Qwen raw candidate: " + role)
    for snap in pred["rounds"]:
        for role in ROLES:
            digest = hashlib.sha256(snap["modules"][role].encode()).hexdigest()
            if digest != snap["modules_sha256"][role]:
                raise ValueError("Round snapshot hash mismatch: " + role)
        if len(snap["public"]["passed"]) != len(ROLES):
            raise ValueError("Round snapshot missing role states")
    for track in ("baseline", "final"):
        for phase in ("public", "holdout"):
            result = report[track][phase]
            if result["phase"] != phase or set(result["modules"]) != set(ROLES):
                raise ValueError("Mismatch in evaluation identity")
            if result["integrated"] and not (
                    all(x["passed"] for x in result["modules"].values())
                    and result["checks"].get("integration") is True
                    and result["checks"].get("ui_offline") is True):
                raise ValueError("Fabricated integrated success")


def collect(root: Path):
    report = json.loads((root / "report.json").read_text(encoding="utf8"))
    pred = json.loads((root / "predictions.json").read_text(encoding="utf8"))
    verify_provenance(report, pred, root)
    verify_vendored_runtime()

    APP_DIR.mkdir(parents=True, exist_ok=True)
    for role, rel in ROLE_PATHS.items():
        target = APP_DIR / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(pred["selected"][role], encoding="utf8")

    gallery = GALLERY_DIR
    if gallery.exists():
        shutil.rmtree(gallery)
    compiled_cache = {}
    for snap in pred["rounds"]:
        compiled_cache[snap["round"]] = transpile_ui(snap["modules"]["ui"])
    ui_compiled_sha = hashlib.sha256(
        compiled_cache[pred["rounds"][-1]["round"]].encode()).hexdigest()
    rounds_dir = gallery / "rounds"
    rounds_dir.mkdir(parents=True)
    for index, snap in enumerate(pred["rounds"]):
        round_dir = rounds_dir / ("%02d" % snap["round"])
        round_dir.mkdir()
        (round_dir / "index.html").write_text(
            live_app_page(snap["round"], snap["modules"],
                          compiled_cache[snap["round"]]), encoding="utf8")
        (round_dir / "report.html").write_text(
            report_card(snap["round"], snap, index == len(pred["rounds"]) - 1),
            encoding="utf8")
    (gallery / "index.html").write_text(
        session_gallery(report, pred, ui_compiled_sha), encoding="utf8")

    Path("docs").mkdir(exist_ok=True)
    (Path("docs") / "index.html").write_text(
        dashboard(report, pred, prior_session_entries()), encoding="utf8")

    preview = Path("docs/previews/session031")
    preview.mkdir(parents=True, exist_ok=True)
    shutil.copy2(gallery / "rounds" / ("%02d" % pred["rounds"][-1]["round"]) / "report.html",
                 preview / "index.html")

    (APP_DIR / "README.md").write_text(
        "# DevMetrics — Qwen2.5-Coder-0.5B autonomous self-repair output\n\n"
        "All five module files are the exact raw bytes generated by the frozen\n"
        "Qwen/Qwen2.5-Coder-0.5B (Session031, branch exp/29-selfrepair-deployment),\n"
        "repaired only by the model itself from public Docker execution feedback.\n"
        "Zero teacher bytes, zero human corrections. File signatures are trusted\n"
        "scaffolding. Run only inside the restricted evaluator image\n"
        "(`docker/session031-selfrepair.Dockerfile`); never execute model output\n"
        "unsandboxed. Live deployment: `docs/gallery/session031/`.\n\n"
        "| module | sha-256 |\n| --- | --- |\n"
        + "".join("| %s | `%s` |\n" % (ROLE_PATHS[r], pred["source_sha256"][r])
                   for r in ROLES), encoding="utf8")

    save_json(Path("experiments/session031_selfrepair_report.json"), report)
    save_json(Path("experiments/session031_selfrepair_predictions.json"), pred)
    shutil.copy2(root / "state.json",
                 Path("experiments/session031_selfrepair_state.json"))
    final_passes = {r: v["passed"] for r, v in report["final"]["holdout"]["modules"].items()}
    print(json.dumps({"final_holdout_integrated": report["final"]["holdout"]["integrated"],
                      "final_holdout_passes": final_passes,
                      "baseline_holdout_integrated": report["baseline"]["holdout"]["integrated"],
                      "rounds": len(pred["rounds"]) - 1,
                      "candidates": report["search"]["candidate_count"]}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs/session031")
    collect(Path(parser.parse_args().output_dir))


if __name__ == "__main__":
    main()
