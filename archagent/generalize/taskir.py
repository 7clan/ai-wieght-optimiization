"""SESSION 037 — PHASE 2: TaskIR, the structured programming interface.

A TaskIR document is a *validated* intermediate representation of an
application: entities + relations, API contracts (methods, params,
pre/postconditions, responses), invariants (with explicit case tables),
UI components, and cross-file dependencies.  Nothing is generated from
it until it VALIDATES.

From a valid TaskIR the engine derives:

  1. a dependency graph over PIECES — the smallest unresolved
     programming contracts (one model, one handler, one invariant
     predicate, one component...);
  2. per-piece prompt material honoring the Phase-1 lessons
     (see prompting.py);
  3. per-piece verification: structural gate contract + behavioral
     oracle (see probe.py).

TaskIR is written by the harness/teacher and is DECLARED input — it is
never counted as model capability.  What the model does with each piece
is what gets scored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ----------------------------------------------------------------- schema


IR_VERSION = "037.1"

ALLOWED_PIECE_KINDS = {
    "prisma-model",      # one model block (with its relations)
    "type-interface",    # one exported interface
    "invariant",         # one predicate function + truth table
    "route-handler",     # ONE http method of ONE route file
    "hook",              # one client data hook
    "component",         # one UI component
    "page",              # the assembling page
}

_KIND_ORDER = {k: i for i, k in enumerate([
    "prisma-model", "type-interface", "invariant",
    "route-handler", "hook", "component", "page"])}


class TaskIRError(ValueError):
    pass


@dataclass
class Case:
    """One row of an invariant's case table (truth table / boundary)."""
    name: str
    inputs: dict[str, Any]
    expect: Any  # bool for predicates


@dataclass
class Invariant:
    pid: str
    statement: str
    signature: str                    # e.g. overlaps(aStart,aEnd,bStart,bEnd)
    cases: list[Case]
    demo_domain: str = ""             # different-domain demo (prompt law)
    ref_expr: str = ""                # reference oracle expression (fuzz)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Field:
    name: str
    type: str
    attrs: list[str] = field(default_factory=list)
    optional: bool = False


@dataclass
class Relation:
    name: str
    target: str
    kind: str            # "one-to-many" | "many-to-one"
    is_list: bool
    fk_field: str = ""          # scalar FK on the many side
    optional: bool = False
    rel_name: str = ""          # named relation (self-relations)
    onDelete: str = ""          # e.g. "Cascade"


@dataclass
class Entity:
    pid: str
    name: str
    fields: list[Field]
    relations: list[Relation]
    demo_domain: str = ""
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Response:
    status: int
    shape: dict[str, str] = field(default_factory=dict)
    message: str = ""


@dataclass
class RouteHandler:
    pid: str
    method: str                     # GET | POST | PUT | DELETE | PATCH
    path: str                       # e.g. /api/rooms
    file: str                       # workspace-relative
    clauses: list[str]              # <= 6 bounded clauses (Phase-1 law)
    responses: list[Response]
    calls: list[str]                # required reachable call chains
    demo_domain: str = ""
    uses_invariants: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class UIPiece:
    pid: str
    kind: str                       # hook | component | page
    file: str
    name: str
    clauses: list[str]
    ui_strings: list[str]
    accesses: list[str]
    demo_domain: str = ""
    depends_on: list[str] = field(default_factory=list)


