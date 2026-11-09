"""SESSION 038A — PHASE 1: independent replay of the 22-candidate queue.

The queue (experiments/finetune-readiness-038/candidate-queue.jsonl)
contains *references* (paths + hashes), never trusted examples.  This
module resolves each reference, verifies the hash chain, reconstructs
the frozen contract from the pinned Session-037 specifications, and
re-verifies the candidate from scratch with MORE depth than the
in-loop gates had:

  prisma-model   structural gate (frozen contract, run_gates.mjs)
               + prisma validate (Prisma's own validator)
               + prisma db push to a FRESH SQLite database
               + SQLite-level relation BEHAVIOR tests (FK enforcement,
                 required/optional nullability, bogus-FK rejection,
                 column defaults, delete-restrict) — these never ran
                 in-loop (in-loop prisma pieces had no piece-level
                 behavioral probe at all)
  invariant     structural gate + case table + SEEDED type-aware
                 property fuzz against the independent reference
                 oracle (the in-loop fuzz was interval-shaped and
                 non-reproducible; this one parses parameter types
                 from the frozen signature)

ISOLATION (disclosed): Docker is unavailable in this sandbox.  All
candidate-derived execution (prisma validate/push on candidate
schemas, bun execution of candidate invariant code) runs inside a
fresh `unshare -Urn` user+network namespace with CPU/wall limits and
scratch working directories — the Session-031/033 ARCHAGENT_LOCAL_EVAL
disclosed local-eval precedent, strengthened with namespaces.  Trusted
harness code (this module, run_gates.mjs) executes on the host.

Teacher exclusion: every queue item resolves to a generation record in
a gen/engine-gen/smoke-gen directory written by the model harness
during Session-037 runs; teacher bytes never entered those
directories.  The challenge attribution additionally confirms the two
challenge pieces are pure model bytes.

NO training, NO gradient work happens here.  Output is a verified /
quarantined manifest only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.finetune.audit_archives import check_record  # noqa: E402

QUEUE_DEFAULT = ROOT / "experiments/finetune-readiness-038/candidate-queue.jsonl"
OUT_DIR = ROOT / "experiments/z038a-independent-retest"
MYPROJECT = Path("/home/z/my-project")          # bun/prisma resolve here
NS = ["unshare", "-Urn", "sh", "-c"]            # user+net namespace
SCHEMA_HEAD = """generator client {
  provider = "prisma-client-js"
}

