"""Pure protocol checks; model-generated code is never run on the host."""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from tinycoder import session032
from tinycoder.session031 import ROLE_CHECKS, metric, total_score
from tinycoder.session031_contract import (NAME, PREFIX, ROLES, fingerprint,
                                           holdout, prompt)
from tinycoder.collect_session032 import (attempt_origin, js_literal,
                                          live_app_page, update_readme_results,
                                          verify_vendored_runtime)
from tinycoder.session032 import (rebuild, splice, strip_comment_echo,
                                  trim_fill, verify_lineage)

PUBLISHED_STATE = Path("experiments/session032_selfrepair_state.json")


def _whole(role, stage, raw, accepted, source, round_=0):
    return {"role": role, "stage": stage, "raw": raw, "fills": None,
            "accepted": accepted, "candidate_source": source, "round": round_,
            "origin": {"type": "whole", "base": None}}


def _lineage_state():
    """Synthetic lineage: greedy baseline plus one accepted compound FIM
    splice of the model's own bytes. Every recorded byte is synthetic model
    output for protocol purposes; nothing here runs model code."""
    raw = "    return {}\n"
    base = PREFIX["logic"] + raw
    attempts = [_whole("logic", "baseline", raw, True, base)]
    for role in ROLES:
        if role != "logic":
            attempts.append(_whole(role, "baseline", "x", True, PREFIX[role] + "x"))
    ops, fills, current = [], [], base
    for (lo, hi), fill in [((2, 2), "    total = 0\n"),
                           ((2, 2), '    return {"total_minutes": total}\n')]:
        ops.append({"lo": lo, "hi": hi,
                    "base_sha256": hashlib.sha256(current.encode()).hexdigest()})
        fills.append(fill)
        current = splice(current, lo, hi, fill)
    attempts.append({"role": "logic", "stage": "fim-compound", "raw": fills[0],
                     "fills": fills, "accepted": True, "round": 1,
                     "candidate_source": current,
                     "origin": {"type": "fim", "base": 0, "ops": ops}})
    others = {r: PREFIX[r] + "x" for r in ROLES if r != "logic"}
    state = {"attempts": attempts,
             "selected": {"logic": current, **others},
             "baseline": {"logic": base, **others}}
    return state, current


class FrozenContractTests(unittest.TestCase):
    def test_reuses_frozen_session031_contract_unchanged(self):
        self.assertEqual(NAME, "DevMetrics")
        self.assertIs(session032.prompt, prompt)  # identical prompt builder
        for role in ROLES:
            self.assertTrue(prompt(role).endswith(PREFIX[role]))
        self.assertEqual(len(fingerprint()), 64)
        # Session032 reuses the frozen public cases; holdout stays disjoint.
        self.assertTrue(all(case not in holdout() for case in session032.PUBLIC))

    def test_prompts_contain_no_teacher_material(self):
        for role in ROLES:
            self.assertNotIn("PocketLedger", prompt(role))
        instructions = session032.fim_instructions(
            "ui", (2, 4, "function handleDelete(id) {"))
        self.assertTrue(instructions)
        for banned in ("PocketLedger", "session028", "session029", "teacher"):
            self.assertNotIn(banned, instructions)
        source = Path("tinycoder/session032.py").read_text(encoding="utf8")
        for banned in ("session028", "session029", "PocketLedger"):
            self.assertNotIn(banned, source)

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


class FIMHelperTests(unittest.TestCase):
    def test_splice_is_pure_line_surgery(self):
        module = "a\nb\nc\nd\n"
        self.assertEqual(splice(module, 2, 3, "X\n"), "a\nX\nd\n")
        self.assertEqual(splice(module, 1, 1, "X\n"), "X\nb\nc\nd\n")
        self.assertEqual(splice(module, 4, 4, "X"), "a\nb\nc\nX")
        # no fill bytes are invented by the harness: only the fill is inserted
        self.assertIn("X", splice(module, 2, 2, "X\n"))

    def test_trim_fill_cuts_duplicated_own_suffix(self):
        suffix = "const next = 1;\nconst after = 2;\nconst last = 3;\n"
        marker = "\n".join([l for l in suffix.splitlines() if l.strip()][:3])
        overrunning = "function fixed() {}\n" + marker + "\nconst echoed = 9;\n"
        self.assertEqual(trim_fill(overrunning, suffix),
                         "function fixed() {}\n")
        short = "function fixed() {}\n"
        self.assertEqual(trim_fill(short, suffix), short)

    def test_strip_comment_echo_trims_instruction_echo_only(self):
        echo = ("// FIX: rewrite the handler\n// second line\n// third\n"
                "function a() {}\n")
        self.assertEqual(strip_comment_echo(echo, "ui"),
                         "function a() {}")
        py_echo = "# fix return\n# second\n# third\nx = 1\n"
        self.assertEqual(strip_comment_echo(py_echo, "logic"), "x = 1")
        # two comment lines followed by code is not an instruction echo
        mixed = "// note\n// note2\nfunction a() {}\n"
        self.assertEqual(strip_comment_echo(mixed, "ui"), mixed)
        plain = "function a() {}\n"
        self.assertEqual(strip_comment_echo(plain, "ui"), plain)
        css = "/* comment */\nbody { margin: 0; }\n"
        self.assertEqual(strip_comment_echo(css, "css"), css)
    def test_syntax_and_requires_gates_reject_only(self):
        # Python gate: parse only; JS gate: pinned esbuild transform.
        self.assertTrue(session032.syntax_ok("x = 1\n", "logic"))
        self.assertFalse(session032.syntax_ok("def broken(:\n", "logic"))
        self.assertTrue(session032.requires_ok(
            "const fs = require('node:fs');\nconst express = require('express');\n"))
        self.assertFalse(session032.requires_ok("const os = require('node:os');\n"))


