"""Check whether an isolated replay attestation is internally consistent.

This is a *metadata* verifier, not a substitute for rerunning tests. A
supplied JSON file cannot cryptographically prove how code was executed.
It deliberately never executes archived model-generated code and never
emits raw prompt/completion contents. Passing records remain subject to
human review and training authorization.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

from .audit_archives import check_record


REQUIRED_CHECKS = {
    "prisma-model": {"schema_validate", "database_behavior"},
    "invariant": {"typescript_compile", "property_behavior"},
    "route-handler": {"typescript_compile", "api_behavior"},
    "ui": {"typescript_compile", "browser_behavior"},
}


def _file_at(repo: Path, relative: str) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    root = repo.resolve()
    candidate = (root / relative).resolve()
    return candidate if candidate.is_relative_to(root) and candidate.is_file() else None


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_proof(repo: Path, item: dict, proof: dict) -> list[str]:
    """Return machine-checkable shortcomings, never model text."""
    errors: list[str] = []
    if proof.get("candidate_sha256") != item.get("candidate_sha256"):
        errors.append("candidate_hash_mismatch")
    if proof.get("prompt_sha256") != item.get("prompt_sha256"):
        errors.append("prompt_hash_mismatch")
    if proof.get("generation_path") != item.get("generation_path"):
        errors.append("generation_path_mismatch")
    if proof.get("provenance") != "QWEN_GENERATED_UNMODIFIED":
        errors.append("unverified_model_provenance")
    if proof.get("teacher_written_bytes") != 0 or proof.get("candidate_edited_after_generation") is not False:
        errors.append("teacher_or_post_generation_edit")

    source = _file_at(repo, str(item.get("generation_path", "")))
    if source is None:
        errors.append("missing_generation_file")
    else:
        try:
            record = json.loads(source.read_text(encoding="utf-8"))
            hashed = check_record(record)
        except (OSError, UnicodeError, json.JSONDecodeError):
            hashed = None
        if hashed is None or hashed["candidate_sha256"] != item.get("candidate_sha256") or hashed["prompt_sha256"] != item.get("prompt_sha256"):
            errors.append("archive_content_hash_mismatch")
        elif hashed["potential_secret"] or hashed["placeholder_or_echo"] or hashed["blank_candidate"]:
            errors.append("unsafe_archive_content")

    sandbox = proof.get("sandbox")
    if not isinstance(sandbox, dict) or not (
        sandbox.get("runtime") == "docker"
        and sandbox.get("network") == "none"
        and sandbox.get("read_only") is True
        and sandbox.get("unprivileged") is True
        and sandbox.get("no_new_privileges") is True
        and isinstance(sandbox.get("memory_mb"), int)
        and 64 <= sandbox["memory_mb"] <= 4096
        and isinstance(sandbox.get("cpus"), (int, float))
        and 0 < sandbox["cpus"] <= 4
    ):
        errors.append("isolation_requirements_not_attested")

    if proof.get("test_fixture_modified_after_generation") is not False:
        errors.append("fixture_not_frozen")
    for key in ("task_spec", "test_report"):
        evidence = proof.get(key)
        if not isinstance(evidence, dict):
            errors.append(f"missing_{key}_evidence")
            continue
        file = _file_at(repo, evidence.get("path"))
        if file is None or evidence.get("sha256") != _sha_file(file):
            errors.append(f"{key}_hash_mismatch")

    required = REQUIRED_CHECKS.get(item.get("kind"))
    if required is None:
        errors.append("unsupported_contract_kind")
    evidence = proof.get("test_report", {})
    report = _file_at(repo, evidence.get("path")) if isinstance(evidence, dict) else None
    if report is not None:
        try:
            result = json.loads(report.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            result = None
        if not isinstance(result, dict) or result.get("exit_code") != 0:
            errors.append("test_report_execution_failed")
        else:
            checks = result.get("checks")
            if not isinstance(checks, list):
                errors.append("test_report_missing_checks")
            else:
                passed = {x.get("name") for x in checks if isinstance(x, dict) and x.get("passed") is True}
                failed = [x for x in checks if not isinstance(x, dict) or x.get("passed") is not True]
                if failed or required is None or not required.issubset(passed):
                    errors.append("test_report_incomplete_or_failed")

    return sorted(set(errors))


def evaluate_queue(repo: Path, queue_path: Path, proof_dir: Path) -> dict:
    counts: Counter[str] = Counter()
    results: list[dict] = []
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        token = item["candidate_sha256"]
        # Queue files are data, so never interpolate unvalidated names into paths.
        if not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{64}", token) is None:
            status, reasons = "QUARANTINED", ["invalid_candidate_hash"]
        elif not (proof_dir / f"{token}.json").is_file():
            status, reasons = "AWAITING_REPLAY", ["missing_replay_proof"]
        else:
            try:
                proof = json.loads((proof_dir / f"{token}.json").read_text(encoding="utf-8"))
                reasons = check_proof(repo, item, proof) if isinstance(proof, dict) else ["invalid_replay_proof_type"]
            except (OSError, UnicodeError, json.JSONDecodeError):
                reasons = ["unreadable_replay_proof"]
            status = "CONSISTENT_ATTESTATION_NEEDS_REVIEW" if not reasons else "QUARANTINED"
        counts[status] += 1
        results.append({"candidate_sha256": token, "status": status, "reasons": reasons, "training_eligible": False})
    return {
        "counts": dict(sorted(counts.items())),
        "records": results,
        "independently_replayed_by_this_command": 0,
        "training_approved_by_this_command": 0,
        "note": "A JSON attestation cannot prove isolation or correctness; reproduce externally and review before training",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--proof-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate_queue(args.repo.resolve(), args.queue, args.proof_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Checked {len(result['records'])} candidates; trained/approved: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
