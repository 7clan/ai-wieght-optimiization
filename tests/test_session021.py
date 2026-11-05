"""Offline protocol tests: no untrusted generated code executed on host."""
import unittest

from tinycoder.session021_contract import PUBLIC, ROLES, holdout, prompt, spec_hash
from tinycoder.session021 import ranking, repair_prompt
from tinycoder.session019_previews import sanitize_markup


class Session021ProtocolTests(unittest.TestCase):
    def test_modules_have_explicit_signatures(self):
        self.assertIn('def transform(payload):', prompt('logic'))
        self.assertIn('function createApp(store, processor) {', prompt('api'))
        self.assertIn('function App() {', prompt('ui'))
        self.assertIn('body {', prompt('css'))
        self.assertEqual(set(ROLES),{'logic','api','ui','css'})

    def test_public_and_holdout_examples_are_disjoint(self):
        self.assertEqual(len(PUBLIC),3)
        self.assertEqual(len(holdout()),3)
        self.assertTrue(all(x not in holdout() for x in PUBLIC))
        self.assertEqual(len(spec_hash()),64)

    def test_repair_does_not_insert_uncommented_previous_code(self):
        for role in ROLES:
            p=repair_prompt(role,'danger();\nimport something','Missing route')
            self.assertIn('Missing route',p)
            self.assertIn(prompt(role),p)

    def test_ranking_is_metric_based(self):
        bad={'integrated':False,'completed_checks':0,
             'modules':{r:{'passed':False,'syntax_valid':False} for r in ROLES}}
        better={'integrated':False,'completed_checks':2,
                'modules':{r:{'passed':r=='logic','syntax_valid':True} for r in ROLES}}
        self.assertGreater(ranking(better),ranking(bad))

    def test_preview_sanitizer_strips_script_handlers(self):
        cleaned=sanitize_markup('<div onclick="alert(1)"><script>bad()</script><h1>Task board</h1></div>')
        self.assertNotIn('onclick',cleaned)
        self.assertNotIn('script',cleaned)
        self.assertIn('Task board',cleaned)


if __name__=='__main__':
    unittest.main()
