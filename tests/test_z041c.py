"""Session 041C module checks; no generated code execution.

Covers the rescore driver's provenance guard (without running any
evaluation) and the longer-code-generation benchmark's structural
invariants: slot planning, repetition metric behavior and prompt
archival. The behavioral gates (11/11 + 15/15 control matrices) are
archived evidence, not unit tests.
"""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from archagent.z041c import bench_long, bench_long_child

ROOT = Path(__file__).resolve().parents[1]


class BenchLongStructuralTests(unittest.TestCase):
    def test_slot_plan_covers_both_models_both_budgets_and_continuity(self):
        slots = bench_long.all_run_slots()
        self.assertEqual(len(slots), 22)
        counts = {}
        for slot in slots:
            counts[(slot["model"], slot["budget"])] = \
                counts.get((slot["model"], slot["budget"]), 0) + 1
        for model in ("base", "merged"):
            self.assertEqual(counts[(model, 512)], 4)
            self.assertEqual(counts[(model, 1024)], 4)
            self.assertEqual(counts[(model, 128)], 3)  # continuity trials
        for slot in slots:
            self.assertTrue(slot["trial"] >= 0)

    def test_long_prompts_are_neutral_and_anchored(self):
        for name, text in bench_long.LONG_PROMPTS.items():
            self.assertIn("continue from it", text, name)
            # anchored continuation: the first line is supplied after the brief
            self.assertTrue(text.rstrip().splitlines()[-1].strip(), name)

    def test_stage_prompts_archives_sha256_of_every_prompt(self):
        import hashlib
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(bench_long, "BENCH", Path(temp) / "bench"), \
                 patch.object(bench_long, "RUNS", Path(temp) / "bench" / "runs"):
                files = bench_long.stage_prompts()
                archive = __import__("json").loads(
                    (Path(temp) / "bench" / "prompts.json").read_text())
            self.assertEqual(set(archive["prompts"]),
                             {"continuity-128", *bench_long.LONG_PROMPTS})
            for name, path in files.items():
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                self.assertEqual(archive["prompts"][name]["sha256"], digest, name)
                self.assertEqual(archive["prompts"][name]["chars"], len(path.read_text()))


class Distinct3Tests(unittest.TestCase):
    def test_perfectly_repetitive_text_scores_near_zero(self):
        text = ("import { useSearchParams } from \"next/navigation\";\n" * 200)
        self.assertLess(bench_long_child.distinct_3(text), 0.05)

    def test_disjoint_text_scores_one_and_short_text_is_defined(self):
        self.assertEqual(bench_long_child.distinct_3("alpha beta gamma delta"), 1.0)
        self.assertEqual(bench_long_child.distinct_3(""), 1.0)
        self.assertEqual(bench_long_child.distinct_3("one two"), 1.0)


class RescoreProvenanceTests(unittest.TestCase):
    def test_driver_pins_the_single_affected_archived_record(self):
        import json
        archived = json.loads(
            (ROOT / "experiments/z041-coding-finetune/eval/merged/track-B/"
             "radiostation__api-post-validation.json").read_text())
        self.assertEqual(archived["verdict"]["passed"], True)  # the 041B PASS
        self.assertEqual(archived["verdict"]["case_count"], 10)  # pre-amendment
        staged = (ROOT / "experiments/z041c-evaluator-correction/rescore/"
                  "merged-trackB-api-post-validation/output.ts").read_text()
        import hashlib
        self.assertEqual(hashlib.sha256(staged.encode()).hexdigest(),
                         archived["candidate_final_sha256"],
                         "staged candidate must be byte-identical to the archive")

    def test_rescore_result_recorded_the_flip_and_amendment(self):
        import json
        record = json.loads(
            (ROOT / "experiments/z041c-evaluator-correction/rescore/"
             "merged-trackB-api-post-validation-corrected-verdict.json"
             ).read_text())
        self.assertEqual(record["original_verdict"]["passed"], True)
        self.assertEqual(record["passed"], False)
        self.assertEqual(record["status"], "BEHAVIOR_FAIL")
        self.assertEqual(record["case_count"], 11)
        self.assertEqual(record["case_amendment"], "041C-duplicate-title-scope")
        failed = [c["name"] for c in record["checks"] if not c["passed"]]
        self.assertEqual(failed, ["duplicate-title-other-parent"])


if __name__ == "__main__":
    unittest.main()
