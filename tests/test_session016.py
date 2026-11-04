"""Contract checks without executing generated programs outside Docker."""
import unittest
from unittest.mock import patch
import subprocess
from tinycoder.session016 import (alternate_web_tests, best, candidate_priority,
                                  make_repair_prompt, _isolated_web_one, TRACKS)
from tinycoder.session014_fixtures import make_web_tasks


class SearchContracts(unittest.TestCase):
    def test_public_web_probes_are_separate_instances(self):
        web=make_web_tasks(offset=25)
        self.assertEqual(len(web),50)
        for task in web:
            smoke=alternate_web_tests(task)
            self.assertTrue(smoke)
            self.assertIn("contains",smoke[0]) if task["mode"]=="ui" else self.assertIn("expected",smoke[0])
            self.assertIsNot(smoke,task["tests"])

    def test_public_result_wins_before_syntactic_only(self):
        a={"completion":"pass","public_result":{
            "passed":False,"syntax_valid":True,"failure_bin":"assertion_error"}}
        b={"completion":"return 1","public_result":{
            "passed":True,"syntax_valid":True,"failure_bin":"passed"}}
        self.assertIs(best([a,b]),b)
        self.assertGreater(candidate_priority(b),candidate_priority(a))

    def test_repair_uses_same_original_prompt(self):
        task={"task_id":"Mbpp/1","prompt":"def foo(x):\n"}
        p=make_repair_prompt(task,"    return 0",{"error":"AssertionError"})
        self.assertTrue(p.endswith(task["prompt"]))
        self.assertIn("AssertionError",p)

    def test_fixed_tracks(self):
        self.assertEqual(TRACKS,("search2","search4"))

    def test_nonterminating_js_is_classified_without_aborting(self):
        task=make_web_tasks(offset=25)[0]
        with patch("tinycoder.session016.subprocess.run",
                   side_effect=[subprocess.TimeoutExpired(cmd=["docker"],timeout=18),
                                subprocess.CompletedProcess(args=["docker"],returncode=0)]):
            outcome=_isolated_web_one(task,"while(true){}")
        self.assertFalse(outcome["passed"])
        self.assertEqual(outcome["failure_bin"],"unclassified_logic_gap")
        self.assertIn("timeout",outcome["error"])


if __name__=="__main__":
    unittest.main()
