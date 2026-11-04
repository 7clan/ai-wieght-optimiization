"""No-network tests of final holdout boundaries, factor edits and collector."""

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from tinycoder.fusion_validation import (
    FINAL_COUNT, FINAL_START, PREVIOUS_START, archived_baseline,
    contiguous_tasks, summarize,
)
from tinycoder.collect_fusion import ALL, NEW, OLD, combine_scores


class ExperimentIsolationTests(unittest.TestCase):
    def setUp(self):
        self.tasks = [{"task_id": f"HumanEval/{i}", "prompt": "def f():\n"} for i in range(164)]

    def test_new_twenty_are_distinct_from_all_previously_tested(self):
        holdout = contiguous_tasks(self.tasks, FINAL_START, FINAL_COUNT)
        comparison = contiguous_tasks(self.tasks, PREVIOUS_START, 70)
        self.assertEqual([x["task_id"] for x in holdout], NEW)
        self.assertEqual([x["task_id"] for x in comparison], ALL)
        self.assertTrue(set(NEW).isdisjoint(OLD))

    def test_rejects_malformed_or_short_dataset(self):
        with self.assertRaises(ValueError):
            contiguous_tasks(self.tasks[:163], FINAL_START, FINAL_COUNT)

    def test_summary_supports_20_and_70_without_legacy_fixed_50(self):
        tasks = self.tasks[144:164]
        before = ["    return 1\n"] * 20
        after = ["    return 2\n"] * 20
        btest = [{"passed": i == 0, "error": None if i == 0 else "container exited 1"} for i in range(20)]
        atest = [{"passed": i in (0, 1), "error": None if i in (0, 1) else "container exited 1"} for i in range(20)]
        score, records = summarize(tasks, before, btest, after, atest)
        self.assertEqual(score["n"], 20)
        self.assertAlmostEqual(score["percentage_point_delta"], 5.0)
        self.assertEqual(score["newly_passed_ids"], ["HumanEval/145"])
        self.assertEqual(score["syntax_before"]["valid"], 20)
        self.assertEqual(len(records), 20)

    def test_reuse_saved_50_and_new_20_baselines_only_when_order_exact(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)
            old = path / "old.json"
            validation = path / "validation.json"
            old.write_text(json.dumps({"variants": {"10%": [
                {"task_id": task, "before_completion": "x", "before_passed": False,
                 "before_error": "container exited 1"} for task in OLD]}}))
            validation.write_text(json.dumps({"baseline_cases": [
                {"task_id": task, "completion": "y", "passed": False, "error": "timeout"} for task in NEW]}))
            self.assertEqual(len(archived_baseline(old, validation)), 70)
            body = json.loads(old.read_text())
            body["variants"]["10%"][0]["task_id"] = "HumanEval/93"
            old.write_text(json.dumps(body))
            with self.assertRaises(ValueError):
                archived_baseline(old, validation)


def mock_score(task_ids, before_ids, after_ids, valid_before=0, valid_after=0):
    return {"n": len(task_ids), "before_passes": len(before_ids), "after_passes": len(after_ids),
            "passed_ids_before": before_ids, "passed_ids_after": after_ids,
            "failed_ids_after": [x for x in task_ids if x not in after_ids],
            "syntax_before": {"valid": valid_before, "invalid": len(task_ids) - valid_before},
            "syntax_after": {"valid": valid_after, "invalid": len(task_ids) - valid_after}}


class CollectorArithmeticTests(unittest.TestCase):
    def test_50_plus_20_results_make_seventy_rows(self):
        fifty = mock_score(OLD, [OLD[1]], [OLD[1], OLD[4]], 5, 8)
        twenty = mock_score(NEW, [NEW[2]], [NEW[2]], 3, 4)
        combined = combine_scores(fifty, twenty)
        self.assertEqual(combined["n"], 70)
        self.assertEqual((combined["before_passes"], combined["after_passes"]), (2, 3))
        self.assertAlmostEqual(combined["percentage_point_delta"], 100 / 70)
        self.assertEqual(combined["syntax_after"]["valid"], 12)

    def test_rejects_invalid_passed_and_failed_partitions(self):
        wrong = mock_score(OLD, [], [OLD[0]])
        wrong["failed_ids_after"].append(OLD[0])
        with self.assertRaises(ValueError):
            combine_scores(wrong, mock_score(NEW, [], []))


@unittest.skipUnless(importlib.util.find_spec("torch") is not None, "PyTorch not installed")
class AlgebraTests(unittest.TestCase):
    def test_saved_factor_change_is_reversible_and_checks_norm(self):
        import torch
        from tinycoder.fusion_validation import apply_reversible

        module = torch.nn.Linear(4, 4, bias=False)
        with torch.no_grad():
            module.weight.copy_(torch.eye(4))
        initial = module.weight.detach().clone()
        left = torch.tensor([[0.2], [0.0], [0.0], [0.0]])
        right = torch.tensor([[1., 0., 0., 0.]])
        observed = apply_reversible(module, left, right, expected_change=.1)
        self.assertAlmostEqual(observed, .1, places=5)
        with torch.no_grad():
            module.weight.copy_(initial)
        self.assertTrue(torch.equal(module.weight, initial))
        with self.assertRaises(ValueError):
            apply_reversible(module, left, right, expected_change=.015)
        self.assertTrue(torch.equal(module.weight, initial))


if __name__ == "__main__":
    unittest.main()
