"""Session032: FIM-anchored self-repair for the frozen DevMetrics contract.

Same frozen Qwen2.5-Coder-0.5B, same frozen public contract and evaluator
checks as Session031 (whose 36 whole-module regeneration rounds plateaued at
logic+css passing; store died on a one-line `const` reassignment bug the model
never managed to regenerate away). One disclosed methodological change: the
model now ALSO repairs its own failing code surgically with native
fill-in-the-middle completions anchored at the exact failing position the
evaluator reports:

- `Assignment to constant variable` -> FIM window around the model's own
  `const` declaration of the variable the failing line reassigns;
- failing Express route envelopes -> FIM window around the model's own
  handler for exactly that route (brace-counted to its closing `});`);
- transform/syntax errors -> FIM window around the reported line:column.

Every module byte is still model output: FIM prefix and suffix are the
model's own prior bytes, the fill is a fresh model completion, and
whole-module candidates remain plain model completions of the unchanged
Session031 prompts. Zero teacher bytes, zero human corrections, weights
frozen. Docker is unavailable in the recycled sandbox, so the evaluator
runs the identical worker logic (vm realms, module allowlists, timeouts,
byte-identical checks) in local node/python subprocesses; parity against
the Docker-verified Session031 record is re-validated in every report.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from .rome20 import save_json
from .session015 import MODEL_PARAMETER_COUNT
from .session014 import MODEL_ID
from .session031 import (LIMITS, ROLE_CHECKS, SELF_MEMORY_EXCLUDE,
                         load_self_memory)
from .session031_contract import (NAME, PREFIX, PUBLIC, ROLES, fingerprint,
                                  holdout, prompt)

MODEL_DIR = os.environ.get("TINYCODER_MODEL_DIR",
                           "/home/z/my-project/models/Qwen2.5-Coder-0.5B")
EVALENV = os.environ.get("SESSION032_EVALENV", "/home/z/my-project/evalenv")
WORKER = str(Path(__file__).with_name("session032_worker.js"))
PY_WORKER = str(Path(__file__).with_name("session032_py_worker.py"))
BASE_SEED = 2026113200
WALL_BUDGET_SECONDS = 14400
TIME_BUDGET_DEFAULT = 500.0
UI_WIRING_TOTAL = 14
SELF_MEMORY_PATH = "experiments/session030_transfer_predictions.json"

# session031 metric parity + ui wiring-count refinement (14 worker patterns).
TRANSFORM_LINE = re.compile(r":(\d+):(\d+): (?:ERROR|error)")
FRAME_LINE = re.compile(r"@ \S+?:(\d+):(\d+)")
UI_LACKS = re.compile(r"UI lacks: (.*?)(?:\s*@ |$)", re.S)
CHECK_ROUTES = {"health": ("get", "/api/health"), "get": ("get", "/api/entries"),
                "post": ("post", "/api/entries"),
                "post_invalid": ("post", "/api/entries"),
                "delete": ("delete", "/api/entries/:id"),
                "projects": ("get", "/api/projects"),
                "summary": ("get", "/api/summary")}

# Second-order coupling: when route A's handler corrupts data that route B's
# check consumes, fixing B alone can never pass. Each entry names the route
# whose handler must ALSO be rewritten (in the same FIM fill) for the check
# named by the key to become satisfiable.
COUPLING = {"delete": "post", "summary": "post"}


def load_model():
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    torch.manual_seed(0)
    torch.set_num_threads(2)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR, dtype=torch.float32).eval().to("cpu")
    if (sum(p.numel() for p in model.parameters()) != MODEL_PARAMETER_COUNT
            or len(model.model.layers) != 24
            or model.config.hidden_size != 896):
        raise ValueError("Not the fixed 0.5B Qwen2.5-Coder architecture")
    model.requires_grad_(False)
    return model, tokenizer


def evaluate(modules, cases, phase, *, timeout=150):
    """Local evaluator: identical worker logic, disclosed non-Docker mode."""
    if set(modules) != set(ROLES) or phase not in ("public", "holdout"):
        raise ValueError("Invalid evaluator request")
    with tempfile.TemporaryDirectory(prefix="qwen032-") as dirname:
        root = Path(dirname)
        inp, out = root / "input.json", root / "output.json"
        inp.write_text(json.dumps({"modules": modules, "cases": cases,
                                   "phase": phase}), encoding="utf8")
        env = dict(os.environ)
        env.update({"SESSION032_LOCAL_EVAL": "1", "SESSION032_PY_WORKER": PY_WORKER,
                    "NODE_PATH": EVALENV + "/node_modules", "NODE_ENV": "production"})
        try:
            proc = subprocess.run(["node", WORKER, str(inp), str(out)],
                                  capture_output=True, text=True, timeout=timeout,
                                  check=False, env=env)
        except subprocess.TimeoutExpired:
            return _failure(phase, "Bounded local evaluator timeout")
        if proc.returncode or not out.is_file():
            return _failure(phase, "Local evaluator error: " + proc.stderr[-220:])
        result = json.loads(out.read_text(encoding="utf8"))
        if result.get("phase") != phase or set(result.get("modules", {})) != set(ROLES):
            raise RuntimeError("Evaluator identity mismatch")
        return result


def _failure(phase, message):
    return {"phase": phase, "integrated": False, "completed_checks": 0,
            "modules": {role: {"passed": False, "syntax_valid": False,
                               "error": message} for role in ROLES},
            "checks": {}, "ui_markup": None, "failure_reasons": [message]}


def generate_one(model, tokenizer, text, *, max_tokens, seed, stochastic):
    import torch
    torch.manual_seed(seed)
    inputs = tokenizer(text, return_tensors="pt", add_special_tokens=False)
    kwargs = {"max_new_tokens": max_tokens, "do_sample": stochastic,
              "pad_token_id": tokenizer.eos_token_id}
    if stochastic:
        kwargs.update({"temperature": 0.72, "top_p": 0.93})
    with torch.inference_mode():
        output = model.generate(**inputs, **kwargs)
    decoded = tokenizer.decode(output[0, inputs["input_ids"].shape[1]:],
                               skip_special_tokens=True)
    return decoded, int(output.shape[1] - inputs["input_ids"].shape[1])


def fim_generate(model, tokenizer, instructions, prefix, suffix, *, max_tokens,
                 seed, stochastic):
    """Native Qwen FIM completion, repair instructions placed at the END of
    the prefix region, immediately adjacent to the gap (measured: this
    placement makes the model rewrite the broken region instead of copying
    its old shape verbatim). The instructions are prompt-only comment lines:
    the spliced module stays 100% model bytes (prefix + fill + suffix)."""
    import torch
    torch.manual_seed(seed)
    text = ("<|fim_prefix|>" + prefix + instructions + "<|fim_suffix|>"
            + suffix + "<|fim_middle|>")
    inputs = tokenizer(text, return_tensors="pt", add_special_tokens=False)
    kwargs = {"max_new_tokens": max_tokens, "do_sample": stochastic,
              "pad_token_id": tokenizer.eos_token_id}
    if stochastic:
        kwargs.update({"temperature": 0.72, "top_p": 0.93})
    with torch.inference_mode():
        output = model.generate(**inputs, **kwargs)
    raw = tokenizer.decode(output[0, inputs["input_ids"].shape[1]:],
                           skip_special_tokens=False)
    # Trim at any boundary special token the model may emit. Delimiters are
    # assembled programmatically so no raw control token is embedded here.
    fill = raw
    for delimiter in ("<|fim_suffix|>", "<|fim_middle|>", "<|im_end|>",
                      "<|" + "endoftext" + "|>", "<|" + "fim_pad" + "|>"):
        fill = fill.split(delimiter)[0]
    return fill, int(output.shape[1] - inputs["input_ids"].shape[1])


def trim_fill(fill: str, suffix: str) -> str:
    """Trim a FIM fill that overruns its window and starts duplicating the
    module's own suffix content (measured: 360-token fills for 5-line windows
    re-declare functions from below the window, breaking the module). The
    marker is the suffix's first three consecutive non-empty lines appearing
    verbatim inside the fill; fills that stay inside the window are returned
    unchanged."""
    slines = [l for l in suffix.splitlines() if l.strip()][:3]
    if len(slines) < 3:
        return fill
    marker = "\n".join(slines)
    pos = fill.find(marker)
    return fill[:pos] if pos != -1 else fill


ALLOWED_REQUIRES = {"node:fs", "fs", "express", "react"}
SYNTAX_SCRIPT = (
    "const esbuild=require('esbuild');const fs=require('fs');"
    "const src=fs.readFileSync(process.argv[1],'utf8');"
    "try{esbuild.transformSync(src,{loader:process.argv[2]});console.log('ok')}"
    "catch(e){console.log('bad')}")


def syntax_ok(module: str, role: str) -> bool:
    """Cheap static gate (ast for Python, pinned esbuild for JS/JSX/CSS) so a
    malformed fill is skipped before any expensive evaluation. This gate only
    REJECTS candidates; it never rewrites a single model byte."""
    if role == "logic":
        try:
            import ast
            ast.parse(module)
            return True
        except (SyntaxError, ValueError):
            return False
    loader = "css" if role == "css" else ("jsx" if role == "ui" else "js")
    with tempfile.NamedTemporaryFile("w", suffix="." + loader, delete=False,
                                     encoding="utf8") as handle:
        handle.write(module)
        name = handle.name
    try:
        proc = subprocess.run(
            ["node", "-e", SYNTAX_SCRIPT, name, loader],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "NODE_PATH": EVALENV + "/node_modules"})
        return proc.stdout.strip() == "ok"
    except (subprocess.SubprocessError, OSError):
        return False
    finally:
        try:
            os.unlink(name)
        except OSError:
            pass


def requires_ok(module: str) -> bool:
    """Static require-allowlist gate mirroring the evaluator's module
    allowlist, so fills that import disallowed modules are skipped early."""
    found = re.findall(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)", module)
    return all(name in ALLOWED_REQUIRES for name in found)


def strip_comment_echo(fill: str, role: str) -> str:
    """Trim a fill that echoes the repair instructions back as its leading
    comment lines (measured on sweeps 8-9). Trimming only, in the spirit of
    the established delimiter normalization; no model logic is replaced."""
    marker = "#" if role == "logic" else "//"
    if role == "css":
        return fill
    lines = fill.splitlines()
    head = [l for l in lines[:3] if l.strip()]
    if len(head) >= 2 and all(l.strip().startswith(marker) for l in head):
        for index, line in enumerate(lines):
            text = line.strip()
            if text and not text.startswith(marker):
                return "\n".join(lines[index:])
        return ""
    return fill


def splice(module: str, lo: int, hi: int, fill: str) -> str:
    """Replace 1-based inclusive lines lo..hi of the model's own module with
    the model's own FIM fill. Pure string surgery: no harness bytes enter."""
    lines = module.splitlines(keepends=True)
    prefix = "".join(lines[:lo - 1])
    suffix = "".join(lines[hi:])
    body = fill.rstrip()
    if body and suffix and not body.endswith("\n"):
        body += "\n"
    return prefix + body + suffix


