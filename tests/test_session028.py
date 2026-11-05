"""Test protocol without executing any generated source outside Docker."""
import unittest

from tinycoder.session027_contract import PUBLIC, ROLES
from tinycoder.session028_contract import LESSONS, PREFIX, ROLE_GOAL, fresh_holdout, prompt
from tinycoder.session028 import score


class MentorProtocolTests(unittest.TestCase):
    def test_unseen_holdout(self):
        self.assertEqual(len(fresh_holdout()),3)
        self.assertNotEqual(fresh_holdout(),PUBLIC)
        self.assertEqual(sum(x["expected"]["total_cents"] for x in fresh_holdout()),500)

    def test_analogy_is_not_target_solution(self):
        for role in ("logic","store","api","ui"):
            self.assertIn("TEACHER'S WORKED EXAMPLE",LESSONS[role])
            self.assertNotIn("function createApp(store, processor)",LESSONS[role])
            self.assertNotIn("function createStore(filePath)",LESSONS[role])
            self.assertNotIn("def transform(payload)",LESSONS[role])
            self.assertNotIn("function App()",LESSONS[role])
            self.assertTrue(prompt(role,"example public error",0).endswith(PREFIX[role]))
            self.assertIn("LAST STUDENT ERROR: example public error",prompt(role,"example public error",2))
        self.assertEqual(set(ROLE_GOAL),set(ROLES)-{"css"})

    def test_role_specific_progress(self):
        def state(passed,checks,syntax=True):
            return {"modules":{"api":{"passed":passed,"syntax_valid":syntax}},
                    "checks":checks}
        self.assertGreater(score(state(True,{}),"api"),score(state(False,{"get":True}),"api"))
        self.assertGreater(score(state(False,{"get":True}),"api"),score(state(False,{}),"api"))


if __name__=="__main__":
    unittest.main()
