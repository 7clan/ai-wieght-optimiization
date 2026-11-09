"""Join Session-037 generation files to per-attempt ledgers, conservatively.

Emits a *verification queue*, not a training dataset. The JSONL output
contains only file locations and hashes (never raw prompts or code).
Training eligibility is always false until an independent isolated
behavioral verifier certifies the complete program and task provenance.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .audit_archives import check_record


def ledger_paths(source: Path) -> list[Path]:
    return sorted(source.rglob("*ledger.jsonl"))


def get_generations_for_ledger(ledger: Path) -> Path | None:
    """Resolve the source dir using known archive conventions only."""
    name = ledger.name
    mapping = {
        "ledger.jsonl": "gen",
        "engine-ledger.jsonl": "engine-gen",
        "smoke-ledger.jsonl": "smoke-gen",
    }
    dirname = mapping.get(name)
    if not dirname:
        return None
    candidate = ledger.parent / dirname
    return candidate if candidate.is_dir() else None


def matches_attempt(record: dict, piece: str, attempt: dict) -> bool:
    if record.get("piece") != piece:
        return False
    if record.get("seed") != attempt.get("seed"):
        return False
    if not isinstance(record.get("candidate"), str):
        return False
    fingerprint = hashlib.sha256(record["candidate"].encode("utf-8")).hexdigest()
    return fingerprint.startswith(str(attempt.get("candidate_sha", "!")))


def build_queue(repo: Path) -> tuple[list[dict], dict]:
    root = repo / "experiments" / "z037-generalization"
    if not (repo / "AGENTS.md").exists() or not root.is_dir():
        raise ValueError("Expected root of the Session-037 repository")

    queue: list[dict] = []
    stats: Counter[str] = Counter()
    seen_outputs: set[str] = set()
    for ledger in ledger_paths(root):
        # Original C/D runs credited other tracks' installed files; don't
        # use their acceptance/provenance metadata for training selection.
        if any("contaminated" in part for part in ledger.parts):
            stats["contaminated_ledgers_skipped"] += 1
            continue
        folder = get_generations_for_ledger(ledger)
        if folder is None:
            stats["ledgers_without_generation_folder"] += 1
            continue
        records: list[tuple[Path, dict]] = []
        for file in sorted(folder.glob("*.json")):
            try:
                rec = json.loads(file.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                stats["malformed_generation_files"] += 1
                continue
            if isinstance(rec, dict):
                records.append((file, rec))
        for line in ledger.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                stats["malformed_ledger_rows"] += 1
                continue
            piece = entry.get("piece")
            if not isinstance(piece, str):
                stats["missing_piece_identifiers"] += 1
                continue
            for attempt in entry.get("attempts", []):
                if not isinstance(attempt, dict) or attempt.get("outcome") != "accept":
                    continue
                stats["reported_acceptances"] += 1
                matches = [(file, record) for file, record in records if matches_attempt(record, piece, attempt)]
                if len(matches) != 1:
                    stats["unmatched_or_ambiguous_acceptances"] += 1
                    continue
                file, record = matches[0]
                checked = check_record(record)
                if checked is None:
                    stats["invalid_generation_records"] += 1
                    continue
                if checked["blank_candidate"] or checked["potential_secret"] or checked["placeholder_or_echo"]:
                    stats["quarantined_for_content_flags"] += 1
                    continue
                if attempt.get("gate", {}).get("pass") is not True:
                    stats["acceptance_without_passed_gate"] += 1
                    continue
                output_hash = checked["candidate_sha256"]
                if output_hash in seen_outputs:
                    stats["duplicate_outputs_skipped"] += 1
                    continue
                seen_outputs.add(output_hash)
                queue.append({
                    "generation_path": file.relative_to(repo).as_posix(),
                    "ledger_path": ledger.relative_to(repo).as_posix(),
                    "piece": piece,
                    "kind": entry.get("kind", "unknown"),
                    "prompt_sha256": checked["prompt_sha256"],
                    "candidate_sha256": output_hash,
                    "in_loop_gate_pass": True,
                    "in_loop_probe_pass": attempt.get("probe", {}).get("pass") if isinstance(attempt.get("probe"), dict) else None,
                    "independent_behavior_verified": False,
                    "training_eligible": False,
                    "status": "AWAITING_ISOLATED_REPLAY",
                })
                stats["queued_for_independent_replay"] += 1
    return queue, dict(sorted(stats.items()))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=Path("."))
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--summary", type=Path, required=True)
    args = p.parse_args()
    queue, stats = build_queue(args.repo.resolve())
    for file in (args.out, args.summary):
        file.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("".join(json.dumps(item, sort_keys=True) + "\n" for item in queue), encoding="utf-8")
    args.summary.write_text(json.dumps({"metrics": stats, "training_eligible": 0, "disclaimer": "Requires independent sandboxed behavioral replay"}, indent=2) + "\n", encoding="utf-8")
    print(f"Queued {len(queue)} in-loop accepted outputs for independent replay; approved 0 for training")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
