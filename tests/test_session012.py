"""Session 012 mathematics and runtime-hook regression tests."""

import unittest

from tinycoder import session012 as s


class ProtocolTests(unittest.TestCase):
    def test_exact_70_reused_tasks(self):
        self.assertEqual((s.START, s.COUNT, s.SOURCE_COUNT, s.RANK), (94, 70, 50, 64))
        self.assertEqual(len(s.TOKEN_POSITIONS) * s.SOURCE_COUNT, 100)

    def test_disallow_leaky_references(self):
        from tinycoder.rome20 import BASE_MODEL, DATA_URL

        source = [{"task_id": f"HumanEval/{i}"} for i in range(164)]
        archive = {"holdout_records": [{"task_id": f"HumanEval/{i}",
                 "before_passed": i >= 90} for i in range(44, 94)]}
        progress = {"base_model": BASE_MODEL, "source": DATA_URL,
                    "selected_failing_ids": [f"HumanEval/{i}" for i in range(20)]}
        selected = s.select_sources(source, archive, progress)
        self.assertEqual(len(selected), 50)
        self.assertEqual(len(set(x["task_id"] for x in selected)), 50)
        self.assertTrue(all(int(x["task_id"].split("/")[-1]) < 94 for x in selected))
        archive["holdout_records"][-1]["before_passed"] = False
        with self.assertRaises(ValueError):
            s.select_sources(source, archive, progress)


try:
    import torch
except ImportError:
    torch = None


@unittest.skipIf(torch is None, "Torch unavailable in local lightweight environment")
class MathHookTests(unittest.TestCase):
    def test_rank64_is_actually_rank64_and_finite(self):
        torch.manual_seed(13)
        weight = torch.randn(96, 96)
        failures = [torch.randn(96) for _ in range(100)]
        teachers = [v + .025 * torch.randn(96) for v in failures]
        left, right, info = s.derive_rank64(weight, failures, teachers)
        self.assertEqual(left.shape, (96, 64))
        self.assertEqual(right.shape, (64, 96))
        self.assertEqual(info["applied_rank"], 64)
        self.assertGreaterEqual(info["observed_numerical_rank"], 64)
        self.assertTrue(torch.isfinite(left @ right).all())

    def test_50_single_position_keys_cannot_be_rank64(self):
        weight = torch.randn(80, 80)
        keys = [torch.randn(80) for _ in range(50)]
        with self.assertRaises(ValueError):
            s.derive_rank64(weight, keys, keys)

    def test_operator_hook_changes_residual_only_when_active(self):
        class Tokens:
            codes = {"for": 1, "while": 2, "if": 3, "return": 4, "def": 5, "range": 6}

            def encode(self, value, add_special_tokens=False):
                return [self.codes[value.strip()]]

            def decode(self, values):
                return next(k for k, v in self.codes.items() if v == values[0])

        class Inner(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.layers = torch.nn.ModuleList([torch.nn.Identity() for _ in range(16)])

        class Fake(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.model = Inner()

            def forward(self, input_ids):
                x = torch.ones((input_ids.shape[0], input_ids.shape[1], 4))
                for layer in self.model.layers:
                    x = layer(x)
                return x

        model = Fake()
        vectors = {13: torch.tensor([1.0, 0.0, 0.0, 0.0]),
                   15: torch.tensor([0.0, 1.0, 0.0, 0.0])}
        hooks = s.ConditionalResidualHooks(model, Tokens(), vectors)
        try:
            hooks.reset(1.75)
            hooks.enabled = True
            edited = model(input_ids=torch.tensor([[1], [0]]))
            self.assertAlmostEqual(edited[0, 0, 0].item(), 2.75)
            self.assertAlmostEqual(edited[0, 0, 1].item(), 2.75)
            self.assertTrue(torch.all(edited[1] == 1))
            self.assertEqual(hooks.stats()["layer_trigger_counts"], {13: 1, 15: 1})
            prompt = model(input_ids=torch.tensor([[1, 1]]))
            self.assertTrue(torch.all(prompt == 1))
        finally:
            hooks.close()
        self.assertTrue(torch.all(model(input_ids=torch.tensor([[1]])) == 1))


if __name__ == "__main__":
    unittest.main()
