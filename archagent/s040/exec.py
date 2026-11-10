"""Restricted execution boundary for Session-040 UNTRUSTED code (dual backend).

Backend 1 — Docker (production tier): mirrors the reviewed Session-039
container flags (network none, read-only root, UID 10001, cap-drop ALL,
no-new-privileges, pids/cpu/memory caps, digest-pinned image, --pull never)
plus a read-only /eval-deps bind for the pinned React evaluation toolchain.
Used only in the approved GitHub Actions workflow with a vetted image; it is
never silently substituted when Docker is absent.

Backend 2 — unshare user+mount+network namespaces (disclosed local tier):
this sandbox has no Docker binary (documented since Session 039B). Model
code must still never execute on the bare host, so this backend reproduces
the Docker flag set as closely as the kernel allows, following the
AGENTS.md ``ARCHAGENT_LOCAL_EVAL=1`` disclosed local-eval precedent of
Sessions 031/032/033 and 038A, strengthened to a pivot_root'd minimal
filesystem:

* fresh user+mount+PID+network namespaces (``--propagation private``);
* network namespace with only a DOWN loopback interface => no networking,
  not even loopback;
* new root is a private tmpfs; the ONLY mounted trees are read-only binds of
  /usr, /lib, /lib64, the candidate, the trusted harness and the pinned
  /eval-deps toolchain; the previous root is covered by an empty tmpfs
  (umount needs /proc, which this kernel refuses inside user namespaces);
* the writable surface is exactly two tmpfs mounts: /work (exec permitted
  for the trusted Prisma engine, nosuid retained) and /tmp (noexec);
* all capabilities are dropped from the bounding set before the runner is
  exec'd, so the process cannot mount, chroot or pivot its way out;
* rlimits: CPU seconds, RLIMIT_AS (address space), RLIMIT_NPROC,
  RLIMIT_FSIZE; wall-clock kill of the whole process group from the
  controller.

Deviations from the Docker flags, all disclosed and recorded in every
evidence record (tier=UNSHARE_USERNS_DISCLOSED): /proc, /dev and /etc are
absent (this kernel forbids binding or mounting them inside a user
namespace; Node 24 boots without them — entropy comes from getrandom(2));
/dev/null is a regular absorbing file inside a tiny tmpfs because device
nodes cannot be created here; the memory cap is RLIMIT_AS (virtual address
space) rather than a cgroup RSS limit. No isolation flag that Docker
provides and this kernel can provide has been omitted.

Both backends parse verdicts identically and fail closed: exactly one
``S040-RESULT `` marker line, valid JSON, non-empty checks, all passed.
Untrusted stdout/stderr are never emitted to the caller beyond the parsed
verdict.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

RESULT_MARKER = "S040-RESULT "
IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9._/:-]*@sha256:[a-f0-9]{64}$")

RUNNERS = ("react_runner.mjs", "integration_runner.mjs", "schema_runner.mjs",
           "runner.mjs", "route_runner.mjs")

# Session-039 trusted runners executed through this tier (compat mode): they
# are env-parameterized (S039_*) and emit their own S039-RESULT marker.
S039_RUNNERS = {"runner.mjs": "invariant", "route_runner.mjs": "route"}

DEFAULT_EVAL_DEPS = Path(__file__).resolve().parents[2] / ".eval-deps"

# Resource caps kept within the Session-039 approved local-evaluation limits.
TIERS = {
    "react": {"cpu_s": 40, "as_kb": 2_097_152, "work_mb": 256, "wall_s": 150},
    # integration needs 3 GiB VA: the Prisma CLI bundle provably aborts under
    # 2.5 GiB inside the namespace (measured 2026-11-10); 3 GiB is the top of
    # the approved local-evaluation limit range.
    "integration": {"cpu_s": 90, "as_kb": 3_145_728, "work_mb": 512, "wall_s": 200},
    "schema": {"cpu_s": 60, "as_kb": 3_145_728, "work_mb": 384, "wall_s": 180},
    "invariant": {"cpu_s": 30, "as_kb": 1_572_864, "work_mb": 64, "wall_s": 60},
    "route": {"cpu_s": 90, "as_kb": 3_145_728, "work_mb": 512, "wall_s": 200},
}


def _validate_dirs(candidate_dir: Path, harness_dir: Path, deps_dir: Path) -> tuple[Path, Path, Path]:
    cand = candidate_dir.resolve(strict=True)
    harness = harness_dir.resolve(strict=True)
    deps = deps_dir.resolve(strict=True)
    for path in (cand, harness, deps):
        if any(c in str(path) for c in (",", "\n", "\r", '"', "'")):
            raise ValueError("Staged paths contain characters unsafe for mount scripting")
    if not cand.is_dir() or not harness.is_dir() or not deps.is_dir():
        raise ValueError("Candidate, harness and eval-deps must be existing directories")
    if len({cand, harness, deps}) != 3:
        raise ValueError("Candidate, harness and eval-deps must be distinct directories")
    for runner in RUNNERS:
        if (harness / runner).is_file():
            break
    else:
        raise ValueError(f"Trusted harness must contain one of {RUNNERS}")
    if not (deps / "node_modules").is_dir():
        raise ValueError("Pinned eval-deps node_modules is missing (run the setup script)")
    return cand, harness, deps


def _check_resource_caps(tier: str) -> dict:
    caps = TIERS[tier]
    if not (0 < caps["cpu_s"] <= 120 and 524_288 <= caps["as_kb"] <= 3_145_728
            and 64 <= caps["work_mb"] <= 1024 and 0 < caps["wall_s"] <= 300):
        raise ValueError("Resource caps outside approved local evaluation limits")
    return caps


def docker_argv(image: str, candidate_dir: Path, harness_dir: Path, deps_dir: Path, *,
                runner: str, tier: str) -> list[str]:
    """Docker argv mirroring the reviewed s039 flags plus /eval-deps (CI tier)."""
    if runner not in RUNNERS:
        raise ValueError("Unknown trusted runner")
    if IMAGE_RE.fullmatch(image) is None:
        raise ValueError("Docker image must have an exact sha256 digest pin")
    caps = _check_resource_caps(tier)
    cand, harness, deps = _validate_dirs(candidate_dir, harness_dir, deps_dir)
    return [
        "docker", "run", "--rm", "--pull", "never",
        "--network", "none", "--read-only", "--ipc", "none",
        "--user", "10001:10001", "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges", "--pids-limit", "96",
        "--cpus", "2", "--memory", f"{caps['as_kb'] // 1024}m",
        "--memory-swap", f"{caps['as_kb'] // 1024}m", "--ulimit", f"cpu={caps['cpu_s']}:{caps['cpu_s']}",
        "--tmpfs", "/tmp:rw,nosuid,noexec,size=64m",
        "--tmpfs", f"/work:rw,nosuid,size={caps['work_mb']}m",
        "--mount", f"type=bind,src={cand},dst=/candidate,readonly",
        "--mount", f"type=bind,src={harness},dst=/harness,readonly",
        "--mount", f"type=bind,src={deps},dst=/eval-deps,readonly",
        "--workdir", "/tmp", image,
        "node", f"/harness/{runner}",
    ]


def unshare_script(candidate_dir: Path, harness_dir: Path, deps_dir: Path, *,
                   runner: str, tier: str, stage_root: Path) -> list[str]:
    """Full argv for the disclosed unshare tier (see module docstring)."""
    if runner not in RUNNERS:
        raise ValueError("Unknown trusted runner")
    caps = _check_resource_caps(tier)
    cand, harness, deps = _validate_dirs(candidate_dir, harness_dir, deps_dir)
    stage = stage_root.resolve(strict=True)
    if stage == cand or stage == harness or stage == deps:
        raise ValueError("Sandbox newroot must be distinct from staged trees")
    newroot = stage / "newroot"
    if newroot.exists():
        raise FileExistsError("Sandbox newroot already exists")
    newroot.mkdir()
    if runner in S039_RUNNERS:
        s039_env = ("S039_HARNESS=/harness S039_CANDIDATE=/candidate/output.ts "
                    "S039_WORK=/work")
    else:
        s039_env = ""
    inner = f"""
