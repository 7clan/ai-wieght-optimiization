"""Session 010 accounting, conservative taxonomy and rank-eight surgery tests."""

import importlib.util
import unittest

from tinycoder.session010 import (
    BINS, LAYERS, RANK, classify_failure, source_risk_labels,
    valid_failed_cases,
)


class TaxonomyTests(unittest.TestCase):
    def test_only_syntax_valid_failures_not_valid_passes_are_diagnosed(self):
        problems = [{"task_id": f"HumanEval/{i}", "prompt": "def f(x):\n"}
                    for i in range(94, 164)]
        records = [{"task_id": p["task_id"], "after_completion": "    return 1\n",
                    "after_passed": i % 2 == 0, "after_error": "failure"}
                   for i, p in enumerate(problems)]
        records[-1]["after_completion"] = "    return (\n"
        fails, valid = valid_failed_cases(problems, {"task_ids": [p["task_id"] for p in problems],
                                                      "cases": records})
        self.assertEqual(len(valid), 69)
        self.assertEqual(len(fails), 34)
        self.assertNotIn("HumanEval/163", valid)

    def test_observed_index_error_is_boundary_not_guessed_from_source(self):
        task = {"prompt": "def f(a):\n", "entry_point": "f"}
        outcome = {"outcome": "failed", "exception_type": "IndexError", "failing_assertion": None}
        self.assertEqual(classify_failure(task, "    return a[10]", outcome)["category"], BINS[0])

    def test_empty_no_return_maps_to_wrong_output_type_proxy(self):
        task = {"prompt": "def f(x):\n", "entry_point": "f"}
        outcome = {"outcome": "failed", "exception_type": "AssertionError", "failing_assertion": "assert f([]) == []"}
        self.assertEqual(classify_failure(task, "    pass", outcome)["category"], BINS[1])

    def test_no_unjustified_off_by_one_label_for_general_assertion(self):
        task = {"prompt": "def f(x):\n", "entry_point": "f"}
        outcome = {"outcome": "failed", "exception_type": "AssertionError", "failing_assertion": "assert f(10) == 2"}
        self.assertIsNone(classify_failure(task, "    return x * 2", outcome)["category"])

    def test_ast_risk_categories_are_explicit_proxies(self):
        task = {"prompt": "def f(xs):\n", "canonical_solution":
                "    return [x for x in xs if x > 0]\n"}
        self.assertEqual(source_risk_labels(task), {"boundary_proxy": True, "return_type_proxy": True})


@unittest.skipUnless(importlib.util.find_spec("torch") is not None, "PyTorch not installed")
class SVDTests(unittest.TestCase):
    def test_rank_eight_surgery_is_reversible_and_norm_bounded(self):
        import torch
        from tinycoder.session010 import derive_svd_rank8

        torch.manual_seed(42)
        weight = torch.eye(16)
        keys = [torch.randn(16) for _ in range(20)]
        references = [key + .1*torch.randn(16) for key in keys]
        labels = [{"boundary_proxy": i % 2 == 0, "return_type_proxy": i % 2 == 1}
                  for i in range(20)]
        left, right, info = derive_svd_rank8(weight, keys, references, labels)
        self.assertEqual(left.shape, (16, RANK))
        self.assertEqual(right.shape, (RANK, 16))
        self.assertEqual(info["rank"], 8)
        self.assertLessEqual(float(torch.linalg.vector_norm(left @ right) /
                                   torch.linalg.vector_norm(weight)), .0150001)
        self.assertEqual(LAYERS, (12, 13, 15))


if __name__ == "__main__":
    unittest.main()
