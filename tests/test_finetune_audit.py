"""Unit tests for the conservative, text-free training-readiness audit."""

import json
from pathlib import Path
import tempfile
import unittest

from archagent.finetune.audit_archives import audit, check_record, digest


class AuditTests(unittest.TestCase):
    def test_digest_deterministic(self):
        self.assertEqual(digest("hello"), digest("hello"))
        self.assertNotEqual(digest("hello"), digest("world"))

    def test_missing_records_not_accepted(self):
        self.assertIsNone(check_record({"prompt": "p"}))
        self.assertIsNone(check_record(["p", "c"]))

    def test_honest_gate_markers(self):
        rec = check_record({"prompt": "make a function", "candidate": "function f() {}", "gate": {"pass": True}})
        self.assertIsNotNone(rec)
        self.assertTrue(rec["archive_gate_pass"])

    def test_bad_candidate_and_secret_never_output_raw_values(self):
        secret = "github_pat_" + "x" * 30
        rec = check_record({"prompt": secret, "candidate": "// TODO later\n"})
        self.assertTrue(rec["potential_secret"])
        self.assertTrue(rec["placeholder_or_echo"])
        self.assertNotIn(secret, json.dumps(rec))

    def test_repo_scan_counts_and_quarantines_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            (repo / "AGENTS.md").write_text("No training", encoding="utf-8")
            folder = repo / "experiments" / "z037-generalization" / "tracks" / "A" / "gen"
            folder.mkdir(parents=True)
            for name in ("a.json", "b.json"):
                (folder / name).write_text(json.dumps({"prompt": "Do X", "candidate": "pass", "gate": {"pass": True}}), encoding="utf-8")
            result = audit(repo)
            self.assertEqual(result["archive_audit"]["valid_generation_records"], 2)
            self.assertEqual(result["archive_audit"]["repeated_candidate_records"], 1)
            self.assertEqual(result["training_examples_approved"], 0)
            self.assertEqual(result["families"]["session037/tracks"]["records"], 2)


if __name__ == "__main__":
    unittest.main()
