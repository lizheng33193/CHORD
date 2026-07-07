"""Evaluator interfaces for shared eval."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.eval.schemas import EvalCase, EvalResult


class BaseEvaluator(ABC):
    @abstractmethod
    def evaluate_case(self, case: EvalCase) -> EvalResult:
        raise NotImplementedError
