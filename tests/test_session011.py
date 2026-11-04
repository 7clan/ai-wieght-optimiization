"""Fast pre-flight checks; tensor tests additionally run on hosted CPU PyTorch."""

import json
import unittest
from pathlib import Path

from tinycoder.session011 import select_fifty, STRESS_LAYERS, RANK32_TARGETS, STRESS_LEVELS


ROOT = Path(__file__).resolve().parents[1]


class Session011FailureSetTest(unittest.TestCase):
    def test_exactly_fifty_source_failures_outside_benchmark(self):
        archive = json.loads((ROOT / "experiments/rome_batch_predictions.json").read_text())
        progress = json.loads((ROOT / "experiments/2026-11-04-rome20/progress.json").read_text())
        ids = progress["selected_failing_ids"] + [r["task_id"] for r in archive["holdout_records"]]
        problems = [{"task_id": task_id} for task_id in ids]
        result = select_fifty(problems, archive, progress)
        self.assertEqual(len(result), 50)
        self.assertEqual(len({r["task_id"] for r in result}), 50)
        self.assertTrue(all(int(r["task_id"].split("/")[1]) < 94 for r in result))

    def test_targets_and_stress_levels(self):
        self.assertEqual(STRESS_LAYERS, (6, 8, 10, 14))
        self.assertEqual(RANK32_TARGETS, ((8, "mlp.down_proj"),
                                          (13, "self_attn.o_proj"),
                                          (15, "self_attn.o_proj")))
        self.assertEqual(STRESS_LEVELS, (.15, .30, .50))


class Session011TensorTest(unittest.TestCase):
    @unittest.skipUnless(__import__("importlib").util.find_spec("torch"), "PyTorch not installed")
    def test_rank32_factorization_reconstruction_and_scaling(self):
        import torch
        from tinycoder.session011 import multi_key_ridge, scaled_factors

        torch.manual_seed(17)
        weight = torch.randn(72, 80)
        failed = [torch.randn(80) for _ in range(50)]
        teacher = [k + torch.randn(80) * 0.03 for k in failed]
        full_l, full_r, full_info = multi_key_ridge(weight, failed, teacher)
        low_l, low_r, low_info = multi_key_ridge(weight, failed, teacher, rank=32)
        self.assertEqual(low_l.shape, (72, 32))
        self.assertEqual(low_r.shape, (32, 80))
        self.assertEqual(low_info["rank_upper_bound"], 32)
        self.assertLessEqual(torch.linalg.vector_norm(low_l @ low_r),
                             torch.linalg.vector_norm(full_l @ full_r) + 1e-3)
        scaled_l, scaled_r, _ = scaled_factors(full_l, full_r, weight, .30)
        actual = (torch.linalg.vector_norm(scaled_l @ scaled_r) /
                  torch.linalg.vector_norm(weight)).item()
        self.assertAlmostEqual(actual, .30, places=5)


if __name__ == "__main__":
    unittest.main()
