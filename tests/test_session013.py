"""CPU-only unit tests: no model downloads, no generated-code execution."""

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from tinycoder.collect_session013 import collect
from tinycoder.session013 import (ANCHOR_BLOB_SHA, DOCKER_IMAGE, MODEL_ID,
                                 TASK_COUNT, docker_eval_command,
                                 freeze_task_selection, git_blob_hash,
                                 is_syntax_valid, normalize_prompt, summarize,
                                 validate_archived_anchor)


class DatasetContractTests(unittest.TestCase):
    def sample(self):
        problems = {}
        originals = {}
        for number in range(11, 161):
            task_id = f"Mbpp/{number}"
            prompt = f"def task_{number}(x):\n    \"\"\"Return x.\"\"\"\n"
            problems[task_id] = {"task_id": task_id, "prompt": prompt,
                                 "canonical_solution": "    return x\n"}
            originals[str(number)] = {"task_id": number, "text": prompt}
        return problems, originals

    def test_fixed_selection_is_deterministic_and_disjoint(self):
        problems, originals = self.sample()
        human_eval = [{"prompt": problems["Mbpp/32"]["prompt"]}]
        first = freeze_task_selection(problems, originals, human_eval)
        second = freeze_task_selection(dict(reversed(list(problems.items()))), originals, human_eval)
        self.assertEqual([p["task_id"] for p in first], [p["task_id"] for p in second])
        self.assertEqual(len(first), TASK_COUNT)
        self.assertNotIn("Mbpp/32", {p["task_id"] for p in first})
        self.assertTrue(all(p["task_id"].startswith("Mbpp/") for p in first))

    def test_not_enough_problems_refused(self):
        problems, originals = self.sample()
        with self.assertRaises(ValueError):
            freeze_task_selection(dict(list(problems.items())[:5]), originals, [])

    def test_pretrained_contamination_not_inferred_from_namespaces(self):
        self.assertNotEqual(normalize_prompt("def foo(x):\n return x"),
                            normalize_prompt("def bar(x):\n return x"))


class EditingAndSandboxTests(unittest.TestCase):
    def test_exact_factor_identity_and_hash(self):
        path = Path("experiments/exp03_norm_break_factors.safetensors")
        self.assertTrue(path.is_file())
        self.assertEqual(git_blob_hash(path.read_bytes()), ANCHOR_BLOB_SHA)
        self.assertEqual(validate_archived_anchor(path), hashlib.sha256(path.read_bytes()).hexdigest())

    def test_model_is_base_0p5b(self):
        self.assertEqual(MODEL_ID, "Qwen/Qwen2.5-Coder-0.5B")

    def test_docker_has_isolation_controls(self):
        cmd = docker_eval_command(Path("/tmp/source"), Path("/tmp/results"), "example")
        self.assertIn("--network", cmd)
        self.assertEqual(cmd[cmd.index("--network") + 1], "none")
        self.assertIn("--read-only", cmd)
        self.assertIn("--cap-drop", cmd)
        self.assertIn("--user", cmd)
        self.assertIn("65534:65534", cmd)
        self.assertIn(DOCKER_IMAGE, cmd)

    def test_syntax_parsing(self):
        self.assertTrue(is_syntax_valid("def ok():\n    return 1\n"))
        self.assertFalse(is_syntax_valid("def bad(:\n"))


class MetricTests(unittest.TestCase):
    def test_taxonomy_exhaustiveness(self):
        rows = []
        for index in range(TASK_COUNT):
            if index < 20:
                base, plus, syntax, label = True, True, True, "passed"
            elif index < 40:
                base, plus, syntax, label = True, False, True, "boundary_edge_case"
            elif index < 70:
                base, plus, syntax, label = False, False, True, "assertion_error"
            else:
                base, plus, syntax, label = False, False, False, "syntax_invalid"
            rows.append({"task_id": f"Mbpp/{index+11}", "base_pass": base,
                         "plus_pass": plus, "syntax_valid": syntax,
                         "failure_bin": label})
        summary = summarize(rows)
        self.assertEqual(summary["base_pass_count"], 40)
        self.assertEqual(summary["plus_pass_count"], 20)
        self.assertEqual(summary["syntax_valid_count"], 70)
        self.assertEqual(summary["failure_taxonomy"]["syntax_invalid"]["count"], 30)

    def test_refuse_incoherent_pass(self):
        rows = [{"task_id": f"Mbpp/{i+11}", "base_pass": False,
                 "plus_pass": True, "syntax_valid": True, "failure_bin": "passed"}
                for i in range(TASK_COUNT)]
        with self.assertRaises(ValueError):
            summarize(rows)

    def test_collector_matches_tracks_and_publishes_real_counts(self):
        def records(after):
            rows = []
            for i in range(TASK_COUNT):
                success = i < (4 if after else 3)
                rows.append({"task_id": f"Mbpp/{i + 11}", "base_pass": success,
                             "plus_pass": success, "syntax_valid": True,
                             "failure_bin": "passed" if success else "assertion_error"})
            return rows

        ids = [f"Mbpp/{i + 11}" for i in range(TASK_COUNT)]
        manifest = {"task_ids": ids, "selection_seed": "session013-mbppplus-independent-v1",
                    "human_eval_normalized_prompt_overlap": [], "prior_experimental_overlap": [],
                    "dataset_md5": "fixture"}
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for name in ("baseline", "anchor"):
                folder = directory / name
                folder.mkdir()
                after = name == "anchor"
                data = records(after)
                report = {"status": "completed", "track": name,
                          "model": MODEL_ID, "training_steps": 0,
                          "factor_git_blob_sha": ANCHOR_BLOB_SHA,
                          "factor_source_commit": "e100c628cd8fcf3c500e5c39070168e213b208aa",
                          "dataset_manifest": manifest, "task_results": data,
                          "metrics": summarize(data), "parameter_count": 494_000_000,
                          "factor_sha256": "matching-factor", "max_new_tokens": 160,
                          "batch_size": 4, "temperature": 0,
                          "observed_relative_frobenius": 0.10 if after else 0.0}
                (folder / "report.json").write_text(json.dumps(report))
                (folder / "manifest.json").write_text(json.dumps(manifest))
                predictions = [{"task_id": id, "completion": "return 1"} for id in ids]
                (folder / "predictions.json").write_text(json.dumps(predictions))
            readme = directory / "README.md"
            readme.write_text("# TinyCoder Weight Lab\n\nOriginal content.\n")
            final = collect(directory / "baseline", directory / "anchor",
                            directory / "experiments", readme)
            self.assertEqual(final["comparison"]["mbpp_plus_execution"]["after_count"], 4)
            self.assertEqual(final["comparison"]["mbpp_plus_execution"]["percentage_point_delta"], 1)
            self.assertIn("Session 013", readme.read_text())
            self.assertTrue((directory / "experiments" / "session013_generalization_report.json").is_file())


if __name__ == "__main__":
    unittest.main()
