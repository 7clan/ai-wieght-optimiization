"""Publish visual, script-free previews of model-generated React UI modules.

Generated JSX executes exclusively in a network-disabled, read-only Docker
container to produce React server-side markup. A strict HTML whitelist strips
all executable content BEFORE publishing static pages. Public examples only.
These preview URLs are visual snapshots, not live Express/Python deployments.
"""
from __future__ import annotations

import argparse
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import uuid

from .rome20 import save_json
from .sandbox_eval import require_sandbox
from .session017_contracts import contracts, contract_sha256


IMAGE = "tinycoder-session019-preview:1"
SAFE_TAGS = {"section", "div", "span", "h1", "h2", "h3", "h4", "h5", "h6",
             "p", "output", "label", "strong", "em", "small", "ul", "ol",
             "li", "blockquote", "code", "pre", "br", "hr", "article",
             "header", "footer", "main", "aside", "button", "input"}
VOID_TAGS = {"br", "hr", "input"}
BLOCKED = {"script", "style", "iframe", "object", "embed", "svg", "math",
           "form", "textarea", "video", "audio"}
SAFE_ATTRS = {"class", "data-testid", "role", "type", "title", "aria-label",
              "disabled", "placeholder", "value"}


class Whitelist(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.suppressed = 0

    def handle_starttag(self, tag, attrs):
        if tag in BLOCKED:
            self.suppressed += 1
            return
        if self.suppressed or tag not in SAFE_TAGS:
            return
        clean = []
        for key, value in attrs:
            if key not in SAFE_ATTRS or value is None:
                continue
            if key == "class":
                value = re.sub(r"[^a-zA-Z0-9_\- ]", "", value)[:160]
            clean.append(f' {key}="{html.escape(value, quote=True)}"')
        self.parts.append(f"<{tag}{''.join(clean)}>")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in SAFE_TAGS and tag not in VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag in BLOCKED:
            self.suppressed = max(0, self.suppressed - 1)
        elif not self.suppressed and tag in SAFE_TAGS and tag not in VOID_TAGS:
            self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(html.escape(data))


def sanitize_markup(value: str) -> str:
    if not isinstance(value, str) or len(value) > 60000:
        raise ValueError("Invalid rendered HTML")
    parser = Whitelist()
    parser.feed(value)
    parser.close()
    return "".join(parser.parts)


def isolated_render(task: dict, source: str) -> dict:
    """Untrusted JSX can execute only inside a disposable isolated container."""
    require_sandbox()
    with tempfile.TemporaryDirectory(prefix="session019_preview_") as tmp:
        root = Path(tmp)
        inp, out = root / "in", root / "out"
        inp.mkdir(mode=0o755)
        out.mkdir(mode=0o777)
        os.chmod(root, 0o755)
        os.chmod(out, 0o777)
        request = inp / "request.json"
        request.write_text(json.dumps({"source": source,
                                       "examples": task["public_cases"][:2]}),
                           encoding="utf-8")
        os.chmod(request, 0o644)
        name = "tinycoder-preview-" + uuid.uuid4().hex[:14]
        cmd = ["docker", "run", "--rm", "--name", name,
               "--network", "none", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--pids-limit", "32",
               "--memory", "256m", "--cpus", "1", "--user", "65534:65534",
               "--tmpfs", "/tmp:rw,nosuid,size=32m",
               "--mount", f"type=bind,src={inp.resolve()},dst=/work,readonly",
               "--mount", f"type=bind,src={out.resolve()},dst=/results",
               IMAGE, "/work/request.json", "/results/result.json"]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=15, check=False)
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                           text=True, timeout=10, check=False)
            return {"ok": False, "html": [], "error": "Docker preview timeout"}
        if result.returncode or not (out / "result.json").exists():
            return {"ok": False, "html": [],
                    "error": "Isolated React preview failure: " + result.stderr[-160:]}
        record = json.loads((out / "result.json").read_text(encoding="utf-8"))
        if record.get("ok") and len(record.get("html", [])) != 2:
            raise ValueError("Renderer returned unexpected preview samples")
        if record.get("ok"):
            record["html"] = [sanitize_markup(markup) for markup in record["html"]]
        return record


