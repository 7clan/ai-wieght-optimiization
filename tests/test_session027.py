"""Offline new-app protocol tests; model code never runs on host."""
import unittest

from tinycoder.session027_contract import ROLES, SPEC, PUBLIC, holdout, prefix, fingerprint
from tinycoder.session027 import metric, feedback_prompt


class NewAppProtocolTests(unittest.TestCase):
    def test_fresh_contract(self):
        self.assertEqual(ROLES,('logic','store','api','ui','css'))
        self.assertIn('PocketLedger',SPEC)
        self.assertIn('amount_cents',SPEC)
        self.assertNotIn('mark them complete',SPEC)
        self.assertEqual(len(PUBLIC),3)
        self.assertEqual(len(holdout()),3)
        self.assertFalse(any(p in holdout() for p in PUBLIC))
        self.assertEqual(len(fingerprint()),64)

    def test_five_minimal_signatures(self):
        self.assertIn('def transform(payload):',prefix('logic'))
        self.assertIn('function createStore(filePath) {',prefix('store'))
        self.assertIn('function createApp(store, processor) {',prefix('api'))
        self.assertIn('function App() {',prefix('ui'))
        self.assertIn('body {',prefix('css'))

    def test_teacher_rules_are_abstract_and_non_target(self):
        baseline=prefix('api')
        with_memory=prefix('api',mentor=True)
        self.assertIn('response envelopes',with_memory)
        self.assertIn('Transfer',with_memory)
        self.assertNotEqual(baseline,with_memory)
        repair=feedback_prompt('api','res.json({oops:true})','Wrong response shape')
        self.assertIn('Wrong response shape',repair)
        self.assertIn('// res.json({oops:true})',repair)
        self.assertIn('function createApp(store, processor)',repair)

    def test_public_module_rank(self):
        def state(pass_,syntax,n):
            return {'modules':{'api':{'passed':pass_,'syntax_valid':syntax}},'completed_checks':n}
        self.assertGreater(metric(state(True,True,1),'api'),metric(state(False,True,10),'api'))
        self.assertGreater(metric(state(False,True,1),'api'),metric(state(False,False,10),'api'))


if __name__=='__main__':
    unittest.main()
