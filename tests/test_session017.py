"""Session017 trusted scaffolding/protocol checks (no generated host execution)."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tinycoder.session017 import choose_roles, make_repair_prompt, metrics, score, _one_docker
from tinycoder.session017_contracts import (MODULES, contract_sha256, contracts,
                                            expected_display, holdout_cases,
                                            module_prompt)
from tinycoder.session017_scaffold import export_project


class ContractTests(unittest.TestCase):
    def test_frozen_contracts_and_no_holdout_in_prompts(self):
        tasks = contracts()
        self.assertEqual(len(tasks), 10)
        self.assertEqual(len({t["task_id"] for t in tasks}), 10)
        self.assertEqual(len(contract_sha256(tasks)), 64)
        hidden = holdout_cases()
        for task in tasks:
            self.assertEqual(len(task["public_cases"]), 2)
            self.assertEqual(len(hidden[task["task_id"]]), 2)
            self.assertNotEqual(task["public_cases"], hidden[task["task_id"]])
            self.assertNotIn("holdout", json.dumps(task))
            for role in MODULES:
                prompt = module_prompt(task, role)
                self.assertTrue(prompt)
                for case in hidden[task["task_id"]]:
                    self.assertNotIn(json.dumps(case["payload"]), prompt)

    def test_value_display_contract(self):
        self.assertEqual(expected_display(None), "none")
        self.assertEqual(expected_display(["a", "b"]), "a, b")
        self.assertEqual(expected_display(42), "42")

    def test_role_selection_only_failed_components(self):
        tasks = contracts()[:2]
        a = {"task_id": tasks[0]["task_id"], "passed": False,
             "modules": {"logic": {"passed": True},
                         "api": {"passed": False}, "ui": {"passed": True}}}
        b = {"task_id": tasks[1]["task_id"], "passed": True,
             "modules": {k: {"passed": True} for k in MODULES}}
        self.assertEqual(choose_roles(tasks, [a,b]), [(tasks[0]["task_id"], "api")])

    def test_score_prefers_integrated_and_repair_is_prompt_compatible(self):
        a = {"passed": False, "modules": {k: {"passed": True, "syntax_valid": True}
                                           for k in MODULES}}
        b = {"passed": True, "modules": {k: {"passed": True, "syntax_valid": True}
                                          for k in MODULES}}
        self.assertGreater(score(b), score(a))
        task = contracts()[0]
        repair = make_repair_prompt(task,"api","return 0",{"error":"bad response"})
        self.assertTrue(repair.endswith(module_prompt(task,"api")))
        self.assertIn("bad response",repair)

    def test_scaffold_exports_file_dependencies_without_execution(self):
        task=contracts()[0]
        sources={r:module_prompt(task,r)+"return null;\n}\n" for r in MODULES}
        with tempfile.TemporaryDirectory() as temp:
            root=export_project(Path(temp),task,sources,holdout_passed=False)
            self.assertTrue((root/"backend/logic.py").exists())
            self.assertTrue((root/"client/src/ResultView.jsx").exists())
            self.assertTrue((root/"server/index.js").exists())
            self.assertEqual(json.loads((root/"package.json").read_text())["name"],
                             "tinycoder-invoice")
            self.assertIn("WARNING",(root/"README.md").read_text())

    def test_docker_timeout_is_failure_not_run_abort(self):
        task=contracts()[0]
        with patch("tinycoder.session017.require_sandbox"), patch(
            "tinycoder.session017.subprocess.run",
            side_effect=[subprocess.TimeoutExpired(cmd=["docker"], timeout=25),
                         subprocess.CompletedProcess(args=["docker"],returncode=0)]):
            outcome=_one_docker(task,{r:"pass" for r in MODULES},task["public_cases"])
        self.assertFalse(outcome["passed"])
        self.assertIn("timeout",outcome["error"])


if __name__ == "__main__":
    unittest.main()
