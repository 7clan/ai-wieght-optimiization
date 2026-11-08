"""Evidence-led controller for new coding tasks with a fixed-size model.

No model-generated code runs here. A separate, explicitly isolated evaluator
must implement SandboxEvaluator. Private holdout results never enter this loop.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
import json
from pathlib import PurePosixPath
import re
from typing import Mapping, Protocol


class ControllerError(RuntimeError):
    """An unsafe or invalid controller configuration or model response."""


@dataclass(frozen=True)
class Task:
    task_id: str
    description: str
    public_acceptance: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.task_id.strip() or not self.description.strip() or not self.public_acceptance:
            raise ValueError("A task requires an ID, description and public acceptance criteria")


@dataclass(frozen=True)
class Budget:
    max_attempts: int = 4
    max_research: int = 2
    max_proposals: int = 9
    max_file_bytes: int = 60_000

    def __post_init__(self) -> None:
        if min(self.max_attempts, self.max_proposals, self.max_file_bytes) < 1 or self.max_research < 0:
            raise ValueError("Invalid non-positive or negative budget")


@dataclass(frozen=True)
class DocFinding:
    query: str
    source_url: str
    excerpt: str
    content_sha256: str = ""


@dataclass(frozen=True)
class SandboxResult:
    # Public checks only; the frozen private oracle must not be supplied here.
    checks: Mapping[str, bool]
    feedback: str = ""

    @property
    def passed(self) -> bool:
        return bool(self.checks) and all(v is True for v in self.checks.values())


@dataclass(frozen=True)
class Proposal:
    files: Mapping[str, str]
    hypothesis: str
    uncertain: bool = False
    research_queries: tuple[str, ...] = ()


@dataclass(frozen=True)
class ModelContext:
    task: Task
    attempt: int
    public_feedback: tuple[str, ...]
    documentation: tuple[DocFinding, ...]
    strategy: str


class ModelClient(Protocol):
    def propose(self, context: ModelContext) -> Proposal: ...


class SandboxEvaluator(Protocol):
    # This marker must be set only by the actual restricted sandbox adapter.
    is_isolated: bool

    def evaluate(self, task: Task, files: Mapping[str, str]) -> SandboxResult: ...


class DocumentationResearch(Protocol):
    def lookup(self, query: str) -> DocFinding | None: ...


@dataclass
class RunReport:
    task_id: str
    status: str = "exhausted"
    proposals: int = 0
    evaluations: int = 0
    research_calls: int = 0
    reused_proposals: int = 0
    invalid_proposals: int = 0
    messages: list[str] = field(default_factory=list)
    accepted_files: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        # Only SHA values are exported, avoiding publication of generated code.
        return {
            "task_id": self.task_id, "status": self.status,
            "proposals": self.proposals, "evaluations": self.evaluations,
            "research_calls": self.research_calls,
            "reused_proposals": self.reused_proposals,
            "invalid_proposals": self.invalid_proposals,
            "messages": self.messages,
            "accepted_sha256": {
                path: sha256(body.encode("utf-8")).hexdigest()
                for path, body in sorted(self.accepted_files.items())
            },
            "provenance": "controller + supplied model; no weight update",
        }


def _validate_proposal(files: Mapping[str, str], max_file_bytes: int) -> None:
    if not files or len(files) > 24:
        raise ControllerError("Proposal must contain between 1 and 24 files")
    total = 0
    for path, content in files.items():
        if not isinstance(path, str) or not path:
            raise ControllerError("Model attempted an unsafe filename")
        p = PurePosixPath(path)
        if ("\\" in path or p.is_absolute()
                or any(part in (".", "..") for part in path.split("/"))
                or not isinstance(content, str)):
            raise ControllerError("Model attempted an unsafe filename or non-text artifact")
        total += len(content.encode("utf-8"))
    if total > max_file_bytes:
        raise ControllerError("Model artifact exceeds the resource budget")


def _failure_family(feedback: str) -> str:
    """General failure *categories*; not an answer cache of solved bugs."""
    if re.search(r"(?:cannot find module|no module named|module not found|importerror)", feedback, re.I):
        return "dependency resolution: verify installed packages and import paths"
    if re.search(r"(?:404|route|endpoint|connection refused|cors)", feedback, re.I):
        return "API contract: compare client URL, method, server route and error handling"
    if re.search(r"(?:typeerror|undefined|null|keyerror|attributeerror)", feedback, re.I):
        return "data contract: check input shape, null paths and type assumptions"
    if re.search(r"(?:responsive|viewport|overflow|layout)", feedback, re.I):
        return "layout: inspect measured viewport and actual computed structure"
    if re.search(r"(?:assert|expected|mismatch|failed)", feedback, re.I):
        return "logic: minimize failing input and compare expected versus actual behavior"
    return "unknown failure: isolate the smallest reproducible observation"


class AgentController:
    """Bounded propose → research/test → diagnose loop; weights remain frozen."""

    def __init__(self, budget: Budget = Budget()) -> None:
        self.budget = budget

    def run(
        self,
        task: Task,
        model: ModelClient,
        sandbox: SandboxEvaluator,
        researcher: DocumentationResearch,
    ) -> RunReport:
        if getattr(sandbox, "is_isolated", False) is not True:
            raise ControllerError("Refusing to evaluate generated code outside a declared sandbox")

        report = RunReport(task_id=task.task_id)
        feedback: list[str] = []
        findings: list[DocFinding] = []
        seen_queries: set[str] = set()
        seen_artifacts: set[str] = set()
        repeated = 0
        strategy = "Split contracts; change one hypothesis at a time; verify public checks."

        while (report.proposals < self.budget.max_proposals
               and report.evaluations < self.budget.max_attempts):
            try:
                proposal = model.propose(ModelContext(
                    task, report.evaluations + 1, tuple(feedback), tuple(findings), strategy,
                ))
                _validate_proposal(proposal.files, self.budget.max_file_bytes)
            except ControllerError as exc:
                report.proposals += 1
                report.invalid_proposals += 1
                # Invalid output is not a public test failure; keep the
                # generated-program sandbox untouched and give format feedback.
                strategy = "Strict JSON object with a files map; no prose, fences or unsafe paths."
                feedback.append(f"Invalid proposal: {str(exc)[:300]}")
                report.messages.append(f"Model output rejected: {str(exc)[:300]}")
                continue
            report.proposals += 1

            # Consult new documentation before executing an uncertain proposal.
            if proposal.uncertain and report.research_calls < self.budget.max_research:
                query = next((q.strip() for q in proposal.research_queries
                              if q.strip() and q.strip() not in seen_queries), None)
                if query:
                    seen_queries.add(query)
                    report.research_calls += 1
                    found = researcher.lookup(query)
                    if found and found.source_url.startswith(("https://", "http://")):
                        findings.append(found)
                        report.messages.append(f"Researched {query} via {found.source_url}")
                        continue  # New proposal must use the evidence.
                    report.messages.append(f"Documentation unavailable for: {query}")

            fingerprint = sha256(json.dumps(
                dict(sorted(proposal.files.items())), sort_keys=True,
            ).encode("utf-8")).hexdigest()
            if fingerprint in seen_artifacts:
                repeated += 1
                report.reused_proposals += 1
                strategy = "This exact patch was already tested. Change the hypothesis, not its wording."
                if repeated >= 2:
                    report.status = "blocked_no_progress"
                    break
                continue
            seen_artifacts.add(fingerprint)
            repeated = 0

            outcome = sandbox.evaluate(task, proposal.files)
            if not isinstance(outcome, SandboxResult):
                raise ControllerError("Sandbox returned an invalid public result")
            report.evaluations += 1
            if outcome.passed:
                report.status = "public_checks_passed"
                report.accepted_files = dict(proposal.files)
                report.messages.append("All supplied public checks passed; private holdout not run")
                break

            detail = outcome.feedback[:1500] or "A public acceptance check failed"
            feedback.append(detail)
            strategy = _failure_family(detail)
            report.messages.append(f"Attempt {report.evaluations}: {strategy}")

            # An agent that is *still failing* should independently seek
            # relevant evidence even when a tiny model fails to ask for it.
            if report.evaluations >= 2 and report.research_calls < self.budget.max_research:
                query = f"{task.description[:90]}: {strategy}"
                if query not in seen_queries:
                    seen_queries.add(query)
                    report.research_calls += 1
                    found = researcher.lookup(query)
                    if found and found.source_url.startswith(("https://", "http://")):
                        findings.append(found)
                        report.messages.append(f"Escalated to documentation: {found.source_url}")
                    else:
                        report.messages.append("Escalated search found no verified documentation")

        return report
