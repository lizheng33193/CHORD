"""Golden-set JSONL loader for M2D-13."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from app.risk_knowledge.evaluation.errors import GoldenSetLoadError, GoldenSetSchemaError
from app.risk_knowledge.evaluation.schemas import GoldenEvaluationCase


def load_golden_cases(path: Path) -> list[GoldenEvaluationCase]:
    try:
        payload = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - filesystem failure path
        raise GoldenSetLoadError(str(exc)) from exc

    cases: list[GoldenEvaluationCase] = []
    for lineno, line in enumerate(payload.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            cases.append(GoldenEvaluationCase.model_validate(json.loads(stripped)))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise GoldenSetSchemaError(f"invalid golden case at line {lineno}: {exc}") from exc
    return cases
