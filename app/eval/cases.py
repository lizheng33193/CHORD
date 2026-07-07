"""Case loading helpers for the shared eval foundation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.eval.schemas import EvalCase


class EvalCaseLoadError(ValueError):
    """Raised when an eval case file cannot be loaded or validated."""


def load_eval_cases(path: Path) -> list[EvalCase]:
    try:
        payload = _load_payload(path)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise EvalCaseLoadError(str(exc)) from exc

    raw_cases = _extract_cases(payload)
    try:
        return [EvalCase.model_validate(item) for item in raw_cases]
    except ValidationError as exc:
        raise EvalCaseLoadError(str(exc)) from exc


def _load_payload(path: Path):
    if path.suffix.lower() in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    raise EvalCaseLoadError(f"unsupported case file type: {path.suffix}")


def _extract_cases(payload) -> list[dict]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("cases"), list):
        return payload["cases"]
    raise EvalCaseLoadError("case file must be a list or a mapping with a cases list")