def error_line(module: str, error: str):
    match = TRANSFORM_LINE.search(str(error)) or FRAME_LINE.search(str(error))
    if not match:
        return None
    line = int(match.group(1))
    return line if 1 <= line <= len(module.splitlines()) else None


def const_window(module, error):
    ln = error_line(module, error)
    if ln is None or "Assignment to constant variable" not in str(error):
        return None
    lines = module.splitlines()
    assign = re.search(r"([A-Za-z_$][\w$]*)\s*=[^=]", lines[ln - 1])
    if not assign:
        return None
    name = assign.group(1)
    decl = next((i for i, l in enumerate(lines, 1)
                 if re.search(r"\bconst\s+" + re.escape(name) + r"\s*=", l)), None)
    if decl is not None:
        lo, hi = max(1, decl - 1), min(len(lines), decl + 1)
        focus = ("Your own module declares the variable '%s' with const in the marked "
                 "window, but line %d reassigns it (%r), which throws TypeError: "
                 "Assignment to constant variable. Rewrite the window so every variable "
                 "that is reassigned later is declared with let instead of const. Keep "
                 "all other lines unchanged. " % (name, ln, lines[ln - 1].strip())
                 + STORE_RESERVED)
    else:
        lo, hi = max(1, ln - 2), min(len(lines), ln + 2)
        focus = ("Line %d of your own module (%r) throws TypeError: Assignment to "
                 "constant variable. Rewrite the marked window so no const variable is "
                 "ever reassigned: declare reassigned variables with let, or mutate the "
                 "existing array/object instead of reassigning it. Keep all other lines "
                 "unchanged. " % (ln, lines[ln - 1].strip()) + STORE_RESERVED)
    return lo, hi, focus


def transform_window(module, error):
    match = TRANSFORM_LINE.search(str(error)) or FRAME_LINE.search(str(error))
    if not match:
        return None
    lines = module.splitlines()
    ln = int(match.group(1))
    if ln > len(lines):
        # Errors reported past the last line mean an unclosed construct at the
        # end of the module (e.g. missing closing brace): repair the tail.
        ln = len(lines)
        lo, hi = max(1, len(lines) - 5), len(lines)
    else:
        lo, hi = max(1, ln - 3), min(len(lines), ln + 2)
    focus = ("The evaluator reports a syntax error at line %d of your own module: %s. "
             "The marked window contains the broken region. Rewrite the window so the "
             "whole module compiles and every string, brace, bracket and tag closes. "
             "Keep all other lines unchanged."
             % (ln, " ".join(str(error).split())[:220]))
    return lo, hi, focus


def _handler_bounds(lines, method, path, cap=30):
    pattern = re.compile(r"\bapp\." + method + r"\(\s*['\"]"
                         + re.escape(path) + r"['\"]")
    start = next((i for i, l in enumerate(lines, 1) if pattern.search(l)), None)
    if start is None:
        return None
    depth, end = 0, start
    for i in range(start, min(len(lines), start + cap) + 1):
        depth += lines[i - 1].count("(") - lines[i - 1].count(")")
        end = i
        if depth <= 0:
            break
    return start, end


