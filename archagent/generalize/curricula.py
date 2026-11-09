"""SESSION 037 — PHASE 7: capability-gap curricula.

Two curricula attacking the two documented Session-036 gaps, each with
five DEV tasks and one TRANSFER task (unseen variant, run after the
engine's learned state is updated):

  A. Relational schemas (the 0/16 gap)
     1 one-to-many required FK        (Band/Album)
     2 optional FK                    (Plot/Planting)
     3 required FK, new identifiers   (Screen/Showing)
     4 two relations on one model     (Order->Customer, ->Coupon)
     5 self-relation                  (Category parent/children)
     T cascade deletion               (Aisle/Bin, onDelete: Cascade)

  B. Logical invariants (predicate + case table + fuzz oracle)
     1 numeric boundary, 2 mutually exclusive states, 3 capacity,
     4 interval containment, 5 duplicate detection,
     T multi-step state transition (order lifecycle)

MEASUREMENT (identical budgets per task per treatment):
  baseline  Session-036 Track-B treatment: construct-start anchor, no
            domain-diff line, no counterexample loop; retries re-prompt
            with raw gate text (the 036 'feedback' ladder)
  engine    TaskIR piece treatment: anchor-inside, demo-completeness,
            bounded clauses, budget policy, counterexample repair
Both verify with the SAME gates + oracles; 6 generations / 2000 tokens.

Domains are deliberately disjoint from TaskFlow/MediVault/StockPilot/
RoomReserve and from the final benchmark families (approval workflows,
equipment maintenance, pricing/quotas).
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from archagent.generalize.taskir import taskir_from_dict  # noqa: E402
from archagent.generalize.controller import PieceController  # noqa: E402
from archagent.generalize.policy import PolicyState  # noqa: E402
from archagent.generalize import prompting  # noqa: E402
from archagent.generalize import probe as probe_mod  # noqa: E402

WS = Path("/home/z/my-project")
OUT = ROOT / "experiments" / "z037-generalization" / "curricula"
BUDGET_TOKENS = 2000
BUDGET_ATTEMPTS = 6


def _rel_demo(child: str, optional: bool = False,
              onDelete: str = "", named: str = "") -> str:
    """Demo-complete Vet-domain relation pair (never the task's).

    Field names follow the Session-036 'neutral labels' law: the child
    uses generic names (id/title/start) so that copying them is safe;
    only the FK/relation names are domain-specific (vetId/vet), which
    the model must rename — measured in curriculum A bring-up: with
    petName/vetId-style names the 0.5B copies the demo child's fields
    wholesale instead of the spec's."""
    opt = "?" if optional else ""
    cascade = f", onDelete: {onDelete}" if onDelete else ""
    nm = f'"{named}", ' if named else ""
    return (
        "model Vet {\n"
        "  id        String  @id @default(cuid())\n"
        "  name      String\n"
        f"  visits    {child}[]\n"
        "}\n\n"
        f"model {child} {{\n"
        "  id        String  @id @default(cuid())\n"
        "  title     String\n"
        "  start     String\n"
        f"  vetId     String{opt}\n"
        f"  vet       Vet{opt} @relation({nm}fields: [vetId], "
        f"references: [id]{cascade})\n"
        "}")


SELF_DEMO = (
    "model Folder {\n"
    "  id        String   @id @default(cuid())\n"
    "  name      String\n"
    "  parentId  String?\n"
    "  parent    Folder?  @relation(\"FolderTree\", "
    "fields: [parentId], references: [id])\n"
    "  children  Folder[] @relation(\"FolderTree\")\n"
    "}")

# ---------------------------------------------------------- curriculum A
# Each task: entities as DIRECT structured IR (no spec re-parsing).

CURRICULUM_A: list[dict] = [
    {"pid": "rel-1tm", "label": "one-to-many required FK",
     "entities": [
         {"pid": "rel-1tm-band", "name": "Band",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "name", "type": "String"},
                     {"name": "genre", "type": "String"}],
          "relations": [{"name": "albums", "target": "Album",
                         "kind": "one-to-many", "is_list": True}]},
         {"pid": "rel-1tm-album", "name": "Album",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "title", "type": "String"},
                     {"name": "releaseYear", "type": "Int"},
                     {"name": "bandId", "type": "String"}],
          "relations": [{"name": "band", "target": "Band",
                         "kind": "many-to-one", "is_list": False,
                         "fk_field": "bandId"}]}],
     "demo": _rel_demo("Album")},
    {"pid": "rel-opt", "label": "optional FK",
     "entities": [
         {"pid": "rel-opt-plot", "name": "Plot",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "label", "type": "String"},
                     {"name": "area", "type": "Int"}],
          "relations": [{"name": "plantings", "target": "Planting",
                         "kind": "one-to-many", "is_list": True}]},
         {"pid": "rel-opt-planting", "name": "Planting",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "crop", "type": "String"},
                     {"name": "plantedAt", "type": "String"},
                     {"name": "plotId", "type": "String", "optional": True}],
          "relations": [{"name": "plot", "target": "Plot",
                         "kind": "many-to-one", "is_list": False,
                         "fk_field": "plotId", "optional": True}]}],
     "demo": _rel_demo("Planting", optional=True)},
    {"pid": "rel-req", "label": "required FK, new identifiers",
     "entities": [
         {"pid": "rel-req-screen", "name": "Screen",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "label", "type": "String"},
                     {"name": "seats", "type": "Int"}],
          "relations": [{"name": "showings", "target": "Showing",
                         "kind": "one-to-many", "is_list": True}]},
         {"pid": "rel-req-showing", "name": "Showing",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "film", "type": "String"},
                     {"name": "startsAt", "type": "String"},
                     {"name": "screenId", "type": "String"}],
          "relations": [{"name": "screen", "target": "Screen",
                         "kind": "many-to-one", "is_list": False,
                         "fk_field": "screenId"}]}],
     "demo": _rel_demo("Visit")},
    {"pid": "rel-two", "label": "two relations on one model",
     "entities": [
         {"pid": "rel-two-customer", "name": "Customer",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "name", "type": "String"}],
          "relations": [{"name": "orders", "target": "Order",
                         "kind": "one-to-many", "is_list": True}]},
         {"pid": "rel-two-coupon", "name": "Coupon",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "code", "type": "String"}],
          "relations": [{"name": "orders", "target": "Order",
                         "kind": "one-to-many", "is_list": True}]},
         {"pid": "rel-two-order", "name": "Order",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "total", "type": "Int"},
                     {"name": "customerId", "type": "String"},
                     {"name": "couponId", "type": "String", "optional": True}],
          "relations": [
              {"name": "customer", "target": "Customer",
               "kind": "many-to-one", "is_list": False,
               "fk_field": "customerId"},
              {"name": "coupon", "target": "Coupon",
               "kind": "many-to-one", "is_list": False,
               "fk_field": "couponId", "optional": True}]}],
     "demo": _rel_demo("Pet", optional=True)},
    {"pid": "rel-self", "label": "self-relation",
     "entities": [
         {"pid": "rel-self-category", "name": "Category",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "name", "type": "String"},
                     {"name": "parentId", "type": "String", "optional": True}],
          "relations": [
              {"name": "parent", "target": "Category",
               "kind": "many-to-one", "is_list": False,
               "fk_field": "parentId", "optional": True},
              {"name": "children", "target": "Category",
               "kind": "one-to-many", "is_list": True}]}],
     "demo": SELF_DEMO},
    # -------- TRANSFER task
    {"pid": "rel-cascade", "label": "TRANSFER: cascade deletion",
     "entities": [
         {"pid": "rel-cascade-aisle", "name": "Aisle",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "code", "type": "String"}],
          "relations": [{"name": "bins", "target": "Bin",
                         "kind": "one-to-many", "is_list": True}]},
         {"pid": "rel-cascade-bin", "name": "Bin",
          "fields": [{"name": "id", "type": "String",
                      "attrs": ["@id", "@default(cuid())"]},
                     {"name": "label", "type": "String"},
                     {"name": "aisleId", "type": "String"}],
          "relations": [{"name": "aisle", "target": "Aisle",
                         "kind": "many-to-one", "is_list": False,
                         "fk_field": "aisleId"}]}],
     "demo": _rel_demo("Visit"),
     "cascade": True},
]

