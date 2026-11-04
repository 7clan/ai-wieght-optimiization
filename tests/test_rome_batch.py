"""Offline checks for disjoint sampling, batch math, and reporting."""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from tinycoder.rome20 import BASE_MODEL, DATA_URL
from tinycoder.rome_batch import (
    RESULTS_END, RESULTS_START, pass_at_one_summary,
    select_disjoint_tasks, update_readme,
)


class BatchSelectionTests(unittest.TestCase):
    def setUp(self):
        self.problems = [{"task_id": f"HumanEval/{i}"} for i in range(164)]
        self.prior = {
            "base_model": BASE_MODEL, "source": DATA_URL,
            "selected_failing_ids": [f"HumanEval/{i}" for i in range(20)],
            "holdout_ids": [f"HumanEval/{i}" for i in range(24, 44)],
        }

    def test_holdout_disjoint_from_original_40_tasks(self):
        failures, holdout = select_disjoint_tasks(self.problems, self.prior, start=44, count=50)
        self.assertEqual(len(failures), 20)
        self.assertEqual(len(holdout), 50)
        self.assertEqual(holdout[0]["task_id"], "HumanEval/44")
        self.assertEqual(holdout[-1]["task_id"], "HumanEval/93")

    def test_rejects_leaked_or_short_holdout(self):
        with self.assertRaisesRegex(ValueError, "intersects"):
            select_disjoint_tasks(self.problems, self.prior, start=40, count=50)
        with self.assertRaisesRegex(ValueError, "Insufficient"):
            select_disjoint_tasks(self.problems, self.prior, start=130, count=50)

    def test_rejects_different_source_or_wrong_count(self):
        other = dict(self.prior, source="different")
        with self.assertRaises(ValueError):
            select_disjoint_tasks(self.problems, other, start=44, count=50)
        with self.assertRaises(ValueError):
            select_disjoint_tasks(self.problems, self.prior, start=44, count=49)

    def test_pass_at_one_id_lists_and_regressions(self):
        records = []
        for i in range(50):
            records.append({"task_id": f"HumanEval/{i+44}",
                            "before_passed": i in (0, 1, 2),
                            "after_passed": i in (0, 2, 3, 4),
                            "before_completion": "a", "after_completion": "b" if i == 3 else "a"})
        s = pass_at_one_summary(records)
        self.assertEqual((s["before_passes"], s["after_passes"]), (3, 4))
        self.assertEqual(s["percentage_point_delta"], 2)
        self.assertEqual(s["regressed_ids"], ["HumanEval/45"])
        self.assertEqual(s["newly_passed_ids"], ["HumanEval/47", "HumanEval/48"])
        self.assertEqual(len(s["failed_ids_after"]), 46)
        self.assertEqual(s["changed_completions"], 1)

    def test_readme_region_update_preserves_rest(self):
        with tempfile.TemporaryDirectory() as d:
            file = Path(d) / "README.md"
            file.write_text("head\n" + RESULTS_START + "\nPending\n" + RESULTS_END + "\ntail\n")
            report = {"status": "completed", "hardware": {"gpu_name": "Synthetic GPU"},
                      "independent_holdout_50": {"before_passes": 3, "after_passes": 5,
                                                  "percentage_point_delta": 4.0,
                                                  "newly_passed_ids": ["HumanEval/49"], "regressed_ids": []}}
            update_readme(file, report)
            result = file.read_text()
            self.assertIn("3/50 → 5/50", result)
            self.assertIn("Synthetic GPU", result)
            self.assertTrue(result.startswith("head\n"))
            self.assertTrue(result.endswith("tail\n"))


@unittest.skipUnless(importlib.util.find_spec("torch") is not None, "PyTorch not installed")
class BatchTensorTests(unittest.TestCase):
    def test_woodbury_matches_dense_regularized_covariance(self):
        import torch
        from tinycoder.rome_batch import covariance_inverse_keys

        k = torch.tensor([[1., 0.], [2., 1.], [0., 2.], [3., 1.]])
        q = torch.tensor([[0.5, 0.3], [0.8, -0.5], [0.2, 0.4], [0.9, 0.7]])
        inverse, ridge = covariance_inverse_keys(k, q)
        c = ridge * torch.eye(4) + k @ k.T / 2
        expected = torch.linalg.solve(c, q)
        self.assertTrue(torch.allclose(inverse, expected, atol=2e-3, rtol=1e-3))

    def test_two_key_closed_form_reduces_target_distance_under_cap(self):
        import torch
        from tinycoder.rome_batch import batch_factors

        weight = torch.eye(4)
        keys = torch.tensor([[2., 0.], [0., 2.], [0., 0.], [0., 0.]])
        targets = (weight @ keys).clone()
        targets[0, 0] += 1
        targets[1, 1] -= 1
        left, right, report = batch_factors(weight, keys, targets, max_relative_change=0.015)
        delta = left @ right
        self.assertEqual(left.shape, (4, 2))
        self.assertEqual(right.shape, (2, 4))
        self.assertLessEqual(float(torch.linalg.vector_norm(delta) / torch.linalg.vector_norm(weight)), 0.015 + 1e-6)
        self.assertLess(report["target_distance_after"], report["target_distance_before"])

    def test_requires_cuda_without_silent_cpu_fallback(self):
        import torch
        from unittest.mock import patch
        from tinycoder.rome_batch import run

        with patch.object(torch.cuda, "is_available", return_value=False):
            with self.assertRaisesRegex(RuntimeError, "CUDA GPU required"):
                run(object())


if __name__ == "__main__":
    unittest.main()
