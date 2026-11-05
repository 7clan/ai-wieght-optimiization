import copy
import json
import tempfile
import unittest
from pathlib import Path

from tinycoder.mentor_patterns import assemble_student_prompt, load_bank, retrieve_patterns


class TestMentorPatterns(unittest.TestCase):
    def setUp(self):
        self.bank = load_bank()

    def test_delete_transfer_prompts_interface_check(self):
        found = retrieve_patterns(
            "Express DELETE route calls a store method and returns JSON", domain="express", bank=self.bank
        )
        self.assertEqual(found[0]["id"], "copy-structure-not-api-names")
        prompt = assemble_student_prompt(
            "Build Express DELETE /api/notes from supplied store interface",
            domain="express",
            bank=self.bank,
        )
        self.assertIn("exact method name", prompt)
        self.assertIn("CURRENT TASK:", prompt)
        self.assertNotIn("res.json({deleted:store.delete(req.params.id)})", prompt)

    def test_response_contract_retrieval(self):
        found = retrieve_patterns("Express GET API res.json response envelope", domain="express", bank=self.bank)
        self.assertEqual(found[0]["id"], "express-response-shape")

    def test_domain_separation(self):
        self.assertEqual(retrieve_patterns("Express DELETE store API",domain="python",bank=self.bank),[])

    def test_malformed_bank_and_private_provenance_rejected(self):
        invalid=copy.deepcopy(self.bank)
        invalid["patterns"][0]["source"]="hidden_holdout"
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/"bad.json"
            dest.write_text(json.dumps(invalid),encoding="utf-8")
            with self.assertRaises(ValueError):
                load_bank(dest)

    def test_no_training_can_be_claimed(self):
        invalid=copy.deepcopy(self.bank)
        invalid["training_steps"]=1
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/"bad.json"
            dest.write_text(json.dumps(invalid),encoding="utf-8")
            with self.assertRaises(ValueError):
                load_bank(dest)


if __name__ == "__main__":
    unittest.main()