STYLE = """
:root{font-family:ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;color:#e9efff;background:#09101e}
*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(ellipse at 70% -30%,#20335e 0,transparent 58%),#09101e}
a{color:#89d4ff}a:hover{color:#d4f3ff}.wrap{max-width:1100px;margin:auto;padding:44px 24px 80px}
.nav{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}.brand{letter-spacing:.15em;font-size:12px;font-weight:800;color:#98b8ff}
h1{font-size:clamp(29px,5vw,52px);letter-spacing:-.04em;margin:28px 0 8px;line-height:1.08}p{line-height:1.6;color:#b6c1d9}
.lead{max-width:800px}.accent{color:#9eeacb}.small{font-size:13px;color:#8e9ab5}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(265px,1fr));gap:17px;margin-top:28px}
.card{background:#121d32;border:1px solid #2a3955;border-radius:19px;padding:22px;box-shadow:0 18px 45px #02061022}
.card h2{margin:8px 0;font-size:21px}.card p{min-height:45px}.stat{display:flex;gap:8px;flex-wrap:wrap;margin:14px 0 22px}
.pill{border-radius:99px;padding:5px 10px;background:#283350;color:#becbe7;font-size:12px;font-weight:650}
.pass{background:#164638;color:#92ecc8}.fail{background:#502b39;color:#ffbdc4}
.btn{display:inline-block;background:#91e7c9;color:#061a20;font-size:14px;text-decoration:none;font-weight:800;padding:11px 17px;border-radius:11px}
.screens{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:20px;margin:30px 0}
.screen{border:1px solid #2a3955;background:#121d32;border-radius:18px;overflow:hidden}
.screen-head{padding:12px 16px;border-bottom:1px solid #2a3955;font-size:12px;color:#aab9d3}
.dots{letter-spacing:2px;color:#f5be95}.canvas{background:#fff;color:#1c2839;min-height:210px;padding:28px}
.canvas section{border:1px solid #d9e1ec;border-radius:12px;background:#f5f8fe;padding:20px}
.canvas h3{font-size:20px;margin:0 0 18px}.canvas output{display:inline-block;color:#0e5e52;font-weight:800;font-size:23px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:14px;border-radius:10px;background:#080e19;color:#ccd8ef;font-size:12px}
details{margin-top:20px;border:1px solid #2a3955;border-radius:12px;padding:17px;background:#101a2b}summary{cursor:pointer;font-weight:700}
footer{margin-top:52px;border-top:1px solid #25334b;padding-top:20px;color:#9eabc5;font-size:13px}
"""


def page(title: str, content: str) -> str:
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; style-src &#39;unsafe-inline&#39;; img-src data:; base-uri &#39;none&#39;; form-action &#39;none&#39;">'
            f"<title>{html.escape(title)}</title><style>{STYLE}</style></head>"
            f"<body><main class=\"wrap\">{content}</main></body></html>\n")


def chip(label: str, ok: bool) -> str:
    return f'<span class="pill {"pass" if ok else "fail"}">{html.escape(label)}: {"PASS" if ok else "FAIL"}</span>'


