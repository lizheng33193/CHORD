"""Parse txt/csv uid files with validation and normalization."""

from __future__ import annotations

import csv
from io import StringIO

from app.utils.uid_utils import normalize_uid, validate_uid_or_raise


def parse_uid_file(filename: str, file_bytes: bytes) -> list[str]:
    """Parse uid list from uploaded txt/csv file."""
    if not filename:
        raise ValueError("Uploaded file must have a filename.")

    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in {"txt", "csv"}:
        raise ValueError("Only txt and csv files are supported.")
    if not file_bytes:
        raise ValueError("Uploaded file is empty.")

    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Uploaded file must use UTF-8 encoding.") from exc

    raw_uids = _parse_txt_uids(text) if suffix == "txt" else _parse_csv_uids(text)
    normalized = normalize_uids(raw_uids)
    if not normalized:
        raise ValueError("No valid uid values were found in the file.")
    return normalized


def _parse_txt_uids(file_text: str) -> list[str]:
    """Read txt lines as uid values."""
    return file_text.splitlines()


def _parse_csv_uids(file_text: str) -> list[str]:
    """Read uid column (or first column) from CSV content."""
    csv_buffer = StringIO(file_text)
    reader = csv.DictReader(csv_buffer)
    if not reader.fieldnames:
        return []

    normalized_fields = {
        (field or "").strip().lower(): field for field in reader.fieldnames if field
    }
    uid_column = normalized_fields.get("uid") or reader.fieldnames[0]

    parsed: list[str] = []
    for row in reader:
        parsed.append((row.get(uid_column) or "").strip())
    return parsed


def normalize_uids(uids: list[str]) -> list[str]:
    """Trim, validate, and deduplicate uid values while keeping order."""
    normalized: list[str] = []
    seen: set[str] = set()
    invalid: list[str] = []

    for uid in uids:
        cleaned = normalize_uid(uid)
        if not cleaned:
            continue
        try:
            validated = validate_uid_or_raise(cleaned)
        except ValueError:
            invalid.append(cleaned)
            continue
        if validated in seen:
            continue
        seen.add(validated)
        normalized.append(validated)

    if invalid:
        preview = ", ".join(invalid[:3])
        raise ValueError(
            f"Only 18-digit numeric uid values are supported. Invalid sample: {preview}"
        )

    return normalized
