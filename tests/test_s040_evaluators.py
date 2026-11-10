"""Session 040 evaluator tests: exec argv construction, fail-closed verdict
parsing, tier caps, fixture derivation, control labeling. All restricted-tier
interactions are mocked; no model code is executed."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from archagent.s040 import exec as s040exec
from archagent.s040 import control_run, integration_fixtures, react_fixtures

ROOT = Path(__file__).resolve().parents[1]


class ExecArgvTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cand = root / "cand"; self.cand.mkdir()
        self.harness = root / "harness"; self.harness.mkdir()
        (self.harness / "react_runner.mjs").write_text("// trusted", encoding="utf-8")
        self.deps = root / "deps"; self.deps.mkdir()
        (self.deps / "node_modules").mkdir()
        self.stage = root / "stage"; self.stage.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_docker_argv_mirrors_s039_hardening_plus_deps(self):
        image = "ghcr.io/7clan/ai-wieght-optimiization/s040-eval@sha256:" + "a" * 64
        argv = s040exec.docker_argv(image, self.cand, self.harness, self.deps,
                                    runner="react_runner.mjs", tier="react")
        for flag in ("--network", "none", "--read-only", "--cap-drop", "ALL",
                     "no-new-privileges", "--pids-limit", "--pull", "never"):
            self.assertIn(flag, argv)
        self.assertIn("type=bind,src=%s,dst=/candidate,readonly" % self.cand, argv)
        self.assertIn("type=bind,src=%s,dst=/eval-deps,readonly" % self.deps, argv)
        with self.assertRaises(ValueError):
            s040exec.docker_argv("s040-eval:latest", self.cand, self.harness, self.deps,
                                 runner="react_runner.mjs", tier="react")

    def test_unshare_script_contains_pivot_and_ro_binds(self):
        argv = s040exec.unshare_script(self.cand, self.harness, self.deps,
                                       runner="react_runner.mjs", tier="react",
                                       stage_root=self.stage)
        script = argv[-1]
        self.assertTrue(argv[:2] == ["unshare", "--user"])
        joined = " ".join(argv)
        for token in ("--map-root-user", "--mount", "--net", "--pid", "--fork",
                      "--propagation", "private"):
            self.assertIn(token, joined)
        for fragment in ("pivot_root . oldroot",
                         "mount -o remount,bind,ro",
                         "setpriv --bounding-set=-all",
                         "ulimit -t 40",
                         "ulimit -v 2097152",
                         "mount -t tmpfs -o size=4m,nosuid tmpfs /oldroot"):
            self.assertIn(fragment, script)
        # the candidate and harness are bind-mounted read-only
        self.assertIn("mount --bind %s " % self.cand, script)

    def test_unsafe_paths_are_rejected(self):
        bad = Path(self.tmp.name) / "can,d"; bad.mkdir()
        with self.assertRaises(ValueError):
            s040exec.unshare_script(bad, self.harness, self.deps,
                                    runner="react_runner.mjs", tier="react",
                                    stage_root=self.stage)
        with self.assertRaises(ValueError):
            s040exec.unshare_script(self.cand, self.harness, self.deps,
                                    runner="evil_runner.mjs", tier="react",
                                    stage_root=self.stage)

    def test_unknown_runner_rejected(self):
        with self.assertRaises(ValueError):
            s040exec.docker_argv("x@sha256:" + "a" * 64, self.cand, self.harness, self.deps,
                                 runner="other.mjs", tier="react")


class VerdictParsingTests(unittest.TestCase):
    def test_single_valid_verdict_passes(self):
        out = 'noise\nS040-RESULT {"pass":true,"checks":[{"name":"a","passed":true}]}\n'
        result = s040exec._parse_verdict(out)
        self.assertTrue(result["passed"])
        self.assertEqual(result["status"], "BEHAVIOR_PASS")

    def test_spoofed_second_marker_fails_closed(self):
        out = 'S040-RESULT {"pass":true,"checks":[{"name":"a","passed":true}]}\n' \
              'S040-RESULT {"pass":true,"checks":[{"name":"a","passed":true}]}\n'
        result = s040exec._parse_verdict(out)
        self.assertEqual(result["status"], "NO_UNAMBIGUOUS_VERDICT")
        self.assertFalse(result["passed"])

    def test_failed_check_and_invalid_json_fail_closed(self):
        result = s040exec._parse_verdict('S040-RESULT {"pass":true,"checks":[{"name":"a","passed":false}]}\n')
        self.assertEqual(result["status"], "BEHAVIOR_FAIL")
        result = s040exec._parse_verdict('S040-RESULT not-json\n')
        self.assertEqual(result["status"], "INVALID_VERDICT")


class DockerBlockedTests(unittest.TestCase):
    def test_missing_docker_is_hard_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cand, harness, deps = root / "c", root / "h", root / "d"
            cand.mkdir(); harness.mkdir(); deps.mkdir()
            (harness / "react_runner.mjs").write_text("// t", encoding="utf-8")
            (deps / "node_modules").mkdir()
            with patch.object(s040exec.shutil, "which", return_value=None):
                result = s040exec.run(cand, harness, deps, runner="react_runner.mjs",
                                      tier="react", backend="docker")
        self.assertEqual(result["status"], "BLOCKED_NO_DOCKER")
        self.assertFalse(result["candidate_executed"])


class FixtureTests(unittest.TestCase):
    def test_react_spec_derives_frozen_cases_and_conventions(self):
        spec = react_fixtures.task_spec(ROOT, "dev", "radiostation:react-interaction")
        names = [c["name"] for c in spec["cases"]]
        self.assertIn("search", names)
        self.assertIn("clear", names)
        self.assertIn("keyboard", names)
        self.assertEqual(spec["conventions"]["export"], "default")
        self.assertEqual(spec["conventions"]["prop"], "data")
        self.assertEqual(len(spec["titles"]), 3)
        with self.assertRaises(ValueError):
            react_fixtures.task_spec(ROOT, "dev", "radiostation:api-get-filter")

    def test_integration_spec_pins_route_semantics(self):
        spec = integration_fixtures.task_spec(ROOT, "dev", "radiostation:fullstack-integration")
        self.assertEqual(spec["route_path"], "/api/radiostation-broadcasts")
        self.assertEqual(spec["envelope_key"], "broadcasts")
        route = integration_fixtures.reference_route_mjs(spec, client_import="/work/generated-client/index.js")
        self.assertIn("export async function POST(", route)
        self.assertIn("409", route)
        self.assertIn("404", route)
        for case in spec["cases"]:
            self.assertIn(case.get("event"),
                          ("submit-form", "check-dom-after-submit", "http-get",
                           "reload-and-http-get", "submit-duplicate"))


class ControlMatrixTests(unittest.TestCase):
    def test_matrix_covers_both_evaluators_with_expected_verdicts(self):
        kinds = {kind for kind, _ in control_run.CONTROL_MATRIX.values()}
        self.assertEqual(kinds, {"react", "integration"})
        self.assertEqual(len(control_run.CONTROL_MATRIX), 15)
        positives = [n for n, (_, p) in control_run.CONTROL_MATRIX.items() if p]
        self.assertEqual(len(positives), 2)
        for name in control_run.CONTROL_MATRIX:
            self.assertTrue(name.endswith(".tsx"))


class EvidenceFileTests(unittest.TestCase):
    def test_restricted_tier_control_evidence_exists_and_validates(self):
        path = ROOT / "experiments/z040-autonomous-fullstack/restricted-tier-controls.json"
        self.assertTrue(path.is_file(), "restricted-tier control evidence missing")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(data["controls"]), 15)
        self.assertTrue(data["all_oracles_validated"])
        self.assertEqual(data["backend"], "unshare")
        self.assertFalse(data["model_generated_code_executed"])
        for name, outcome in data["controls"].items():
            self.assertTrue(outcome["oracle_validated"], name)
            self.assertIn(outcome.get("tier"), ("UNSHARE_USERNS_DISCLOSED",), name)


if __name__ == "__main__":
    unittest.main()
