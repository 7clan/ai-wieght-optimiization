"""Execute generated HumanEval code only inside a restricted Docker container.

This is a defense-in-depth research sandbox, not a proof of perfect isolation.
Do NOT silently fall back to running model output on the host.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

IMAGE = "python:3.11-alpine"


def docker_command(directory: str, name: str) -> list[str]:
    return [
        "docker", "run", "--rm", "--name", name,
        "--network", "none", "--read-only",
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "32", "--memory", "256m", "--cpus", "1",
        "--user", "65534:65534",
        "--mount", f"type=bind,src={directory},dst=/work,readonly",
        IMAGE, "python", "-I", "-B", "/work/solution.py",
    ]


def require_sandbox() -> None:
    if not shutil.which("docker"):
        raise RuntimeError("Docker unavailable: refusing to execute generated code on the host")
    result = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"],
                            capture_output=True, text=True, timeout=15, check=False)
    if result.returncode:
        raise RuntimeError("Docker daemon unavailable: refusing unsandboxed evaluation")


def evaluate_completion(problem: dict, completion: str, timeout: int = 4) -> dict:
    """One completion, one isolated container, exact official HumanEval assertions."""
    if not isinstance(completion, str) or len(completion) > 30000:
        return {"passed": False, "error": "invalid/oversized completion"}
    if not 1 <= timeout <= 30:
        raise ValueError("timeout out of range")
    source = (
        problem["prompt"] + completion + "\n\n" + problem["test"]
        + "\n\ncheck(globals()[" + repr(problem["entry_point"]) + "])\n"
    )
    with tempfile.TemporaryDirectory(prefix="tinycoder_sandbox_") as folder:
        os.chmod(folder, 0o755)  # Unprivileged container user needs read access.
        file = Path(folder) / "solution.py"
        file.write_text(source, encoding="utf-8")
        os.chmod(file, 0o644)
        name = "tinycoder-" + uuid.uuid4().hex[:16]
        try:
            result = subprocess.run(
                docker_command(folder, name), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                timeout=timeout + 4, check=False,
            )
        except subprocess.TimeoutExpired:
            subprocess.run(["docker", "rm", "-f", name],
                           capture_output=True, timeout=10, check=False)
            return {"passed": False, "error": "timeout"}
        if result.returncode:
            if result.returncode == 125:
                raise RuntimeError("Docker rejected the container; cannot score execution safely")
            return {"passed": False, "error": f"container exited {result.returncode}"}
        return {"passed": True, "error": None}

