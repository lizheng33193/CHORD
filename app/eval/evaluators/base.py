"""Evaluator interfaces for shared eval."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.eval.schemas import EvalCase, EvalResult


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate_case(self, case: EvalCase) -> EvalResult:
        raise NotImplementedError

    def build_suite_metrics(self, results: list[EvalResult]) -> dict[str, Any]:
        return {}