# ---------------------------------------------------------- curriculum B

CURRICULUM_B: list[dict] = [
    {"pid": "inv-weight", "label": "numeric boundary",
     "statement": ("isWithinWeightLimit is true exactly when weight is "
                   "at least 0.5 and at most 30 (both inclusive)."),
     "signature": "isWithinWeightLimit(weight: number)",
     "ref_expr": "weight >= 0.5 && weight <= 30",
     "cases": [
         {"name": "below", "inputs": [0.4], "expect": False},
         {"name": "min-boundary", "inputs": [0.5], "expect": True},
         {"name": "mid", "inputs": [15], "expect": True},
         {"name": "max-boundary", "inputs": [30], "expect": True},
         {"name": "above", "inputs": [30.1], "expect": False}],
     "demo": ("// ferry crossing capacity check (different domain)\n"
              "export function ferryHasRoom(current: number, "
              "capacity: number) {\n  return current < capacity\n}\n")},
    {"pid": "inv-exclusive", "label": "mutually exclusive states",
     "statement": ("canHoldBothFlags is false exactly when both flags "
                   "are true (mutually exclusive; else allowed)."),
     "signature": "canHoldBothFlags(paused: boolean, billed: boolean)",
     "ref_expr": "!(paused && billed)",
     "cases": [
         {"name": "both-true", "inputs": [True, True], "expect": False},
         {"name": "first-only", "inputs": [True, False], "expect": True},
         {"name": "second-only", "inputs": [False, True], "expect": True},
         {"name": "neither", "inputs": [False, False], "expect": True}],
     "demo": ("// lamp mode exclusivity (different domain)\n"
              "export function lampCanBoth(a: boolean, b: boolean) {\n"
              "  return !(a && b)\n}\n")},
    {"pid": "inv-capacity", "label": "resource capacity",
     "statement": ("hasOpenSeats is true exactly when enrolled is less "
                   "than capacity (equal means full)."),
     "signature": "hasOpenSeats(enrolled: number, capacity: number)",
     "ref_expr": "enrolled < capacity",
     "cases": [
         {"name": "empty", "inputs": [0, 10], "expect": True},
         {"name": "near-full", "inputs": [9, 10], "expect": True},
         {"name": "exactly-full", "inputs": [10, 10], "expect": False},
         {"name": "over", "inputs": [11, 10], "expect": False}],
     "demo": ("// elevator load check (different domain)\n"
              "export function elevatorFits(riders: number, "
              "maxRiders: number) {\n  return riders <= maxRiders\n}\n")},
    {"pid": "inv-window", "label": "interval containment",
     "statement": ("isInsideWindow is true exactly when both the start "
                   "and the end lie within the bounds (inclusive)."),
     "signature": "isInsideWindow(start: string, end: string, dayStart: string, dayEnd: string)",
     "ref_expr": "dayStart <= start && end <= dayEnd",
     "cases": [
         {"name": "inside", "inputs": ["T08:00", "T09:00", "T06:00", "T17:00"], "expect": True},
         {"name": "touching-start", "inputs": ["T06:00", "T10:00", "T06:00", "T17:00"], "expect": True},
         {"name": "touching-end", "inputs": ["T15:00", "T17:00", "T06:00", "T17:00"], "expect": True},
         {"name": "starts-before", "inputs": ["T05:00", "T08:00", "T06:00", "T17:00"], "expect": False},
         {"name": "ends-after", "inputs": ["T16:00", "T18:00", "T06:00", "T17:00"], "expect": False}],
     "demo": ("// broadcast slot containment (different domain)\n"
              "export function slotInside(showStart: string, "
              "showEnd: string,\n"
              "                           dayStart: string, "
              "dayEnd: string) {\n"
              "  return dayStart <= showStart && showEnd <= dayEnd\n"
              "}\n")},
    {"pid": "inv-duplicate", "label": "duplicate detection",
     "statement": ("isSameBookingRef is true exactly when BOTH the "
                   "reference code and the slot match."),
     "signature": "isSameBookingRef(codeA: string, slotA: string, codeB: string, slotB: string)",
     "ref_expr": "codeA === codeB && slotA === slotB",
     "cases": [
         {"name": "identical", "inputs": ["X1", "S1", "X1", "S1"], "expect": True},
         {"name": "code-differs", "inputs": ["X1", "S1", "X2", "S1"], "expect": False},
         {"name": "slot-differs", "inputs": ["X1", "S1", "X1", "S2"], "expect": False},
         {"name": "both-differ", "inputs": ["X1", "S1", "X2", "S2"], "expect": False}],
     "demo": ("// twin-room key check (different domain)\n"
              "export function sameKey(aRoom: string, aGuest: string,\n"
              "                        bRoom: string, bGuest: string) {\n"
              "  return aRoom === bRoom && aGuest === bGuest\n}\n")},
    # -------- TRANSFER task
    {"pid": "inv-lifecycle", "label": "TRANSFER: multi-step transitions",
     "statement": ("canAdvanceOrder is true exactly for draft -> review "
                   "-> approved -> shipped. Any other transition is "
                   "invalid, including same-state or skipping."),
     "signature": "canAdvanceOrder(current: string, next: string)",
     "ref_expr": "(current === 'draft' && next === 'review') || (current === 'review' && next === 'approved') || (current === 'approved' && next === 'shipped')",
     "cases": [
         {"name": "draft-to-review", "inputs": ["draft", "review"], "expect": True},
         {"name": "review-to-approved", "inputs": ["review", "approved"], "expect": True},
         {"name": "approved-to-shipped", "inputs": ["approved", "shipped"], "expect": True},
         {"name": "skip-step", "inputs": ["draft", "approved"], "expect": False},
         {"name": "backwards", "inputs": ["review", "draft"], "expect": False},
         {"name": "same-state", "inputs": ["draft", "draft"], "expect": False},
         {"name": "terminal", "inputs": ["shipped", "shipped"], "expect": False}],
     "demo": ("// pipeline stage check (different domain)\n"
              "export function canAdvance(current: string, "
              "next: string) {\n"
              "  return (current === 'raw' && next === 'edited') ||\n"
              "         (current === 'edited' && next === 'published')\n"
              "}\n")},
]
