"""Unit tests for high-risk branch algebra, disjoint tasks, and collector."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from tinycoder.branch_experiments import (
    HOLDOUT_START, select_pristine_holdout, syntax_counts,
    syntax_failure_examples, validate_branch_config,
)
from tinycoder.collect_experiments import END, EXPECTED, START, prepare_comparison, publish
from tinycoder.rome20 import BASE_MODEL, DATA_URL


class ExperimentalMetadataTests(unittest.TestCase):
    def setUp(self):
        self.problems = [{"task_id": f"HumanEval/{i}", "prompt": "def f():\n"} for i in range(164)]
        self.prior = {"base_model": BASE_MODEL, "source": DATA_URL,
                      "selected_failing_ids": [f"HumanEval/{i}" for i in range(20)],
                      "holdout_ids": [f"HumanEval/{i}" for i in range(24, 44)]}

    def test_50_tasks_fresh_after_prior_94(self):
        failures, holdout = select_pristine_holdout(self.problems, self.prior)
        self.assertEqual(len(failures), 20)
        self.assertEqual(len(holdout), 50)
        self.assertEqual(holdout[0]["task_id"], f"HumanEval/{HOLDOUT_START}")
        self.assertEqual(holdout[-1]["task_id"], "HumanEval/143")

    def test_syntax_label_uses_full_program_not_just_raw_suffix(self):
        failures = [{"task_id": "HumanEval/0", "prompt": "def f():\n"},
                    {"task_id": "HumanEval/1", "prompt": "def f():\n"}]
        history = {"edited_cases": [
            {"task_id": "HumanEval/0", "before_passed": False, "before_completion": "    return ("},
            {"task_id": "HumanEval/1", "before_passed": False, "before_completion": "    return 1\n"},
        ]}
        selection = syntax_failure_examples(failures, history)
        self.assertEqual([x["task_id"] for x in selection], ["HumanEval/0"])
        self.assertEqual(syntax_counts(failures, ["    return (", "    return 1\n"])["valid"], 1)

    def test_branch_config_must_match_and_holdout(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "branch_spec.json"
            path.write_text(json.dumps({"variant": "transplant", "holdout_start": 94}))
            self.assertEqual(validate_branch_config(path, "transplant")["variant"], "transplant")
            with self.assertRaises(ValueError):
                validate_branch_config(path, "memit_single")


@unittest.skipUnless(importlib.util.find_spec("torch") is not None, "PyTorch not installed")
class ExperimentalAlgebraTests(unittest.TestCase):
    def test_svd_zeroing_removes_two_selected_components(self):
        import torch
        from tinycoder.branch_experiments import exact_svd_erasure

        weight = torch.diag(torch.tensor([5., 4., 3., 2.]))
        gaps = torch.tensor([[10., 1., 0., 0.], [8., 2., 0., 0.]])
        left, right, description = exact_svd_erasure(weight, gaps, candidates=4)
        self.assertEqual(left.shape, (4, 2))
        self.assertEqual(right.shape, (2, 4))
        self.assertEqual(len(description["selection"]), 2)
        self.assertLess(description["post_erasure_component_max_abs"], 1e-5)
        self.assertTrue(torch.isfinite(weight + left @ right).all())

    def test_stress_factor_norm_matches_all_pre_registered_thresholds(self):
        import torch
        from tinycoder.branch_experiments import normalized_stress_factors, TESTED_NORMS

        weight = torch.eye(4)
        left = torch.tensor([[1.], [0.], [0.], [0.]])
        right = torch.tensor([[1., 0., 0., 0.]])
        for fraction in TESTED_NORMS:
            scaled, other = normalized_stress_factors(weight, left, right, fraction)
            actual = float(torch.linalg.vector_norm(scaled @ other) / torch.linalg.vector_norm(weight))
            self.assertAlmostEqual(actual, fraction, places=6)


class CollectorTests(unittest.TestCase):
    def test_rejects_missing_branch_artifact(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                prepare_comparison(Path(d))

    def test_aggregates_exactly_six_rows_and_preserves_readme(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            tasks = [f"HumanEval/{i}" for i in range(94, 144)]
            baseline = [tasks[0]]
            for variant, (artid, _) in EXPECTED.items():
                folder = root / "branch_artifacts" / f"branch-{artid}-results"
                folder.mkdir(parents=True)
                row = {"n": 50, "before_passes": 1, "after_passes": 2,
                       "pass_at_1_before": .02, "pass_at_1_after": .04,
                       "percentage_point_delta": 2.0,
                       "passed_ids_before": baseline, "passed_ids_after": tasks[:2],
                       "newly_passed_ids": [tasks[1]], "regressed_ids": []}
                variants = {key: dict(row) for key in ("3%", "5%", "10%")}
                if variant != "norm_break":
                    variants = {"default": row}
                details = {"observed_relative_delta_norm": 0.0149} if variant in ("transplant", "memit_single") else {}
                (folder / "report.json").write_text(json.dumps({"status": "completed", "variant": variant,
                                                                  "no_training": True, "holdout_ids": tasks,
                                                                  "variants": variants, "intervention": details}))
                (folder / "predictions.json").write_text("{}")
                (folder / "factors.safetensors").write_bytes(b"reversible")
            readme = root / "README.md"
            readme.write_text("begin\n" + START + "\npending\n" + END + "\nend\n")
            publish(root / "branch_artifacts", root / "experiments", readme)
            changed = readme.read_text()
            self.assertIn("Session 007", changed)
            self.assertIn("(10%)", changed)
            self.assertTrue(changed.startswith("begin\n"))
            self.assertTrue(changed.endswith("end\n"))
            self.assertTrue((root / "experiments" / "high_risk_comparison.json").is_file())


if __name__ == "__main__":
    unittest.main()