def route_windows(module, error):
    """Surgical per-route repair windows, anchored on the exact statements the
    public check message names. The model compresses large windows (a 30-line
    window gets a 5-line fill that drops handlers), so every window here is a
    handful of statement lines. The delete check also emits a POST response
    window: the delete check consumes res.body.item.id from the post handler,
    so the post envelope must be repaired for delete to ever pass."""
    windows = []
    lines = module.splitlines()

    def bounds(method, path, cap=30):
        return _handler_bounds(lines, method, path, cap)

    def window_around(anchor, before, after, focus):
        lo = max(1, anchor - before)
        hi = min(len(lines), anchor + after)
        return lo, hi, focus

    for part in str(error).split(" | "):
        head = re.match(r"\s*(\w+)\s*->\s*(.*)", part, re.S)
        if not head:
            continue
        name, message = head.group(1), head.group(2)
        route = CHECK_ROUTES.get(name)
        if not route:
            continue
        method, path = route
        span = bounds(method, path)
        if span is None:
            continue
        h_lo, h_hi = span
        region = list(enumerate(lines, 1))[h_lo - 1:h_hi]
        flat = " ".join(message.split())[:200]
        if name in ("delete", "post", "post_invalid"):
            create_line = next((i for i, l in region if "store.create(" in l), None)
            if create_line is not None:
                windows.append(window_around(
                    create_line, 1, 2,
                    "The POST /api/entries response construction (marked window) is "
                    "wrong. The public check requires POST /api/entries to return "
                    "201 with body EXACTLY {item: store.create(req.body)} - the "
                    "created entry object itself, so item.id stays the string id. "
                    "The DELETE test reads res.body.item.id from this response and "
                    "calls DELETE /api/entries/<that id>, so a spread like "
                    "{ id, ...entry } (which makes item.id an object) can never "
                    "pass. Rewrite the window as: const item = "
                    "store.create(req.body); res.status(201).json({ item }); and "
                    "keep the invalid-input catch returning 400 {error: "
                    "'Invalid entry'} when store.create throws."))
            if name == "delete":
                status4 = next((i for i, l in region
                                if re.search(r"status\(4\d\d", l)), None)
                if status4 is not None:
                    anchor = status4
                    before = 0
                    for j in range(status4 - 1, max(h_lo - 1, status4 - 12) - 1, -1):
                        if re.search(r"\bif\s*\(", lines[j - 1]):
                            before = status4 - j
                            break
                    windows.append(window_around(
                        anchor, before, 2,
                        "The DELETE /api/entries/:id handler (marked window) returns "
                        "a 404/4xx branch. The public check requires HTTP 200 with "
                        "body EXACTLY {deleted: store.delete(req.params.id)} - ALWAYS "
                        "200, even when nothing was deleted, never 404, response key "
                        "named deleted. Rewrite the window as: res.status(200)."
                        "json({ deleted: store.delete(req.params.id) }); and remove "
                        "any if/else that returns a different status."))
                else:
                    res_line = next((i for i, l in region if re.search(r"res\.", l)),
                                    None)
                    if res_line is not None:
                        windows.append(window_around(
                            res_line, 1, 1,
                            "The DELETE /api/entries/:id response (marked window) "
                            "fails the public check: " + flat
                            + ". Required: HTTP 200 with body EXACTLY {deleted: "
                              "store.delete(req.params.id)} - ALWAYS 200, never 404, "
                              "response key named deleted."))
        elif name == "projects":
            set_line = next((i for i, l in region
                             if "new Set(" in l or "store.list()" in l), h_lo)
            windows.append(window_around(
                set_line, 0, 2,
                "The GET /api/projects handler (marked window) must return 200 with "
                "body EXACTLY {projects: sorted distinct project NAME strings}. "
                "store.list() returns entry OBJECTS: map them to their project "
                "field first. Correct shape: const projects = "
                "Array.from(new Set(store.list().map((entry) => "
                "entry.project))).sort(); res.status(200).json({ projects });"))
        elif name == "summary":
            proc_line = next((i for i, l in region if "processor(" in l), h_lo)
            windows.append(window_around(
                proc_line, 1, 1,
                "The GET /api/summary handler (marked window) must return 200 with "
                "the processor result as the WHOLE response body, exactly "
                "processor({ entries: store.list() }) - no wrapper key. Correct "
                "shape: res.status(200).json(processor({ entries: "
                "store.list() }));"))
        else:
            res_line = next((i for i, l in region if re.search(r"res\.", l)), None)
            if res_line is not None:
                windows.append(window_around(
                    res_line, 1, 1,
                    "The %s %s response (marked window) fails the public check: %s. "
                    "Rewrite the window so the route returns the exact required "
                    "status and envelope."
                    % (method.upper(), path, flat)))
    return windows[:5]


def logic_return_window(module, error):
    """Semantic anchors for the two measured logic failure shapes: correct
    values returned as a tuple, and incomplete stub bodies."""
    error = str(error)
    lines = module.splitlines()
    if "received [" in error or "received (" in error:
        rets = [i for i, l in enumerate(lines, 1) if re.match(r"\s*return\b", l)]
        if not rets:
            return None
        lo, hi = max(1, rets[0] - 1), min(len(lines), rets[-1] + 1)
        focus = ("Your function computes the right values but RETURNS them as "
                 "separate values (a tuple). Return ONE dict with EXACTLY these "
                 "keys: total_minutes, by_project, by_day, active_projects, "
                 "busiest_day. Shape: return {'total_minutes': ..., 'by_project': "
                 "..., 'by_day': ..., 'active_projects': ..., 'busiest_day': ...}.")
        return lo, hi, focus
    if ("received null" in error or "received 0" in error or "received 0.0" in error
            or "KeyError" in error or "received " in error):
        lo, hi = 2, len(lines)
        focus = ("Your function body is an incomplete stub. Write the complete "
                 "body: read the list payload['entries']; when it is missing or "
                 "empty return {'total_minutes': 0, 'by_project': {}, 'by_day': "
                 "{}, 'active_projects': 0, 'busiest_day': None}; otherwise "
                 "accumulate by_project and by_day dicts, total_minutes, "
                 "active_projects (distinct projects) and busiest_day (date with "
                 "the highest total minutes; ties -> earliest date string; None "
                 "when empty); return ONE dict with EXACTLY the keys "
                 "total_minutes, by_project, by_day, active_projects, busiest_day. "
                 "Never a tuple, never separate values.")
        return lo, hi, focus
    return None


STORE_RESERVED = ("NEVER name a function 'delete' - it is a reserved word in "
                   "JavaScript and makes the module fail to parse. Name the "
                   "implementation deleteEntry or removeEntry and expose it in the "
                   "returned object as { list: list, create: create, delete: "
                   "deleteEntry }.")


def store_read_window(module, error):
    """Semantic anchor: readFileSync that throws ENOENT on a missing file."""
    if "ENOENT" not in str(error):
        return None
    lines = module.splitlines()
    read_line = next((i for i, l in enumerate(lines, 1) if "readFileSync" in l), None)
    if read_line is None:
        return None
    lo, hi = max(1, read_line - 2), min(len(lines), read_line + 2)
    focus = ("Your own readFileSync (marked window) throws ENOENT when the JSON "
             "file does not exist yet, but the store must work before the file "
             "exists. Rewrite the window so a missing or unreadable file is "
             "treated as an empty array: wrap the read in try { ... } catch "
             "(error) { return []; }, or check fs.existsSync(filePath) first. "
             "Keep every other behavior. " + STORE_RESERVED)
    return lo, hi, focus


