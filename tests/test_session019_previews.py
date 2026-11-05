"""Static gallery and defense-in-depth tests, no generated host execution."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tinycoder.session017_contracts import contract_sha256, contracts
from tinycoder.session019_previews import (isolated_render, render_gallery,
                                          sanitize_markup)


class PreviewTests(unittest.TestCase):
    def test_strict_html_whitelist_disallows_executable_markup(self):
        original = ('<section class="ok" onclick="alert(1)">'
                    '<h3>Demo</h3><script>alert(2)</script>'
                    '<iframe src="javascript:alert(3)">HIDDEN</iframe>'
                    '<output style="color:red">42</output><img src=x onerror=alert(4)>'
                    '</section>')
        cleaned = sanitize_markup(original)
        self.assertIn('<section class="ok">', cleaned)
        self.assertIn('<output>42</output>', cleaned)
        for token in ("onclick", "<script", "alert(", "iframe", "HIDDEN", "<img", "style="):
            self.assertNotIn(token, cleaned)

    def test_restricted_renderer_fails_closed_on_timeout(self):
        task = contracts()[0]
        with patch("tinycoder.session019_previews.require_sandbox"), patch(
            "tinycoder.session019_previews.subprocess.run", side_effect=[
                subprocess.TimeoutExpired(cmd=["docker"], timeout=15),
                subprocess.CompletedProcess(args=["docker", "rm"], returncode=0)
            ]):
            outcome = isolated_render(task, "function ResultView(){return null;}")
        self.assertFalse(outcome["ok"])
        self.assertIn("timeout", outcome["error"])

    def test_all_ten_apps_receive_visual_pages_and_source(self):
        tasks = contracts()
        sources = {task["task_id"]: {"logic": "def transform(p): return {'value':0}",
                                      "api": "function createApp(x) {return null;}",
                                      "ui": "function ResultView(){return null;}"}
                   for task in tasks}
        result = {"status": "completed", "session": "018", "model": "0.5B",
                  "manifest_sha256": contract_sha256(tasks),
                  "task_ids": [task["task_id"] for task in tasks],
                  "tracks": {"search8_repair2": {"task_results": [
                      {"task_id": task["task_id"], "passed": True,
                       "modules": {role: {"passed": True}
                                   for role in ("logic", "api", "ui")}}
                      for task in tasks]}}}
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder / "predictions.json").write_text(
                json.dumps({"search8_repair2": sources}), encoding="utf-8")
            (folder / "report.json").write_text(json.dumps(result), encoding="utf-8")
            with patch("tinycoder.session019_previews.require_sandbox"), patch(
                "tinycoder.session019_previews.isolated_render",
                return_value={"ok": True, "html": ["<section><h3>Preview</h3><output>3</output></section>"]*2}):
                render_gallery(folder / "predictions.json", folder / "report.json",
                               folder / "gallery", "search8_repair2")
            manifest = json.loads((folder / "gallery/manifest.json").read_text())
            self.assertEqual(len(manifest["apps"]), 10)
            self.assertEqual(len(list((folder / "gallery").glob("*.html"))), 11)
            self.assertIn("Open Preview", (folder / "gallery/index.html").read_text())
            self.assertIn("generated React component", (folder / "gallery/invoice.html").read_text())
            self.assertIn("LOGIC generated source",
                          (folder / "gallery/invoice.html").read_text())


if __name__ == "__main__":
    unittest.main()
