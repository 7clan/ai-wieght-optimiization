"""Read-only, metadata-only reconciliation of Z.ai Session 038A replay claims.

This does not re-execute candidates or verify the reported namespace setup.
In particular, an `unshare` result must not silently satisfy a Docker-only
proof requirement. No output can mark a candidate training-eligible.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from .audit_archives import check_record


BASE = Path("experiments/z038a-independent-retest")
QUEUE = Path("experiments/finetune-readiness-038/candidate-queue.jsonl")
MODEL_SHA = "aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80"


def _read_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _safe_file(repo: Path, relative: object) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    root = repo.resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        return None
    return path


def evaluate(repo: Path) -> dict:
    """Cross-check claims and hashes, never certify a sandbox or behavior."""
    repo = repo.resolve()
    queue = _read_jsonl(repo / QUEUE)
    replays = _read_jsonl(repo / BASE / "replay-results.jsonl")
    manifest = _read_json(repo / BASE / "training-candidates.json")
    summary = _read_json(repo / BASE / "replay-summary.json")
    if not isinstance(manifest, dict) or not isinstance(summary, dict):
        raise ValueError("Session 038A metadata must be JSON objects")

    q_by_hash = {x["candidate_sha256"]: x for x in queue}
    r_by_hash = {x["candidate_sha256"]: x for x in replays}
    entries = manifest.get("entries", [])
    errors: list[str] = []

    if len(q_by_hash) != len(queue) or len(q_by_hash) != 22:
        errors.append("queue_count_or_candidate_hash_collision")
    if len(r_by_hash) != len(replays) or set(r_by_hash) != set(q_by_hash):
        errors.append("replay_queue_membership_mismatch")
    if not isinstance(entries, list) or len(entries) != len(queue):
        errors.append("manifest_count_mismatch")
        entries = []
    e_by_hash = {e.get("provenance", {}).get("candidate_sha256"): e for e in entries if isinstance(e, dict)}
    if set(e_by_hash) != set(q_by_hash) or len(e_by_hash) != len(entries):
        errors.append("manifest_queue_membership_mismatch")

    reported = Counter()
    families = Counter()
    normalized: set[str] = set()
    for sha, q in sorted(q_by_hash.items()):
        r = r_by_hash.get(sha)
        e = e_by_hash.get(sha)
        if not isinstance(r, dict) or not isinstance(e, dict):
            continue
        if q.get("piece") != r.get("piece") or q.get("piece") != e.get("piece"):
            errors.append(f"piece_mismatch:{sha}")
        if q.get("kind") != r.get("kind") or q.get("kind") != e.get("kind"):
            errors.append(f"kind_mismatch:{sha}")
        provenance = e.get("provenance", {})
        if not isinstance(provenance, dict) or any(
            provenance.get(k) != q.get(k) for k in ("candidate_sha256", "prompt_sha256", "generation_path", "ledger_path")
        ):
            errors.append(f"provenance_mismatch:{sha}")
        if isinstance(provenance, dict) and provenance.get("model_sha256") != MODEL_SHA:
            errors.append(f"model_pin_mismatch:{sha}")

        src = _safe_file(repo, q.get("generation_path"))
        record = None
        if src:
            try:
                record = check_record(_read_json(src))
            except (OSError, UnicodeError, json.JSONDecodeError):
                pass
        if (record is None or record["candidate_sha256"] != sha
                or record["prompt_sha256"] != q.get("prompt_sha256")):
            errors.append(f"original_generation_hash_mismatch:{sha}")
        elif record["blank_candidate"] or record["potential_secret"] or record["placeholder_or_echo"]:
            errors.append(f"content_screen_flag:{sha}")

        v = r.get("verification")
        good = isinstance(v, dict) and v.get("structural_gate") is True
        if q.get("kind") == "prisma-model":
            good = good and v.get("prisma_validate") is True and v.get("prisma_db_push") is True
            behavior = v.get("sqlite_behavior")
            good = good and isinstance(behavior, dict) and behavior.get("pass") is True and behavior.get("n_checks", 0) >= 5 and behavior.get("failures") == []
        elif q.get("kind") == "invariant":
            probe = v.get("invariant_behavior") or v.get("invariant_probe")
            good = good and isinstance(probe, dict) and probe.get("pass") is True
        else:
            good = False
        if not good or not str(r.get("status", "")).startswith("INDEPENDENTLY_VERIFIED"):
            errors.append(f"behavior_claim_incomplete:{sha}")
        if r.get("fingerprint", "")[:16] != e.get("normalized_structure"):
            errors.append(f"fingerprint_mismatch:{sha}")
        normalized.add(r.get("fingerprint", ""))
        families[e.get("task_family", "UNLABELED")] += 1
        reported[q.get("kind", "unknown")] += 1

    if manifest.get("training_eligible") != 0 or summary.get("training_eligible") != 0:
        errors.append("training_permission_claim")
    stats = summary.get("stats", {})
    if not isinstance(stats, dict) or stats.get("verified") != 22 or stats.get("quarantined") != 0:
        errors.append("replay_summary_claim_mismatch")
    if manifest.get("counts", {}).get("distinct_normalized_structures") != len(normalized):
        errors.append("normalized_structure_count_mismatch")
    isolation = summary.get("isolation", "")
    if not isinstance(isolation, str) or "unshare" not in isolation or "Docker unavailable" not in isolation:
        errors.append("isolation_disclosure_mismatch")

    return {
        "source": "Session 038A archived evidence (metadata only)",
        "queue_candidates": len(queue),
        "reported_behavior_passes": sum(r["status"].startswith("INDEPENDENTLY_VERIFIED") for r in replays),
        "normalized_structures": len(normalized),
        "task_family_counts": dict(sorted(families.items())),
        "kind_counts": dict(sorted(reported.items())),
        "errors": sorted(set(errors)),
        "metadata_consistent": not errors,
        "reported_isolation": "unshare-user-network-namespaces",
        "docker_reproduced": False,
        "executions_performed_by_this_audit": 0,
        "training_eligible": 0,
        "interpretation": "Consistent archives are not independent proof of execution, container isolation or generalization",
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.repo)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Metadata consistent: {result['metadata_consistent']}; replay claims: {result['reported_behavior_passes']}; training allowed: 0")
    return 0 if result["metadata_consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