set -eu
R={shlex.quote(str(newroot))}
mount -t tmpfs -o size=96m,nosuid tmpfs "$R"
mkdir -p "$R/usr" "$R/lib" "$R/lib64" "$R/work" "$R/tmp" "$R/dev" \
         "$R/candidate" "$R/harness" "$R/eval-deps" "$R/oldroot"
mount --bind /usr "$R/usr"
mount -o remount,bind,ro "$R/usr"
mount --bind /lib "$R/lib"
mount -o remount,bind,ro "$R/lib"
mount --bind /usr/lib64 "$R/lib64"
mount -o remount,bind,ro "$R/lib64"
mount --bind {shlex.quote(str(cand))} "$R/candidate"
mount -o remount,bind,ro "$R/candidate"
mount --bind {shlex.quote(str(harness))} "$R/harness"
mount -o remount,bind,ro "$R/harness"
mount --bind {shlex.quote(str(deps))} "$R/eval-deps"
mount -o remount,bind,ro "$R/eval-deps"
mount -t tmpfs -o size={caps['work_mb']}m,nosuid tmpfs "$R/work"
mkdir -p "$R/work/node_modules"
mount --bind {shlex.quote(str(deps))}/node_modules "$R/work/node_modules"
mount -o remount,bind,ro "$R/work/node_modules"
mount -t tmpfs -o size=64m,nosuid,nodev,noexec tmpfs "$R/tmp"
mount -t tmpfs -o size=4m,nosuid tmpfs "$R/dev"
: > "$R/dev/null"
ulimit -t {caps['cpu_s']}
ulimit -v {caps['as_kb']}
ulimit -f 131072
cd "$R"
pivot_root . oldroot
mount -t tmpfs -o size=4m,nosuid tmpfs /oldroot
exec /usr/bin/setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
  /usr/bin/env -i PATH=/usr/bin:/bin:/eval-deps/node_modules/.bin \
  HOME=/work TMPDIR=/tmp \
  PRISMA_HIDE_UPDATE_MESSAGE=1 PRISMA_SKIP_POSTINSTALL_GENERATE=1 PRISMA_GENERATE_SKIP_AUTOINSTALL=1 \
  PRISMA_CLI_BINARY_TARGETS=debian-openssl-3.0.x \
  PRISMA_SCHEMA_ENGINE_BINARY=/eval-deps/node_modules/@prisma/engines/schema-engine-debian-openssl-3.0.x \
  PRISMA_QUERY_ENGINE_LIBRARY=/eval-deps/node_modules/@prisma/engines/libquery_engine-debian-openssl-3.0.x.so.node \
  NODE_ENV=test NO_COLOR=1 \
  {s039_env}\
  /usr/bin/node --experimental-strip-types /harness/{runner}
