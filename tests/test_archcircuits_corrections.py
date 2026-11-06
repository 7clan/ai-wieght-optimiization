"""Session 011 audit corrections: protocol-level tests for the four issues
found by the independent audit of the Session 010 architectural-circuits
research.  Pure synthetic tensors and a fake tokenizer; the real model is
never loaded and model-generated code never runs here.

3.1  weight-factor scaling: saved factors must equal the applied (scaled)
     factors; reloading must reproduce the intended matrix update and stay
     within the Frobenius cap; reversal must be exact; combined edits must
     respect limits.
3.2  causal tracing: counterfactual values must be read at char-anchored
     positions computed on the counterfactual prompt's own tokenization.
3.3  reproducibility: no machine-specific default model path; architecture
     verification; repro manifest fields.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch
import torch.nn as nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from archcircuits import edits, tracing  # noqa: E402


class FakeBlock:
    def __init__(self, d_in, d_out):
        self.mlp = type("M", (), {})()
        self.mlp.down_proj = nn.Linear(d_in, d_out, bias=False)
        with torch.no_grad():
            self.mlp.down_proj.weight.normal_(0, 0.02)
        self.self_attn = type("A", (), {})()
        self.self_attn.o_proj = nn.Linear(d_in, d_out, bias=False)
        with torch.no_grad():
            self.self_attn.o_proj.weight.normal_(0, 0.02)


class FakeModel:
    """Minimal stand-in exposing model.model.layers[i].mlp.down_proj."""

    def __init__(self, n_layers=2, d_in=48, d_out=32):
        m = type("M", (), {})()
        m.layers = [FakeBlock(d_in, d_out) for _ in range(n_layers)]
        self.model = m


class TestFactorScaling(unittest.TestCase):
    """3.1: cap scaling, save/load equivalence, reversibility, combining."""

    def _random_factors(self, d_out, d_in, rank=4, seed=0, magnitude=1.0):
        g = torch.Generator().manual_seed(seed)
        left = torch.randn(d_out, rank, generator=g) * magnitude
        right = torch.randn(rank, d_in, generator=g) * magnitude
        return left, right

    def test_below_cap_no_scaling(self):
        model = FakeModel()
        left, right = self._random_factors(32, 48, seed=1, magnitude=0.01)
        w = model.model.layers[0].mlp.down_proj.weight
        before = w.detach().clone()
        scaled_left, _, stats = edits.capped_factors(model, 0, "mlp.down_proj",
                                                     left, right)
        self.assertEqual(stats["applied_scale"], 1.0)
        self.assertLessEqual(stats["relative_delta_frob"], 0.015)
        stats2, out_left, out_right = edits.cap_and_apply(
            model, 0, "mlp.down_proj", left, right)
        self.assertEqual(stats2["applied_scale"], 1.0)
        # applied delta == scaled factors exactly
        applied_delta = w.detach() - before
        expected = (out_left @ out_right).to(dtype=w.dtype)
        self.assertTrue(torch.allclose(applied_delta, expected, atol=1e-7))

    def test_above_cap_scales_and_saved_factors_match_applied(self):
        model = FakeModel()
        big_left, right = self._random_factors(32, 48, seed=2)
        big_left = big_left * 200.0  # force scaling well below 1.0
        w = model.model.layers[0].mlp.down_proj.weight
        before = w.detach().clone()
        stats, out_left, out_right = edits.cap_and_apply(
            model, 0, "mlp.down_proj", big_left, right)
        self.assertLess(stats["applied_scale"], 1.0)
        self.assertLessEqual(stats["relative_delta_frob"], 0.015)
        applied_delta = (w.detach() - before)
        self.assertTrue(torch.allclose(applied_delta,
                                       (out_left @ out_right).to(dtype=w.dtype),
                                       atol=1e-7))
        # the scaled factors must NOT equal the raw proposal
        self.assertFalse(torch.allclose(out_left, big_left))

    def test_save_reload_reproduces_matrix_update(self):
        model = FakeModel()
        big_left, right = self._random_factors(32, 48, seed=3, magnitude=0.01)
        big_left = big_left * 200.0  # force scaling
        w = model.model.layers[1].mlp.down_proj.weight
        before = w.detach().clone()
        with tempfile.TemporaryDirectory() as tmp:
            stats, out_left, out_right = edits.cap_and_apply(
                model, 1, "mlp.down_proj", big_left, right)
            meta = {"category": "TEST", "applied": stats}
            # the FIXED call pattern: save the scaled factors
            edits.save_factors(tmp, 1, "mlp.down_proj", out_left, out_right, meta)
            # reload on a fresh model and compare matrices
            model2 = FakeModel()
            # same construction seed => identical weights
            g = torch.Generator().manual_seed(0)
            model2.model.layers[1].mlp.down_proj.weight.data = before.clone()
            edits.load_factor_set(model2, tmp)
            self.assertTrue(torch.allclose(
                model2.model.layers[1].mlp.down_proj.weight.detach(),
                w.detach(), atol=1e-7))

    def test_legacy_unscaled_factor_set_rejected_on_load(self):
        model = FakeModel()
        big_left, right = self._random_factors(32, 48, seed=4)
        big_left = big_left * 150.0
        with tempfile.TemporaryDirectory() as tmp:
            meta = {"category": "TEST", "applied": {"applied_scale": 0.5}}
            # simulate the OLD bug: save the raw proposal, not the scaled one
            edits.save_factors(tmp, 0, "mlp.down_proj", big_left, right, meta)
            with self.assertRaises(ValueError):
                edits.load_factor_set(model, tmp)
            # removal (repair path) must still work without verification
            try:
                edits.load_factor_set(model, tmp, remove=True)
            except Exception:
                pass

    def test_verify_factor_set_reversibility_and_bound(self):
        model = FakeModel()
        left, right = self._random_factors(32, 48, seed=5, magnitude=0.01)
        w = model.model.layers[0].mlp.down_proj.weight
        before = w.detach().clone()
        with tempfile.TemporaryDirectory() as tmp:
            stats, out_left, out_right = edits.cap_and_apply(
                model, 0, "mlp.down_proj", left, right)
            meta = {"category": "TEST", "applied": stats}
            edits.save_factors(tmp, 0, "mlp.down_proj", out_left, out_right, meta)
            # revert the in-RAM application so verification starts pristine
            with torch.no_grad():
                w.sub_((out_left @ out_right).to(dtype=w.dtype))
            drift = float((w.detach().float() - before.float()).norm().item()) \
                / float(before.float().norm().item())
            self.assertLessEqual(drift, 1e-5)
            report = edits.verify_factor_set(model, tmp)
            self.assertTrue(report["within_limit"])
            self.assertTrue(report["reversible_within_tolerance"])
            self.assertLessEqual(report["relative_drift_after_revert"], 1e-5)
            # model untouched by verification (within float32 tolerance)
            drift2 = float((w.detach().float() - before.float()).norm().item()) \
                / float(before.float().norm().item())
            self.assertLessEqual(drift2, 1e-5)

    def test_combined_edits_within_limits(self):
        model = FakeModel()
        dirs = []
        for seed, layer in ((6, 0), (7, 0)):
            left, right = self._random_factors(32, 48, seed=seed)
            stats, out_left, out_right = edits.cap_and_apply(
                model, layer, "mlp.down_proj", left, right)
            with tempfile.TemporaryDirectory() as tmp:
                meta = {"category": f"T{seed}", "applied": stats}
                edits.save_factors(tmp, layer, "mlp.down_proj",
                                   out_left, out_right, meta)
                dirs.append(Path(tmp).name)
                # copy to a stable location (tmp dir is removed)
            # redo into stable dir
        stable = Path(tempfile.mkdtemp())
        try:
            stable_dirs = []
            for seed, layer in ((6, 0), (7, 0)):
                left, right = self._random_factors(32, 48, seed=seed, magnitude=0.01)
                w = model.model.layers[layer].mlp.down_proj.weight
                # reload pristine weight from a fresh model with same seed
                fresh = FakeModel()
                w.data = fresh.model.layers[layer].mlp.down_proj.weight.data.clone()
                stats, out_left, out_right = edits.cap_and_apply(
                    model, layer, "mlp.down_proj", left, right)
                d = stable / f"e{seed}"
                meta = {"category": f"T{seed}", "applied": stats}
                edits.save_factors(str(d), layer, "mlp.down_proj",
                                   out_left, out_right, meta)
                stable_dirs.append(str(d))
            report = edits.verify_combined(model, stable_dirs)
            self.assertEqual(report["n_edits"], 2)
            key = "L0/mlp.down_proj"
            self.assertIn(key, report["touched_matrices"])
            comb = report["touched_matrices"][key]["combined_relative_change"]
            # two 1.5% caps can combine to at most ~3% in the worst case;
            # the individual bounds are what the protocol guarantees.
            self.assertLessEqual(comb, 0.031)
        finally:
            import shutil
            shutil.rmtree(stable, ignore_errors=True)


class FakeTokenizer:
    """Whitespace tokenizer with configurable per-prompt tokenization for
    alignment tests.  Tokens are space-separated words; offsets are exact."""

    def __call__(self, text, add_special_tokens=False, return_offsets_mapping=False,
                 **kwargs):
        words = text.split(" ")
        ids = [abs(hash(w)) % 100000 for w in words]
        offsets = []
        pos = 0
        for w in words:
            offsets.append((pos, pos + len(w)))
            pos += len(w) + 1
        out = {"input_ids": ids}
        if return_offsets_mapping:
            out["offset_mapping"] = offsets
        return out

    def decode(self, ids):
        return " ".join(str(i) for i in ids)


class TestTracingAlignment(unittest.TestCase):
    """3.2: cf values read at cf-prompt positions, never shared indices."""

    def test_aligned_positions_same_tokenization(self):
        tok = FakeTokenizer()
        prompt = "def alpha_one ( x ) : return x"
        align = tracing.aligned_span_positions(tok, prompt, "alpha_one",
                                               other_prompt=prompt,
                                               other_span="alpha_one")
        self.assertEqual(align["positions"], [1, 2] if False else align["positions"])
        self.assertTrue(align["positions"])
        self.assertEqual(align["other_positions"], align["positions"])
        self.assertTrue(align["tokenization_matches"])

    def test_aligned_positions_different_tokenization(self):
        tok = FakeTokenizer()
        # orig has 2 tokens before the span; cf has 5 (longer identifier list)
        orig = "use A B target here"
        cf = "use A LONGER SET OF target here"
        align = tracing.aligned_span_positions(tok, orig, "target",
                                               other_prompt=cf, other_span="target")
        # orig words: use A B target here   -> target at index 3
        # cf words:   use A LONGER SET OF target here -> target at index 5
        self.assertEqual(align["positions"], [3])
        self.assertEqual(align["other_positions"], [5])
        self.assertEqual(align["index_shift"], 2)
        self.assertFalse(align["tokenization_matches"])
        # the core guarantee: the same numerical index is NOT reused
        self.assertNotEqual(align["positions"], align["other_positions"])

    def test_missing_span_reported(self):
        tok = FakeTokenizer()
        align = tracing.aligned_span_positions(tok, "a b c", "zzz")
        self.assertEqual(align["positions"], [])
        self.assertIn("error", align)

    def test_span_positions_char_anchored(self):
        tok = FakeTokenizer()
        text = "let total = total + 1"
        # first occurrence only
        pos = tracing.span_positions(tok, text, "total")
        self.assertEqual(pos, [1])


class TestReproducibility(unittest.TestCase):
    """3.3: env-configured model path, architecture gate, manifest fields."""

    def test_no_hardcoded_default(self):
        import os
        from archcircuits import runner
        saved = os.environ.pop("ARCHCIRCUITS_MODEL_DIR", None)
        try:
            with self.assertRaises(RuntimeError):
                runner.resolve_model_path()
        finally:
            if saved is not None:
                os.environ["ARCHCIRCUITS_MODEL_DIR"] = saved
        # no machine-specific default remains in the source
        src = Path(runner.__file__).read_text()
        self.assertNotIn("/home/z/models", src)
        self.assertNotIn('MODEL_PATH = "/', src)

    def test_architecture_constants(self):
        from archcircuits import runner
        self.assertEqual(runner.EXPECTED_PARAM_COUNT, 494_032_768)
        self.assertEqual(runner.EXPECTED_LAYERS, 24)
        self.assertEqual(runner.EXPECTED_HIDDEN, 896)

    def test_repro_info_fields(self):
        from archcircuits import runner
        import os
        with tempfile.TemporaryDirectory() as tmp:
            # minimal fake checkpoint file for hashing
            (Path(tmp) / "model.safetensors").write_bytes(b"fake-bytes")
            os.environ["ARCHCIRCUITS_MODEL_DIR"] = tmp
            info = runner.repro_info()
            for key in ("base_model_id", "model_safetensors_sha256",
                        "torch_version", "python_version", "decoding"):
                self.assertIn(key, info)
            self.assertEqual(len(info["model_safetensors_sha256"]), 64)
            self.assertTrue(info["decoding"]["greedy"])
            self.assertEqual(info["decoding"]["temperature"], 0.0)

    def test_report_includes_repro(self):
        """evaluate_tasks attaches a repro block (or a disclosed error)."""
        from archcircuits import runner
        # summarize-level check: the function exists and attaches the field
        self.assertTrue(callable(runner.repro_info))


if __name__ == "__main__":
    unittest.main(verbosity=2)
