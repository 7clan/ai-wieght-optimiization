"""Deterministic controller tests; no model download or generated execution."""

import json
import unittest

from adaptive_agent import (
    AgentController, Budget, ControllerError, DocFinding, Proposal,
    SandboxResult, Task,
)
from adaptive_agent.qwen_adapter import QwenJSONAdapter


TASK = Task("novel-001", "Implement a small inventory endpoint", ("GET returns items",))


class FakeModel:
    def __init__(self, proposals):
        self.proposals = iter(proposals)
        self.contexts = []

    def propose(self, context):
        self.contexts.append(context)
        return next(self.proposals)


class FakeSandbox:
    is_isolated = True  # Simulator only; no code is executed.

    def __init__(self, results):
        self.results = iter(results)
        self.calls = []

    def evaluate(self, task, files):
        self.calls.append((task.task_id, dict(files)))
        return next(self.results)


class FakeResearcher:
    def __init__(self):
        self.calls = []

    def lookup(self, query):
        self.calls.append(query)
        return DocFinding(query, "https://developer.mozilla.org/example", "Methods must match")


def proposal(body, *, unsure=False):
    return Proposal({"src/index.js": body}, "test a hypothesis", unsure, ("fetch HTTP route docs",))


class ControllerTests(unittest.TestCase):
    def test_research_before_test_then_uses_finding(self):
        model = FakeModel([proposal("draft", unsure=True), proposal("correct")])
        sandbox = FakeSandbox([SandboxResult({"endpoint": True})])
        research = FakeResearcher()
        report = AgentController().run(TASK, model, sandbox, research)
        self.assertEqual(report.status, "public_checks_passed")
        self.assertEqual((report.proposals, report.evaluations, report.research_calls), (2, 1, 1))
        self.assertEqual(len(model.contexts[1].documentation), 1)
        self.assertEqual(len(sandbox.calls), 1)

    def test_general_failure_family_influences_next_attempt(self):
        model = FakeModel([proposal("wrong"), proposal("fixed")])
        sandbox = FakeSandbox([
            SandboxResult({"endpoint": False}, "GET /api/items returned 404"),
            SandboxResult({"endpoint": True}),
        ])
        report = AgentController().run(TASK, model, sandbox, FakeResearcher())
        self.assertEqual(report.evaluations, 2)
        self.assertIn("API contract", model.contexts[1].strategy)
        self.assertIn("404", model.contexts[1].public_feedback[0])

    def test_repeated_identical_patch_stops_without_reexecuting(self):
        model = FakeModel([proposal("bad"), proposal("bad"), proposal("bad")])
        sandbox = FakeSandbox([SandboxResult({"endpoint": False}, "Assertion failed")])
        report = AgentController().run(TASK, model, sandbox, FakeResearcher())
        self.assertEqual(report.status, "blocked_no_progress")
        self.assertEqual(report.evaluations, 1)
        self.assertEqual(report.reused_proposals, 2)

    def test_never_runs_outside_sandbox(self):
        sandbox = FakeSandbox([SandboxResult({"pass": True})])
        sandbox.is_isolated = False
        with self.assertRaises(ControllerError):
            AgentController().run(TASK, FakeModel([proposal("ok")]), sandbox, FakeResearcher())
        self.assertEqual(len(sandbox.calls), 0)

    def test_rejects_parent_path_and_oversized_files(self):
        for files in ({"../escape.py": "oops"}, {"x.js": "x" * 20}):
            sandbox = FakeSandbox([])
            model = FakeModel([Proposal(files, "unsafe")])
            result = AgentController(Budget(max_file_bytes=10, max_proposals=1)).run(
                TASK, model, sandbox, FakeResearcher(),
            )
            self.assertEqual(result.invalid_proposals, 1)
            self.assertEqual(result.status, "exhausted")
            self.assertEqual(len(sandbox.calls), 0)

    def test_attempt_budget_enforced(self):
        model = FakeModel([proposal("wrong1"), proposal("wrong2"), proposal("wrong3")])
        sandbox = FakeSandbox([SandboxResult({"a": False}, "failed"), SandboxResult({"a": False}, "failed")])
        result = AgentController(Budget(max_attempts=2)).run(TASK, model, sandbox, FakeResearcher())
        self.assertEqual((result.status, result.evaluations), ("exhausted", 2))
        self.assertEqual(len(model.contexts), 2)

    def test_two_novel_failures_trigger_research_even_if_model_does_not_ask(self):
        model = FakeModel([proposal("wrong1"), proposal("wrong2"), proposal("fixed")])
        sandbox = FakeSandbox([
            SandboxResult({"a": False}, "Expected 4, got 5"),
            SandboxResult({"a": False}, "Expected 6, got 3"),
            SandboxResult({"a": True}),
        ])
        researcher = FakeResearcher()
        result = AgentController().run(TASK, model, sandbox, researcher)
        self.assertEqual(result.status, "public_checks_passed")
        self.assertEqual(result.research_calls, 1)
        self.assertEqual(len(researcher.calls), 1)
        self.assertIn("logic", researcher.calls[0])
        self.assertEqual(len(model.contexts[2].documentation), 1)

    def test_frozen_private_holdout_is_not_in_context(self):
        model = FakeModel([proposal("ok")])
        sandbox = FakeSandbox([SandboxResult({"public": True})])
        report = AgentController().run(TASK, model, sandbox, FakeResearcher())
        self.assertEqual(report.status, "public_checks_passed")
        self.assertFalse(hasattr(model.contexts[0], "private_tests"))
        self.assertIn("private holdout not run", report.messages[-1])

    def test_qwen_json_adapter_contract_and_no_eval(self):
        response = json.dumps({"files": {"main.py": "print(1)"}, "hypothesis": "test", "uncertain": False})
        model = QwenJSONAdapter(lambda prompt: response)
        context = FakeModel([])  # use real context object below
        from adaptive_agent import ModelContext
        proposal_value = model.propose(ModelContext(TASK, 1, (), (), "check API"))
        self.assertEqual(proposal_value.files["main.py"], "print(1)")
        with self.assertRaises(ControllerError):
            QwenJSONAdapter(lambda _: "not json").propose(ModelContext(TASK, 1, (), (), ""))

    def test_bad_json_can_be_repaired_within_proposal_budget(self):
        responses = iter(["not json", json.dumps({
            "files": {"main.py": "print('works')"}, "hypothesis": "format repaired",
        })])
        model = QwenJSONAdapter(lambda _: next(responses))
        sandbox = FakeSandbox([SandboxResult({"public": True})])
        report = AgentController(Budget(max_proposals=3)).run(TASK, model, sandbox, FakeResearcher())
        self.assertEqual(report.status, "public_checks_passed")
        self.assertEqual(report.invalid_proposals, 1)
        self.assertEqual(report.evaluations, 1)

    def test_only_invalid_json_exits_at_budget(self):
        model = QwenJSONAdapter(lambda _: "not JSON")
        sandbox = FakeSandbox([])
        report = AgentController(Budget(max_proposals=2)).run(TASK, model, sandbox, FakeResearcher())
        self.assertEqual(report.status, "exhausted")
        self.assertEqual((report.proposals, report.invalid_proposals), (2, 2))
        self.assertEqual(len(sandbox.calls), 0)


if __name__ == "__main__":
    unittest.main()