def ui_effect_window(module, error):
    """Rewrite window over the model's own load effect so it keeps existing
    fetches AND adds the missing wiring, instead of regressing features."""
    match = UI_LACKS.search(str(error))
    if not match:
        return None
    missing = [x for x in match.group(1).split(", ") if x]
    if not missing:
        return None
    lines = module.splitlines()
    start = next((i for i, l in enumerate(lines, 1) if "useEffect" in l), None)
    if start is None:
        return None
    depth, end = 0, start
    for i in range(start, min(len(lines), start + 40) + 1):
        depth += lines[i - 1].count("(") - lines[i - 1].count(")")
        end = i
        if depth <= 0:
            break
    focus = ("Your own load effect (marked window) is missing required pieces: "
             + "; ".join(missing[:6])
             + ". Rewrite the window so it keeps loading /api/entries AND ALSO "
               "adds every missing piece (the fetch to /api/summary, the POST "
               "and DELETE requests with their handlers, the demo dataset "
               "entries and the project filter), keeping the offline demo "
               "fallback and every existing feature working.")
    return start, end, focus


def ui_extend_window(module, error):
    """Anchor at the end of the model's own component body, just before its
    return JSX: the fill keeps the existing lines and ADDS the missing
    request handlers after them. Measured: whole-module UI regeneration
    regresses features and truncates; small additive windows do not."""
    match = UI_LACKS.search(str(error))
    if not match:
        return None
    missing = [x for x in match.group(1).split(", ") if x]
    if not missing:
        return None
    lines = module.splitlines()
    ret = next((i for i, l in enumerate(lines, 1) if re.search(r"\breturn\s*\(", l)), None)
    if ret is None:
        ret = next((i for i, l in enumerate(lines, 1) if "<div" in l or "<form" in l), None)
    if ret is None or ret < 3:
        return None
    lo, hi = max(1, ret - 2), ret - 1
    wants = []
    if any("summary endpoint" in m for m in missing):
        wants.append("a fetch to /api/summary inside the load flow (for example "
                     "const summaryResponse = await fetch('/api/summary'); "
                     "if (summaryResponse.ok) setSummary(await "
                     "summaryResponse.json()); on failure keep the offline "
                     "demo summary)")
    if any("POST request" in m for m in missing):
        wants.append("an addEntry function using POST (for example async "
                     "function addEntry(event) { event.preventDefault(); "
                     "await fetch('/api/entries', { method: 'POST', headers: "
                     "{ 'Content-Type': 'application/json' }, body: "
                     "JSON.stringify(form) }); load(); })")
    if any("DELETE request" in m for m in missing):
        wants.append("a removeEntry function using DELETE (for example async "
                     "function removeEntry(id) { await fetch('/api/entries/' "
                     "+ id, { method: 'DELETE' }); load(); })")
    if any("project filter" in m for m in missing):
        wants.append("a filter variable with React.useState('') and a "
                     "filtered list using entries.filter((entry) => "
                     "entry.project.includes(filter))")
    if any("demo dataset entry" in m for m in missing):
        wants.append("the fixed offline demo entries array with the three "
                     "entries api-server 95 2026-11-03, mobile-ui 140 "
                     "2026-11-04 and docs 60 2026-11-04")
    if not wants:
        wants.append("every missing piece named in the check feedback")
    focus = ("Your own UI module is missing: " + "; ".join(missing[:6])
             + ". The marked window is the end of your own component body, "
               "just before your return JSX. Rewrite the window so it KEEPS "
               "its existing lines and ADDS right after them (still before "
               "the return): " + "; ALSO ".join(wants)
             + ". Keep every existing feature and the offline demo fallback "
               "working, and keep the module compact.")
    return lo, hi, focus


def ui_input_window(module, error):
    """Anchor on the model's own value= inputs that lack onChange handlers."""
    match = UI_LACKS.search(str(error))
    if not match or "controlled input" not in match.group(1):
        return None
    lines = module.splitlines()
    inputs = [i for i, l in enumerate(lines, 1)
              if re.search(r"<input[^>]*value=", l)]
    if not inputs:
        return None
    lo, hi = max(1, inputs[0] - 1), min(len(lines), inputs[-1] + 1)
    focus = ("Your own JSX inputs (marked window) use value= without a "
             "controlled onChange handler, so the controlled-input check can "
             "never pass. Rewrite the window so EVERY input keeps its value= "
             "AND gains its own onChange handler, for example: <input "
             "value={form.project} onChange={(event) => setForm({ ...form, "
             "project: event.target.value })} />. Keep every other attribute "
             "and line unchanged.")
    return lo, hi, focus


def ui_targeted_windows(module, error):
    """Targeted windows on the model's own named handlers, derived from which
    wiring pattern the public check reports missing. Generic before-the-return
    anchors landed inside unrelated handlers, so each window here starts at a
    concrete construct of the model's own module."""
    error = str(error)
    lines = module.splitlines()

    def fn_bounds(start, cap=40):
        depth = 0
        for j in range(start, min(len(lines), start + cap) + 1):
            depth += lines[j - 1].count("{") - lines[j - 1].count("}")
            if depth <= 0 and j > start:
                return start, j
        return start, min(len(lines), start + cap)

    def find(pred):
        return next((i for i in range(1, len(lines) + 1) if pred(lines[i - 1])), None)

    def back_to_handler(line):
        for j in range(line, 0, -1):
            if re.search(r"(const|let|var|function)\s+\w+\s*[=(]", lines[j - 1]):
                return j
        return line

    windows = []
    load_line = find(lambda l: "fetch(" in l)
    if load_line is not None:
        start = back_to_handler(load_line)
        lo, hi = fn_bounds(start)
        focus = ("Your own load function (marked window) only fetches /api/entries "
                 "and has no failure handling, so the required offline demo mode "
                 "can never trigger. Rewrite the window so it: (1) keeps fetching "
                 "/api/entries and on failure or a non-ok response calls "
                 "setOffline(true); (2) ALSO fetches /api/summary and stores it "
                 "with setSummary, with the same failure handling. Keep the same "
                 "function name so the rest of your module keeps working.")
        windows.append((start, hi, focus))
    if "POST request" in error:
        sub = find(lambda l: "preventDefault" in l)
        if sub is not None:
            start = back_to_handler(sub)
            lo, hi = fn_bounds(start)
            focus = ("Your own submit handler (marked window) only changes local "
                     "state and never sends the required POST request. Rewrite the "
                     "window so it sends POST /api/entries with the form as JSON "
                     "and then reloads, falling back to offline mode on failure: "
                     "const response = await fetch('/api/entries', { method: "
                     "'POST', headers: { 'Content-Type': 'application/json' }, "
                     "body: JSON.stringify(form) }); if (!response.ok) throw new "
                     "Error('offline'); load(); ... catch (error) { "
                     "setOffline(true); }. Keep the same function name.")
            windows.append((start, hi, focus))
    if "DELETE request" in error:
        dele = find(lambda l: re.search(r"\bhandleDelete\s*[=(]", l))
        if dele is not None:
            lo, hi = fn_bounds(dele)
            focus = ("Your own delete handler (marked window) only filters local "
                     "state and never sends the required DELETE request. Rewrite "
                     "the window so it sends DELETE /api/entries/:id and then "
                     "reloads, falling back to offline mode on failure: const "
                     "response = await fetch('/api/entries/' + id, { method: "
                     "'DELETE' }); if (!response.ok) throw new Error('offline'); "
                     "load(); ... catch (error) { setOffline(true); }. Keep the "
                     "same function name.")
            windows.append((dele, hi, focus))
    if "demo dataset entry" in error or "offline badge" in error:
        off = find(lambda l: "offline ?" in l or ("offline" in l and "?" in l))
        if off is not None:
            focus = ("Your own offline branch (marked window) only renders a "
                     "heading. The required OFFLINE DEMO MODE must render a "
                     "visible badge containing the word offline, the fixed built-in "
                     "demo entries (api-server 95 min 2026-11-03, mobile-ui 140 min "
                     "2026-11-04, docs 60 min 2026-11-04) and a summary showing "
                     "the total minutes 295 as a plain number. Rewrite the window "
                     "so offline mode shows all of that, for example from const "
                     "demoEntries = [{ project: 'api-server', minutes: 95, date: "
                     "'2026-11-03', note: 'routes' }, { project: 'mobile-ui', "
                     "minutes: 140, date: '2026-11-04', note: 'screens' }, "
                     "{ project: 'docs', minutes: 60, date: '2026-11-04', note: "
                     "'guide' }]; rendered when offline is true, with the badge, "
                     "the three entries and the number 295.")
            windows.append((max(1, off - 1), min(len(lines), off + 2), focus))
    return windows[:4]


