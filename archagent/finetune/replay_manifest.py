"""SESSION 038A — Phase 1 deliverable compiler.

Builds the sanitized training-candidate manifest + dataset card from
the replay results.  Emits NO raw prompts, NO raw candidates, NO
credentials — only hashes, paths, provenance chains, verification
layers and family/structure groupings.

Usage:  python -m archagent.finetune.replay_manifest
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from archagent.finetune.replay import ROOT, load_specs, model_fingerprint

REPLAY = ROOT / "experiments/z038a-independent-retest/replay-results.jsonl"
QUEUE = ROOT / "experiments/finetune-readiness-038/candidate-queue.jsonl"
OUT = ROOT / "experiments/z038a-independent-retest"

# task-family classification (hand-mapped from the frozen specs)
FAMILY = {
    "gh-plant": ("challenge", "relations-parent-1tm"),
    "gh-watering": ("challenge", "relations-child-required-fk"),
    "rel-1tm-band": ("curriculum-a", "relations-parent-1tm"),
    "rel-1tm-album": ("curriculum-a", "relations-child-required-fk"),
    "rel-opt-plot": ("curriculum-a", "relations-parent-1tm"),
    "rel-opt-planting": ("curriculum-a", "relations-child-optional-fk"),
    "rel-req-screen": ("curriculum-a", "relations-parent-1tm"),
    "rel-req-showing": ("curriculum-a", "relations-child-required-fk"),
    "rel-two-customer": ("curriculum-a", "relations-parent-1tm"),
    "rel-two-coupon": ("curriculum-a", "relations-parent-1tm"),
    "rel-self-category": ("curriculum-a", "relations-self"),
    "rel-cascade-aisle": ("curriculum-a", "relations-parent-1tm"),
    "rel-cascade-bin": ("curriculum-a", "relations-child-required-fk"),
    "inv-weight": ("curriculum-b", "invariant-numeric-boundary"),
    "inv-capacity": ("curriculum-b", "invariant-capacity"),
    "inv-duplicate": ("curriculum-b", "invariant-duplicate-detection"),
    "ap-approver": ("suite-approvals", "relations-parent-1tm"),
    "ap-request": ("suite-approvals", "relations-child-required-fk"),
    "mn-machine": ("suite-maintenance", "relations-parent-1tm"),
    "mn-log": ("suite-maintenance", "relations-child-required-fk"),
    "pr-plan": ("suite-pricing", "relations-parent-1tm"),
    "pr-subscription": ("suite-pricing", "relations-child-required-fk"),
}


def build() -> None:
    rows = [json.loads(l) for l in REPLAY.read_text().splitlines() if l.strip()]
    queue = {json.loads(l)["piece"]: json.loads(l)
             for l in QUEUE.read_text().splitlines() if l.strip()}

    # token/seed provenance from ledgers
    prov = {}
    for pid, item in queue.items():
        for line in open(ROOT / item["ledger_path"]):
            e = json.loads(line)
            if e.get("piece") != pid:
                continue
            for a in e.get("attempts", []):
                if a.get("candidate_sha") and \
                        item["candidate_sha256"].startswith(a["candidate_sha"]):
                    prov[pid] = {"attempt_action": a.get("action"),
                                 "attempt_seed": a.get("seed"),
                                 "generated_tokens": a.get("tokens")}

    entries = []
    for r in rows:
        pid = r["piece"]
        src, fam = FAMILY[pid]
        q = queue[pid]
        entries.append({
            "piece": pid,
            "kind": r["kind"],
            "task_family": fam,
            "spec_source": src,
            "status": r["status"],
            "provenance": {
                "generation_path": q["generation_path"],
                "ledger_path": q["ledger_path"],
                "candidate_sha256": r["candidate_sha256"],
                "prompt_sha256": q["prompt_sha256"],
                "model_checkpoint": "Qwen/Qwen2.5-Coder-0.5B",
                "model_sha256":
                    "aff8914ec707fcaf9e2d4dc97197cded50b1c63e1d3a7a82e56f54d83ea47f80",
                "origin": "model-generated (in-loop accepted; teacher bytes "
                          "never enter generation dirs; challenge pieces "
                          "confirmed model-origin by 037 attribution.json)",
                **prov.get(pid, {}),
            },
            "verification_layers": r["verification"],
            "normalized_structure": (r.get("fingerprint") or "")[:16],
            "normalized_duplicate_of": r.get("normalized_duplicate_of"),
        })

    fam_counts = Counter(e["task_family"] for e in entries)
    struct_ids = {e["normalized_structure"] for e in entries}
    verified = [e for e in entries
                if e["status"].startswith("INDEPENDENTLY_VERIFIED")]
    manifest = {
        "session": "SESSION038A",
        "phase": "1 — independent replay",
        "counts": {
            "queue": len(entries),
            "independently_verified": len(verified),
            "quarantined": len(entries) - len(verified),
            "distinct_normalized_structures": len(struct_ids),
            "unique_after_family_dedup": len(
                {e["task_family"] for e in verified}),
        },
        "family_counts": dict(sorted(fam_counts.items())),
        "training_eligible": 0,
        "graduation_rule": "QUARANTINED -> ELIGIBLE requires: (a) this "
                           "manifest's verification layers all pass (done "
                           "here), (b) explicit user authorization of a "
                           "training branch, (c) final license/contamination "
                           "review. This session performs (a) only.",
        "no_credentials": "manifest contains hashes and repo-relative "
                          "paths only; no secrets, no raw prompts, no raw "
                          "candidates",
        "entries": entries,
    }
    (OUT / "training-candidates.json").write_text(
        json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=1))
    print("family_counts:", dict(sorted(fam_counts.items())))


if __name__ == "__main__":
    build()