@dataclass
class TaskIR:
    app: str
    concept: str
    entities: list[Entity]
    invariants: list[Invariant]
    routes: list[RouteHandler]
    ui: list[UIPiece]
    types_file: str = "src/lib/%(app)s/types.ts"
    ir_version: str = IR_VERSION

    # ------------------------------------------------------ validation
    def validate(self) -> list[str]:
        errs: list[str] = []
        pids: list[str] = []

        def reg(pid: str, what: str) -> None:
            if not re.fullmatch(r"[a-z0-9~-]{2,44}", pid or ""):
                errs.append(f"{what}: bad id {pid!r}")
            if pid in pids:
                errs.append(f"{what}: duplicate id {pid!r}")
            pids.append(pid)

        for e in self.entities:
            reg(e.pid, "entity")
            if not re.fullmatch(r"[A-Z][A-Za-z0-9]{1,30}", e.name):
                errs.append(f"entity {e.pid}: bad model name {e.name!r}")
            names = [f.name for f in e.fields]
            if len(names) != len(set(names)):
                errs.append(f"entity {e.pid}: duplicate fields")
            if not any("@id" in a for f in e.fields for a in f.attrs):
                errs.append(f"entity {e.pid}: no @id field")
            for r in e.relations:
                reg(f"{e.pid}~{r.name}", "relation")
                if r.kind not in ("one-to-many", "many-to-one"):
                    errs.append(f"relation {e.pid}.{r.name}: bad kind")
                if r.kind == "many-to-one" and not r.fk_field:
                    errs.append(
                        f"relation {e.pid}.{r.name}: many-to-one needs fk_field")
        entity_names = {e.name for e in self.entities}

        # relation referential integrity (the M1 lesson: verify BOTH sides)
        for e in self.entities:
            for r in e.relations:
                if r.target not in entity_names:
                    errs.append(f"relation {e.pid}.{r.name}: unknown target "
                                f"{r.target!r}")
        for e in self.entities:
            for r in e.relations:
                if r.kind == "many-to-one":
                    fk_ok = any(f.name == r.fk_field for f in e.fields)
                    if not fk_ok:
                        errs.append(f"relation {e.pid}.{r.name}: fk_field "
                                    f"{r.fk_field!r} not in fields")
                    # reverse side must exist on the target
                    rev = [rr for t in self.entities if t.name == r.target
                           for rr in t.relations
                           if rr.target == e.name and rr.kind == "one-to-many"]
                    if not rev:
                        errs.append(f"relation {e.pid}.{r.name}: no reverse "
                                    f"one-to-many on {r.target}")

        for inv in self.invariants:
            reg(inv.pid, "invariant")
            if len(inv.cases) < 4:
                errs.append(f"invariant {inv.pid}: case table too small "
                            f"(<4) — boundary discipline (Phase-1 P1)")
            if not inv.signature or "(" not in inv.signature:
                errs.append(f"invariant {inv.pid}: missing signature")
            for c in inv.cases:
                if not isinstance(c.expect, bool):
                    errs.append(f"invariant {inv.pid}: case {c.name}: "
                                f"expect must be bool")
        for h in self.routes:
            reg(h.pid, "route")
            if h.method not in ("GET", "POST", "PUT", "DELETE", "PATCH"):
                errs.append(f"route {h.pid}: bad method {h.method!r}")
            if len(h.clauses) > 6:
                errs.append(f"route {h.pid}: {len(h.clauses)} clauses > 6 "
                            f"(Phase-1 P1 granularity law)")
            if not h.responses:
                errs.append(f"route {h.pid}: no responses declared")
            for u in h.uses_invariants:
                if u not in {i.pid for i in self.invariants}:
                    errs.append(f"route {h.pid}: unknown invariant {u!r}")
        for p in self.ui:
            reg(p.pid, "ui")
            if p.kind not in ("hook", "component", "page"):
                errs.append(f"ui {p.pid}: bad kind {p.kind!r}")
            if len(p.clauses) > 6:
                errs.append(f"ui {p.pid}: >6 clauses")
        # dangling depends_on
        known = set(pids)
        for coll, get in ((self.entities, lambda x: x.depends_on),
                          (self.invariants, lambda x: x.depends_on),
                          (self.routes, lambda x: x.depends_on),
                          (self.ui, lambda x: x.depends_on)):
            for item in coll:
                for d in get(item):
                    if d not in known:
                        errs.append(f"depends_on {d!r} unknown ({item.pid})")
        return errs

    # ------------------------------------------------------ pieces/graph
    def pieces(self) -> list["Piece"]:
        """Flatten to PIECES — smallest unresolved programming contracts."""
        out: list[Piece] = []
        for e in self.entities:
            out.append(Piece(
                pid=e.pid, kind="prisma-model", file="prisma/schema.prisma",
                spec=self._model_spec(e), demo=e.demo_domain,
                anchor=f"model {e.name} {{",
                gate={"kind": "prisma", "models": [self._model_gate(e)]},
                depends_on=list(e.depends_on),
                ir=self))
        for inv in self.invariants:
            out.append(Piece(
                pid=inv.pid, kind="invariant",
                file=f"src/lib/{self.app}/invariants.ts",
                spec=self._invariant_spec(inv), demo=inv.demo_domain,
                anchor=f"export function {inv.signature.split('(')[0]}(",
                gate={"kind": "invariant", "signature": inv.signature},
                oracle={"cases": [{"name": c.name, "inputs": c.inputs,
                                   "expect": c.expect}
                                  for c in inv.cases],
                        "signature": inv.signature,
                        "ref_expr": inv.ref_expr},
                depends_on=list(inv.depends_on), ir=self))
        for h in self.routes:
            out.append(Piece(
                pid=h.pid, kind="route-handler", file=h.file,
                spec=self._route_spec(h), demo=h.demo_domain,
                anchor=self._route_anchor(h),
                gate={"kind": "route", "handlers": [h.method],
                      "calls": h.calls, "file": h.file},
                oracle={"probe": "route", "method": h.method, "path": h.path,
                        "responses": [{"status": r.status, "message": r.message}
                                      for r in h.responses]},
                depends_on=list(h.depends_on)
                + [f"inv:{u}" for u in h.uses_invariants], ir=self))
        for p in self.ui:
            out.append(Piece(
                pid=p.pid, kind=p.kind, file=p.file,
                spec=self._ui_spec(p), demo=p.demo_domain,
                anchor=self._ui_anchor(p),
                gate={"kind": "component" if p.kind != "page" else "page",
                      "uiStrings": p.ui_strings, "accesses": p.accesses,
                      "exports": [p.name] if p.kind != "page" else ["default"]},
                depends_on=list(p.depends_on), ir=self))
        _toposort(out)
        return out

    # --------------------------------------------------- spec rendering
    def _model_spec(self, e: Entity) -> str:
        lines = [f"Add the model {e.name} to the schema file."]
        for f in e.fields:
            attrs = " ".join(f.attrs)
            opt = "?" if getattr(f, "optional", False) else ""
            lines.append(f"field {f.name} {f.type}{opt}"
                         + (f" {attrs}" if attrs else ""))
        for r in e.relations:
            if r.kind == "many-to-one":
                opt = "?" if r.optional else ""
                nm = f'"{r.rel_name}", ' if r.rel_name else ""
                casc = f", onDelete: {r.onDelete}" if r.onDelete else ""
                lines.append(
                    f"relation field {r.name} {r.target}{opt} "
                    f"@relation({nm}fields: [{r.fk_field}], "
                    f"references: [id]{casc})")
            else:
                nm = f'"{r.rel_name}", ' if r.rel_name else ""
                lines.append(f"relation field {r.name} {r.target}[]"
                             + (f" @relation({nm})" if nm else ""))
        return ". ".join(lines) + "."

    def _model_gate(self, e: Entity) -> dict:
        fields = [{"name": f.name, "type": f.type,
                   "optional": bool(getattr(f, "optional", False)),
                   "attrsIncludes": [a for a in f.attrs
                                     if a.startswith("@") and "(" not in a]}
                  for f in e.fields]
        for r in e.relations:
            g = {"name": r.name, "type": r.target, "isList": r.is_list,
                 "optional": r.optional}
            if r.kind == "many-to-one":
                want = ["@relation"]
                if r.onDelete:
                    want.append(f"onDelete: {r.onDelete}")
                if r.fk_field:
                    want.append(f"fields: [{r.fk_field}]")
                g["attrsIncludes"] = want
            elif r.rel_name:
                g["attrsIncludes"] = [f'"{r.rel_name}"']
            fields.append(g)
        return {"name": e.name, "fields": fields}

    def _invariant_spec(self, inv: Invariant) -> str:
        return (f"Write the predicate function {inv.signature}. "
                + inv.statement + " "
                + "The file may hold several such functions; add this one.")

    def _route_spec(self, h: RouteHandler) -> str:
        head = (f"Write the {h.method} handler for {h.path} in {h.file}.")
        body = " ".join(h.clauses)
        return f"{head} {body}"

    def _route_anchor(self, h: RouteHandler) -> str:
        # Phase-1 law: anchor INSIDE the construct (never the bare import)
        return f"export async function {h.method}("

    def _ui_spec(self, p: UIPiece) -> str:
        head = f"Write the {p.kind} {p.name} in {p.file}."
        return f"{head} " + " ".join(p.clauses)

    def _ui_anchor(self, p: UIPiece) -> str:
        if p.kind == "page":
            return "export default function"
        return f"export function {p.name}("