""".strip()
    return ["unshare", "--user", "--map-root-user", "--mount", "--net", "--pid", "--fork",
            "--propagation", "private", "sh", "-c", inner]


def _parse_verdict(stdout: str, marker: str = RESULT_MARKER) -> dict:
    lines = [line[len(marker):] for line in stdout.splitlines()
             if line.startswith(marker)]
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
            "candidate_executed": True,
            "reported_checks": len(checks) if isinstance(checks, list) else 0}


def _make_rlimits():
    def apply() -> None:
        import resource
        # Backstops applied in the forked child before exec. RLIMIT_AS must
        # exceed the controller Python process's own address space (a forked
        # child carries the parent's mappings until execve replaces them;
        # 2 GB provably breaks exec of the sandbox helper). The TIGHT per-tier
        # cpu/memory/filesize caps are applied inside the namespace by the
        # inner script's ulimit calls, which run after the small shell image
        # has loaded. RLIMIT_NPROC is dash-ulimit-incompatible and per real
        # uid system-wide (9 processes existed for this uid at design time;
        # 256 is a coarse fork-bomb backstop — the wall-clock group kill is
        # the primary bound).
        # NOTE: resource.setrlimit values are BYTES (the inner script's
        # ulimit uses KiB); the tight per-tier caps below stay in the script.
        resource.setrlimit(resource.RLIMIT_AS, (3_221_225_472, 3_221_225_472))
        resource.setrlimit(resource.RLIMIT_NPROC, (256, 256))
        resource.setrlimit(resource.RLIMIT_FSIZE, (134_217_728, 134_217_728))
    return apply


def run(candidate_dir: Path, harness_dir: Path, deps_dir: Path, *, runner: str,
        tier: str | None = None, backend: str = "auto", image: str | None = None) -> dict:
    """Execute one restricted evaluation; returns a sanitized fail-closed verdict.

    ``backend``: ``"docker"`` (requires ``image``, hard-fails if the Docker
    binary is absent), ``"unshare"`` (the disclosed local tier), or ``"auto"``
    (Docker when available, otherwise the disclosed unshare tier with the
    tier recorded in the result).
    ``tier`` defaults from the runner name (Session-039 compat runners map to
    their own approved caps).
    """
    if tier is None:
        tier = S039_RUNNERS.get(runner) or runner.split("_")[0]
    caps = _check_resource_caps(tier)
    marker = "S039-RESULT " if runner in S039_RUNNERS else RESULT_MARKER
    stage_root: Path | None = None
    if backend not in ("auto", "docker", "unshare"):
        raise ValueError("Unknown backend")
    if backend == "docker" and shutil.which("docker") is None:
        return {"status": "BLOCKED_NO_DOCKER", "passed": False, "candidate_executed": False}
    use_docker = (backend == "docker") or (backend == "auto" and shutil.which("docker") is not None)
    if use_docker:
        if not image:
            raise ValueError("Docker backend requires a pinned image digest")
        argv = docker_argv(image, candidate_dir, harness_dir, deps_dir,
                           runner=runner, tier=tier)
        used_tier = "DOCKER_RESTRICTED"
        cwd = None
    else:
        if backend == "docker":
            return {"status": "BLOCKED_NO_DOCKER", "passed": False, "candidate_executed": False}
        stage_root = Path(tempfile.mkdtemp(prefix="s040-ns-stage-", dir="/tmp"))
        try:
            argv = unshare_script(candidate_dir, harness_dir, deps_dir,
                                  runner=runner, tier=tier, stage_root=stage_root)
        except Exception:
            shutil.rmtree(stage_root, ignore_errors=True)
            raise
        used_tier = "UNSHARE_USERNS_DISCLOSED"
        cwd = str(stage_root)
    env = {"PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"), "HOME": "/tmp"}
    try:
        proc = subprocess.Popen(argv, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, env=env, cwd=cwd,
                                start_new_session=True,
                                preexec_fn=_make_rlimits())
        try:
            stdout, _stderr = proc.communicate(timeout=caps["wall_s"])
        except subprocess.TimeoutExpired:
            import signal
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except OSError:
                pass
            stdout, _stderr = proc.communicate()
            return {"status": "TIMEOUT", "passed": False, "candidate_executed": True,
                    "tier": used_tier}
        if proc.returncode != 0:
            return {"status": "EXECUTION_FAILED", "passed": False,
                    "candidate_executed": True, "exit_code": proc.returncode, "tier": used_tier}
        result = _parse_verdict(stdout or "", marker=marker)
        result["tier"] = used_tier
        return result
    finally:
        if stage_root is not None:
            shutil.rmtree(stage_root, ignore_errors=True)
