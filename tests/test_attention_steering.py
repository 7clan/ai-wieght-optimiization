"""Head-resolved intervention integrity and benchmark isolation tests."""

import importlib.util
import unittest

from tinycoder.attention_steering import (
    EDITABLE_LAYERS, SCAN_LAYERS, logic_labels, rank_layers,
    select_causal_heads, source_failures,
)
from tinycoder.rome20 import BASE_MODEL, DATA_URL


class LogicProxies(unittest.TestCase):
    def test_ast_proxy_labels_come_only_from_reference_code(self):
        loop = {"prompt": "def f(n):\n", "canonical_solution":
                "    count = 0\n    for i in range(n):\n        count += i\n    return count\n"}
        self.assertEqual(logic_labels(loop), {"loop_state": True, "variable_tracking": True})
        plain = {"prompt": "def f(n):\n", "canonical_solution": "    return n + 1\n"}
        self.assertEqual(logic_labels(plain), {"loop_state": False, "variable_tracking": False})

    def test_failure_references_are_exactly_original_20_and_never_70_task_suite(self):
        problems = [{"task_id": f"HumanEval/{i}"} for i in range(164)]
        prior = {"base_model": BASE_MODEL, "source": DATA_URL,
                 "selected_failing_ids": [f"HumanEval/{i}" for i in range(20)]}
        self.assertEqual(len(source_failures(problems, prior)), 20)
        prior["selected_failing_ids"][0] = "HumanEval/94"
        with self.assertRaises(ValueError):
            source_failures(problems, prior)


class CausalRankingTests(unittest.TestCase):
    def setUp(self):
        self.cases = [{"labels": {"loop_state": i % 2 == 0,
                                  "variable_tracking": i % 2 != 0}}
                      for i in range(20)]

    def test_full_layer_scan_selects_top_two_within_12_16(self):
        effects = {layer: [0.01] * 20 for layer in SCAN_LAYERS}
        effects[11] = [10] * 20  # Out-of-window winner must be recorded but not selected.
        effects[13] = [1] * 20
        effects[16] = [2] * 20
        rows, top = rank_layers(self.cases, effects)
        self.assertEqual({x["layer"] for x in rows}, set(SCAN_LAYERS))
        self.assertEqual([x["layer"] for x in top], [16, 13])
        self.assertTrue(all(x["layer"] in EDITABLE_LAYERS for x in top))

    def test_head_assignment_one_each_loop_and_variable(self):
        effects = {12: {h: [0.5 if h == 1 else 0.0] * 20 for h in range(3)},
                   15: {h: [0.7 if h == 2 else 0.0] * 20 for h in range(3)}}
        selected = select_causal_heads(self.cases, [12, 15], effects)
        self.assertEqual({row["category"] for row in selected}, {"loop_state", "variable_tracking"})
        self.assertEqual({row["layer"] for row in selected}, {12, 15})


@unittest.skipUnless(importlib.util.find_spec("torch") is not None, "PyTorch not installed")
class TensorInterventionTests(unittest.TestCase):
    def test_rank_one_factors_touch_only_selected_head_slice_and_cap_norm(self):
        import torch
        from tinycoder.attention_steering import derive_head_rank_one

        torch.manual_seed(0)
        weight = torch.eye(8)
        keys = [torch.rand(8) for _ in range(20)]
        references = [x + .3 for x in keys]
        left, right, details = derive_head_rank_one(weight, keys, references, head=2, head_dim=2)
        self.assertEqual(left.shape, (8,))
        self.assertEqual(right.shape, (8,))
        self.assertEqual(details["rank"], 1)
        self.assertTrue(torch.count_nonzero(right[:4]) == 0)
        self.assertTrue(torch.count_nonzero(right[6:]) == 0)
        self.assertLessEqual(float(torch.linalg.vector_norm(torch.outer(left, right)) /
                                   torch.linalg.vector_norm(weight)), 0.01500001)

    def test_output_and_head_input_hooks_execute_real_counterfactuals(self):
        import torch
        from types import SimpleNamespace
        from tinycoder.attention_steering import (
            collect_attn, full_output_patch, head_input_patch_batch)

        class Block(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.self_attn = torch.nn.Module()
                self.self_attn.o_proj = torch.nn.Linear(8, 8, bias=False)
                with torch.no_grad():
                    self.self_attn.o_proj.weight.copy_(torch.eye(8))

        class Toy(torch.nn.Module):
            def __init__(self):
                super().__init__()
                self.embed = torch.nn.Embedding(8, 8)
                self.model = torch.nn.Module()
                self.model.layers = torch.nn.ModuleList(Block() for _ in range(19))
                self.head = torch.nn.Linear(8, 8)

            def forward(self, input_ids, attention_mask=None, use_cache=False):
                value = self.embed(input_ids)
                for layer in self.model.layers:
                    value = layer.self_attn.o_proj(value)
                return SimpleNamespace(logits=self.head(value))

        class Tok:
            def __call__(self, _source, add_special_tokens=False):
                return {"input_ids": [1, 2]}

        model = Toy().eval()
        tokenizer = Tok()
        captured, _ = collect_attn(model, tokenizer, "x", layers=(12, 16))
        self.assertEqual(captured[12]["input"].shape, (8,))
        score = full_output_patch(model, tokenizer, "x", 12, torch.ones(8), 3)
        self.assertIsInstance(score, float)
        values = head_input_patch_batch(model, tokenizer, "x", 12, torch.ones(8),
                                        heads=[0, 1], head_dim=4, token=3)
        self.assertEqual(len(values), 2)
        self.assertTrue(all(isinstance(x, float) for x in values))


if __name__ == "__main__":
    unittest.main()