class LineageReplayTests(unittest.TestCase):
    def test_compound_acceptance_replays_byte_exact(self):
        state, current = _lineage_state()
        verify_lineage(state)
        self.assertEqual(rebuild(state["attempts"], 5, "logic"), current)

    def test_tampered_fill_is_rejected(self):
        state, _ = _lineage_state()
        state["attempts"][5]["fills"] = ["    return 42\n",
                                         state["attempts"][5]["fills"][1]]
        with self.assertRaises(ValueError):
            verify_lineage(state)

    def test_tampered_op_hash_is_rejected(self):
        state, _ = _lineage_state()
        state["attempts"][5]["origin"]["ops"][0]["base_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            verify_lineage(state)

    def test_foreign_selected_module_is_rejected(self):
        state, current = _lineage_state()
        state["selected"]["logic"] = current + "// foreign\n"
        with self.assertRaises(ValueError):
            verify_lineage(state)

    def test_unrecorded_lineage_is_rejected(self):
        state, _ = _lineage_state()
        del state["attempts"][5]["origin"]["ops"]
        with self.assertRaises(ValueError):
            verify_lineage(state)


class CollectorSafetyTests(unittest.TestCase):
    def test_attempt_origin_rejects_foreign_source(self):
        state, current = _lineage_state()
        pred = {"selected": state["selected"], "greedy": state["baseline"],
                "attempts": state["attempts"], "source_sha256": {}}
        pred["selected"]["logic"] = current + "// foreign\n"
        with self.assertRaises(ValueError):
            attempt_origin(pred, "logic")

    def test_attempt_origin_reports_the_fim_splice(self):
        state, current = _lineage_state()
        pred = {"selected": state["selected"], "greedy": state["baseline"],
                "attempts": state["attempts"], "source_sha256": {}}
        origin = attempt_origin(pred, "logic")
        self.assertEqual(origin["attempt_index"], 5)
        self.assertEqual(origin["stage"], "fim-compound")
        self.assertEqual(origin["origin_type"], "fim")

    def test_js_literal_never_contains_raw_tag_open(self):
        hostile = "</script><script>alert(1)</script>\n\u2028line"
        literal = js_literal(hostile)
        self.assertNotIn("<", literal)
        self.assertEqual(json.loads(literal), hostile)

    def test_live_page_with_uncompilable_ui_shows_raw_bytes(self):
        modules = {"ui": "const React = require('react');\nfunction App() {\n  return <h1>broken",
                   "css": "body {}", "logic": "x", "store": "x", "api": "x"}
        page = live_app_page(2, modules, None)
        start = page.index("var APP_SRC=") + len("var APP_SRC=")
        end = page.index(";\n", start)
        self.assertEqual(json.loads(page[start:end]), modules["ui"])

    def test_vendored_runtime_is_pinned(self):
        verify_vendored_runtime()

    def test_update_readme_results_inserts_then_refreshes_in_place(self):
        def modmap(*passed):
            out = {}
            for role in ROLES:
                out[role] = {"passed": role in passed}
            return out
        report = {"new_application": "DevMetrics", "sweeps": 9,
                  "fim_repairs": {"attempts": 96, "accepted": 1},
                  "search": {"candidate_count": 142,
                             "output_tokens": 50000,
                             "wall_seconds": 7214.1},
                  "baseline": {"holdout": {"modules": modmap("css"),
                                           "integrated": False}},
                  "final": {"holdout": {"modules": modmap("css", "ui"),
                                        "integrated": False}}}
        pred = {"rounds": [{"round": 9,
                            "public": {"passed": modmap("css"),
                                       "completed_checks": 5,
                                       "integrated": False},
                            "fim_accepted": 1, "fim_attempts": 96}]}
        old = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                Path("README.md").write_text(
                    "Intro\n\n<!-- SESSION031-RESULTS-START -->\n031 block\n"
                    "<!-- SESSION031-RESULTS-END -->\n\nTail\n", encoding="utf8")
                update_readme_results(report, pred)
                text = Path("README.md").read_text(encoding="utf8")
                self.assertIn("<!-- SESSION032-RESULTS-START -->", text)
                self.assertIn("<!-- SESSION032-RESULTS-END -->", text)
                self.assertLess(text.index("SESSION031-RESULTS-END"),
                                text.index("SESSION032-RESULTS-START"))
                self.assertIn("exp/32-fim-selfrepair", text)
                self.assertTrue(text.endswith("\nTail\n"))
                report["sweeps"] = 10
                update_readme_results(report, pred)
                text2 = Path("README.md").read_text(encoding="utf8")
                self.assertEqual(text2.count("SESSION032-RESULTS-START"), 1)
                self.assertIn("10 sweep(s)", text2)
        finally:
            os.chdir(old)


@unittest.skipUnless(PUBLISHED_STATE.is_file(), "published state not yet collected")
class PublishedStateTests(unittest.TestCase):
    def test_published_state_lineage_verifies(self):
        state = json.loads(PUBLISHED_STATE.read_text(encoding="utf8"))
        verify_lineage(state)


if __name__ == "__main__":
    unittest.main()
