"""Test lineage and quarantine behavior without executing generated code."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from archagent.finetune.candidate_queue import build_queue, matches_attempt


class CandidateQueueTests(unittest.TestCase):
    def test_hash_and_piece_must_both_match(self):
        candidate = "model Example { id String @id }"
        sha = hashlib.sha256(candidate.encode()).hexdigest()[:12]
        record = {"piece": "pieceA", "seed": 44, "candidate": candidate, "prompt": "make a model"}
        attempt = {"seed": 44, "candidate_sha": sha}
        self.assertTrue(matches_attempt(record, "pieceA", attempt))
        self.assertFalse(matches_attempt(record, "pieceB", attempt))
        self.assertFalse(matches_attempt(record, "pieceA", {"seed": 44, "candidate_sha": "bad"}))

    def test_only_traceable_gate_accepts_are_queued(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "AGENTS.md").write_text("No training", encoding="utf-8")
            folder = repo / "experiments" / "z037-generalization" / "tracks" / "D"
            (folder / "gen").mkdir(parents=True)
            code = "model A { id String @id }"
            record = {"piece": "a", "seed": 10, "candidate": code, "prompt": "make model"}
            (folder / "gen" / "a-10.json").write_text(json.dumps(record), encoding="utf-8")
            row = {"piece": "a", "kind": "prisma-model", "attempts": [{
                "outcome": "accept", "seed": 10,
                "candidate_sha": hashlib.sha256(code.encode()).hexdigest()[:12],
                "gate": {"pass": True}, "probe": None,
            }]}
            (folder / "ledger.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
            queue, stats = build_queue(repo)
            self.assertEqual(len(queue), 1)
            self.assertEqual(stats["queued_for_independent_replay"], 1)
            self.assertFalse(queue[0]["training_eligible"])
            self.assertFalse(queue[0]["independent_behavior_verified"])
            self.assertNotIn(code, json.dumps(queue))

    def test_contaminated_run_is_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "AGENTS.md").write_text("No training", encoding="utf-8")
            folder = repo / "experiments" / "z037-generalization" / "tracks" / "D-run1-contaminated"
            (folder / "gen").mkdir(parents=True)
            (folder / "ledger.jsonl").write_text("{}\n", encoding="utf-8")
            queue, stats = build_queue(repo)
            self.assertEqual(queue, [])
            self.assertEqual(stats["contaminated_ledgers_skipped"], 1)


if __name__ == "__main__":
    unittest.main()
