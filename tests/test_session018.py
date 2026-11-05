"""Trusted Session018 unit tests; never execute model-generated code on host."""
from __future__ import annotations

import ast
import json
import subprocess
import unittest
from unittest.mock import patch

from tinycoder.session017_contracts import contracts, holdout_cases, module_prompt
from tinycoder.session018 import docker_python, priority, repair_prompt
from tinycoder.session018_probes import PROBES, augmented_public, typed_ast_repair


class ExtremeSearchTests(unittest.TestCase):
    def test_public_distinguishing_probes_are_frozen_and_disjoint(self):
        tasks = contracts()
        self.assertEqual(len(tasks), 10)
        self.assertEqual(set(PROBES), {t["contract"]["slug"] for t in tasks})
        hidden = holdout_cases()
        for task in tasks:
            tid = task["task_id"]
            original = task["public_cases"]
            new = augmented_public(task)
            self.assertEqual(len(new), 4)
            self.assertEqual(new[:2], original)
            self.assertEqual(len({json.dumps(c, sort_keys=True) for c in new}), 4)
            self.assertFalse({json.dumps(c["payload"], sort_keys=True) for c in new} &
                             {json.dumps(c["payload"], sort_keys=True)
                              for c in hidden[tid]})

    def test_type_directed_repair_based_only_on_public_dictionary_fields(self):
        invoice = contracts()[0]
        original = ("def transform(payload):\n"
                    "    return {'value': sum(item.price * item.qty for item in payload.items)}\n")
        fixed, changes = typed_ast_repair(original, invoice)
        ast.parse(fixed)
        self.assertEqual(changes, 3)
        self.assertIn("payload['items']", fixed)
        self.assertIn("item['price']", fixed)
        self.assertIn("item['qty']", fixed)

    def test_repair_does_not_touch_explicit_dict_access_or_invalid_source(self):
        invoice = contracts()[0]
        correct = "def transform(payload):\n    return {'value': payload['items']}\n"
        self.assertEqual(typed_ast_repair(correct, invoice), (correct, 0))
        bad = "def transform(payload):\n    return (\n"
        self.assertEqual(typed_ast_repair(bad, invoice), (bad, 0))

    def test_prioritize_verified_public_cases_over_syntax(self):
        three = {"passed_count": 3, "syntax_valid": True}
        four = {"passed_count": 4, "syntax_valid": True}
        self.assertGreater(priority(four, "def transform(p): pass"),
                           priority(three, "def transform(p): pass"))

    def test_feedback_uses_explicit_public_only(self):
        task = contracts()[1]
        public = augmented_public(task)
        diagnostic = {"failures": [{"index": 2, "error": "Wrong answer"}]}
        prompt = repair_prompt(task, "return {'value': ''}", diagnostic, public)
        self.assertIn('"  Tiny   App  "', prompt)
        self.assertIn('"tiny-app"', prompt)
        self.assertTrue(prompt.endswith(module_prompt(task, "logic")))
        self.assertNotIn("Multiple\\tSpaces", prompt)

    def test_docker_timeout_terminates_named_container_and_fails_closed(self):
        task = contracts()[0]
        with patch("tinycoder.session018.subprocess.run", side_effect=[
            subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=18),
            subprocess.CompletedProcess(args=["docker", "rm"], returncode=0),
        ]) as mocked:
            outcome = docker_python(task, "def transform(p): pass", augmented_public(task))
        self.assertEqual(mocked.call_count, 2)
        self.assertFalse(outcome["passed_all"])
        self.assertIn("timeout", outcome["failures"][0]["error"])


if __name__ == "__main__":
    unittest.main()
