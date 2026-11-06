"""TRUSTED-SCAFFOLD bridge: run the Qwen-authored logic module once.

Reads one JSON payload from stdin, executes server/logic.py (Qwen bytes)
in this isolated `python3 -I -B` process, prints the JSON result.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "server"))
import logic  # noqa: E402  (Qwen-authored module)

payload = json.load(sys.stdin)
result = logic.summarize_project(payload)
print(json.dumps(result))
