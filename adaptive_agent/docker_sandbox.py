"""Bounded Docker evaluator for model-generated Python or JavaScript.

Generated code is never executed on the host. A trusted public test program
is mounted separately from candidate source. No host execution fallback.
Docker is defense-in-depth, not a formal malicious-code isolation guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import tempfile
import time
from typing import Mapping
from uuid import uuid4

from .controller import ControllerError, SandboxResult, Task, _validate_proposal


IMAGES = {"python": "python:3.11-alpine", "javascript": "node:22-alpine"}
ENTRYPOINT = {"python": ("python", "-I", "-B", "/checks/public_test.py"),
              "javascript": ("node", "/checks/public_test.cjs")}


@dataclass(frozen=True)
class PublicFixture:
    """Trusted test source prepared *before* generating a candidate."""

    runtime: str
    test_source: str
    timeout_s: int = 15

    def __post_init__(self) -> None:
        if self.runtime not in IMAGES:
            raise ValueError("Only preapproved Python and JavaScript runtimes are supported")
        if not (1 <= self.timeout_s <= 30):
            raise ValueError("Public test timeout must be within [1, 30] seconds")
        if not self.test_source or len(self.test_source.encode("utf-8")) > 40_000:
            raise ValueError("Missing or oversized trusted test suite")


def docker_command(candidate_dir: Path, tests_dir: Path, fixture: PublicFixture, name: str) -> list[str]:
    """A fixed allowlisted command; no model text becomes a shell argument."""

    if not name.startswith("adaptive-") or len(name) > 50:
        raise ValueError("Invalid container name")
    for directory in (candidate_dir, tests_dir):
        if not directory.is_absolute() or not directory.is_dir():
            raise ValueError("Docker mount roots must be existing absolute directories")
    return [
        "docker", "run", "--rm", "--pull=never", "--name", name,
        "--network", "none", "--read-only", "--ipc", "none",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "32", "--memory", "256m", "--memory-swap", "256m",
        "--cpus", "1", "--user", "65534:65534",
        "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
        "--mount", f"type=bind,src={candidate_dir},dst=/app,readonly",
        "--mount", f"type=bind,src={tests_dir},dst=/checks,readonly",
        "--workdir", "/app",
        IMAGES[fixture.runtime], *ENTRYPOINT[fixture.runtime],
    ]


def require_docker() -> None:
    if shutil.which("docker") is None:
        raise ControllerError("Docker CLI unavailable; refusing host execution")
    try:
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, text=True, timeout=10, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ControllerError("Docker daemon unavailable; refusing host execution") from exc
    if result.returncode:
        raise ControllerError("Docker daemon not ready; refusing host execution")


def _run_capped(cmd: list[str], deadline_s: int, output_cap: int = 12_000) -> tuple[int, str, bool]:
    """Drain output without retaining unbounded logs or waiting forever."""

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    pieces: list[bytes] = []
    stored = 0
    expired = False
    end = time.monotonic() + deadline_s
    assert process.stdout is not None
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while selector.get_map():
            remaining = end - time.monotonic()
            if remaining <= 0:
                expired = True
                break
            for key, _ in selector.select(min(remaining, 0.25)):
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                if stored < output_cap:
                    part = chunk[:output_cap - stored]
                    pieces.append(part)
                    stored += len(part)

    if expired:
        process.kill()
    try:
        process.wait(timeout=4)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    return process.returncode, b"".join(pieces).decode("utf-8", "replace"), expired


class DockerSandbox:
    """Evaluate with a fixed trusted test fixture, one container per candidate."""

    is_isolated = True  # Only this adapter provides the restricted Docker path.

    def __init__(self, fixtures: Mapping[str, PublicFixture]):
        self.fixtures = dict(fixtures)

    def evaluate(self, task: Task, files: Mapping[str, str]) -> SandboxResult:
        fixture = self.fixtures.get(task.task_id)
        if fixture is None:
            raise ControllerError("No frozen public test fixture for task")
        _validate_proposal(files, max_file_bytes=60_000)
        require_docker()  # Must occur before any generated file is executed.

        name = "adaptive-" + uuid4().hex[:16]
        with tempfile.TemporaryDirectory(prefix="adaptive_candidate_") as workspace:
            root = Path(workspace)
            candidate_dir = root / "candidate"
            checks_dir = root / "checks"
            candidate_dir.mkdir(mode=0o755)
            checks_dir.mkdir(mode=0o755)
            os.chmod(root, 0o755)
            for relpath, source in files.items():
                target = candidate_dir / relpath
                target.parent.mkdir(parents=True, exist_ok=True)
                os.chmod(target.parent, 0o755)
                target.write_text(source, encoding="utf-8")
                os.chmod(target, 0o644)
            test_file = checks_dir / ("public_test.py" if fixture.runtime == "python"
                                     else "public_test.cjs")
            test_file.write_text(fixture.test_source, encoding="utf-8")
            os.chmod(test_file, 0o644)
            cmd = docker_command(candidate_dir, checks_dir, fixture, name)
            try:
                code, output, timed_out = _run_capped(cmd, fixture.timeout_s + 5)
            except OSError as exc:
                raise ControllerError("Failed to launch isolated Docker evaluator") from exc
            finally:
                # Cleanup is idempotent even if --rm already removed the container.
                subprocess.run(["docker", "rm", "-f", name],
                               capture_output=True, check=False, timeout=8)

        if timed_out:
            return SandboxResult({"public_suite": False}, "Sandbox timed out")
        if code == 125:
            raise ControllerError("Docker rejected the container; cannot score safely")
        return SandboxResult({"public_suite": code == 0}, output[-1500:])
