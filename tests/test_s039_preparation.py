"""Session 039 trusted metadata checks; no generated code execution."""

import hashlib
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from archagent.finetune import reconcile_038a
from archagent.s039 import curriculum, curriculum_v2, scenarios, docker_only, invariant_eval


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

    def test_version_two_repairs_status_requirement_without_rewriting_v1(self):
        v1_file = ROOT / "experiments/z039-generalization-learning/suite/MANIFEST.json"
        before = v1_file.read_bytes()
        directory = ROOT / "experiments/z039-generalization-learning/suite-v2"
        curriculum_v2.freeze(directory, check=True)
        self.assertEqual(before, v1_file.read_bytes())
        amended = curriculum_v2.build("dev")
        schema = next(x for x in amended["tasks"] if x["skill"] == "schema-relationship")
        self.assertTrue(any("status String" in req for req in schema["requirements"]))
        self.assertEqual(schema["contract_version"], 2)

    def test_version_two_scenario_export_and_heldout_lock(self):
        for split in ("train", "dev"):
            target = ROOT / "experiments/z039-generalization-learning/scenarios-v2" / f"{split}.json"
            scenarios.write(ROOT, split, target, check=True, suite_version=2)
        with self.assertRaises(PermissionError):
            scenarios.build(ROOT, "holdout", suite_version=2)


class DockerOnlyHarnessTests(unittest.TestCase):
    IMAGE = "s039-eval@sha256:" + "a" * 64

    def test_docker_command_pins_image_and_constrains_capabilities(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cand, harness = root / "candidate", root / "harness"
            cand.mkdir(); harness.mkdir()
            (harness / "runner.mjs").write_text("// trusted fixture", encoding="utf-8")
            args = docker_only.command(self.IMAGE, cand, harness)
            self.assertIn("none", args)
            self.assertIn("--read-only", args)
            self.assertIn("--cap-drop", args)
            self.assertIn("no-new-privileges", args)
            self.assertIn("readonly", " ".join(args))
            self.assertIn(self.IMAGE, args)
            with self.assertRaises(ValueError):
                docker_only.command("node:latest", cand, harness)

    # ------------------------------------------------------------------
    # CI identification contract (post-review fix, see
    # docs/ZAI_SESSION039_DOCKER_EXECUTION.md "CI workflow review fixes").
    # The workflow records the pushed GHCR reference
    # ghcr.io/<owner>/<repo>/s039-route-eval@sha256:<64-hex> (RepoDigests[0]
    # after the push) and gate-checks it with a grep regex that MUST stay
    # identical to the evaluator's IMAGE_RE. The first workflow draft fell
    # back to the repository-less local image ID, which the evaluators
    # reject — these tests pin the fixed behaviour on both sides.
    # ------------------------------------------------------------------
    GHCR_IMAGE = "ghcr.io/7clan/ai-wieght-optimiization/s039-route-eval@sha256:" + "c" * 64
    BARE_LOCAL_ID = "sha256:" + "d" * 64  # `docker image inspect --format '{{.Id}}'`

    def _workflow_grep_patterns(self):
        text = (ROOT / ".github/workflows/s039-docker-eval.yml").read_text(encoding="utf-8")
        return re.findall(r"grep -Eq '(\^[^']*\$)'", text)

    def test_ci_workflow_gate_matches_evaluator_regex(self):
        patterns = self._workflow_grep_patterns()
        self.assertEqual(len(patterns), 2,
                         "expected the digest gate in both the build and the pull step")
        for pattern in patterns:
            self.assertEqual(pattern, docker_only.IMAGE_RE.pattern)

    def test_ghcr_digest_reference_is_accepted_by_command(self):
        self.assertIsNotNone(docker_only.IMAGE_RE.fullmatch(self.GHCR_IMAGE))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cand, harness = root / "candidate", root / "harness"
            cand.mkdir(); harness.mkdir()
            (harness / "runner.mjs").write_text("// trusted fixture", encoding="utf-8")
            args = docker_only.command(self.GHCR_IMAGE, cand, harness)
            self.assertIn(self.GHCR_IMAGE, args)
            self.assertIn("--pull", args)
            self.assertIn("never", args)  # the image must be pulled by CI beforehand

    def test_bare_local_image_id_is_rejected(self):
        self.assertIsNone(docker_only.IMAGE_RE.fullmatch(self.BARE_LOCAL_ID))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cand, harness = root / "candidate", root / "harness"
            cand.mkdir(); harness.mkdir()
            (harness / "runner.mjs").write_text("// trusted fixture", encoding="utf-8")
            with self.assertRaises(ValueError):
                docker_only.command(self.BARE_LOCAL_ID, cand, harness)

    def test_uppercase_and_floating_references_are_rejected(self):
        for bad in ("ghcr.io/7Clan/AIWO/s039-route-eval@sha256:" + "e" * 64,
                    "ghcr.io/7clan/ai-wieght-optimiization/s039-route-eval:ci",
                    "s039-route-eval@sha256:" + "F" * 64):
            self.assertIsNone(docker_only.IMAGE_RE.fullmatch(bad), bad)

    def test_missing_docker_is_hard_block_and_no_fallback(self):
        with patch.object(docker_only.shutil, "which", return_value=None):
            result = docker_only.run(self.IMAGE, Path("/nonexistent"), Path("/nonexistent"))
        self.assertEqual(result["status"], "BLOCKED_NO_DOCKER")
        self.assertFalse(result["candidate_executed"])

    def test_ambiguous_candidate_stdout_is_rejected(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); cand = root / "candidate"; harness = root / "harness"
            cand.mkdir(); harness.mkdir(); (harness / "runner.mjs").write_text("// fixture", encoding="utf-8")
            verdict = 'S039-RESULT {"pass":true,"checks":[{"name":"x","passed":true}]}\n'
            with patch.object(docker_only.shutil, "which", return_value="/usr/bin/docker"), \
                 patch.object(docker_only.subprocess, "run", return_value=CompletedProcess([], 0, verdict * 2, "")):
                result = docker_only.run(self.IMAGE, cand, harness)
            self.assertEqual(result["status"], "NO_UNAMBIGUOUS_VERDICT")
            self.assertFalse(result["passed"])

    def test_single_valid_mocked_verdict_is_parsed_not_executed(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); cand = root / "candidate"; harness = root / "harness"
            cand.mkdir(); harness.mkdir(); (harness / "runner.mjs").write_text("// fixture", encoding="utf-8")
            verdict = 'S039-RESULT {"pass":true,"checks":[{"name":"transition","passed":true}]}\n'
            with patch.object(docker_only.shutil, "which", return_value="/usr/bin/docker"), \
                 patch.object(docker_only.subprocess, "run", return_value=CompletedProcess([], 0, verdict, "")) as mocked:
                result = docker_only.run(self.IMAGE, cand, harness)
            self.assertTrue(result["passed"])
            self.assertEqual(result["status"], "BEHAVIOR_PASS")
            args = mocked.call_args.args[0]
            self.assertIn("--network", args)
            self.assertIn("none", args)
            self.assertEqual(mocked.call_count, 1)

    def test_trusted_invariant_fixture_uses_amended_suite(self):
        record = invariant_eval.task_fixture(ROOT, "dev", "radiostation:state-invariant")
        self.assertEqual(record["export_name"], "canAdvanceBroadcast")
        self.assertGreaterEqual(len(record["cases"]), 6)
        with self.assertRaises(ValueError):
            invariant_eval.task_fixture(ROOT, "dev", "radiostation:api-post-validation")


if __name__ == "__main__":
    unittest.main()
