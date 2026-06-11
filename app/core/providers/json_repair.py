"""JSON repair helpers — extracted from baseline ModelClient._parse_json_text.

Pure functions, no logging, no LLM client dependency. Shared by GeminiProvider
(and any future Provider needing JSON repair on imperfect model output).

Baseline behavior preserved 1:1 — see commit 32d64e0 for the Real LLM 0/3 → 3/3
fix that this code-path is fight-tested against. Do not "simplify" without
re-running tests/test_golden_behavior_comprehensive.py.
"""

from __future__ import annotations

import json
import re
from typing import Any


RETRYABLE_PARSE_HINTS: tuple[str, ...] = (
    "Model response candidates were empty",
    "Model response did not include text content",
    "Unterminated string",
    "Invalid \\u",
    "Invalid control character",
    "Expecting value",
    "Expecting ',' delimiter",
    "Expecting ':' delimiter",
    "Expecting property name enclosed in double quotes",
    "Extra data",
    "JSONDecodeError",
    "json_parse",
    "json_repair_failed",
)


def parse_json_text(response_text: str) -> dict[str, Any]:
    """Parse model text output as a JSON object, with code-fence stripping
    and multi-tier repair.

    Returns the parsed dict. Raises ValueError with a hint matching
    RETRYABLE_PARSE_HINTS so caller's tenacity retry can catch.
    """
    normalized = response_text.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()
        if normalized.lower().startswith("json"):
            normalized = normalized[4:].strip()
    # Real LLMs (Gemini/Vertex) sometimes emit raw \n / \r / \t inside
    # string values instead of the JSON escapes \\n / \\r / \\t. Pre-escape
    # control chars inside strings so the first json.loads succeeds for
    # otherwise well-formed payloads.
    normalized = _escape_control_chars_in_strings(normalized)
    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError as exc:
        candidate = _extract_first_json_object(normalized)
        if not candidate:
            if "Unterminated string" in str(exc):
                truncated = _truncate_to_balanced_json(normalized)
                if truncated is not None:
                    payload = json.loads(truncated)
                    if not isinstance(payload, dict):
                        raise ValueError("Model JSON output must be an object") from exc
                    return payload
            raise ValueError(f"json_parse: {exc}") from exc

        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError as inner_exc:
            repaired = _repair_json_candidate(candidate, inner_exc)
            try:
                payload = json.loads(repaired)
            except json.JSONDecodeError as final_exc:
                raise ValueError(f"json_repair_failed: {final_exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Model JSON output must be an object")
    return payload


def _repair_json_candidate(candidate: str, exc: json.JSONDecodeError) -> str:
    repaired = candidate
    repaired = re.sub(r"\\u(?![0-9a-fA-F]{4})", r"\\\\u", repaired)
    repaired = _escape_control_chars_in_strings(repaired)
    if _should_strip_trailing_commas(exc):
        repaired = _strip_trailing_commas(repaired)
    if "Unterminated string" in str(exc):
        truncated = _truncate_to_balanced_json(repaired)
        if truncated is not None:
            return truncated
    return repaired


def _truncate_to_balanced_json(text: str) -> str | None:
    """Try to recover a truncated JSON object by trimming to the rightmost balanced `}`.

    For a payload truncated mid-string (e.g. LLM hit max_output_tokens), there is no
    complete top-level object. We scan from right to left for `}` candidates and
    return the longest prefix that parses as a JSON object. Returns None if no such
    prefix exists.
    """
    start = text.find("{")
    if start == -1:
        return None
    for i in range(len(text) - 1, start, -1):
        if text[i] != "}":
            continue
        candidate = text[start : i + 1]
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return candidate
    return None


def _should_strip_trailing_commas(exc: json.JSONDecodeError) -> bool:
    message = str(exc)
    return (
        "Expecting property name enclosed in double quotes" in message
        or "Expecting value" in message
        or "Expecting ',' delimiter" in message
    )


def _extract_first_json_object(text: str) -> str | None:
    """Extract the first complete top-level JSON object, respecting quoted strings."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        ch = text[index]
        if in_string:
            if escaped:
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None


def _escape_control_chars_in_strings(text: str) -> str:
    """Escape control chars inside JSON strings (raw newlines -> \\n), leaving JSON structure intact."""
    out: list[str] = []
    in_string = False
    escaped = False

    for ch in text:
        if not in_string:
            out.append(ch)
            if ch == '"':
                in_string = True
                escaped = False
            continue

        if escaped:
            # Handle broken sequences like backslash + literal newline inside a string.
            # At this point the backslash was already appended. Replace control chars
            # with a valid JSON escape to keep the string terminated properly.
            if ch == "\n":
                out.append("n")
            elif ch == "\r":
                out.append("r")
            elif ch == "\t":
                out.append("t")
            else:
                out.append(ch)
            escaped = False
            continue

        if ch == "\\":
            out.append(ch)
            escaped = True
            continue

        if ch == '"':
            out.append(ch)
            in_string = False
            continue

        if ch == "\n":
            out.append("\\n")
            continue
        if ch == "\r":
            out.append("\\r")
            continue
        if ch == "\t":
            out.append("\\t")
            continue

        codepoint = ord(ch)
        if codepoint < 0x20:
            out.append(f"\\u{codepoint:04x}")
            continue

        out.append(ch)

    return "".join(out)


def _strip_trailing_commas(text: str) -> str:
    """Remove trailing commas before } or ] (minimal, non-recursive repair)."""
    return re.sub(r",(\s*[}\]])", r"\1", text)
