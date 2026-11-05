"""No inference or model-generated execution on host."""
import unittest

from tinycoder.session030_contract import PREFIX, ROLES
from tinycoder.session031 import CONTRACTS, lesson_prompt


class ContractTeachingTests(unittest.TestCase):
    def test_explicit_new_domain_mapping(self):
        for role in ROLES:
            prompt = lesson_prompt(role, "Failed public check")
            self.assertTrue(prompt.endswith(PREFIX[role]))
            self.assertIn("Failed public check", prompt)
            self.assertIn("ShelfStock", prompt)
        self.assertIn("total_units", CONTRACTS["logic"])
        self.assertIn("list()", CONTRACTS["store"])
        self.assertIn("/api/items", CONTRACTS["ui"])
        self.assertIn("PocketLedger", CONTRACTS["ui"])

    def test_no_teacher_target_source(self):
        for role in ROLES:
            prompt = lesson_prompt(role, "TypeError: missing function")
            self.assertNotIn("function createStore(filePath) {\n  function read", prompt)
            self.assertNotIn("const [expenses, setExpenses]", prompt)

    def test_invalid_role(self):
        with self.assertRaises(ValueError):
            lesson_prompt("unknown", "error")


if __name__ == "__main__":
    unittest.main()