def windows_for(role, module, error):
    if role == "api":
        found = route_windows(module, error)
        if found:
            return found[:5]
        w = transform_window(module, error)
        return [w] if w else []
    if role == "store":
        w = (store_read_window(module, error) or const_window(module, error)
             or transform_window(module, error))
        return [w] if w else []
    if role == "logic":
        w = logic_return_window(module, error) or transform_window(module, error)
        return [w] if w else []
    if role == "ui":
        w = transform_window(module, error)
        if w:
            return [w]
        return ui_targeted_windows(module, error)
    w = transform_window(module, error)
    return [w] if w else []


def store_focus_lines(error):
    error = str(error)
    if "ENOENT" in error or "Expected identifier" in error:
        return ("// CURRENT FOCUS - your store fails on two known pitfalls:\n"
                "// 1. A missing data file must be treated as an empty array: wrap\n"
                "//    the fs.readFileSync in try { ... } catch (error) { return []; }\n"
                "//    or check fs.existsSync(filePath) first - never let ENOENT escape.\n"
                "// 2. " + STORE_RESERVED + "\n")
    return ""


def logic_focus_lines(error):
    error = str(error)
    if "received [" in error or "received (" in error:
        return ("# CURRENT FOCUS - your function returned SEPARATE VALUES (a tuple).\n"
                "# Return ONE single dict with EXACTLY the keys: total_minutes,\n"
                "# by_project, by_day, active_projects, busiest_day.\n")
    if "received null" in error or re.search(r"received 0(\.0)?[,.]", error):
        return ("# CURRENT FOCUS - your function body is an incomplete stub (it returns\n"
                "# null or a constant). Write the COMPLETE body: iterate the entries,\n"
                "# accumulate by_project and by_day dicts, count active_projects, pick\n"
                "# busiest_day (ties -> earliest date string, empty -> None), and return\n"
                "# ONE dict with the five exact keys. Never a tuple.\n")
    return ""


def ui_focus_lines(error):
    match = UI_LACKS.search(str(error))
    if not match:
        return ""
    items = [x.strip() for x in match.group(1).split(", ") if x.strip()][:3]
    if not items:
        return ""
    comment = "// CURRENT FOCUS - your UI is still missing these required pieces:\n"
    comment += "".join("//   - %s\n" % item for item in items)
    comment += ("// Add every missing piece listed in the check feedback, keep the pieces\n"
                "// that already work, keep exactly five React.useState hooks (entries,\n"
                "// form, filter, summary, offline) and end with module.exports = App;\n")
    return comment


def fim_instructions(role, window):
    lo, hi, focus = window
    comment = "#" if role == "logic" else "/* " if role == "css" else "// "
    end = " */" if role == "css" else ""
    text = comment + "REPAIR YOUR OWN " + role.upper() + " MODULE." + end + "\n"
    for line in re.findall(r".{1,110}(?:\s|$)", focus):
        text += comment + line.strip() + end + "\n"
    text += (comment + "The gap below is lines %d-%d of YOUR OWN module. The code before"
             % (lo, hi) + end + "\n")
    text += (comment + "and after the gap is your own unchanged code. Fill ONLY the gap"
             + end + "\n")
    text += (comment + "so the whole module passes the public check. Output only the gap"
             + end + "\n")
    text += comment + "code itself, no explanation, no fences." + end + "\n"
    return text


def metric(result, role):
    entry = result["modules"][role]
    if role == "ui":
        if entry["passed"]:
            wiring = UI_WIRING_TOTAL
        else:
            match = UI_LACKS.search(str(entry["error"] or ""))
            wiring = (UI_WIRING_TOTAL - len([x for x in match.group(1).split(", ") if x])
                      if match else 0)
        return (int(entry["passed"]),
                sum(bool(result["checks"].get(x)) for x in ROLE_CHECKS["ui"]),
                wiring, int(entry["syntax_valid"]))
    if role == "logic":
        error = str(entry["error"] or "")
        # Distance-from-trivial refinement: a candidate that already computes
        # the correct VALUES but returns them as a tuple is one surgical FIM
        # repair away from passing; a null/constant stub is not. This only
        # orders runner-side candidate selection; the worker checks stay
        # byte-identical and a tuple still FAILS every real check.
        tuple_close = 1 if ("received [" in error or "received (" in error) else 0
        return (int(entry["passed"]),
                sum(bool(result["checks"].get(x)) for x in ROLE_CHECKS["logic"]),
                tuple_close, int(entry["syntax_valid"]))
    return (int(entry["passed"]),
            sum(bool(result["checks"].get(x)) for x in ROLE_CHECKS[role]),
            int(entry["syntax_valid"]))


def total_score(result):
    return (int(bool(result["integrated"])),
            sum(int(bool(result["modules"][r]["passed"])) for r in ROLES),
            int(result["completed_checks"]),
            sum(int(bool(result["modules"][r]["syntax_valid"])) for r in ROLES))


def ui_insert_window(module, error):
    """Insertion anchor for missing UI wiring: inside the model's own
    load-effect / fetch area, so its own code gains the missing pieces while
    every existing feature line stays present in the FIM fill."""
    match = UI_LACKS.search(str(error))
    if not match:
        return None
    missing = [x for x in match.group(1).split(", ") if x]
    if not missing:
        return None
    lines = module.splitlines()
    anchor = 0
    for i, line in enumerate(lines, 1):
        if "fetch(" in line or "useEffect" in line:
            anchor = i
    if anchor == 0:
        for i, line in enumerate(lines, 1):
            if "useState" in line:
                anchor = i
    if anchor == 0:
        anchor = min(len(lines), 10)
    lo = min(len(lines), anchor + 1)
    hi = min(len(lines), lo + 2)
    focus = ("Your own UI module is missing required pieces: "
             + "; ".join(missing[:5])
             + ". The marked window sits inside your own load-effect area. "
               "Rewrite the window so it KEEPS the existing working code and ADDS "
               "every missing piece (for example the fetch to /api/summary and the "
               "POST and DELETE requests with their handlers), keeping every "
               "existing feature and the offline demo mode working.")
    return lo, hi, focus


