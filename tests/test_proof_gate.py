"""Attestation metadata checks; generated code is never executed."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from archagent.finetune.proof_gate import check_proof, evaluate_queue


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ProofGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        root = self.repo / "experiments" / "z037-generalization" / "tracks" / "D" / "gen"
        root.mkdir(parents=True)
        self.source = root / "sample.json"
        self.source.write_text(json.dumps({"prompt": "Create model A", "candidate": "model A { id String @id }"}), encoding="utf-8")
        self.spec = self.repo / "spec.json"
        self.spec.write_text('{"example": true}', encoding="utf-8")
        self.report = self.repo / "test-report.json"
        self.report.write_text(json.dumps({"exit_code": 0, "checks": [
            {"name": "schema_validate", "passed": True},
            {"name": "database_behavior", "passed": True},
        ]}), encoding="utf-8")
        p = json.loads(self.source.read_text())
        self.item = {
            "generation_path": self.source.relative_to(self.repo).as_posix(),
            "candidate_sha256": _sha(p["candidate"].encode()),
            "prompt_sha256": _sha(p["prompt"].encode()),
            "kind": "prisma-model",
        }
        self.proof = {
            **{k: self.item[k] for k in ("generation_path", "candidate_sha256", "prompt_sha256")},
            "provenance": "QWEN_GENERATED_UNMODIFIED",
            "teacher_written_bytes": 0,
            "candidate_edited_after_generation": False,
            "test_fixture_modified_after_generation": False,
            "sandbox": {"runtime": "docker", "network": "none", "read_only": True, "unprivileged": True,
                        "no_new_privileges": True, "memory_mb": 512, "cpus": 1},
            "task_spec": {"path": self.spec.relative_to(self.repo).as_posix(), "sha256": _sha(self.spec.read_bytes())},
            "test_report": {"path": self.report.relative_to(self.repo).as_posix(), "sha256": _sha(self.report.read_bytes())},
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_consistent_attestation_still_needs_review(self):
        self.assertEqual(check_proof(self.repo, self.item, self.proof), [])
        proof_dir = self.repo / "proofs"
        proof_dir.mkdir()
        (proof_dir / f"{self.item['candidate_sha256']}.json").write_text(json.dumps(self.proof), encoding="utf-8")
        queue = self.repo / "queue.jsonl"
        queue.write_text(json.dumps(self.item) + "\n", encoding="utf-8")
        result = evaluate_queue(self.repo, queue, proof_dir)
        self.assertEqual(result["counts"]["CONSISTENT_ATTESTATION_NEEDS_REVIEW"], 1)
        self.assertFalse(result["records"][0]["training_eligible"])

    def test_rejects_forged_hash(self):
        self.proof["candidate_sha256"] = "0" * 64
        self.assertIn("candidate_hash_mismatch", check_proof(self.repo, self.item, self.proof))

    def test_rejects_no_isolation(self):
        self.proof["sandbox"]["network"] = "host"
        self.assertIn("isolation_requirements_not_attested", check_proof(self.repo, self.item, self.proof))

    def test_rejects_missing_behavior(self):
        self.report.write_text(json.dumps({"exit_code": 0, "checks": [
            {"name": "schema_validate", "passed": True},
        ]}), encoding="utf-8")
        self.proof["test_report"]["sha256"] = _sha(self.report.read_bytes())
        self.assertIn("test_report_incomplete_or_failed", check_proof(self.repo, self.item, self.proof))

    def test_no_path_traversal(self):
        self.proof["test_report"]["path"] = "../outside.json"
        self.assertIn("test_report_hash_mismatch", check_proof(self.repo, self.item, self.proof))

    def test_rejects_malformed_proof_object(self):
        proof_dir = self.repo / "proofs"
        proof_dir.mkdir()
        (proof_dir / f"{self.item['candidate_sha256']}.json").write_text("[]", encoding="utf-8")
        queue = self.repo / "queue.jsonl"
        queue.write_text(json.dumps(self.item) + "\n", encoding="utf-8")
        result = evaluate_queue(self.repo, queue, proof_dir)
        self.assertEqual(result["records"][0]["status"], "QUARANTINED")

    def test_rejects_non_sha_queue_token_without_file_lookup(self):
        self.item["candidate_sha256"] = "../../outside"
        queue = self.repo / "queue.jsonl"
        queue.write_text(json.dumps(self.item) + "\n", encoding="utf-8")
        result = evaluate_queue(self.repo, queue, self.repo / "proofs")
        self.assertEqual(result["records"][0]["reasons"], ["invalid_candidate_hash"])


if __name__ == "__main__":
    unittest.main()
