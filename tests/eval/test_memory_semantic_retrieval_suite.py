from __future__ import annotations

from pathlib import Path


FIXTURES = Path(__file__).parent.parent / "eval_cases"


def test_memory_semantic_retrieval_suite_is_registered_and_runtime_backed() -> None:
    from app.eval.cases import load_eval_cases
    from app.eval.evaluators.memory_semantic import MemorySemanticRetrievalEvaluator
    from app.eval.registry import get_suite

    suite = get_suite("memory_semantic_retrieval")
    assert suite.evaluator == "memory_semantic_retrieval"

    cases = load_eval_cases(FIXTURES / "memory_semantic_retrieval.yaml")
    results = [MemorySemanticRetrievalEvaluator().evaluate_case(case) for case in cases]

    assert results
    assert all(result.passed for result in results)


def test_runner_returns_zero_for_memory_semantic_retrieval_suite(tmp_path) -> None:
    from app.eval.runner import main

    exit_code = main(
        [
            "--suite",
            "memory_semantic_retrieval",
            "--output-dir",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
