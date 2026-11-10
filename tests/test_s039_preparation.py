"""Session 039 trusted metadata checks; no generated code execution."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from archagent.finetune import reconcile_038a
from archagent.s039 import curriculum, scenarios


ROOT = Path(__file__).resolve().parents[1]


class ReconciliationTests(unittest.TestCase):
    def test_archived_replay_claims_metadata_consistent_but_no_training(self):
        out = reconcile_038a.evaluate(ROOT)
        self.assertEqual(out["queue_candidates"], 22)
        self.assertEqual(out["reported_behavior_passes"], 22)
        self.assertEqual(out["kind_counts"], {"invariant": 3, "prisma-model": 19})
        self.assertTrue(out["metadata_consistent"], out["errors"])
        self.assertFalse(out["docker_reproduced"])
        self.assertEqual(out["training_eligible"], 0)

    def test_tampered_replay_check_is_caught(self):
        original = reconcile_038a._read_jsonl

        def changed(path):
            rows = original(path)
            if path.name == "replay-results.jsonl":
                rows[0]["verification"]["sqlite_behavior"]["pass"] = False
            return rows

        with patch.object(reconcile_038a, "_read_jsonl", side_effect=changed):
            out = reconcile_038a.evaluate(ROOT)
        self.assertFalse(out["metadata_consistent"])
        self.assertTrue(any("behavior_claim_incomplete" in x for x in out["errors"]))

    def test_provenance_model_pin_change_is_caught(self):
        original = reconcile_038a._read_json

        def changed(path):
            result = original(path)
            if path.name == "training-candidates.json":
                result["entries"][0]["provenance"]["model_sha256"] = "0" * 64
            return result

        with patch.object(reconcile_038a, "_read_json", side_effect=changed):
            out = reconcile_038a.evaluate(ROOT)
        self.assertFalse(out["metadata_consistent"])
        self.assertTrue(any("model_pin_mismatch" in x for x in out["errors"]))

    def test_path_escape_is_rejected(self):
        self.assertIsNone(reconcile_038a._safe_file(ROOT, "../outside.json"))


class CurriculumTests(unittest.TestCase):
    def test_unique_split_domains_and_task_ids(self):
        domains = [d[0] for pack in curriculum.DOMAINS.values() for d in pack]
        self.assertEqual(len(domains), len(set(domains)))
        tasks = [t for split in curriculum.DOMAINS for t in curriculum.build(split)["tasks"]]
        self.assertEqual(len(tasks), 96)
        self.assertEqual(len({t["id"] for t in tasks}), 96)
        self.assertEqual({t["skill"] for t in tasks}, set(curriculum.SKILLS))

    def test_all_tasks_contain_behavioral_edge_cases(self):
        for split in curriculum.DOMAINS:
            for t in curriculum.build(split)["tasks"]:
                self.assertTrue(t["positive_cases_required"], t["id"])
                self.assertTrue(t["negative_cases_required"], t["id"])
                self.assertEqual(t["status"], "SPEC_ONLY_NOT_GENERATED")
                self.assertEqual(t["provenance"], "AUTHOR_SPEC_NOT_QWEN_CODE")

    def test_sealed_holdout(self):
        self.assertFalse(curriculum.build("holdout")["generation_permitted"])
        self.assertTrue(curriculum.build("holdout")["sealed_until_final_scoring"])
        self.assertFalse(curriculum.build("train")["sealed_until_final_scoring"])

    def test_freeze_is_reproducible_and_not_overwritable(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            curriculum.freeze(path, check_only=False)
            curriculum.freeze(path, check_only=True)
            with self.assertRaises(FileExistsError):
                curriculum.freeze(path, check_only=False)
            (path / "dev.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                curriculum.freeze(path, check_only=True)

    def test_frozen_files_and_hashes_match_checked_in(self):
        path = ROOT / "experiments/z039-generalization-learning/suite"
        curriculum.freeze(path, check_only=True)
        manifest = json.loads((path / "MANIFEST.json").read_text(encoding="utf-8"))
        for split, detail in manifest["splits"].items():
            data = (path / f"{split}.json").read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), detail["sha256"])
        self.assertEqual(manifest["trainable_records"], 0)


class ScenarioPlanTests(unittest.TestCase):
    def test_train_and_dev_scenarios_are_nonexecuting_plans(self):
        for split, expected in (("train", 54), ("dev", 18)):
            result = scenarios.build(ROOT, split)
            self.assertEqual(len(result["tasks"]), expected)
            self.assertEqual(result["candidate_execution_count"], 0)
            self.assertEqual(result["training_eligible"], 0)
            for item in result["tasks"]:
                self.assertTrue(item["cases"])
                self.assertEqual(len(item["fixture"]["children"]), 3)
                self.assertEqual(item["status"], "UNEXECUTED_BEHAVIOR_SCENARIOS")

    def test_holdout_is_never_opened_by_preparation(self):
        with self.assertRaises(PermissionError):
            scenarios.load_split(ROOT, "holdout")
        with self.assertRaises(PermissionError):
            scenarios.build(ROOT, "holdout")
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(PermissionError):
                scenarios.write(ROOT, "holdout", Path(temp) / "x.json", check=False)

    def test_get_and_post_scenarios_discriminate_valid_invalid(self):
        suite = scenarios.build(ROOT, "dev")
        get = next(t for t in suite["tasks"] if t["skill"] == "api-get-filter")
        post = next(t for t in suite["tasks"] if t["skill"] == "api-post-validation")
        self.assertEqual(next(c for c in get["cases"] if c["name"] == "list-all")["expected_titles"], ["Amber", "Beacon", "Cobalt"])
        self.assertEqual(next(c for c in get["cases"] if c["name"] == "no-matches")["expected_total"], 0)
        self.assertEqual(next(c for c in post["cases"] if c["name"] == "below-min")["expected_persist_delta"], 0)
        self.assertEqual(next(c for c in post["cases"] if c["name"] == "min-boundary")["expected_persist_delta"], 1)
        self.assertEqual(next(c for c in post["cases"] if c["name"] == "duplicate-title")["expected_status"], 409)

    def test_scenario_files_reproduce_without_overwrite(self):
        for split in ("train", "dev"):
            target = ROOT / "experiments/z039-generalization-learning/scenarios" / f"{split}.json"
            scenarios.write(ROOT, split, target, check=True)
            with self.assertRaises(FileExistsError):
                scenarios.write(ROOT, split, target, check=False)


if __name__ == "__main__":
    unittest.main()