def render_gallery(predictions: Path, report: Path, output: Path, track: str):
    require_sandbox()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError("Refusing to overwrite an existing preview gallery")
    output.mkdir(parents=True, exist_ok=True)
    generated = json.loads(predictions.read_text(encoding="utf-8"))
    measured = json.loads(report.read_text(encoding="utf-8"))
    tasks = contracts()
    ids = [task["task_id"] for task in tasks]
    if (measured.get("status") != "completed"
        or measured.get("manifest_sha256") != contract_sha256(tasks)
        or measured.get("task_ids") != ids
        or track not in measured["tracks"] or track not in generated):
        raise ValueError("Refusing previews without compatible verified benchmark")
    sources = generated[track]
    observations = measured["tracks"][track]["task_results"]
    if (set(sources) != set(ids)
        or [row["task_id"] for row in observations] != ids):
        raise ValueError("Preview sources do not match benchmark identity")
    by_id = {row["task_id"]: row for row in observations}
    cards, entries = [], []
    for task in tasks:
        tid, contract = task["task_id"], task["contract"]
        slug, title = contract["slug"], contract["heading"]
        source = sources[tid]
        if any(not isinstance(source.get(role), str) for role in ("logic", "api", "ui")):
            raise ValueError("Missing generated application module")
        outcome = by_id[tid]
        screenshot = isolated_render(task, source["ui"])
        available = bool(screenshot.get("ok"))
        screens = []
        for i, case in enumerate(task["public_cases"][:2]):
            markup = screenshot["html"][i] if available else (
                '<p>Generated UI could not be rendered in the isolated container.</p>')
            screens.append(
                f'<section class="screen"><div class="screen-head"><span class="dots">● ● ●</span> &nbsp; '
                f'Public example {i+1}</div><div class="canvas">{markup}</div>'
                f'<div class="screen-head">Input (public)</div>'
                f'<pre>{html.escape(json.dumps(case["payload"], indent=2))}</pre></section>')
        badges = "".join(chip(role.upper(), bool(outcome["modules"][role]["passed"]))
                          for role in ("logic", "api", "ui"))
        badges += chip("INTEGRATED", bool(outcome["passed"]))
        error = (f'<p class="small">Preview rendering: {html.escape(screenshot.get("error", "failed"))}</p>'
                 if not available else "")
        code = "".join(f'<details><summary>{role.upper()} generated source</summary>'
                       f'<pre>{html.escape(source[role])}</pre></details>'
                       for role in ("logic", "api", "ui"))
        detail = (f'<nav class="nav"><span class="brand">TINY CODER · SESSION 018</span>'
                  '<a href="index.html">← All previews</a></nav>'
                  f'<h1>{html.escape(title)}</h1>'
                  f'<p class="lead">{html.escape(contract["operation"])}.</p>'
                  f'<div class="stat">{badges}</div>'
                  '<p class="small">These are static snapshots of the actual generated React component, rendered in a sandbox '
                  'with public fixture data. They are not a running Express backend or a deployable web app.</p>'
                  + error + '<div class="screens">' + "".join(screens) + '</div>' + code
                  + '<footer>Generated model code never executes in your browser. '
                  'Behavioral grades come from separate isolated Python/API/React execution tests.</footer>')
        (output / f"{slug}.html").write_text(page(title, detail), encoding="utf-8")
        cards.append('<article class="card">'
                     f'<span class="small">{html.escape(tid)}</span><h2>{html.escape(title)}</h2>'
                     f'<p>{html.escape(contract["operation"])}.</p><div class="stat">'
                     + chip("APP", bool(outcome["passed"]))
                     + chip("UI", bool(outcome["modules"]["ui"]["passed"]))
                     + '</div>' + f'<a class="btn" href="{slug}.html">Open Preview →</a></article>')
        entries.append({"task_id": tid, "slug": slug, "page": f"{slug}.html",
                        "react_rendered": available,
                        "integrated_holdout_passed": bool(outcome["passed"]),
                        "module_passed": {role: bool(outcome["modules"][role]["passed"])
                                          for role in ("logic", "api", "ui")}})
    passed = sum(int(x["integrated_holdout_passed"]) for x in entries)
    intro = ('<nav class="nav"><span class="brand">TINY CODER · VISUAL LAB</span>'
             '<span class="small">Qwen2.5-Coder-0.5B · unchanged weights</span></nav>'
             '<h1>Generated app <span class="accent">previews.</span></h1>'
             f'<p class="lead">Open each app to inspect how its generated React UI actually renders. '
             f'<strong>{passed}/10</strong> applications also passed their independent full-stack holdout. '
             'Every card has a preview regardless of its execution score.</p>'
             '<p class="small">Snapshots use public sample values. This is visual inspection, '
             'not live full-stack hosting; no model-written JavaScript is served to viewers.</p>'
             '<div class="grid">' + "".join(cards) + '</div>'
             '<footer>These are small authored mini-apps, not production-ready software. '
             'The badge summarizes separate Docker execution tests.</footer>')
    (output / "index.html").write_text(page("TinyCoder · Application Previews", intro),
                                       encoding="utf-8")
    save_json(output / "manifest.json", {"session": measured["session"],
                                         "model": measured["model"],
                                         "track": track, "holdout_passes": passed,
                                         "apps": entries})
    print(json.dumps({"gallery": str(output / "index.html"),
                      "rendered": sum(x["react_rendered"] for x in entries),
                      "holdout": passed}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--predictions", type=Path,
                        default=Path("experiments/session018_extreme_predictions.json"))
    parser.add_argument("--report", type=Path,
                        default=Path("experiments/session018_extreme_report.json"))
    parser.add_argument("--track", default="search8_repair2")
    parser.add_argument("--output-dir", type=Path,
                        default=Path("docs/previews/session018"))
    args = parser.parse_args()
    render_gallery(args.predictions, args.report, args.output_dir, args.track)


if __name__ == "__main__":
    main()
