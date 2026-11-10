"""Session-039B route evaluator checks; no generated code execution.

All Docker interactions are mocked. These tests validate staging,
command construction, fail-closed verdict parsing and control hygiene —
they are controls on our wrapper, not a measurement of Qwen skill and not
proof of Docker runtime compatibility.
"""

import json
from pathlib import Path
import tempfile
import unittest
from subprocess import CompletedProcess
from unittest.mock import patch

from archagent.s039 import control_run, docker_only, route_eval, route_fixtures, scenarios

ROOT = Path(__file__).resolve().parents[1]
IMAGE = "s039-route-eval@sha256:" + "b" * 64


def _dirs(temp: str, runner: str = "route_runner.mjs"):
    root = Path(temp)
    cand, harness = root / "candidate", root / "harness"
    cand.mkdir()
    harness.mkdir()
    (harness / runner).write_text("// trusted fixture", encoding="utf-8")
    return cand, harness


class RouteCommandTests(unittest.TestCase):
    def test_route_command_pins_image_and_constrains_capabilities(self):
        with tempfile.TemporaryDirectory() as temp:
            cand, harness = _dirs(temp)
            args = docker_only.command_route(IMAGE, cand, harness)
            joined = " ".join(args)
            self.assertIn("--network", args)
            self.assertIn("none", args)
            self.assertIn("--read-only", args)
            self.assertIn("--cap-drop", args)
            self.assertIn("no-new-privileges", args)
            self.assertIn(IMAGE, args)
            self.assertIn("--user", args)
            self.assertIn("10001:10001", args)
            self.assertIn("--pull", args)
            self.assertIn("never", args)
            self.assertIn("route_runner.mjs", joined)
            self.assertIn("/work:rw,nosuid,size=512m", args)
            self.assertIn("/tmp:rw,nosuid,noexec,size=64m", args)
            self.assertIn("--memory", args)
            with self.assertRaises(ValueError):
                docker_only.command_route("node:24", cand, harness)

    def test_route_command_rejects_missing_runner_and_nested_dirs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cand, harness = root / "candidate", root / "harness"
            cand.mkdir()
            harness.mkdir()
            with self.assertRaises(ValueError):
                docker_only.command_route(IMAGE, cand, harness)  # no route_runner.mjs
            (harness / "route_runner.mjs").write_text("// t", encoding="utf-8")
            nested = harness / "inner"
            nested.mkdir()
            with self.assertRaises(ValueError):
                docker_only.command_route(IMAGE, harness, nested)

    def test_resource_caps_stay_within_approved_limits(self):
        with tempfile.TemporaryDirectory() as temp:
            cand, harness = _dirs(temp)
            with self.assertRaises(ValueError):
                docker_only.command_route(IMAGE, cand, harness, memory_mb=4096)
            with self.assertRaises(ValueError):
                docker_only.command_route(IMAGE, cand, harness, cpu_count=4)


class RouteVerdictTests(unittest.TestCase):
    def test_missing_docker_is_hard_block_for_routes_too(self):
        with patch.object(docker_only.shutil, "which", return_value=None):
            result = docker_only.run_route(IMAGE, Path("/nonexistent"), Path("/nonexistent"))
        self.assertEqual(result["status"], "BLOCKED_NO_DOCKER")
        self.assertFalse(result["candidate_executed"])

    def test_run_route_uses_route_builder_and_fail_closed_verdicts(self):
        verdict = 'S039-RESULT {"pass":true,"checks":[{"name":"min-boundary","passed":true}]}\n'
        with tempfile.TemporaryDirectory() as temp:
            cand, harness = _dirs(temp)
            with patch.object(docker_only.shutil, "which", return_value="/usr/bin/docker"), \
                 patch.object(docker_only.subprocess, "run",
                              return_value=CompletedProcess([], 0, verdict, "")) as mocked:
                result = docker_only.run_route(IMAGE, cand, harness)
            argv = mocked.call_args.args[0]
            self.assertIn("route_runner.mjs", " ".join(argv))
            self.assertTrue(result["passed"])
            self.assertEqual(result["status"], "BEHAVIOR_PASS")
            for stdout, status in (
                (verdict * 2, "NO_UNAMBIGUOUS_VERDICT"),
                ("S039-RESULT not-json\n", "INVALID_VERDICT"),
                ('S039-RESULT {"pass":false,"checks":[{"name":"x","passed":false}]}\n', "BEHAVIOR_FAIL"),
            ):
                with patch.object(docker_only.shutil, "which", return_value="/usr/bin/docker"), \
                     patch.object(docker_only.subprocess, "run",
                                  return_value=CompletedProcess([], 0, stdout, "")):
                    outcome = docker_only.run_route(IMAGE, cand, harness)
                self.assertEqual(outcome["status"], status)
                self.assertFalse(outcome["passed"])


