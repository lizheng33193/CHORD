"""Unit tests for ModelClient JSON repair (truncated string recovery).

The truncation recovery only fires when json.loads raises 'Unterminated string'
on the raw normalized text. It tries to trim back to the rightmost '}' that
yields a parseable JSON object. For most truncation cases (mid-string in the
outer object) recovery is impossible and we conservatively fall through to the
original failure path.
"""

from __future__ import annotations

import json
import unittest

from app.core.model_client import ModelClient


class TestTruncateToBalancedJson(unittest.TestCase):
    def test_returns_none_when_outer_object_never_closes(self) -> None:
        text = '{"summary": "ok", "details": {"a": 1, "b": 2}, "more": "trunc'
        # The outer { never closes; no prefix [outer_start .. some '}'] is valid JSON.
        self.assertIsNone(ModelClient._truncate_to_balanced_json(text))

    def test_returns_none_when_string_unterminated_with_no_inner_object(self) -> None:
        text = '{"a": 1, "b": "still open'
        self.assertIsNone(ModelClient._truncate_to_balanced_json(text))

    def test_returns_none_when_no_open_brace(self) -> None:
        self.assertIsNone(ModelClient._truncate_to_balanced_json("just text"))

    def test_recovers_when_balanced_object_followed_by_garbage_close(self) -> None:
        # If model emits a valid object then garbage that happens to contain a '}',
        # truncation back to the legitimate close yields a parseable object.
        text = '{"a": 1, "b": 2}}}'
        recovered = ModelClient._truncate_to_balanced_json(text)
        self.assertIsNotNone(recovered)
        self.assertEqual(json.loads(recovered), {"a": 1, "b": 2})


class TestParseJsonTextTruncationFallback(unittest.TestCase):
    def setUp(self) -> None:
        self.client = ModelClient()

    def test_unrecoverable_unterminated_still_raises_json_parse(self) -> None:
        text = '{"a": 1, "b": "still open'
        with self.assertRaises(ValueError) as ctx:
            self.client._parse_json_text(text)
        self.assertIn("json_parse", str(ctx.exception))


class TestRepairJsonCandidateUnchanged(unittest.TestCase):
    """Pre-existing trailing-comma path must continue to work."""

    def setUp(self) -> None:
        self.client = ModelClient()

    def test_trailing_comma_repair(self) -> None:
        text = '{"a": 1,}'
        try:
            json.loads(text)
        except json.JSONDecodeError as exc:
            repaired = self.client._repair_json_candidate(text, exc)
            self.assertEqual(json.loads(repaired), {"a": 1})
            return
        self.fail("expected JSONDecodeError")


if __name__ == "__main__":
    unittest.main()
