"""Restricted Docker execution boundary for UNTRUSTED Session-039 code.

No Docker executable -> no execution. Never switch to host Node/Python,
`unshare` or a less isolated fallback. This module only invokes Docker; the
image and trusted test runner must be independently vetted and pinned.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess


IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/:-]*@sha256:[a-f0-9]{64}$")
RESULT_MARKER = "S039-RESULT "


def command(image: str, candidate_dir: Path, harness_dir: Path, *, memory_mb: int = 1536,
            cpu_count: float = 2.0) -> list[str]:
    if not IMAGE_RE.fullmatch(image):
        raise ValueError("Docker image must have an exact sha256 digest pin")
    if not (256 <= memory_mb <= 3072 and 0 < cpu_count <= 2):
        raise ValueError("Resource caps outside approved local evaluation limits")
    cand = candidate_dir.resolve(strict=True)
    harness = harness_dir.resolve(strict=True)
    if any(c in str(path) for path in (cand, harness) for c in (",", "\n", "\r")):
        raise ValueError("Bind-mount paths contain an unsafe Docker --mount delimiter")
    if not cand.is_dir() or not harness.is_dir() or cand == harness:
        raise ValueError("Candidate and harness must be separate existing directories")
    if cand in harness.parents or harness in cand.parents:
        raise ValueError("Candidate and trusted harness directories must not contain one another")
    if not (harness / "runner.mjs").is_file():
        raise ValueError("Trusted harness runner.mjs is missing")
    return [
        "docker", "run", "--rm", "--pull", "never",
        "--network", "none", "--read-only", "--ipc", "none",
        "--user", "10001:10001", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "64",
        "--cpus", str(cpu_count), "--memory", f"{memory_mb}m",
        "--memory-swap", f"{memory_mb}m", "--ulimit", "cpu=30:30",
        "--tmpfs", "/tmp:rw,nosuid,noexec,size=64m",
        "--mount", f"type=bind,src={cand},dst=/candidate,readonly",
        "--mount", f"type=bind,src={harness},dst=/harness,readonly",
        "--workdir", "/tmp", image,
        "node", "--experimental-strip-types", "/harness/runner.mjs",
    ]


def command_route(image: str, candidate_dir: Path, harness_dir: Path, *, memory_mb: int = 2560,
                  cpu_count: float = 2.0) -> list[str]:
    """Restricted Docker argv for the trusted *route* evaluator runner.

    Same hardening as :func:`command`, with two disclosed differences forced
    by the trusted Prisma toolchain: the /work tmpfs workspace permits exec
    (nosuid retained) because the pinned image's trusted Prisma query-engine
    library must be loadable from a writable location, and resource caps are
    raised within the approved local evaluation limits because Prisma needs
    more memory, PIDs and wall time than the invariant probe.
    """
    if not IMAGE_RE.fullmatch(image):
        raise ValueError("Docker image must have an exact sha256 digest pin")
    if not (256 <= memory_mb <= 3072 and 0 < cpu_count <= 2):
        raise ValueError("Resource caps outside approved local evaluation limits")
    cand = candidate_dir.resolve(strict=True)
    harness = harness_dir.resolve(strict=True)
    if any(c in str(path) for path in (cand, harness) for c in (",", "\n", "\r")):
        raise ValueError("Bind-mount paths contain an unsafe Docker --mount delimiter")
    if not cand.is_dir() or not harness.is_dir() or cand == harness:
        raise ValueError("Candidate and harness must be separate existing directories")
    if cand in harness.parents or harness in cand.parents:
        raise ValueError("Candidate and trusted harness directories must not contain one another")
    if not (harness / "route_runner.mjs").is_file():
        raise ValueError("Trusted harness route_runner.mjs is missing")
    return [
        "docker", "run", "--rm", "--pull", "never",
        "--network", "none", "--read-only", "--ipc", "none",
        "--user", "10001:10001", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "96",
        "--cpus", str(cpu_count), "--memory", f"{memory_mb}m",
        "--memory-swap", f"{memory_mb}m", "--ulimit", "cpu=90:90",
        "--tmpfs", "/tmp:rw,nosuid,noexec,size=64m",
        "--tmpfs", "/work:rw,nosuid,size=512m",
        "--mount", f"type=bind,src={cand},dst=/candidate,readonly",
        "--mount", f"type=bind,src={harness},dst=/harness,readonly",
        "--workdir", "/tmp", image,
        "node", "--experimental-strip-types", "/harness/route_runner.mjs",
    ]


def run(image: str, candidate_dir: Path, harness_dir: Path, *, timeout_seconds: int = 45,
         builder=None) -> dict:
    """Return sanitized verdict. Untrusted stdout/stderr are never emitted."""
    if shutil.which("docker") is None:
        return {"status": "BLOCKED_NO_DOCKER", "passed": False, "candidate_executed": False}
    argv = (builder or command)(image, candidate_dir, harness_dir)
    if timeout_seconds <= 0 or timeout_seconds > 120:
        raise ValueError("Timeout must be between 1 and 120 seconds")
    try:
        result = subprocess.run(
            argv, text=True, capture_output=True, timeout=timeout_seconds,
            env={"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/tmp"},
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "passed": False, "candidate_executed": True}
    except OSError:
        return {"status": "DOCKER_LAUNCH_FAILED", "passed": False, "candidate_executed": False}
    if result.returncode != 0:
        return {"status": "EXECUTION_FAILED", "passed": False, "candidate_executed": True,
                "exit_code": result.returncode}
    # A single trusted result line is required. Multiple lines make
    # candidate-stdout spoofing ambiguous and therefore fail closed.
    lines = [line[len(RESULT_MARKER):] for line in result.stdout.splitlines()
             if line.startswith(RESULT_MARKER)]
    if len(lines) != 1:
        return {"status": "NO_UNAMBIGUOUS_VERDICT", "passed": False, "candidate_executed": True}
    try:
        verdict = json.loads(lines[0])
    except json.JSONDecodeError:
        return {"status": "INVALID_VERDICT", "passed": False, "candidate_executed": True}
    checks = verdict.get("checks") if isinstance(verdict, dict) else None
    valid = (isinstance(checks, list) and bool(checks)
             and all(isinstance(c, dict) and isinstance(c.get("name"), str)
                     and c.get("passed") is True for c in checks)
             and verdict.get("pass") is True)
    return {"status": "BEHAVIOR_PASS" if valid else "BEHAVIOR_FAIL", "passed": valid,
            "candidate_executed": True, "reported_checks": len(checks) if isinstance(checks, list) else 0}


def run_route(image: str, candidate_dir: Path, harness_dir: Path, *, timeout_seconds: int = 110) -> dict:
    """Docker-only route verdict; same fail-closed parsing as :func:`run`."""
    return run(image, candidate_dir, harness_dir, timeout_seconds=timeout_seconds,
               builder=command_route)
