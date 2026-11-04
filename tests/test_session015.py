"""New-task, prompt-context and exact functional prehook contracts."""

import importlib.util
import json
from pathlib import Path
import unittest

from tinycoder.session015 import (BACKEND_TRIGGERS, EXPECTED_FACTOR_SHA256,
                                  TRACKS, UI_TRIGGERS, ContextGatedFactors,
                                  classify_prompt, track_configuration)
from tinycoder.session014_fixtures import make_web_tasks


class SelectionTests(unittest.TestCase):
    def test_fresh_web_prompts_and_ids(self):
        old=make_web_tasks(offset=0)
        new=make_web_tasks(offset=25)
        self.assertEqual(len(new),50)
        self.assertFalse({x["task_id"] for x in old}&{x["task_id"] for x in new})
        self.assertFalse({x["prompt"] for x in old}&{x["prompt"] for x in new})
        self.assertEqual(sum(classify_prompt(t["prompt"])["mode"]=="ui" for t in new),25)
        self.assertEqual(sum(classify_prompt(t["prompt"])["mode"]=="backend" for t in new),25)

    def test_historical_mbpp_ids_excluded(self):
        obj=json.loads(Path("data/session015_excluded_mbpp_ids.json").read_text())
        self.assertEqual(obj["excluded_count"],150)
        self.assertEqual(len(set(obj["session013_ids"]+obj["session014_ids"])),150)
        self.assertEqual(obj["session014_factor_sha256"],EXPECTED_FACTOR_SHA256)


class PromptClassificationTests(unittest.TestCase):
    def test_explicit_keywords_and_baseline_fallback(self):
        for keyword in UI_TRIGGERS:
            self.assertEqual(classify_prompt("Build " + keyword)["mode"],"ui")
        for keyword in BACKEND_TRIGGERS:
            self.assertEqual(classify_prompt("Build " + keyword)["mode"],"backend")
        for prompt in ("def factorial(n):", "Compute gcd of two integers", "class Stack:"):
            self.assertEqual(classify_prompt(prompt)["mode"],"baseline")
        self.assertEqual(classify_prompt("JSX express")["mode"],"baseline")

    def test_tracks_and_zero_mask(self):
        self.assertEqual(len(TRACKS),6)
        self.assertEqual(track_configuration("gated-0.0")["multiplier"],0.0)
        self.assertTrue(track_configuration("gated-ui-only-1.0")["ui_only"])
        with self.assertRaises(ValueError):
            track_configuration("unknown")


@unittest.skipUnless(importlib.util.find_spec("torch"),"PyTorch unavailable locally")
class FunctionalHookTests(unittest.TestCase):
    def test_prehooks_implement_exact_conditional_low_rank_weights(self):
        import torch
        import torch.nn.functional as F
        class Layer:
            def __init__(self):
                self.mlp=type("MLP",(),{})()
                self.mlp.down_proj=torch.nn.Linear(12,8,bias=False)
        class FakeModel:
            def __init__(self):
                self.model=type("Decoder",(),{})()
                self.model.layers=[Layer() for _ in range(17)]
        model=FakeModel()
        factors={f"layer{n}.{part}":torch.randn(8,3) if part=="left" else torch.randn(3,12)
                 for n in (8,16) for part in ("left","right")}
        x=torch.randn(2,4,12)
        w8=model.model.layers[8].mlp.down_proj.weight.detach().clone()
        w16=model.model.layers[16].mlp.down_proj.weight.detach().clone()
        orig8=F.linear(x,w8)
        orig16=F.linear(x,w16)
        for mode,gain,expected_ui,expected_api in (
            ("baseline",1.0,0.0,0.0),
            ("ui",1.0,1.0,0.0),
            ("backend",0.5,0.0,0.5),
            ("ui",0.0,0.0,0.0)):
            with self.subTest(mode=mode,gain=gain):
                with ContextGatedFactors(model,factors,mode,gain):
                    y8=model.model.layers[8].mlp.down_proj(x)
                    y16=model.model.layers[16].mlp.down_proj(x)
                delta8=F.linear(F.linear(x,factors["layer8.right"]),factors["layer8.left"])
                delta16=F.linear(F.linear(x,factors["layer16.right"]),factors["layer16.left"])
                self.assertTrue(torch.allclose(y8,orig8+expected_ui*delta8,atol=1e-5))
                self.assertTrue(torch.allclose(y16,orig16+expected_api*delta16,atol=1e-5))
        with ContextGatedFactors(model,factors,"backend",1.0,ui_only=True):
            actual=model.model.layers[16].mlp.down_proj(x)
        self.assertTrue(torch.equal(actual,orig16))
        self.assertTrue(torch.equal(w8,model.model.layers[8].mlp.down_proj.weight))
        self.assertTrue(torch.equal(w16,model.model.layers[16].mlp.down_proj.weight))


if __name__=="__main__":
    unittest.main()
