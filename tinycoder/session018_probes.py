"""Additional PUBLIC distinguishing inputs and static type-directed AST repair.

This is NOT the heldout test set. Probes were authored solely from the task
contracts and are disjoint from both Session017's public and holdout examples.
Only trusted fixture data is inspected outside Docker; generated code is
PARSED, but never executed, on the generation host.
"""
from __future__ import annotations

import ast


PROBES = {
    "invoice": [({"items": [{"price": 3, "qty": 4}]}, 12),
                ({"items": [{"price": 5, "qty": 0}]}, 0)],
    "slug": [({"text": "  Tiny   App  "}, "tiny-app"),
             ({"text": "line\nbreak"}, "line-break")],
    "discount": [({"amount": 101, "percent": 10}, 90),
                 ({"amount": 60, "percent": 50}, 30)],
    "filter": [({"numbers": [-2, 4, 0], "minimum": 0}, [4, 0]),
               ({"numbers": [3, 3, 1], "minimum": 3}, [3, 3])],
    "progress": [({"done": 1, "total": 2}, 50),
                 ({"done": 7, "total": 10}, 70)],
    "vowels": [({"text": "Banana"}, 3),
               ({"text": "XYZ"}, 0)],
    "fahrenheit": [({"celsius": 10}, 50),
                   ({"celsius": 25}, 77)],
    "unique": [({"tags": ["red", "red", "blue"]}, ["red", "blue"]),
               ({"tags": ["q", "r", "q"]}, ["q", "r"])],
    "maximum": [({"numbers": [5, 8, 1]}, 8),
                ({"numbers": [-3, -9]}, -3)],
    "words": [({"text": "alpha beta"}, 2),
              ({"text": "   "}, 0)],
}


def augmented_public(task):
    name = task["contract"]["slug"]
    extra = [{"payload": payload, "expected": {"value": value}}
             for payload, value in PROBES[name]]
    return task["public_cases"] + extra


def typed_ast_repair(source: str, task: dict):
    """Convert dict-style attribute access based on public input schemas.

    E.g. payload.items -> payload['items'], item.price -> item['price'].
    This is a syntax/type correction only; it does NOT implement the target
    operation, inspect solution outputs or use a reference implementation.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, MemoryError):
        return source, 0
    roots = set()
    nested = set()
    for test in task["public_cases"]:
        for key, value in test["payload"].items():
            roots.add(key)
            if isinstance(value, list):
                for entry in value:
                    if isinstance(entry, dict):
                        nested.update(entry.keys())
    collection_vars = {node.target.id for node in ast.walk(tree)
                       if isinstance(node, ast.comprehension)
                       and isinstance(node.target, ast.Name)}

    class Rewriter(ast.NodeTransformer):
        def __init__(self):
            self.changes = 0

        def visit_Attribute(self, node):
            node = self.generic_visit(node)
            if (isinstance(node.value, ast.Name)
                and ((node.value.id == "payload" and node.attr in roots)
                     or (node.value.id in collection_vars and node.attr in nested))):
                self.changes += 1
                return ast.copy_location(ast.Subscript(
                    value=node.value, slice=ast.Constant(node.attr), ctx=node.ctx), node)
            return node

    transform = Rewriter()
    changed = transform.visit(tree)
    if not transform.changes:
        return source, 0
    ast.fix_missing_locations(changed)
    return ast.unparse(changed) + "\n", transform.changes
