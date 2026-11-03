"""Lightweight tests that need no model download or ML dependencies."""

import json
import tempfile
import unittest
from pathlib import Path

from tinycoder.data import check_no_overlap, read_examples, supervised_tokens
from tinycoder.evaluation import extract_python, static_check


class FakeTokenizer:
    eos_token = "!"
    chat_template = None

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [ord(c) for c in text]}


class LabTests(unittest.TestCase):
    def test_sample_data_is_valid_and_disjoint(self):
        root = Path(__file__).resolve().parents[1]
        train = read_examples(root / "data/train.jsonl")
        eval_items = read_examples(root / "data/eval.jsonl", require_answer=False)
        self.assertEqual(len(train), 12)
        self.assertEqual(len(eval_items), 4)
        check_no_overlap(train, eval_items)

    def test_duplicate_prompts_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "examples.jsonl"
            path.write_text(json.dumps({"prompt": "x", "answer": "y"}) + "\n"
                            + json.dumps({"prompt": "x", "answer": "z"}) + "\n")
            with self.assertRaisesRegex(ValueError, "duplicate prompt"):
                read_examples(path)

    def test_completion_only_loss(self):
        record = supervised_tokens(FakeTokenizer(), {"prompt": "hi", "answer": "ok"}, 200)
        self.assertIsNotNone(record)
        prefix_length = record["labels"].index(ord("o"))
        self.assertTrue(all(x == -100 for x in record["labels"][:prefix_length]))
        self.assertEqual(record["labels"][prefix_length:], [ord("o"), ord("k"), ord("!")])

    def test_long_rows_are_skipped(self):
        self.assertIsNone(supervised_tokens(FakeTokenizer(), {"prompt": "a", "answer": "b"}, 3))

    def test_static_eval_does_not_execute_code(self):
        answer = "```python\ndef target(x):\n    return x + 1\n```"
        self.assertEqual(extract_python(answer), "def target(x):\n    return x + 1")
        self.assertTrue(static_check(answer, "target")["static_pass"])
        self.assertFalse(static_check(answer, "other")["static_pass"])
        self.assertFalse(static_check("def target(:", "target")["syntax_valid"])


if __name__ == "__main__":
    unittest.main()

