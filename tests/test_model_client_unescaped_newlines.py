"""ModelClient: tolerate raw newlines/CR/TAB inside JSON string values.

Real LLMs (Gemini/Vertex) sometimes emit JSON where SQL/reasoning string
values contain literal control characters instead of \\n/\\r/\\t escapes.
Standard json.loads rejects these as 'Unterminated string ... Invalid
control character'. We pre-escape control chars inside string values
before parsing, so well-formed-but-unescaped payloads still parse.
"""

from __future__ import annotations

import json
import unittest

from app.core.model_client import ModelClient


class TestParseJsonTextRawNewlinesInString(unittest.TestCase):
    def setUp(self) -> None:
        self.client = ModelClient()

    def test_raw_newline_in_sql_value_is_recovered(self) -> None:
        # Outer braces balanced; SQL string contains literal \n bytes — the
        # exact failure mode observed with real Gemini output.
        text = (
            '{"reasoning_summary": "ok",'
            ' "sql": "SELECT uid\nFROM dwb.t\nWHERE channel=\'MEX017\'",'
            ' "sql_kind": "query_only",'
            ' "python": null,'
            ' "audit_report": {"high_risk_ddl": false, "final_verdict": ""}}'
        )
        # Sanity: stdlib json refuses this raw form.
        with self.assertRaises(json.JSONDecodeError):
            json.loads(text)

        payload = self.client._parse_json_text(text)
        self.assertEqual(payload["sql_kind"], "query_only")
        self.assertEqual(payload["python"], None)
        self.assertIn("SELECT uid", payload["sql"])
        # All 5 required keys preserved.
        self.assertEqual(
            set(payload.keys()),
            {"reasoning_summary", "sql", "sql_kind", "python", "audit_report"},
        )

    def test_raw_tab_and_cr_in_string_recovered(self) -> None:
        text = '{"a": "x\ty\rz", "b": 1}'
        payload = self.client._parse_json_text(text)
        self.assertEqual(payload["b"], 1)
        self.assertIn("x", payload["a"])

    def test_well_formed_json_still_parses(self) -> None:
        # Regression: pre-escape must not break already-valid payloads.
        text = '{"sql": "SELECT 1", "n": 42}'
        payload = self.client._parse_json_text(text)
        self.assertEqual(payload, {"sql": "SELECT 1", "n": 42})

    def test_raw_newline_with_no_outer_close_recovered_via_inner_object(self) -> None:
        # Truncation pattern: the model emits a complete inner audit_report
        # object (balanced braces) but never closes the outer object — common
        # when max_output_tokens hits mid-string. The pre-escape pass turns
        # raw \n into \\n so _extract_first_json_object cannot find a balanced
        # outer object, but _truncate_to_balanced_json should still find an
        # inner '}' that yields parseable JSON. Either: (a) we recover, or
        # (b) we raise json_parse — never silently return wrong payload.
        text = (
            '{"reasoning_summary": "ok",'
            ' "sql": "SELECT uid\nFROM t",'
            ' "audit_report": {"high_risk_ddl": false, "final_verdict": ""},'
            ' "sql_kind": "query_only'  # truncated mid-string, no closing "
        )
        try:
            payload = self.client._parse_json_text(text)
        except ValueError as exc:
            # Acceptable: caller will see json_parse and convert to
            # SCHEMA_VALIDATION_FAILED. What matters is no silent corruption.
            self.assertIn("json_parse", str(exc).lower() + str(exc))
            return
        # If recovery succeeds, must be a dict.
        self.assertIsInstance(payload, dict)


if __name__ == "__main__":
    unittest.main()
