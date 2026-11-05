"""Pure protocol checks; model-generated code is never run on the host."""
import unittest

from tinycoder.session030_contract import NAME, ROLES, PUBLIC, GOALS, PREFIX, fingerprint, holdout, prompt
from tinycoder.session030 import metric
from tinycoder.session029_teacher import STORE


class TransferCurriculumTests(unittest.TestCase):
    def test_new_task_independent_data(self):
        self.assertEqual(NAME,"ShelfStock")
        self.assertEqual(ROLES,("logic","store","api","ui","css"))
        self.assertIn("/api/items",GOALS["api"])
        self.assertNotIn("PocketLedger",prompt("api"))
        self.assertEqual(len(PUBLIC),3)
        self.assertEqual(len(holdout()),3)
        self.assertFalse(any(x in holdout() for x in PUBLIC))
        self.assertEqual(len(fingerprint()),64)

    def test_teaching_is_other_domain_code(self):
        guided=prompt("store",teacher=STORE,error="public failure")
        self.assertIn("PocketLedger",guided) if "PocketLedger" in STORE else self.assertIn("amount_cents",guided)
        self.assertIn("PUBLIC CHECK FEEDBACK: public failure",guided)
        self.assertIn("SHELFSTOCK",guided)
        self.assertTrue(guided.endswith(PREFIX["store"]))
        self.assertNotIn("/api/items",STORE)

    def test_progress_ranking(self):
        def r(ok,checks,syntax=True):
            return {"modules":{"api":{"passed":ok,"syntax_valid":syntax}},"checks":checks}
        self.assertGreater(metric(r(True,{}),"api"),metric(r(False,{"get":True}),"api"))
        self.assertGreater(metric(r(False,{"get":True}),"api"),metric(r(False,{}),"api"))


if __name__=="__main__":
    unittest.main()
