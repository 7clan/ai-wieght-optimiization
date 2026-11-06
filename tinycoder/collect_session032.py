"""Verify Qwen-only authorship for the Session032 FIM self-repair run, then
publish the live deployment gallery.

Strict rules enforced here (Session031 rules plus FIM lineage):
- every deployed byte of the five app modules is raw Qwen2.5-Coder-0.5B
  output, proven by full lineage replay: each selected module is rebuilt
  from the recorded greedy baseline attempt plus the recorded accepted
  attempts (whole-module completions and native fill-in-the-middle splices
  of the model's own bytes), with sha-256 checks at every splice;
- FIM prefix and suffix are the model's own prior bytes, the fill is a
  recorded raw model completion, and only strict public-metric improvement
  accepts a candidate;
- zero teacher bytes, zero human corrections of model code;
- the browser React runtime is pinned vendored infrastructure, disclosed in
  every ledger; the evaluator runs the byte-identical Session031 worker
  logic locally (disclosed) and publication requires the live parity check
  against the Docker-verified Session031 record to validate;
- each scored sweep gets its own live, interactive deployed page plus a
  script-free static report card.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil

from .rome20 import save_json
from .session014 import MODEL_ID
from .session015 import MODEL_PARAMETER_COUNT
from .session027 import ROLE_PATHS
from .session031_contract import NAME, PREFIX, ROLES, fingerprint
from .session032 import parity_check, rebuild, verify_lineage
from .collect_session031 import (CHECK_REGISTRY, STYLE, badges, badges_snapshot,
                                 esc, js_literal, live_app_page, transpile_ui,
                                 verify_vendored_runtime)

GALLERY_DIR = Path("docs/gallery/session032")
APP_DIR = Path("apps/devmetrics-qwen-fim-selfrepair")
REPORT_JSON = Path("experiments/session032_selfrepair_report.json")
PRED_JSON = Path("experiments/session032_selfrepair_predictions.json")
STATE_JSON = Path("experiments/session032_selfrepair_state.json")


def attempt_origin(pred, role):
    """Locate the recorded attempt whose accepted lineage produced
    selected[role], replaying every accepted attempt for the role from raw
    model bytes alone. Raises ValueError on any foreign byte."""
    attempts = pred["attempts"]
    selected = pred["selected"][role]
    accepted = [i for i, a in enumerate(attempts)
                if a["role"] == role and a.get("accepted")]
    if not accepted:
        accepted = [next(i for i, a in enumerate(attempts)
                         if a["role"] == role and a["stage"] == "baseline")]
    source = pred["greedy"][role]
    for i in accepted:
        source = rebuild(attempts, i, role)
    if source != selected:
        raise ValueError("Selected module fails lineage replay: " + role)
    attempt = attempts[accepted[-1]]
    window = attempt.get("fim_window")
    return {"attempt_index": accepted[-1], "stage": attempt["stage"],
            "round": attempt["round"], "fim_window": window,
            "origin_type": attempt["origin"]["type"]}


def report_card(round_no: int, snap: dict, is_final: bool) -> str:
    sources = "".join(
        "<details><summary>%s</summary><pre>%s</pre></details>"
        % (esc(ROLE_PATHS[role]), esc(snap["modules"][role])) for role in ROLES)
    checks = " ".join("<code>%s%s</code>" % (esc(k), "✓" if v else "✗")
                      for k, v in sorted(snap["public"]["checks"].items()))
    failures = "".join("<li>%s</li>" % esc(r) for r in snap["public"].get(
        "failure_reasons", [])) or "<li>none recorded</li>"
    passed = sum(1 for v in snap["public"]["passed"].values() if v)
    label = "final FIM self-repair sweep" if is_final else "FIM self-repair sweep"
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>DevMetrics sweep {round} report — Qwen2.5-Coder-0.5B</title>
<style>{style}</style></head><body><main>
<h1>DevMetrics — sweep {round} <span class="muted">({label})</span></h1>
<p>Every module below is raw Qwen2.5-Coder-0.5B output from the Session032
FIM-anchored self-repair loop on branch <code>exp/32-fim-selfrepair</code>:
whole-module regenerations plus native fill-in-the-middle splices of the
model&rsquo;s own bytes anchored at the evaluator-reported failing line.
Zero teacher bytes, zero human corrections.</p>
<p><strong>Public score: {passed}/5 modules, {completed} checks, integrated: {integrated}</strong></p>
<div>{badges}</div>
<h2>Execution checks</h2>
<p>{checks}</p>
<h2>Public failure reasons</h2>
<ul>{failures}</ul>
<h2>Model source (exact bytes)</h2>
{sources}
<p><a href="./index.html">Open this sweep&rsquo;s live app →</a> ·
<a href="../index.html">Back to the session gallery</a></p>
<p class="muted">Elapsed {elapsed}s · {tokens} output tokens so far ·
FIM splices: {fim_attempts} attempted, {fim_accepted} accepted ·
SHA-256 of every module is published in the session gallery ledger.</p>
</main></body></html>""".format(round=round_no, label=label, style=STYLE,
                                passed=passed,
                                completed=snap["public"]["completed_checks"],
                                integrated="yes" if snap["public"]["integrated"] else "no",
                                badges=badges_snapshot(snap["public"]),
                                checks=checks, failures=failures, sources=sources,
                                elapsed=snap["elapsed_seconds"],
                                tokens=snap["output_tokens"],
                                fim_attempts=snap.get("fim_attempts", 0),
                                fim_accepted=snap.get("fim_accepted", 0))


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
        if origin["origin_type"] == "fim" and origin.get("fim_window"):
            origin_label = ("Qwen FIM splice attempt #%d (%s, sweep %d, own lines %d–%d)"
                            % (origin["attempt_index"], origin["stage"],
                               origin["round"], origin["fim_window"][0],
                               origin["fim_window"][1]))
        else:
            origin_label = ("Qwen whole-module attempt #%d (%s, sweep %d)"
                            % (origin["attempt_index"], origin["stage"],
                               origin["round"]))
        rows.append("<tr><td>%s</td><td>%s</td><td><code>%s</code></td>"
                    "<td>%d bytes</td></tr>"
                    % (esc(ROLE_PATHS[role]), esc(origin_label),
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
        rows.append("<tr><td>sweep %d</td><td>%s</td><td>%d/5</td><td>%d</td>"
                    "<td>%d/%d</td><td>%s</td>"
                    "<td><a href=\"rounds/%02d/index.html\">live app</a> · "
                    "<a href=\"rounds/%02d/report.html\">report</a></td></tr>"
                    % (round_no, marks, passed, snap["public"]["completed_checks"],
                       snap.get("fim_accepted", 0), snap.get("fim_attempts", 0),
                       "yes" if snap["public"]["integrated"] else "no",
                       round_no, round_no))
    base_pass = sum(1 for v in report["baseline"]["holdout"]["modules"].values() if v["passed"])
    final_pass = sum(1 for v in report["final"]["holdout"]["modules"].values() if v["passed"])
    fim = report.get("fim_repairs", {})
    return """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>DevMetrics — Qwen2.5-Coder-0.5B FIM-anchored self-repair gallery</title>
<style>{style}</style></head><body><main>
<h1>DevMetrics — the 0.5B model surgically repairs its own code</h1>
<p>Frozen <strong>Qwen2.5-Coder-0.5B</strong> (494,032,768 parameters, no training,
no weight edits) wrote every application byte of a React + Express + Python
developer-analytics dashboard, then repaired its own failing modules using only
public execution feedback. Session032 (branch
<code>exp/32-fim-selfrepair</code>) keeps every Session031 rule and adds native
fill-in-the-middle splices: the model&rsquo;s own prior bytes around the
evaluator-reported failing line, with the model completing the gap itself.
Every FIM prefix, suffix and fill is a model completion. Teacher bytes:
<strong>0</strong>. Human corrections: <strong>none</strong>. Every scored sweep
below is deployed exactly as the model wrote it.</p>
<h2>Score progression (public contract)</h2>
<table><tr><th>sweep</th><th>modules</th><th>passes</th><th>checks</th>
<th>FIM acc/att</th><th>integrated</th><th>links</th></tr>{rows}</table>
<h2>Independent holdout (first opened after selection froze)</h2>
<p>Untouched greedy baseline: <strong>{base_pass}/5</strong> modules,
integrated {base_int}. After {sweeps} self-repair sweep(s):
<strong>{final_pass}/5</strong> modules, integrated {final_int}.</p>
<div>{final_badges}</div>
<h2>FIM repair statistics</h2>
<p><strong>{fim_accepted}</strong> of <strong>{fim_attempts}</strong> native
fill-in-the-middle completions were accepted; an accepted splice must strictly
improve the role&rsquo;s public metric under the byte-identical evaluator.
The remaining candidates were whole-module regenerations of the unchanged
Session031 prompts.</p>
<h2>Final deployed app (runs the model&rsquo;s required offline demo mode)</h2>
<iframe src="rounds/{final_round:02d}/index.html" sandbox="allow-scripts allow-forms" loading="lazy" title="Qwen-generated DevMetrics UI"></iframe>
<p><a href="rounds/{final_round:02d}/index.html">Open the live app standalone →</a></p>
<h2>Authorship ledger</h2>
{ledger}
<h2>Verification and disclosure</h2>
<p>Model code executed only in restricted, network-disabled evaluator realms
with module allowlists and timeouts (Express routes via supertest, Python via
a restricted subprocess, React behavior in a jsdom realm with failing fetch).
The recycled sandbox has no Docker daemon, so this session runs the evaluator
as local node/python subprocesses whose worker logic is byte-identical to the
Session031 Docker image; the parity check against the Docker-verified
Session031 record is re-validated live before this gallery is published. The
static gallery serves the same model bytes with vendored React 18.3.1 UMD
(<code>docs/vendor/</code>, sha-256 pinned); the evaluator itself runs React
19.1.1. The jsdom mount is a behavioral DOM check, not a real browser click
test. The Express/Python half cannot run on static hosting; CI verifies it
end-to-end and publishes the report JSON below.</p>
<p><a href="../../../../experiments/session032_selfrepair_report.json">report JSON</a> ·
<a href="../../../../experiments/session032_selfrepair_predictions.json">predictions JSON</a> ·
<a href="../../../index.html">mission dashboard</a></p>
<p class="muted">{candidates} model generations · {tokens} output tokens ·
{wall}s wall time · production_ready=false · no frontier-model parity claim.</p>
</main></body></html>""".format(style=STYLE, rows="".join(rows),
                               base_pass=base_pass,
                               base_int="yes" if report["baseline"]["holdout"]["integrated"] else "no",
                               sweeps=report["sweeps"],
                               final_pass=final_pass,
                               final_int="yes" if report["final"]["holdout"]["integrated"] else "no",
                               final_badges=badges(report["final"]["holdout"]),
                               fim_accepted=fim.get("accepted", 0),
                               fim_attempts=fim.get("attempts", 0),
                               final_round=pred["rounds"][-1]["round"],
                               ledger=ledger_table(pred, ui_compiled_sha),
                               candidates=report["search"]["candidate_count"],
                               tokens=report["search"]["output_tokens"],
                               wall=report["search"]["wall_seconds"])


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
    path = Path("experiments/session031_selfrepair_report.json")
    if path.is_file():
        data = json.loads(path.read_text(encoding="utf8"))
        final = data.get("final", {}).get("holdout", {})
        passes = sum(1 for v in final.get("modules", {}).values() if v.get("passed"))
        entries.append({"session": "031 (exp/29)", "app": "DevMetrics — autonomous self-repair",
                        "passes": passes, "integrated": final.get("integrated", False),
                        "link": "gallery/session031/index.html",
                        "link_label": "live gallery"})
    return entries


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
        "<tr><td>032 (this branch)</td><td>DevMetrics — FIM-anchored self-repair</td>"
        "<td>%d/5</td><td>%s</td><td><a href=\"gallery/session032/index.html\">live gallery</a></td></tr>"
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
<p>This page deploys from the <code>exp/32-fim-selfrepair</code> branch
(Session032; per-branch action ledger: <code>BRANCH_ACTIONS.md</code>, commits
prefixed <code>[exp/32-fim-selfrepair]</code>).
It exists so that <strong>every measured score the frozen Qwen2.5-Coder-0.5B
model achieves is visible as an actual deployed site</strong>, built exactly
from the model&rsquo;s own bytes — never from human- or teacher-corrected code.</p>
<h2>Measured full-stack application sessions</h2>
<table><tr><th>session</th><th>app</th><th>holdout modules</th><th>integrated</th><th>visit</th></tr>{rows}</table>
<h2>Historical sanitized previews</h2>
<p>{previews}</p>
<p class="muted">Static hosting runs the model&rsquo;s required offline demo mode;
the Express/Python halves are verified by the restricted evaluator. No
production-readiness or frontier-model parity claims.</p>
</main></body></html>""".format(style=STYLE, rows="".join(session_rows),
                               previews=" · ".join(preview_links) or "none yet")


def update_readme_results(report, pred):
    """Insert or refresh the measured Session032 results block in README.md."""
    readme = Path("README.md")
    if not readme.is_file():
        return
    text = readme.read_text(encoding="utf8")
    mstart = "<!-- SESSION032-RESULTS-START -->"
    mend = "<!-- SESSION032-RESULTS-END -->"
    base = report["baseline"]["holdout"]
    final = report["final"]["holdout"]
    base_pass = sum(1 for v in base["modules"].values() if v["passed"])
    final_pass = sum(1 for v in final["modules"].values() if v["passed"])
    passes = ", ".join("%s: %s" % (r, "PASS" if final["modules"][r]["passed"] else "FAIL")
                       for r in ROLES)
    fim = report.get("fim_repairs", {})
    rounds_rows = []
    for snap in pred["rounds"]:
        passed = sum(1 for v in snap["public"]["passed"].values() if v)
        rounds_rows.append("| %d | %d/5 | %d | %d/%d | %s | [live](https://7clan.github.io/"
                           "ai-wieght-optimiization/gallery/session032/rounds/%02d/"
                           "index.html) · [report](https://7clan.github.io/"
                           "ai-wieght-optimiization/gallery/session032/rounds/%02d/"
                           "report.html) |" % (
                               snap["round"], passed,
                               snap["public"]["completed_checks"],
                               snap.get("fim_accepted", 0), snap.get("fim_attempts", 0),
                               "yes" if snap["public"]["integrated"] else "no",
                               snap["round"], snap["round"]))
    block = ("""%s
**Measured run — %s (branch exp/32-fim-selfrepair).** Frozen
Qwen2.5-Coder-0.5B, zero teacher bytes, zero human corrections. Same frozen
DevMetrics contract as Session031; self-repair now also splices native
fill-in-the-middle completions anchored at the evaluator-reported failing
line (%d FIM attempts, %d accepted). %d sweep(s), %d generations, %s output
tokens, %s s wall time. Independent holdout — untouched greedy baseline:
**%d/5** modules, integrated: %s. Final: **%d/5** modules, integrated:
**%s**. Final module results: %s.

| sweep | public passes | checks | FIM acc/att | integrated | deployed sweep |
| ---: | ---: | ---: | ---: | --- | --- |
%s

Live mission gallery: <https://7clan.github.io/ai-wieght-optimiization/> ·
Session gallery: <https://7clan.github.io/ai-wieght-optimiization/gallery/session032/>

The static gallery runs the model's required offline demo mode with vendored
React 18.3.1 UMD; the Express/Python halves are verified by the restricted
evaluator (byte-identical Session031 worker logic; Docker parity re-validated
per report). The jsdom check is a behavioral DOM check, not a real browser
click test. No production-readiness or frontier-model parity claim.
%s""" % (mstart, report["new_application"], fim.get("attempts", 0),
         fim.get("accepted", 0), report["sweeps"],
         report["search"]["candidate_count"], report["search"]["output_tokens"],
         report["search"]["wall_seconds"], base_pass,
         "yes" if base["integrated"] else "no", final_pass,
         "yes" if final["integrated"] else "no", passes,
         "\n".join(rounds_rows), mend))
    if mstart in text and mend in text:
        text = text[:text.index(mstart)] + block + text[text.index(mend) + len(mend):]
    elif "<!-- SESSION031-RESULTS-END -->" in text:
        anchor = "<!-- SESSION031-RESULTS-END -->"
        text = text.replace(anchor, anchor + "\n\n" + block, 1)
    else:
        return
    readme.write_text(text, encoding="utf8")


def verify_provenance(report, pred, root):
    if (report.get("session") != "032" or report.get("status") != "completed"
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
    parity = report.get("evaluator_parity_check") or {}
    if parity.get("validated") is not True:
        raise ValueError("Report lacks validated evaluator parity with the "
                         "Docker-verified Session031 record")
    live_parity = parity_check()
    if live_parity.get("validated") is not True:
        raise ValueError("Live evaluator parity did not validate; refusing "
                         "to publish: " + json.dumps(live_parity))
    fim = report.get("fim_repairs") or {}
    if (not isinstance(fim.get("attempts"), int) or fim["attempts"] < 0
            or not isinstance(fim.get("accepted"), int) or fim["accepted"] < 0
            or fim["accepted"] > fim["attempts"]):
        raise ValueError("Invalid FIM repair statistics")
    attempts = pred["attempts"]
    if report["search"]["candidate_count"] != len(attempts) or len(attempts) < len(ROLES):
        raise ValueError("Candidate count does not match raw generations")
    if [(x["stage"], x["role"]) for x in attempts[:5]] != [("baseline", r) for r in ROLES]:
        raise ValueError("Missing actual greedy baseline per role")
    if set(pred["selected"]) != set(ROLES) or set(pred["greedy"]) != set(ROLES):
        raise ValueError("Incomplete generated model sources")
    # Full lineage replay proves every selected byte is model output: whole
    # completions and FIM splices of the model's own recorded bytes only.
    verify_lineage({"attempts": attempts, "selected": pred["selected"],
                    "baseline": pred["greedy"]})
    for role in ROLES:
        source = pred["selected"][role]
        if not source.startswith(PREFIX[role]):
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
    final_compiled = compiled_cache[pred["rounds"][-1]["round"]]
    ui_compiled_sha = (hashlib.sha256(final_compiled.encode()).hexdigest()
                       if final_compiled is not None else "")
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

    preview = Path("docs/previews/session032")
    preview.mkdir(parents=True, exist_ok=True)
    shutil.copy2(gallery / "rounds" / ("%02d" % pred["rounds"][-1]["round"]) / "report.html",
                 preview / "index.html")

    (APP_DIR / "README.md").write_text(
        "# DevMetrics — Qwen2.5-Coder-0.5B FIM-anchored self-repair output\n\n"
        "All five module files are the exact raw bytes generated by the frozen\n"
        "Qwen/Qwen2.5-Coder-0.5B (Session032, branch exp/32-fim-selfrepair):\n"
        "whole-module completions plus native fill-in-the-middle splices of the\n"
        "model's own bytes anchored at the evaluator-reported failing line,\n"
        "accepted only on strict public-metric improvement. Zero teacher bytes,\n"
        "zero human corrections. File signatures are trusted scaffolding. Run\n"
        "only inside the restricted evaluator (the Session031 Docker image or\n"
        "its byte-identical disclosed local worker mode); never execute model\n"
        "output unsandboxed. Live deployment: `docs/gallery/session032/`.\n\n"
        "| module | sha-256 |\n| --- | --- |\n"
        + "".join("| %s | `%s` |\n" % (ROLE_PATHS[r], pred["source_sha256"][r])
                   for r in ROLES), encoding="utf8")

    update_readme_results(report, pred)

    save_json(REPORT_JSON, report)
    save_json(PRED_JSON, pred)
    shutil.copy2(root / "state.json", STATE_JSON)
    final_passes = {r: v["passed"] for r, v in report["final"]["holdout"]["modules"].items()}
    print(json.dumps({"final_holdout_integrated": report["final"]["holdout"]["integrated"],
                      "final_holdout_passes": final_passes,
                      "baseline_holdout_integrated": report["baseline"]["holdout"]["integrated"],
                      "sweeps": report["sweeps"],
                      "fim": report["fim_repairs"],
                      "candidates": report["search"]["candidate_count"]}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs/session032")
    collect(Path(parser.parse_args().output_dir))


if __name__ == "__main__":
    main()
