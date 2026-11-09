"""SESSION 037 — PHASE 6: behavioral probes inside the repair loop.

Two probe families (both run with `bun`, model unloaded state not
required — probes are cheap):

  invariant   the piece's predicate function is imported and executed
              against (a) the IR's frozen case table and (b) a property
              fuzz against an INDEPENDENT harness reference oracle.
              Failures return MINIMAL COUNTEREXAMPLES (smallest failing
              case) for the repair prompt.

  route       the route file's handler is imported with a mocked
              NextRequest against a scratch SQLite database; declared
              probe cases check status codes / response shapes.
              (Phase-1 H4: the POST-listing hook passed every
              structural gate — behavior must be in the loop.)

Reference oracles are TEST-ONLY harness code: they are never shown to
the model and never enter the application.  Probes classify failures as
(app | harness) separately — a harness crash never counts against the
model.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

PROBE_DIR = Path("/tmp/z037-probes")
NODE_ENV = {**os.environ, "NODE_OPTIONS": ""}


def _run_bun(script: Path, cwd: str, timeout: int = 60) -> dict:
    r = subprocess.run(
        ["bun", "run", str(script)], capture_output=True, text=True,
        timeout=timeout, cwd=cwd, env=NODE_ENV)
    out = r.stdout.strip().splitlines()
    verdict = None
    for line in out:
        if line.startswith("PROBE-RESULT "):
            verdict = json.loads(line[len("PROBE-RESULT "):])
    if verdict is None:
        return {"pass": False, "class": "harness",
                "failures": [f"probe produced no verdict: "
                             f"{(r.stdout + r.stderr)[:300]}"]}
    return verdict


def _abs_import(ws: Path, rel_file: str) -> str:
    """Absolute POSIX path for bun dynamic import."""
    p = (ws / rel_file).resolve()
    return p.as_posix()


# ------------------------------------------------------------ invariants

def invariant_probe(ws: Path, invariants_file: str, signature: str,
                    cases: list[dict], fuzz: int = 300,
                    ref_expr: str | None = None) -> dict:
    """Run the case table + property fuzz against a reference oracle.

    ref_expr: a JS boolean expression over the signature's parameters
    (the INDEPENDENT implementation).  Required for the fuzz phase; the
    case table alone runs without it.
    """
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    fname = signature.split("(")[0]
    params = signature[signature.index("(") + 1:].rstrip(")").strip()
    pnames = [p.split(":")[0].strip() for p in params.split(",")] if params else []
    mod_path = _abs_import(Path("/home/z/my-project"), invariants_file)

    ref = ref_expr or "false"
    fuzz_js = ""
    if ref_expr:
        # fuzz over string ISO datetimes on a fixed day, minute offsets;
        # bind the signature's first four parameter names to the fuzzed
        # interval endpoints so the ref_expr evaluates in scope.
        bind = ", ".join(f"{n} = iso({v})" for n, v in zip(
            pnames[:4], ("a1", "a2", "b1", "b2")))
        call_args = ", ".join(pnames[:4])
        fuzz_js = f"""
    const base = new Date('2026-03-01T00:00:00Z').getTime();
    const iso = (m) => new Date(base + m * 60000).toISOString().slice(0, 16);
    let fuzzFail = null;
    for (let i = 0; i < {fuzz}; i++) {{
      const a1 = Math.floor(Math.random() * 240);
      const a2 = a1 + Math.floor(Math.random() * 240);
      const b1 = Math.floor(Math.random() * 240);
      const b2 = b1 + Math.floor(Math.random() * 240);
      const {bind};
      const got = fn({call_args});
      const want = ({ref});
      if (got !== want) {{ fuzzFail = {{inputs: [{call_args}], got, want}}; break; }}
    }}
    if (fuzzFail) {{ emit({{pass: false, class: 'app', failures: ['fuzz: ' + JSON.stringify(fuzzFail)]}}); }}
"""

    script = f"""
