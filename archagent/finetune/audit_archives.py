"""Audit archived Qwen generations without copying training text.

This command is deliberately read-only with respect to the experiment archive.
Only aggregate counts and SHA-256 identifiers appear in its JSON output.
An accepted structural gate is *not* equivalent to a behaviorally verified
training target; all examples remain quarantined pending independent review.

Usage:
    python -m archagent.finetune.audit_archives --repo . --out /tmp/audit.json
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re


SECRET_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
)
PLACEHOLDER_PATTERNS = (
    re.compile(r"\b(?:TODO|FIXME|not implemented)\b", re.IGNORECASE),
    re.compile(r"<another sentence>|<yet another sentence>", re.IGNORECASE),
    re.compile(r"\b(?:Now your task|The first line is already written)\b", re.IGNORECASE),
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def family(relative_path: Path) -> str:
    parts = relative_path.parts
    if "z036-roomreserve" in parts:
        return "session036"
    if "z037-generalization" in parts:
        i = parts.index("z037-generalization")
        return "session037/" + (parts[i + 1] if len(parts) > i + 1 else "unknown")
    return "other"


def check_record(record: object) -> dict[str, object] | None:
    if not isinstance(record, dict):
        return None
    prompt = record.get("prompt")
    candidate = record.get("candidate")
    if not isinstance(prompt, str) or not isinstance(candidate, str):
        return None
    combined = prompt + "\n" + candidate
    return {
        "prompt_sha256": digest(prompt),
        "candidate_sha256": digest(candidate),
        "prompt_bytes": len(prompt.encode("utf-8")),
        "candidate_bytes": len(candidate.encode("utf-8")),
        "blank_candidate": not candidate.strip(),
        "potential_secret": any(pattern.search(combined) for pattern in SECRET_PATTERNS),
        "placeholder_or_echo": any(pattern.search(candidate) for pattern in PLACEHOLDER_PATTERNS),
        "archive_gate_pass": record.get("gate", {}).get("pass") if isinstance(record.get("gate"), dict) else None,
    }


def audit(repo: Path) -> dict[str, object]:
    root = (repo / "experiments").resolve()
    if not root.is_dir() or not (repo / "AGENTS.md").is_file():
        raise ValueError("Expected a repository with AGENTS.md and experiments/")

    stats: Counter[str] = Counter()
    by_family: dict[str, Counter[str]] = defaultdict(Counter)
    prompt_hashes: Counter[str] = Counter()
    candidate_hashes: Counter[str] = Counter()
    flagged_examples: list[dict[str, str]] = []

    for path in sorted(root.rglob("*.json")):
        relative = path.relative_to(repo)
        if "gen" not in relative.parts and "generations" not in relative.parts and not any(
            x.endswith("-gen") for x in relative.parts
        ):
            continue
        stats["json_files_examined"] += 1
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            stats["unreadable_json_files"] += 1
            continue
        rec = check_record(data)
        if rec is None:
            stats["missing_prompt_candidate"] += 1
            continue
        stats["valid_generation_records"] += 1
        category = family(relative)
        by_family[category]["records"] += 1
        prompt_hashes[str(rec["prompt_sha256"])] += 1
        candidate_hashes[str(rec["candidate_sha256"])] += 1
        for key in ("blank_candidate", "potential_secret", "placeholder_or_echo"):
            if rec[key]:
                stats[key] += 1
                by_family[category][key] += 1
                if key == "potential_secret":
                    flagged_examples.append({"path": relative.as_posix(), "reason": "potential_secret"})
        if rec["archive_gate_pass"] is True:
            stats["archive_structural_gate_pass"] += 1
        elif rec["archive_gate_pass"] is False:
            stats["archive_structural_gate_fail"] += 1

    stats["repeated_prompt_records"] = sum(n - 1 for n in prompt_hashes.values() if n > 1)
    stats["repeated_candidate_records"] = sum(n - 1 for n in candidate_hashes.values() if n > 1)

    return {
        "schema_version": 1,
        "archive_audit": dict(sorted(stats.items())),
        "families": {name: dict(sorted(counts.items())) for name, counts in sorted(by_family.items())},
        "potential_secret_paths_only": flagged_examples,
        "training_examples_approved": 0,
        "status": "QUARANTINED: archive structural acceptance is not independent behavioral verification",
        "required_before_training": [
            "Obtain explicit authorization to change repository training restrictions on a separate branch",
            "Verify candidate provenance and behavior in isolated execution with stable reference tests",
            "Deduplicate by code, prompt, and task family; exclude teacher-written and contaminated artifacts",
            "Freeze a new domain-disjoint holdout before reviewing or selecting training examples",
            "Confirm hardware feasibility and compare unmodified base model to any trained adapter",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.repo.resolve())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Audited {result['archive_audit'].get('valid_generation_records', 0)} generation records; training examples approved: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
