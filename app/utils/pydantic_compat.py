"""Compatibility helpers for Pydantic v1/v2 APIs used in the repo."""

from __future__ import annotations

from typing import Any


def model_dump_compat(model: Any) -> dict[str, Any]:
    """Dump a model to dict across Pydantic major versions."""
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def model_validate_compat(model_cls: Any, payload: dict[str, Any]) -> Any:
    """Validate a payload across Pydantic major versions."""
    if hasattr(model_cls, "model_validate"):
        return model_cls.model_validate(payload)
    return model_cls.parse_obj(payload)


def model_json_schema_compat(model_cls: Any) -> dict[str, Any]:
    """Read JSON schema across Pydantic major versions."""
    if hasattr(model_cls, "model_json_schema"):
        return model_cls.model_json_schema()
    return model_cls.schema()