datasource db {
  provider = "sqlite"
  url      = env("DATABASE_URL")
}
"""


# ------------------------------------------------------------ utilities

def sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def ns_run(cmd: str, *, cwd: str, timeout: int = 120) -> dict:
    """Run a command inside the isolation namespace with CPU + wall
    limits.  Returns {returncode, stdout, stderr, timed_out}."""
    full = NS + [f"ulimit -t 90 2>/dev/null; cd {shlex.quote(cwd)} && {cmd}"]
    try:
        r = subprocess.run(full, capture_output=True, text=True,
                           timeout=timeout)
        return {"returncode": r.returncode,
                "stdout": r.stdout[-4000:], "stderr": r.stderr[-4000:],
                "timed_out": False}
    except subprocess.TimeoutExpired as e:
        return {"returncode": -1, "stdout": (e.stdout or b"")[-2000:],
                "stderr": "TIMEOUT", "timed_out": True}


# ------------------------------------------------- spec reconstruction

def load_specs() -> dict[str, dict]:
    """Map every queue piece id to its FROZEN Session-037 spec source.

    Returns {pid: {source, kind, gate, oracle?, entity?, siblings?,
    domain, level?}} where siblings are the OTHER entities of the same
    task needed to build a complete schema for behavioral testing.
    """
    from archagent.generalize.curricula import CURRICULUM_A, CURRICULUM_B
    from archagent.generalize.frozen_suite import DOMAINS
    from archagent.generalize.taskir import taskir_from_dict

    out: dict[str, dict] = {}

    def add_task(d: dict, source: str, siblings_by_pid: dict | None = None):
        ir = taskir_from_dict(d)
        for p in ir.pieces():
            if p.kind not in ("prisma-model", "invariant"):
                continue
            entry = {"source": source, "kind": p.kind,
                     "domain": d["app"], "gate": dict(p.gate),
                     "file": p.file}
            if p.kind == "invariant":
                entry["oracle"] = p.oracle
            else:
                ent = next(e for e in d["entities"] if e["pid"] == p.pid)
                entry["entity"] = ent
                sibs = [e for e in d["entities"] if e["pid"] != p.pid]
                entry["siblings"] = sibs
            out[p.pid] = entry

    for lvl in CURRICULUM_A:
        d = {"app": f"curriculum-a-{lvl['pid']}",
             "concept": "A small relational store.",
             "entities": [{**e, "demo_domain": lvl["demo"]}
                          for e in lvl["entities"]],
             "invariants": [], "routes": [], "ui": []}
        add_task(d, "curricula/A (Session-037 Phase 7)")

    for lvl in CURRICULUM_B:
        d = {"app": f"curriculum-b-{lvl['pid']}",
             "concept": "A small logic library.",
             "entities": [],
             "invariants": [lvl], "routes": [], "ui": []}
        add_task(d, "curricula/B (Session-037 Phase 7)")

    for dom in DOMAINS:
        add_task(dom, "tracks/C four-track (Session-037 Phase 10)")

    ch_spec = json.loads(
        (ROOT / "experiments/z037-generalization/challenge/SPEC.json")
        .read_text())
    add_task(ch_spec, "challenge run-2 (Session-037 Phase 11)")
    return out


def render_entity(entity: dict) -> str:
    """TRUSTED harness rendering of a spec entity (sibling fixture for
    behavioral tests; never part of any training example)."""
    lines = [f"model {entity['name']} {{"]
    for f in entity.get("fields", []):
        opt = "?" if f.get("optional") else ""
        attrs = " ".join(f.get("attrs", []))
        lines.append(f"  {f['name']:<12} {f['type']}{opt}"
                     + (f" {attrs}" if attrs else ""))
    for r in entity.get("relations", []):
        if r["kind"] == "many-to-one":
            opt = "?" if r.get("optional") else ""
            lines.append(f"  {r['name']:<12} {r['target']}{opt} "
                         f"@relation(fields: [{r['fk_field']}], "
                         f"references: [id])")
        else:
            lines.append(f"  {r['name']:<12} {r['target']}[]")
    lines.append("}")
    return "\n".join(lines)


def assemble_schema(candidate: str, entity: dict,
                    siblings: list[dict]) -> str:
    """Scaffold + candidate model + trusted sibling renderings.  If the
    candidate declares a sibling's model too, the trusted rendering
    still replaces it (the candidate under test keeps ONLY its own
    model block; extra model blocks are a spec violation reported by
    the structural gate's strictFields check)."""
    body = SCHEMA_HEAD.rstrip() + "\n\n" + candidate.strip() + "\n"
    for sib in siblings:
        body += "\n" + render_entity(sib) + "\n"
    return body


# ------------------------------------------------------- verification

def structural_gate(code: str, gate: dict, filename: str,
                    oracle: dict | None = None) -> dict:
    """Frozen-contract structural gate via run_gates.mjs --stdin."""
    contract = dict(gate)
    contract["file"] = filename
    if contract.get("kind") == "invariant" and oracle:
        contract["function"] = oracle["signature"].split("(")[0]
    with tempfile.NamedTemporaryFile("w", suffix=".json",
                                     delete=False) as cf:
        json.dump(contract, cf)
        cpath = cf.name
    r = subprocess.run(
        ["node", str(ROOT / "archagent/verify/run_gates.mjs"),
         "--contract", cpath, "--stdin"],
        input=code, capture_output=True, text=True, timeout=90,
        cwd=str(ROOT))
    os.unlink(cpath)
    try:
        return json.loads(r.stdout.strip().splitlines()[-1])
    except (json.JSONDecodeError, IndexError):
        return {"pass": False,
                "failures": [f"gate harness error: {r.stderr[:200]}"]}


def prisma_validate_and_push(schema_path: Path, db_path: Path) -> dict:
    """validate + db push inside the namespace (fresh SQLite file)."""
    schema_arg = shlex.quote(str(schema_path))
    env = f"DATABASE_URL='file:{db_path}'"
    v = ns_run(
        f"env {env} bunx --bun prisma validate --schema {schema_arg}",
        cwd=str(MYPROJECT), timeout=150)
    ok = v["returncode"] == 0 and "is valid" in (v["stdout"] + v["stderr"])
    if not ok:
        return {"validate": False,
                "validate_errors": [l for l in (v["stdout"] + v["stderr"])
                                    .splitlines()
                                    if "error" in l.lower()][:4]}
    p = ns_run(
        f"env {env} bunx --bun prisma db push --schema {schema_arg} "
        f"--skip-generate",
        cwd=str(MYPROJECT), timeout=150)
    pushed = p["returncode"] == 0 and "in sync" in (p["stdout"] + p["stderr"])
    return {"validate": True, "push": pushed,
            "push_errors": [] if pushed else
            [l for l in (p["stdout"] + p["stderr"]).splitlines()
             if "error" in l.lower()][:4]}


def sqlite_behavior_tests(db_path: Path, entity: dict,
                          siblings: list[dict]) -> dict:
    """Relation BEHAVIOR tests derived from the frozen spec (never from
    the candidate).  Runs trusted python3 -I -B against the pushed DB.

    Tests per declared many-to-one relation of the piece under test
    (or, when the piece is the parent side, of its sibling child):
      R1 valid FK insert succeeds
      R2 NULL FK: rejected iff required, accepted iff optional
      R3 bogus FK rejected (foreign_keys pragma ON)
      R4 delete parent with child present is RESTRICTED (default;
         cascade only when the spec declares onDelete)
      D1 column defaults from @default("literal") appear in DDL
    """
    under_test = entity["name"]
    all_ents = [entity] + siblings
    # child relations to test: every many-to-one among the task's
    # entities (whichever side is under test, the behavior must hold)
    tests: list[dict] = []
    for e in all_ents:
        for r in e.get("relations", []):
            if r["kind"] == "many-to-one":
                tests.append({"child": e["name"], "parent": r["target"],
                              "fk": r["fk_field"],
                              "optional": bool(r.get("optional")),
                              "cascade": bool(r.get("onDelete"))})
    defaults = [{"model": e["name"],
                 "field": f["name"],
                 "value": _literal_default(f.get("attrs", []))}
                for e in all_ents for f in e.get("fields", [])
                if _literal_default(f.get("attrs", [])) is not None]
    payload = json.dumps({"db": str(db_path), "under_test": under_test,
                          "tests": tests, "defaults": defaults})
    # HARNESS FIX DISCLOSURE (pre-results): the first replay draft had
    # three evaluator defects, all found on the initial 22-candidate
    # run and fixed BEFORE publishing any candidate verdicts from it:
    #   (1) R4 assumed RESTRICT for every non-cascade relation; Prisma
    #       optional relations default to SetNull (delete succeeds, FK
    #       nulled) — optional now expects SetNull, required expects
    #       Restrict, declared cascade expects cascade.
    #   (2) required-column filling wrote placeholder 'x' into OTHER
    #       FK columns, violating their constraints spuriously; now a
    #       valid parent row is inserted for every related parent and
    #       child FK columns resolve to real parent ids.
    #   (3) INSERT column lists were unquoted, breaking on reserved
    #       words (pricing's `limit` column); all identifiers quoted.
    script = f"""
import json, sqlite3
spec = json.loads({json.dumps(payload)})
con = sqlite3.connect(spec["db"])
con.execute("PRAGMA foreign_keys = ON")
results = []
def has_table(t):
    return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None
def cols(t):
    return {{r[1]: r for r in con.execute(f'PRAGMA table_info("{{t}}")')}}
def q(names):
    return ",".join(f'"{{n}}"' for n in names)
def insert_row(t, values):
    con.execute(f'INSERT INTO "{{t}}" ({{q(values)}}) VALUES ({{",".join("?" * len(values))}})', list(values.values()))
def clear(t):
    try: con.execute(f'DELETE FROM "{{t}}"')
    except sqlite3.Error: pass
def fill_required(info_cols, skip):
    out = {{}}
    for cname, info in info_cols.items():
        if cname in skip: continue
        if info[3] and info[4] is None:
            out[cname] = 1 if "INT" in (info[2] or "").upper() else "x"
    return out
def fk_map(t):
    return {{r[3]: r[2] for r in con.execute(f'PRAGMA foreign_key_list("{{t}}")')}}
for t in spec["tests"]:
    tag = f'{{t["child"]}}.{{t["fk"]}} -> {{t["parent"]}}'
    if not (has_table(t["child"]) and has_table(t["parent"])):
        results.append((tag + "/tables", False, "missing table")); continue
    cc, pc = cols(t["child"]), cols(t["parent"])
    if t["fk"] not in cc:
        results.append((tag + "/column", False, "missing FK column")); continue
    pid = "p1"
    clear(t["child"]); clear(t["parent"])
    # insert valid rows for EVERY parent the child references (fix 2)
    child_fks = fk_map(t["child"])
    parent_ids = {{}}
    pfill = {{"id": pid}}
    pfill.update(fill_required(pc, skip=("id",)))
    insert_row(t["parent"], pfill)
    parent_ids[t["parent"]] = pid
    for fk_col, ref_table in child_fks.items():
        if fk_col == t["fk"] or ref_table == t["parent"]: continue
        if ref_table in parent_ids: continue
        if not has_table(ref_table): continue
        rc = cols(ref_table)
        rfill = {{"id": "p-" + ref_table}}
        rfill.update(fill_required(rc, skip=("id",)))
        # self-referencing FK: point at the child's own row later; use a
        # fresh root row instead
        if ref_table == t["child"]:
            rfill2 = {{"id": "root-" + ref_table}}
            rfill2.update(fill_required(rc, skip=("id",) + tuple(fk_map(ref_table))))
            insert_row(ref_table, rfill2)
            parent_ids[ref_table] = rfill2["id"]
            continue
        insert_row(ref_table, rfill)
        parent_ids[ref_table] = rfill["id"]
    results.append((tag + "/P-parent-insert", True, ""))
    # R1 valid FK insert (all FK columns resolve to real parents)
    cvals = {{"id": "c1"}}
    for fk_col, ref_table in child_fks.items():
        cvals[fk_col] = parent_ids.get(ref_table, pid)
    cvals.update(fill_required(cc, skip=("id",) + tuple(child_fks)))
    try:
        insert_row(t["child"], cvals); con.commit()
        results.append((tag + "/R1-valid-fk", True, ""))
    except sqlite3.Error as e:
        results.append((tag + "/R1-valid-fk", False, str(e)[:120])); continue
    # R2 null FK (only the relation under test becomes NULL)
    try:
        c2 = dict(cvals); c2["id"] = "c2"; c2[t["fk"]] = None
        insert_row(t["child"], c2); con.commit(); null_ok = True
    except sqlite3.Error:
        null_ok = False; con.rollback()
    want_null = t["optional"]
    results.append((tag + "/R2-null-" + ("allowed" if want_null else "rejected"),
                    null_ok == want_null, f"null_ok={{null_ok}} spec_optional={{want_null}}"))
    # R3 bogus FK (only the relation under test is bogus)
    try:
        c3 = dict(cvals); c3["id"] = "c3"; c3[t["fk"]] = "no-such-parent"
        insert_row(t["child"], c3); con.commit()
        results.append((tag + "/R3-bogus-rejected", False, "bogus FK accepted"))
    except sqlite3.Error:
        results.append((tag + "/R3-bogus-rejected", True, ""))
    # R4 delete parent with child present (fix 1)
    con.rollback()
    still = con.execute(f'SELECT COUNT(*) FROM "{{t["child"]}}" WHERE "{{t["fk"]}}" = ?', (pid,)).fetchone()[0]
    try:
        con.execute(f'DELETE FROM "{{t["parent"]}}" WHERE "id" = ?', (pid,)); con.commit(); deleted = True
    except sqlite3.Error:
        deleted = False; con.rollback()
    if t["cascade"]:
        ok4 = deleted and still > 0
        note4 = f"deleted={{deleted}} children_before={{still}}"
    elif t["optional"]:
        # SetNull: parent delete succeeds; child survives with NULL FK
        child_kept = con.execute(f'SELECT COUNT(*) FROM "{{t["child"]}}" WHERE "id" = ?', ("c1",)).fetchone()[0]
        fk_now = con.execute(f'SELECT "{{t["fk"]}}" FROM "{{t["child"]}}" WHERE "id" = ?', ("c1",)).fetchone()[0]
        ok4 = deleted and child_kept == 1 and fk_now is None
        note4 = f"deleted={{deleted}} child_kept={{child_kept}} fk_now={{fk_now}}"
    else:
        ok4 = (not deleted) and still > 0
        note4 = f"deleted={{deleted}} children_before={{still}}"
    results.append((tag + "/R4-" + ("cascade" if t["cascade"] else "setnull" if t["optional"] else "restrict"), ok4, note4))
for d in spec["defaults"]:
    t, f, want = d["model"], d["field"], d["value"]
    try:
        info = cols(t)[f]
        got = info[4]
        ok = got is not None and str(got).strip("'\\"") == str(want).strip("'\\"")
        results.append((f"{{t}}.{{f}}/D1-default", ok, f"ddl={{got!r}} want={{want!r}}"))
    except KeyError:
        results.append((f"{{t}}.{{f}}/D1-default", False, "column missing"))
print("BEHAVIOR-RESULT " + json.dumps({{"n": len(results), "r": results}}))
"""
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as sf:
        sf.write(script)
        spath = sf.name
    try:
        r = subprocess.run(["python3", "-I", "-B", spath],
                           capture_output=True, text=True, timeout=60)
        for line in r.stdout.splitlines():
            if line.startswith("BEHAVIOR-RESULT "):
                payload = json.loads(line[len("BEHAVIOR-RESULT "):])
                fails = [f"{t}: {note}" for t, ok, note in payload["r"]
                         if not ok]
                return {"pass": not fails, "n": payload["n"],
                        "failures": fails}
        return {"pass": False, "n": 0,
                "failures": [f"behavior harness no verdict: "
                             f"{(r.stdout + r.stderr)[:200]}"]}
    finally:
        os.unlink(spath)


def _literal_default(attrs: list[str]) -> str | None:
    """Extract @default("lit") string literal, if any (cuid() is
    client-side and produces no SQL default — skipped)."""
    for a in attrs:
        m = re.match(r'@default\("([^"]*)"\)$', a.strip())
        if m:
            return m.group(1)
    return None


# ------------------------------------------------------ invariant probe

INV_PROBE_TEMPLATE = """
// SESSION-038A independent invariant probe (seeded, type-aware).
const emit = (v) => console.log('PROBE-RESULT ' + JSON.stringify(v));
const mod = await import(__MODPATH__);
const fn = mod[__FNAME__];
// deterministic xorshift32 — reproducible fuzz
let _s = __SEED__ >>> 0;
const rnd = () => { _s ^= _s << 13; _s >>>= 0; _s ^= _s >> 17; _s ^= _s << 5; _s >>>= 0; return _s / 4294967296; };
if (typeof fn !== 'function') {
  emit({pass: false, failures: ['export is not a function']});
} else {
  const cases = __CASES__;
  const P = __PNAMES__;
  const fails = [];
  for (const c of cases) {
    const args = Array.isArray(c.inputs) ? c.inputs : P.map(k => c.inputs[k]);
    let got;
    try { got = fn(...args); } catch (e) { fails.push(c.name + ': threw ' + String(e).slice(0,80)); continue; }
    if (got !== c.expect) fails.push(c.name + ': ' + JSON.stringify(args) + ' -> ' + JSON.stringify(got) + ' want ' + JSON.stringify(c.expect));
  }
  if (fails.length) { emit({pass: false, failures: fails}); }
  else if (!__HASREF__) {
    emit({pass: true, failures: [], note: 'case-table only (no ref oracle)'});
  } else {
    // type-aware property fuzz vs the independent reference oracle
    const pools = __POOLS__;
    const refExpr = __REFEXPR__;
    const refFn = new Function(P.join(','), 'return (' + refExpr + ');');
    let ff = null;
    for (let i = 0; i < __FUZZN__ && !ff; i++) {
      const args = pools.map(p => p[Math.floor(rnd() * p.length)]);
      let got, want;
      try { got = fn(...args); } catch (e) { got = 'THREW'; }
      try { want = refFn(...args); } catch (e) { want = 'THREW'; }
      if (got !== want) ff = {args, got, want};
    }
    if (ff) emit({pass: false, failures: ['fuzz: ' + JSON.stringify(ff)]});
    else emit({pass: true, failures: []});
  }
}
"""


def _param_types(signature: str) -> list[tuple[str, str]]:
    params = signature[signature.index("(") + 1:].rstrip(")")
    out = []
    for p in params.split(","):
        p = p.strip()
        if not p:
            continue
        name, _, typ = p.partition(":")
        out.append((name.strip(), typ.strip()))
    return out


def invariant_probe(code: str, oracle: dict, workdir: Path,
                    fuzz_n: int = 400, seed: int = 20261109) -> dict:
    """Assemble the candidate into a scratch TS file and run the seeded
    type-aware probe under the namespace (bun executes ONLY the
    candidate-derived file; the probe script is trusted harness code
    run from the scratch dir)."""
    fname = oracle["signature"].split("(")[0]
    inv_file = workdir / "invariants.ts"
    inv_file.write_text(
        "// SESSION-038A scratch replay surface\n" + code.strip() + "\n")
    pts = _param_types(oracle["signature"])
    pnames = [n for n, _ in pts]
    pools = []
    case_vals = []
    for c in oracle["cases"]:
        case_vals += c["inputs"] if isinstance(c["inputs"], list) else \
            list(c["inputs"].values())
    for _, typ in pts:
        if "number" in typ:
            pools.append([0.4, 0.5, 15, 30, 30.1, -1, 0, 1, 10, 11,
                          100, 1e9, 0.9999999, 9.5, 10.5] + case_vals)
        elif "boolean" in typ:
            pools.append([True, False])
        else:
            pools.append(["", "X1", "X2", "S1", "S2", "draft", "review",
                          "approved", "rejected", "x"] + case_vals)
    script = (INV_PROBE_TEMPLATE
              .replace("__MODPATH__", json.dumps(inv_file.as_posix()))
              .replace("__FNAME__", json.dumps(fname))
              .replace("__CASES__", json.dumps(oracle["cases"]))
              .replace("__PNAMES__", json.dumps(pnames))
              .replace("__POOLS__", json.dumps(pools))
              .replace("__REFEXPR__", json.dumps(oracle.get("ref_expr") or "false"))
              .replace("__HASREF__", "true" if oracle.get("ref_expr") else "false")
              .replace("__FUZZN__", str(fuzz_n))
              .replace("__SEED__", str(seed)))
    spath = workdir / "probe.ts"
    spath.write_text(script)
    r = ns_run(f"bun run {shlex.quote(str(spath))}",
               cwd=str(workdir), timeout=90)
    for line in r["stdout"].splitlines():
        if line.startswith("PROBE-RESULT "):
            return json.loads(line[len("PROBE-RESULT "):])
    return {"pass": False, "class": "harness",
            "failures": [f"probe no verdict: "
                         f"{(r['stdout'] + r['stderr'])[:250]}"]}


# --------------------------------------------------------- fingerprints

def model_fingerprint(code: str) -> str:
    """Normalized structural fingerprint of a prisma model block:
    names of models/fields replaced by canonical placeholders, so two
    candidates differing only in domain vocabulary collide (family /
    normalized-code duplicate detection)."""
    norm = re.sub(r"//[^\n]*", "", code)
    norm = re.sub(r"model\s+(\w+)", "model M", norm)
    # field names: first token on a field line inside the block
    out_lines = []
    for line in norm.splitlines():
        s = line.strip()
        if not s or s.startswith("model ") or s == "}" or s == "{":
            out_lines.append(s)
            continue
        m = re.match(r"(\w+)\s+(.+)$", s)
        if m:
            rest = m.group(2)
            rest = re.sub(r"\b\w+Id\b", "FK", rest)
            rest = re.sub(r"\b[A-Z]\w*\b", "T", rest)  # type names
            out_lines.append("f " + rest)
        else:
            out_lines.append(s)
    return sha256("\n".join(out_lines))


def invariant_fingerprint(code: str) -> str:
    """Normalized fingerprint of an invariant function: rename fn and
    parameters, collapse whitespace."""
    norm = re.sub(r"//[^\n]*", "", code)
    norm = re.sub(r"\bfunction\s+\w+", "function F", norm)
    norm = re.sub(r"\s+", " ", norm)
    return sha256(norm[:400])


# ---------------------------------------------------------------- main

def replay(queue_path: Path, limit: int | None = None) -> tuple[list, dict]:
    specs = load_specs()
    queue = [json.loads(l) for l in queue_path.read_text().splitlines()
             if l.strip()]
    if limit:
        queue = queue[:limit]
    results = []
    stats = {"resolved": 0, "hash_chain_failures": 0,
             "content_flagged": 0, "structural_fail": 0,
             "prisma_fail": 0, "behavior_fail": 0, "probe_fail": 0,
             "verified": 0, "quarantined": 0}
    seen_fp: dict[str, str] = {}
    for item in queue:
        pid = item["piece"]
        spec = specs.get(pid)
        rec_path = ROOT / item["generation_path"]
        res = {"piece": pid, "kind": item["kind"],
               "source": spec["source"] if spec else "UNKNOWN",
               "candidate_sha256": item["candidate_sha256"],
               "verification": {}, "status": "QUARANTINED",
               "reason": ""}
        try:
            rec = json.loads(rec_path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            res["reason"] = f"generation unreadable: {e}"
            results.append(res); stats["quarantined"] += 1
            continue
        # --- hash chain (independent re-derivation) ---
        if sha256(rec.get("candidate", "")) != item["candidate_sha256"] \
                or sha256(rec.get("prompt", "")) != item["prompt_sha256"]:
            res["reason"] = "hash chain mismatch vs queue"
            stats["hash_chain_failures"] += 1
            results.append(res); stats["quarantined"] += 1
            continue
        checked = check_record(rec)
        if checked is None or checked["blank_candidate"] or \
                checked["potential_secret"] or checked["placeholder_or_echo"]:
            res["reason"] = f"content flags: {checked}"
            stats["content_flagged"] += 1
            results.append(res); stats["quarantined"] += 1
            continue
        if not spec:
            res["reason"] = "no frozen spec found for piece"
            results.append(res); stats["quarantined"] += 1
            continue
        stats["resolved"] += 1
        code = rec["candidate"]

        # --- structural gate (frozen contract) ---
        g = structural_gate(code, spec["gate"], spec["file"],
                            spec.get("oracle"))
        res["verification"]["structural_gate"] = g["pass"]
        if not g["pass"]:
            res["reason"] = "structural gate failed on replay: " + \
                "; ".join(g.get("failures", [])[:3])
            stats["structural_fail"] += 1
            results.append(res); stats["quarantined"] += 1
            continue

        # --- kind-specific deep verification ---
        if item["kind"] == "prisma-model":
            with tempfile.TemporaryDirectory(prefix="z038a-") as td:
                tdp = Path(td)
                schema = assemble_schema(code, spec["entity"],
                                         spec["siblings"])
                spath = tdp / "schema.prisma"
                spath.write_text(schema)
                dbp = tdp / "replay.db"
                pv = prisma_validate_and_push(spath, dbp)
                res["verification"]["prisma_validate"] = pv["validate"]
                res["verification"]["prisma_db_push"] = pv.get("push")
                if not pv["validate"] or not pv.get("push"):
                    res["reason"] = "prisma validate/push failed: " + \
                        "; ".join(pv.get("validate_errors")
                                  or pv.get("push_errors") or [])[:300]
                    stats["prisma_fail"] += 1
                    results.append(res); stats["quarantined"] += 1
                    continue
                bt = sqlite_behavior_tests(dbp, spec["entity"],
                                           spec["siblings"])
                res["verification"]["sqlite_behavior"] = {
                    "pass": bt["pass"], "n_checks": bt["n"],
                    "failures": bt["failures"][:6]}
                if not bt["pass"]:
                    res["reason"] = "relation behavior failed: " + \
                        "; ".join(bt["failures"][:3])
                    stats["behavior_fail"] += 1
                    results.append(res); stats["quarantined"] += 1
                    continue
            fp = model_fingerprint(code)
        else:  # invariant
            with tempfile.TemporaryDirectory(prefix="z038a-") as td:
                tdp = Path(td)
                pr = invariant_probe(code, spec["oracle"], tdp)
                res["verification"]["invariant_probe"] = {
                    "pass": pr.get("pass"),
                    "failures": pr.get("failures", [])[:4]}
                if not pr.get("pass"):
                    cls = pr.get("class", "app")
                    res["reason"] = f"invariant probe failed ({cls}): " + \
                        "; ".join(pr.get("failures", [])[:2])[:300]
                    stats["probe_fail"] += 1
                    results.append(res); stats["quarantined"] += 1
                    continue
            fp = invariant_fingerprint(code)

        res["fingerprint"] = fp
        dup_of = seen_fp.get(fp)
        seen_fp.setdefault(fp, pid)
        res["normalized_duplicate_of"] = dup_of
        res["status"] = "INDEPENDENTLY_VERIFIED" if dup_of is None \
            else "INDEPENDENTLY_VERIFIED_DUPLICATE"
        stats["verified"] += 1
        results.append(res)
    return results, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queue", type=Path, default=QUEUE_DEFAULT)
    ap.add_argument("--out", type=Path,
                    default=OUT_DIR / "replay-results.jsonl")
    ap.add_argument("--summary", type=Path,
                    default=OUT_DIR / "replay-summary.json")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    t0 = time.time()
    results, stats = replay(args.queue, args.limit)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in results),
        encoding="utf-8")
    stats["wall_seconds"] = round(time.time() - t0, 1)
    args.summary.write_text(json.dumps(
        {"stats": stats,
         "isolation": "unshare -Urn user+network namespaces; prisma/"
                      "bun/sqlite run inside; trusted gates on host; "
                      "Docker unavailable in sandbox (disclosed)",
         "training_eligible": 0}, indent=2) + "\n", encoding="utf-8")
    print(f"replay complete: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