class FixtureStagingTests(unittest.TestCase):
    def test_task_spec_extracts_route_facts_from_frozen_contract(self):
        spec = route_fixtures.task_spec(ROOT, "dev", "radiostation:api-get-filter")
        self.assertEqual(spec["route_path"], "/api/radiostation-broadcasts")
        self.assertEqual(spec["envelope_key"], "broadcasts")
        self.assertEqual(len(spec["cases"]), 6)
        self.assertEqual(spec["entities"]["child_client"], "broadcast")
        self.assertEqual(spec["entities"]["foreign_key_optional"], True)
        post = route_fixtures.task_spec(ROOT, "dev", "radiostation:api-post-validation")
        self.assertEqual(post["route_path"], "/api/radiostation-broadcasts")
        self.assertEqual(len(post["cases"]), 10)
        self.assertNotIn("envelope_key", post)

    def test_fixture_rows_match_frozen_scenario_plans(self):
        for split in ("train", "dev"):
            plan = scenarios.build(ROOT, split, suite_version=2)
            suite = scenarios.load_split(ROOT, split, suite_version=2)
            by_id = {t["id"]: t for t in suite["tasks"]}
            for item in plan["tasks"]:
                self.assertEqual(route_fixtures.fixture_rows(by_id[item["task_id"]]),
                                 item["fixture"], item["task_id"])

    def test_route_extraction_covers_every_train_and_dev_contract(self):
        count = 0
        for split in ("train", "dev"):
            for task_id in ("",):
                pass
            suite = scenarios.load_split(ROOT, split, suite_version=2)
            for task in suite["tasks"]:
                if task["skill"] in route_fixtures.ROUTE_SKILLS:
                    spec = route_fixtures.route_contract(ROOT, split, task["id"])
                    self.assertTrue(spec["route_path"].startswith("/api/"))
                    if task["skill"] == "api-get-filter":
                        self.assertTrue(spec["envelope_key"])
                    count += 1
        self.assertEqual(count, 24)

    def test_prisma_schema_implements_v2_semantics(self):
        suite = scenarios.load_split(ROOT, "dev", suite_version=2)
        radio = next(t for t in suite["tasks"] if t["id"] == "radiostation:api-get-filter")
        schema = route_fixtures.prisma_schema(radio)
        self.assertIn('transmitterId String?', schema)
        self.assertIn("onDelete: SetNull", schema)
        self.assertIn('status      String  @default("drafted")', schema)
        self.assertIn("@id @default(cuid())", schema)
        required = next(t for t in suite["tasks"]
                        if t["skill"] == "api-get-filter"
                        and t["entities"]["foreign_key_mode"] == "required")
        self.assertIn("onDelete: Restrict", route_fixtures.prisma_schema(required))
        self.assertNotIn("SetNull", route_fixtures.prisma_schema(required))

    def test_stage_harness_writes_the_trusted_fixture_set(self):
        with tempfile.TemporaryDirectory() as temp:
            harness = Path(temp)
            spec = route_eval.stage_harness(ROOT, "dev", "radiostation:api-get-filter", harness)
            names = sorted(p.name for p in harness.iterdir())
            self.assertEqual(names, ["db.ts", "fixture.mjs", "route_runner.mjs",
                                     "schema.prisma", "seed.mjs", "task.json"])
            staged = json.loads((harness / "task.json").read_text())
            self.assertEqual(staged["route_path"], spec["route_path"])
            db_ts = (harness / "db.ts").read_text()
            self.assertIn("AUTHORED_DB_PROVIDER_NOT_QWEN_CODE", db_ts)
            self.assertIn("TRUSTED", (harness / "fixture.mjs").read_text())
            self.assertIn("TRUSTED", (harness / "seed.mjs").read_text())
            self.assertIn("TRUSTED", (harness / "schema.prisma").read_text())

    def test_staged_paths_follow_overrides_for_host_smoke(self):
        with tempfile.TemporaryDirectory() as temp:
            harness = Path(temp)
            route_eval.stage_harness(ROOT, "dev", "radiostation:api-get-filter", harness,
                                     work_dir="/tmp/smoke-work",
                                     client_import="/tmp/smoke-client/index.js")
            schema = (harness / "schema.prisma").read_text()
            self.assertIn("file:/tmp/smoke-work/db.sqlite", schema)
            self.assertIn('/tmp/smoke-client/index.js', (harness / "db.ts").read_text())


