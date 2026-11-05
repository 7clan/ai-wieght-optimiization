"""Pure protocol checks; model-generated code is never run on the host."""
import json
import unittest
from pathlib import Path

from tinycoder.session031_contract import (DEMO_PROJECTS, ENDPOINTS, FIELDS,
                                           GOALS, NAME, PREFIX, PUBLIC, ROLES,
                                           fingerprint, holdout, prompt)
from tinycoder.session031 import ROLE_CHECKS, metric, total_score
from tinycoder.collect_session031 import (attempt_origin, js_literal,
                                          live_app_page, verify_vendored_runtime)


class DevMetricsContractTests(unittest.TestCase):
    def test_new_task_shape(self):
        self.assertEqual(NAME, "DevMetrics")
        self.assertEqual(ROLES, ("logic", "store", "api", "ui", "css"))
        self.assertEqual(len(PUBLIC), 3)
        self.assertEqual(len(holdout()), 3)
        self.assertFalse(any(x in holdout() for x in PUBLIC))
        self.assertEqual(len(fingerprint()), 64)
        for role in ROLES:
            self.assertTrue(GOALS[role])
            self.assertTrue(prompt(role).endswith(PREFIX[role]))

    def test_schema_anchor_and_offline_demo_contract(self):
        head = prompt("ui")
        for field in FIELDS:
            self.assertIn(field, head)
        for endpoint in ENDPOINTS:
            self.assertIn(endpoint, prompt("api"))
        for project in DEMO_PROJECTS:
            self.assertIn(project, GOALS["ui"])
        self.assertIn("295", GOALS["ui"])
        self.assertIn("offline", GOALS["ui"].lower())

    def test_prompts_contain_no_teacher_material(self):
        source = Path("tinycoder/session031.py").read_text(encoding="utf8")
        self.assertNotIn("session029", source)
        self.assertNotIn("session028", source)
        self.assertNotIn("PocketLedger", prompt("ui") + prompt("api") + prompt("store"))
        guided = prompt("store", error="TypeError: s.list is not a function",
                        previous="return {list(){}};\n}")
        self.assertIn("PUBLIC CHECK FEEDBACK:", guided)
        self.assertIn("YOUR PREVIOUS ATTEMPT", guided)
        self.assertTrue(guided.endswith(PREFIX["store"]))
        own = prompt("api", own_example="app.get('/api/items', (req, res) => {});")
        self.assertIn("YOUR OWN PREVIOUSLY VERIFIED WORKING CODE", own)
        self.assertIn("never its old names", own)
        # Self-memory examples must be model bytes, never teacher constants.
        self.assertNotIn("PocketLedger", own)

    def test_metric_ordering(self):
        def result(role_ok, checks, syntax=True, integrated=None):
            return {"modules": {r: {"passed": role_ok and r == "api",
                                    "syntax_valid": syntax} for r in ROLES},
                    "checks": checks, "completed_checks": 0,
                    "integrated": role_ok if integrated is None else integrated}
        self.assertGreater(metric(result(True, {"get": True}), "api"),
                           metric(result(True, {}), "api"))
        self.assertGreater(metric(result(True, {}), "api"),
                           metric(result(False, {"get": True}), "api"))
        self.assertEqual(ROLE_CHECKS["api"],
                         ("health", "get", "post", "post_invalid", "delete",
                          "projects", "summary"))
        self.assertGreater(total_score(result(True, {}, True))[0:1],
                           total_score(result(False, {}, True))[0:1])

    def test_vendored_runtime_is_pinned(self):
        verify_vendored_runtime()


class GallerySafetyTests(unittest.TestCase):
    def test_js_literal_never_contains_raw_tag_open(self):
        hostile = "</script><script>alert(1)</script>\n\u2028line"
        literal = js_literal(hostile)
        self.assertNotIn("<", literal)
        self.assertEqual(json.loads(literal), hostile)
        self.assertEqual(json.loads(js_literal("a<b")), "a<b")

    def test_live_page_with_uncompilable_ui_shows_raw_bytes(self):
        modules = {"ui": "const React = require('react');\nfunction App() {\n  return <h1>broken",
                   "css": "body {\n  background: #0d1527;\n}",
                   "logic": "x", "store": "x", "api": "x"}
        page = live_app_page(1, modules, None)
        start = page.index("var APP_SRC=") + len("var APP_SRC=")
        end = page.index(";\n", start)
        # Raw uncompiled model bytes are deployed; the runtime error banner
        # reports the syntax failure honestly.
        self.assertEqual(json.loads(page[start:end]), modules["ui"])

    def test_live_page_embeds_model_source_verbatim_and_no_teacher_code(self):
        modules = {"ui": "const React = require('react');\nfunction App() {\n"
                         "  return <h1>DevMetrics</h1>;\n}\nmodule.exports = App;\n",
                   "css": "body {\n  background: #0d1527;\n}\n",
                   "logic": "x", "store": "x", "api": "x"}
        compiled = ('"use strict";\nconst React = require("react");\n'
                    'function App() {\n  return /*#__PURE__*/React.createElement("h1", null, "DevMetrics");\n}\n'
                    'module.exports = App;\n')
        page = live_app_page(3, modules, compiled)
        self.assertIn("round 3", page)
        self.assertNotIn("__ROUND__", page)
        self.assertIn("docs/vendor", page)  # disclosure comment only
        self.assertIn("esbuild 0.25.9", page)
        # Embedded sources decode byte-identically.
        start = page.index("var APP_SRC=") + len("var APP_SRC=")
        end = page.index(";\n", start)
        self.assertEqual(json.loads(page[start:end]), compiled)
        start = page.index("var CSS_SRC=") + len("var CSS_SRC=")
        end = page.index(";\n", start)
        self.assertEqual(json.loads(page[start:end]), modules["css"])
        # The raw JSX (with '<') never appears uncompiled in a script context.
        self.assertNotIn("<h1>", page)

    def test_attempt_origin_rejects_foreign_source(self):
        pred = {"selected": {"ui": "const React = require('react');\nX"},
                "attempts": [{"role": "ui", "stage": "baseline", "round": 0,
                              "raw": "Y"}],
                "source_sha256": {}}
        with self.assertRaises(ValueError):
            attempt_origin(pred, "ui")


if __name__ == "__main__":
    unittest.main()