const emit = (v) => console.log('PROBE-RESULT ' + JSON.stringify(v));
const mod = await import({json.dumps(mod_path)});
const fn = mod[{json.dumps(fname)}];
if (typeof fn !== 'function') {{
  emit({{pass: false, class: 'app', failures: ['export {fname} is not a function']}});
}} else {{
  const cases = {json.dumps(cases)};
  const fails = [];
  for (const c of cases) {{
    let got;
    try {{ got = fn(...c.inputs); }} catch (e) {{
      fails.push(c.name + ': threw ' + String(e).slice(0, 80)); continue; }}
    if (got !== c.expect) {{
      fails.push(c.name + ': ' + JSON.stringify(c.inputs) + ' returned ' +
        JSON.stringify(got) + ', expected ' + JSON.stringify(c.expect));
    }}
  }}
  if (fails.length) {{
    emit({{pass: false, class: 'app', failures: fails}});
  }} else {{
{fuzz_js}
    emit({{pass: true, failures: []}});
  }}
}}
"""
    sp = PROBE_DIR / f"inv-{fname}.ts"
    sp.write_text(script)
    return _run_bun(sp, cwd=str(ws))


# ---------------------------------------------------------------- routes

def route_probe(ws: Path, route_file: str, method: str,
                cases: list[dict]) -> dict:
    """Import the handler and run declared probe cases with a mocked
    NextRequest against the scratch probe database.

    cases: [{name, params?, body?, expect_status, json_contains?,
             json_keys?}]
    """
    PROBE_DIR.mkdir(parents=True, exist_ok=True)
    mod_path = _abs_import(Path("/home/z/my-project"), route_file)
    script = f"""
const emit = (v) => console.log('PROBE-RESULT ' + JSON.stringify(v));
process.env.DATABASE_URL = 'file:' + process.cwd() + '/db/probe.db';
class FakeURL {{
  constructor(params) {{
    this.searchParams = new URLSearchParams(params || {{}});
  }}
}}
class FakeReq {{
  constructor(params, body) {{
    this.nextUrl = new FakeURL(params);
    this._body = body ?? null;
  }}
  async json() {{
    if (this._body === null) throw new Error('no body');
    if (typeof this._body === 'string') return JSON.parse(this._body);
    return this._body;
  }}
}}
const NS = {{
  json: (payload, init) => ({{
    status: init?.status ?? 200,
    json: payload,
    __nextResponse: true,
  }}),
}};
const mod = await import({json.dumps(mod_path)});
const handler = mod[{json.dumps(method)}];
if (typeof handler !== 'function') {{
  emit({{pass: false, class: 'app', failures: ['{method} not exported']}});
}} else {{
  const cases = {json.dumps(cases)};
  const fails = [];
  for (const c of cases) {{
    let res;
    try {{
      res = await handler(new FakeReq(c.params, c.body));
    }} catch (e) {{
      fails.push(c.name + ': handler threw ' + String(e).slice(0, 120));
      continue;
    }}
    if (!res || !res.__nextResponse) {{
      fails.push(c.name + ': handler returned a non-NextResponse'); continue; }}
    if (res.status !== c.expect_status) {{
      fails.push(c.name + ': status ' + res.status + ' != expected ' +
                 c.expect_status); continue; }}
    if (c.json_contains) {{
      const s = JSON.stringify(res.json ?? {{}});
      for (const frag of c.json_contains) {{
        if (!s.includes(frag)) {{
          fails.push(c.name + ': response missing ' + JSON.stringify(frag));
        }}}}}}
    if (c.json_keys) {{
      const keys = Object.keys(res.json ?? {{}});
      for (const k of c.json_keys) {{
        if (!keys.includes(k)) fails.push(c.name + ': response lacks key ' + k);
      }}}}}}
  }}
  emit({{pass: fails.length === 0, class: 'app', failures: fails}});
}}
"""
    sp = PROBE_DIR / f"route-{method}-{Path(route_file).parent.name}.ts"
    sp.write_text(script)
    return _run_bun(sp, cwd=str(ws))


# ------------------------------------------------- counterexample mining

def minimal_counterexample(probe_result: dict) -> str:
    """Render the smallest failing case for a repair prompt."""
    fails = probe_result.get("failures", [])[:2]
    return " | ".join(fails)[:400]
