"""No unsandboxed execution of model code in these protocol tests."""
import unittest

from tinycoder.session029_teacher import STORE, API, UI, REASONING_RULES
from tinycoder.collect_session029 import PKG


class TeacherCorrectionTests(unittest.TestCase):
    def test_store_corrected_patterns(self):
        self.assertIn("!fs.existsSync(filePath)",STORE)
        self.assertIn("fs.writeFileSync",STORE)
        self.assertIn("delete(id)",STORE)

    def test_api_contract_wiring(self):
        self.assertIn("return app;",API)
        self.assertIn("express.json()",API)
        self.assertIn("processor({expenses: store.list()})",API)
        self.assertIn("status(201)",API)

    def test_react_interactions(self):
        self.assertIn("React.useEffect",UI)
        self.assertIn("onSubmit={addExpense}",UI)
        self.assertIn("onClick={() => deleteExpense",UI)
        self.assertIn("'/api/summary'",UI)

    def test_attribution(self):
        self.assertEqual(set(REASONING_RULES),{"logic","store","api","ui"})
        self.assertEqual(PKG["name"],"pocketledger-qwen-mentored")


if __name__=="__main__":
    unittest.main()