def _ui_onchange_extend(window, module):
    """Second-order UI coupling: the wiring check requires a controlled input
    (onChange=) inside the JSX; when the model's own return JSX contains value=
    inputs without onChange handlers, extend the effect window to the whole
    module so one fill can add them."""
    if window is None:
        return None
    lines = module.splitlines()
    has_onchange = any("onChange" in line for line in lines)
    has_value = any(re.search(r"value=", line) for line in lines)
    if has_onchange or not has_value:
        return window
    lo, hi, focus = window
    focus = focus + (" The JSX inputs use value= but no onChange= handler: add a "
                     "controlled onChange handler to every input (for example "
                     "onChange={(event) => setForm({...form, project: "
                     "event.target.value})}), otherwise the controlled-input "
                     "check can never pass.")
    return 1, len(lines), focus


def job_estimate(role, kind):
    """Rough generation+evaluation cost in seconds, used only to decide
    whether a job fits in the remaining invocation budget."""
    if kind.startswith("fim"):
        return 90 if role == "ui" else 70
    return 150 if role == "ui" else 160


def plan_role(role, module, error, sweep):
    """Candidate schedule for one failing role in one sweep.

    FIM jobs carry a window index; windows are recomputed at execution time
    against the currently selected module, so a mid-sweep acceptance can never
    leave a stale line-anchored window from an older module. UI gets surgical
    FIM windows only: every measured whole-module UI regeneration truncated
    at the token cap or regressed features."""
    plan = []
    windows = windows_for(role, module, error)
    if windows:
        # Compound first: several checks (e.g. delete) can only pass once a
        # DIFFERENT route's envelope is also repaired, so single-window
        # candidates tie the metric and never get selected.
        plan.append(("fim-compound", None))
        plan.append(("fim-greedy", 0))
        plan.append(("fim-sample", 0))
        plan.append(("fim-sample-2", 0))
    if role == "ui":
        if not windows:
            plan.append(("focus-error-only", None))
        return plan
    plan.append(("focus-error-only", None))
    plan.append(("focus-error-only-2", None))
    if sweep % 2 == 1:
        plan.append(("feedback-repair", None))
    return plan


def snapshot(round_, selected, public, elapsed, tokens, fim_stats):
    return {"round": round_,
            "modules": dict(selected),
            "modules_sha256": {r: hashlib.sha256(selected[r].encode()).hexdigest()
                               for r in ROLES},
            "public": {"integrated": public["integrated"],
                       "passed": {r: public["modules"][r]["passed"] for r in ROLES},
                       "checks": dict(public["checks"]),
                       "completed_checks": public["completed_checks"],
                       "failure_reasons": list(public.get("failure_reasons", []))},
            "elapsed_seconds": round(elapsed, 1), "output_tokens": tokens,
            "fim_attempts": fim_stats["attempts"], "fim_accepted": fim_stats["accepted"]}


def rebuild(attempts, index, role):
    """Reconstruct any recorded candidate from the attempts log alone."""
    entry = attempts[index]
    origin = entry["origin"]
    if origin["type"] == "whole":
        return PREFIX[role] + entry["raw"]
    base = rebuild(attempts, origin["base"], role)
    if hashlib.sha256(base.encode()).hexdigest() != origin["base_sha256"]:
        raise ValueError("FIM base hash mismatch in lineage: " + role)
    if "ops" in origin:
        ops, fills = origin["ops"], entry["fills"]
    else:  # legacy single-splice attempt recorded before compound jobs
        ops = [{"lo": origin["lo"], "hi": origin["hi"],
                "base_sha256": origin["base_sha256"]}]
        fills = [entry["raw"]]
    module = base
    for op, fill in zip(ops, fills):
        if hashlib.sha256(module.encode()).hexdigest() != op["base_sha256"]:
            raise ValueError("Compound FIM op base hash mismatch: " + role)
        module = splice(module, op["lo"], op["hi"], fill)
    return module


def verify_lineage(state):
    if set(state["selected"]) != set(ROLES) or set(state["baseline"]) != set(ROLES):
        raise ValueError("Corrupt lineage modules")
    for role in ROLES:
        accepted = [i for i, a in enumerate(state["attempts"])
                    if a["role"] == role and a.get("accepted")]
        base = next(i for i, a in enumerate(state["attempts"])
                    if a["role"] == role and a["stage"] == "baseline")
        source = state["baseline"][role]
        for i in accepted:
            source = rebuild(state["attempts"], i, role)
        if source != state["selected"][role]:
            raise ValueError("Lineage replay mismatch: " + role)


def save_state(root: Path, state):
    verify_lineage(state)
    save_json(root / "state.json", state)


def parity_check():
    """Re-validate the local evaluator against Session031's Docker record."""
    try:
        prior = json.loads(Path("experiments/session031_selfrepair_predictions.json")
                           .read_text(encoding="utf8"))
        report = json.loads(Path("experiments/session031_selfrepair_report.json")
                            .read_text(encoding="utf8"))
        local = evaluate(prior["selected"], PUBLIC, "public")
        recorded = report["final"]["public"]
        mismatch = []
        for role in ROLES:
            if bool(recorded["modules"][role]["passed"]) != bool(
                    local["modules"][role]["passed"]):
                mismatch.append(role + ".passed")
        for key in set(recorded["checks"]) | set(local["checks"]):
            if bool(recorded["checks"].get(key)) != bool(local["checks"].get(key)):
                mismatch.append("check:" + key)
        return {"validated": not mismatch,
                "compared": "session031 final public record (Docker) vs local",
                "mismatches": mismatch}
    except (OSError, ValueError, KeyError) as exc:
        return {"validated": False, "error": str(exc)}