class EvaluatorBoundaryTests(unittest.TestCase):
    def test_holdout_is_sealed_from_route_staging(self):
        with self.assertRaises(PermissionError):
            route_fixtures.task_spec(ROOT, "holdout", "any:api-get-filter")
        with self.assertRaises(PermissionError):
            route_eval.evaluate(ROOT, "holdout", "any:api-get-filter",
                                Path("/nonexistent"), IMAGE)

    def test_candidate_must_live_in_its_dedicated_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            elsewhere = Path(temp) / "output.ts"
            elsewhere.write_text("export const GET = 1;", encoding="utf-8")
            with self.assertRaises(ValueError):
                route_eval.evaluate(ROOT, "dev", "radiostation:api-get-filter",
                                    elsewhere.parent, IMAGE)

    def test_candidate_hygiene_rejects_extra_files_and_symlinks(self):
        candidate_root = ROOT / "experiments/z039-generalization-learning/candidates"
        target = candidate_root / "radiostation__api-get-filter"
        created = False
        if not target.exists():
            target.mkdir(parents=True)
            created = True
        try:
            (target / "output.ts").write_text("export const GET = 1;", encoding="utf-8")
            (target / "notes.txt").write_text("stray", encoding="utf-8")
            with self.assertRaises(FileNotFoundError):
                route_eval.evaluate(ROOT, "dev", "radiostation:api-get-filter", target, IMAGE)
            (target / "notes.txt").unlink()
            (target / "link.ts").symlink_to(target / "output.ts")
            with self.assertRaises(FileNotFoundError):
                route_eval.evaluate(ROOT, "dev", "radiostation:api-get-filter", target, IMAGE)
            (target / "link.ts").unlink()
        finally:
            if created:
                for child in target.iterdir():
                    child.unlink()
                target.rmdir()
                candidate_root.rmdir()


class ControlTests(unittest.TestCase):
    def test_control_matrix_files_exist_with_trusted_labels(self):
        for name in control_run.CONTROL_MATRIX:
            path = ROOT / control_run.CONTROLS / name
            self.assertTrue(path.is_file(), name)
            text = path.read_text(encoding="utf-8")
            self.assertIn("TRUSTED_TEACHER_CONTROL_NOT_QWEN_CODE", text, name)
            if "negative" in name:
                self.assertIn("KNOWN-BAD", text, name)
        self.assertEqual(len(control_run.CONTROL_MATRIX), 10)

    def test_positive_and_negative_expectations_are_balanced(self):
        expected = [v[2] for v in control_run.CONTROL_MATRIX.values()]
        self.assertEqual(expected.count(True), 3)
        self.assertEqual(expected.count(False), 7)

    def test_control_staging_rejects_paths_outside_controls_directory(self):
        with tempfile.TemporaryDirectory() as temp:
            outside = Path(temp) / "evil.ts"
            outside.write_text("export const GET = 1;", encoding="utf-8")
            with self.assertRaises(ValueError):
                control_run._control_dir(ROOT, str(outside), Path(temp))

    def test_host_smoke_requires_control_not_candidate_directory(self):
        # The invariant host-smoke path stages the trusted runner plus a
        # control file; a missing control cannot be staged.
        with tempfile.TemporaryDirectory() as temp:
            missing = "missing-control.ts"
            with self.assertRaises(ValueError):
                control_run._control_dir(ROOT, missing, Path(temp))


if __name__ == "__main__":
    unittest.main()