@dataclass
class Piece:
    pid: str
    kind: str
    file: str
    spec: str
    demo: str
    anchor: str
    gate: dict
    oracle: dict | None = None
    depends_on: list[str] = field(default_factory=list)
    ir: TaskIR | None = None


def _toposort(pieces: list[Piece]) -> None:
    by_pid = {p.pid: p for p in pieces}
    kind_rank = {p.pid: _KIND_ORDER[p.kind] for p in pieces}
    seen: dict[str, int] = {}
    order: list[Piece] = []

    def visit(p: Piece, stack: set[str]) -> None:
        if p.pid in seen:
            return
        if p.pid in stack:
            raise TaskIRError(f"dependency cycle at {p.pid}")
        stack.add(p.pid)
        for d in p.depends_on:
            if d.startswith("inv:"):
                d = d[4:]
            if d in by_pid:
                visit(by_pid[d], stack)
        stack.discard(p.pid)
        seen[p.pid] = 1
        order.append(p)

    for p in sorted(pieces, key=lambda x: (kind_rank[x.pid], x.pid)):
        visit(p, set())
    pieces[:] = order


# ------------------------------------------------------------ constructor

def taskir_from_dict(d: dict) -> TaskIR:
    """Build + validate a TaskIR from a JSON dict.  Raises TaskIRError."""
    ents = [Entity(
        pid=e["pid"], name=e["name"],
        fields=[Field(**f) for f in e.get("fields", [])],
        relations=[Relation(**r) for r in e.get("relations", [])],
        demo_domain=e.get("demo_domain", ""),
        depends_on=e.get("depends_on", [])) for e in d.get("entities", [])]
    invs = [Invariant(
        pid=i["pid"], statement=i["statement"], signature=i["signature"],
        cases=[Case(**c) for c in i.get("cases", [])],
        demo_domain=i.get("demo_domain", ""),
        ref_expr=i.get("ref_expr", "")) for i in d.get("invariants", [])]
    rts = [RouteHandler(
        pid=r["pid"], method=r["method"], path=r["path"], file=r["file"],
        clauses=r.get("clauses", []), responses=[Response(**x) for x in
                                                  r.get("responses", [])],
        calls=r.get("calls", []), demo_domain=r.get("demo_domain", ""),
        uses_invariants=r.get("uses_invariants", []),
        depends_on=r.get("depends_on", [])) for r in d.get("routes", [])]
    ui = [UIPiece(
        pid=u["pid"], kind=u["kind"], file=u["file"], name=u.get("name", ""),
        clauses=u.get("clauses", []), ui_strings=u.get("ui_strings", []),
        accesses=u.get("accesses", []), demo_domain=u.get("demo_domain", ""),
        depends_on=u.get("depends_on", [])) for u in d.get("ui", [])]
    ir = TaskIR(app=d["app"], concept=d.get("concept", ""), entities=ents,
                invariants=invs, routes=rts, ui=ui)
    errs = ir.validate()
    if errs:
        raise TaskIRError("; ".join(errs[:8]))
    return ir