def run(args):
    root = Path(args.output_dir)
    started = time.monotonic()
    if args.resume:
        state = json.loads((Path(args.state) if Path(args.state).is_file()
                            else root / "state.json").read_text(encoding="utf8"))
        for key in ("sweep", "selected", "baseline", "public", "attempts",
                    "tokens", "elapsed", "rounds", "pending", "last_try",
                    "fim_stats", "baseline_public"):
            if key not in state:
                raise ValueError("Incomplete resume state: " + key)
        # v2 pending schema (window_index instead of absolute windows): drop
        # queued v1 jobs; the next sweep re-plans against the selected modules.
        state["pending"] = [j for j in state["pending"] if j.get("v") == 2]
        # v8: drop queued whole-module UI jobs - every measured one truncated
        # or regressed features; UI budget goes to surgical FIM windows.
        state["pending"] = [j for j in state["pending"]
                             if not (j.get("role") == "ui"
                                     and not j.get("kind", "").startswith("fim"))]
    else:
        if root.exists() and any(root.iterdir()):
            raise FileExistsError("Prior output exists")
        state = {"sweep": 0, "selected": {}, "baseline": {}, "public": None,
                 "attempts": [], "tokens": 0, "elapsed": 0.0, "rounds": [],
                 "pending": [], "last_try": {}, "fim_stats": {"attempts": 0, "accepted": 0},
                 "baseline_public": None}
    root.mkdir(parents=True, exist_ok=True)
    entry_elapsed = state["elapsed"]

    def tick():
        state["elapsed"] = entry_elapsed + (time.monotonic() - started)
        return state["elapsed"]

    model, tokenizer = load_model()
    count = sum(p.numel() for p in model.parameters())
    if count != MODEL_PARAMETER_COUNT:
        raise RuntimeError("Unexpected model capacity")

    self_memory = load_self_memory(SELF_MEMORY_PATH) if args.self_memory else {}
    if self_memory:
        print(json.dumps({"self_memory_roles": sorted(self_memory)}), flush=True)

    def fresh_plan():
        state["pending"] = []
        for i, role in enumerate(ROLES):
            if state["public"] is None or state["public"]["modules"][role]["passed"]:
                continue
            selected_error = (state["public"]["modules"][role]["error"]
                              or "Public contract failed")
            for kind, window_index in plan_role(role, state["selected"][role],
                                                selected_error, state["sweep"]):
                state["pending"].append({"role": role, "kind": kind,
                                         "window_index": window_index, "v": 2})

    if state["public"] is None:
        for i, role in enumerate(ROLES):
            head = prompt(role)
            raw, n = generate_one(model, tokenizer, head, max_tokens=LIMITS[role],
                                  seed=BASE_SEED + i, stochastic=False)
            state["baseline"][role] = PREFIX[role] + raw
            state["attempts"].append({"stage": "baseline", "sweep": 0, "round": 0,
                                      "role": role, "prompt": head, "raw": raw,
                                      "output_tokens": n, "accepted": True,
                                      "candidate_source": state["baseline"][role],
                                      "origin": {"type": "whole", "base": None}})
            state["tokens"] += n
            print(json.dumps({"baseline": role, "tokens": n}), flush=True)
        state["selected"] = dict(state["baseline"])
        state["public"] = evaluate(state["baseline"], PUBLIC, "public")
        state["baseline_public"] = state["public"]
        state["rounds"].append(snapshot(0, state["selected"], state["public"],
                                        tick(), state["tokens"],
                                        state["fim_stats"]))
        save_state(root, state)
        print(json.dumps({"sweep": 0, "score": total_score(state["public"]),
                          "passed": {r: state["public"]["modules"][r]["passed"]
                                     for r in ROLES}}), flush=True)

    finished = False
    while not finished:
        if not state["pending"]:
            if all(state["public"]["modules"][r]["passed"] for r in ROLES):
                finished = True
                break
            if state["sweep"] >= args.rounds:
                finished = True
                break
            if state["elapsed"] > args.wall_budget:
                finished = True
                break
            state["sweep"] += 1
            fresh_plan()
            if not state["pending"]:  # everything passes
                continue
        next_kind = state["pending"][0]["kind"] if state["pending"] else None
        next_role = state["pending"][0]["role"] if state["pending"] else None
        spent = time.monotonic() - started
        if (spent > args.time_budget
                or (next_kind and spent + job_estimate(next_role, next_kind)
                    > args.time_budget + 120)):
            tick()
            save_state(root, state)
            print(json.dumps({"paused": True, "sweep": state["sweep"],
                              "pending": len(state["pending"]),
                              "elapsed_total": round(state["elapsed"], 1)}),
                  flush=True)
            del model
            return
        job = state["pending"].pop(0)
        role = job["role"]
        sweep = state["sweep"]
        i = ROLES.index(role)
        recent = state["last_try"].get(role)
        if recent is not None:
            previous_src, previous_err = recent
        else:
            previous_src = state["selected"][role]
            previous_err = (state["public"]["modules"][role]["error"]
                            or "Public contract failed")
        own_example = self_memory.get(role, "")
        if job["kind"].startswith("fim"):
            # FIM surgery always targets the CURRENTLY SELECTED module: repairs
            # of rejected candidates cannot improve the selected metric.
            selected_module = state["selected"][role]
            selected_error = (state["public"]["modules"][role]["error"]
                              or "Public contract failed")
            windows = windows_for(role, selected_module, selected_error)
            if job["kind"] == "fim-compound":
                window_list = list(windows)
            else:
                index = job.get("window_index") or 0
                if index >= len(windows):
                    continue  # window no longer applies to the selected module
                window_list = [windows[index]]
            if not window_list:
                continue
            base_module = selected_module
            base_index = next((idx for idx in range(len(state["attempts"]) - 1, -1, -1)
                               if state["attempts"][idx]["role"] == role
                               and state["attempts"][idx].get("candidate_source")
                               == base_module), None)
            if base_index is None:
                # Should be unreachable: every candidate_source is archived.
                continue
            fills, ops, compound_tokens = [], [], 0
            current = base_module
            for window in window_list:
                lo, hi, focus = window
                instructions = fim_instructions(role, (lo, hi, focus))
                span = hi - lo + 1
                if role == "ui":
                    # Additive windows stay small but their fills add whole
                    # handlers, so ui fills need real headroom.
                    cap = 460
                elif role == "logic":
                    # Whole-body window: the fill is a complete function body,
                    # far larger than the tiny stub it replaces.
                    cap = 340
                elif role == "store":
                    cap = min(1100, 130 + 46 * span)
                else:
                    cap = min(700, 110 + 42 * span)
                stochastic = job["kind"] in ("fim-sample", "fim-sample-2",
                                              "fim-compound")
                variant = (3 if job["kind"] == "fim-sample-2"
                           else 2 if stochastic else 1)
                seed = (BASE_SEED + 500000 + sweep * 100 + i * 10
                        + variant * 7 + len(ops))
                lines = current.splitlines(keepends=True)
                prefix_text = "".join(lines[:lo - 1])
                suffix_text = "".join(lines[hi:])
                fill, n = fim_generate(model, tokenizer, instructions, prefix_text,
                                       suffix_text, max_tokens=cap, seed=seed,
                                       stochastic=stochastic)
                state["tokens"] += n
                compound_tokens += n
                state["fim_stats"]["attempts"] += 1
                fill = strip_comment_echo(trim_fill(fill, suffix_text), role)
                if not fill.strip():
                    continue
                spliced = splice(current, lo, hi, fill)
                if not syntax_ok(spliced, role) or not requires_ok(spliced):
                    continue  # skip a malformed fill, keep the valid ones
                ops.append({"lo": lo, "hi": hi,
                            "base_sha256": hashlib.sha256(current.encode()).hexdigest()})
                fills.append(fill)
                current = spliced
            if not fills:
                continue
            challenger = dict(state["selected"])
            challenger[role] = current
            stage = job["kind"]
            origin = {"type": "fim", "base": base_index, "ops": ops}
            fill = fills[0]
            n = compound_tokens
            fim_window = [ops[0]["lo"], ops[-1]["hi"]]
        else:
            if job["kind"].startswith("focus-error-only"):
                if role == "ui":
                    prefix_lines = ui_focus_lines(previous_err)
                elif role == "store":
                    prefix_lines = store_focus_lines(previous_err)
                elif role == "logic":
                    prefix_lines = logic_focus_lines(previous_err)
                else:
                    prefix_lines = ""
                head = prefix_lines
                head += prompt(role, error=previous_err, previous=previous_src,
                               own_example=own_example, show_previous=False)
                seed = BASE_SEED + 2000 + sweep * 100 + i
                if job["kind"].endswith("2"):
                    seed += 413  # second exploration seed
            else:
                head = prompt(role, error=previous_err, previous=previous_src,
                              own_example=own_example, show_previous=True)
                seed = BASE_SEED + 3000 + sweep * 100 + i
            raw, n = generate_one(model, tokenizer, head, max_tokens=LIMITS[role],
                                  seed=seed, stochastic=True)
            state["tokens"] += n
            challenger = dict(state["selected"])
            challenger[role] = PREFIX[role] + raw
            if not syntax_ok(challenger[role], role) or not requires_ok(challenger[role]):
                state["last_try"][role] = (challenger[role],
                                           "static gate: syntax or module allowlist")
                state["attempts"].append({"stage": job["kind"], "sweep": sweep,
                                          "round": sweep, "role": role, "prompt": head,
                                          "raw": raw, "fills": None, "output_tokens": n,
                                          "accepted": False,
                                          "candidate_source": challenger[role],
                                          "public_result": {"passed": False,
                                                             "syntax_valid": False,
                                                             "error": "static gate: syntax or module allowlist"},
                                          "fim_window": None,
                                          "origin": {"type": "whole", "base": None}})
                save_state(root, state)
                print(json.dumps({"sweep": sweep, "role": role, "stage": job["kind"],
                                  "tokens": n, "passed": False, "accepted": False,
                                  "error": "static gate: syntax or module allowlist"}),
                      flush=True)
                continue
            stage = job["kind"]
            origin = {"type": "whole", "base": None}
            fill = raw
            fills = None
            fim_window = None
        result = evaluate(challenger, PUBLIC, "public")
        accepted = metric(result, role) > metric(state["public"], role)
        state["last_try"][role] = (challenger[role],
                                   result["modules"][role]["error"]
                                   or "Public contract failed")
        state["attempts"].append({"stage": stage, "sweep": sweep, "round": sweep,
                                  "role": role, "prompt": (instructions if stage.startswith("fim")
                                                           else head),
                                  "raw": fill, "fills": fills, "output_tokens": n,
                                  "accepted": accepted,
                                  "candidate_source": challenger[role],
                                  "public_result": result["modules"][role],
                                  "fim_window": fim_window,
                                  "origin": origin})
        if accepted:
            state["selected"] = challenger
            state["public"] = result
            state["last_try"].pop(role, None)
            if stage.startswith("fim"):
                state["fim_stats"]["accepted"] += 1
        tick()
        print(json.dumps({"sweep": sweep, "role": role, "stage": stage,
                          "tokens": n, "passed": result["modules"][role]["passed"],
                          "accepted": accepted,
                          "error": (result["modules"][role]["error"] or "")[:150]}),
              flush=True)
        save_state(root, state)
        if all(state["public"]["modules"][r]["passed"] for r in ROLES):
            state["pending"] = []
        if not state["pending"] and not all(
                state["public"]["modules"][r]["passed"] for r in ROLES):
            state["rounds"].append(snapshot(sweep, state["selected"], state["public"],
                                            state["elapsed"], state["tokens"],
                                            state["fim_stats"]))
            save_state(root, state)
            print(json.dumps({"sweep": sweep, "score": total_score(state["public"]),
                              "passed": {r: state["public"]["modules"][r]["passed"]
                                         for r in ROLES}}), flush=True)
        if all(state["public"]["modules"][r]["passed"] for r in ROLES):
            finished = True

    elapsed = tick()
    del model
    gc.collect()
    holdout_cases = holdout()
    baseline_hold = evaluate(state["baseline"], holdout_cases, "holdout")
    final_hold = evaluate(state["selected"], holdout_cases, "holdout")
    final_public = evaluate(state["selected"], PUBLIC, "public")
    report = {"session": "032", "status": "completed", "model": MODEL_ID,
              "model_source": "local hf download, byte-identical to " + MODEL_ID,
              "parameter_count": count, "training_steps": 0, "weight_edits": 0,
              "new_application": NAME, "contract_sha256": fingerprint(),
              "target_app_modules_from_qwen": list(ROLES),
              "teacher_bytes": 0, "teacher_supplied_anything": False,
              "self_repair_only": True,
              "method": "fim-anchored-self-repair (Session031 whole-module "
                        "regeneration plus native FIM splices of the model's own "
                        "bytes anchored at evaluator-reported failing positions)",
              "fim_repairs": dict(state["fim_stats"]),
              "sweeps": state["sweep"],
              "own_prior_session_bytes_in_prompts": sorted(self_memory),
              "permanent_weight_learning": False,
              "evaluator": "local node/python subprocesses, vm realms and checks "
                           "byte-identical to the Session031 Docker worker; Docker "
                           "daemon unavailable in the recycled sandbox (disclosed)",
              "evaluator_parity_check": parity_check(),
              "trusted_scaffold": ["file signatures/imports", "evaluation runtime",
                                   "React runtime", "deployment gallery"],
              "baseline": {"public": state["baseline_public"],
                           "holdout": baseline_hold},
              "final": {"public": final_public, "holdout": final_hold},
              "rounds": [{k: v for k, v in snap.items() if k != "modules"}
                         for snap in state["rounds"]],
              "search": {"candidate_count": len(state["attempts"]),
                         "output_tokens": state["tokens"],
                         "wall_seconds": round(elapsed, 2),
                         "max_sweeps": args.rounds,
                         "wall_budget_seconds": args.wall_budget,
                         "private_holdout_seen_during_selection": False},
              "ui_behavior_verified_in_jsdom": bool(final_public["checks"].get("ui_offline")),
              "ui_browser_clicks_verified": False,
              "production_ready": False}
    save_json(root / "report.json", report)
    save_json(root / "predictions.json",
              {"greedy": state["baseline"], "selected": state["selected"],
               "attempts": state["attempts"], "rounds": state["rounds"],
               "source_sha256": {r: hashlib.sha256(state["selected"][r].encode()).hexdigest()
                                 for r in ROLES}})
    from .session027 import ROLE_PATHS
    for role, path in ROLE_PATHS.items():
        target = root / "generated" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(state["selected"][role], encoding="utf8")
    print(json.dumps({"baseline_holdout": baseline_hold["integrated"],
                      "final_holdout": final_hold["integrated"],
                      "final_public_integrated": final_public["integrated"],
                      "final_passes": {r: final_hold["modules"][r]["passed"] for r in ROLES},
                      "sweeps": state["sweep"], "candidates": len(state["attempts"]),
                      "fim": state["fim_stats"]}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="outputs/session032")
    parser.add_argument("--rounds", type=int, default=12,
                        help="maximum repair sweeps")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--self-memory", action="store_true")
    parser.add_argument("--state", default="experiments/session032_selfrepair_state.json")
    parser.add_argument("--time-budget", type=float, default=TIME_BUDGET_DEFAULT,
                        help="wall seconds for this invocation before checkpoint exit")
    parser.add_argument("--wall-budget", type=float, default=WALL_BUDGET_SECONDS,
                        help="cumulative wall-clock budget in seconds")
    args = parser.parse_args()
    if args.rounds < 0 or args.rounds > 40:
        raise ValueError("rounds must be within 0..40")
    run(args)


if __name__ == "__main__":
    main()
