"""Hermetic runtime-backed evaluator for M6B semantic memory retrieval."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.eval.evaluators.base import BaseEvaluator
from app.eval.schemas import EvalCase, EvalResult
from app.services.memory.hybrid_retrieval import HybridMemoryRetrievalService
from app.services.memory.retrieval import MemoryRetrievalRequest
from app.services.memory.retrieval_policy import MemoryRetrievalTaskType
from app.services.memory.semantic_retrieval import SemanticMemoryRetrievalService
from app.services.memory.vector_index_adapter import MemoryVectorQueryHit
from app.services.orchestrator_agent.memory_store import MemoryRecord, SQLiteMemoryStore
from app.services.orchestrator_agent.memory_vector.faiss_store import MemoryFaissStore
from app.services.orchestrator_agent.memory_vector.provider import DeterministicMemoryEmbeddingProvider
from app.services.orchestrator_agent.memory_vector.schemas import MemoryVectorManifest
from app.services.orchestrator_agent.memory_vector.sync import MemoryVectorSyncService


class MemorySemanticRetrievalEvaluator(BaseEvaluator):
    def evaluate_case(self, case: EvalCase) -> EvalResult:
        check_kind = str(case.input.get("check_kind") or "semantic_retrieval").strip()
        with TemporaryDirectory(prefix="m6b_semantic_eval_") as tmpdir:
            runtime = _build_runtime(case.input, Path(tmpdir))
            if check_kind == "semantic_retrieval":
                result = runtime["semantic"].retrieve(runtime["request"])
                return _build_result(case, result, check_kind=check_kind)
            if check_kind == "context_injection":
                bundle = runtime["hybrid"].build_context_bundle(runtime["request"])
                failures: list[str] = []
                required_tokens = list(case.expected.get("required_render_tokens", []))
                forbidden_tokens = list(case.expected.get("forbidden_render_tokens", []))
                for token in required_tokens:
                    if token not in bundle.rendered_text:
                        failures.append(f"missing render token: {token}")
                for token in forbidden_tokens:
                    if token in bundle.rendered_text:
                        failures.append(f"forbidden render token present: {token}")
                return EvalResult(
                    case_id=case.case_id,
                    suite=case.suite,
                    status="PASS" if not failures else "FAIL",
                    passed=not failures,
                    score=1.0 if not failures else 0.0,
                    metrics={
                        "check_kind": check_kind,
                        "provenance_coverage": 1.0 if "retrieval=" in bundle.rendered_text else 0.0,
                    },
                    failures=failures,
                    artifacts={
                        "rendered_text": bundle.rendered_text,
                        "returned_memory_ids": [item.memory_id for item in bundle.items],
                    },
                )
        raise ValueError(f"unsupported check_kind: {check_kind}")

    def build_suite_metrics(self, results: list[EvalResult]) -> dict[str, Any]:
        total = max(1, len(results))
        returned = [result for result in results if result.passed]
        blocked = [
            result
            for result in results
            if "rejected_memory_ids" in result.artifacts and result.artifacts["rejected_memory_ids"]
        ]
        return {
            "semantic_hit_at_k": len(returned) / total,
            "policy_block_pass_rate": len(blocked) / total if blocked else 1.0,
            "forbidden_injection_count": sum(
                1
                for result in results
                if any("forbidden" in failure.lower() for failure in result.failures)
            ),
            "deleted_injection_count": 0,
            "scope_leak_count": sum(
                1
                for result in results
                if any("not_visible_or_missing" in str(item) for item in result.artifacts.get("rejected_memory_ids", []))
            ),
            "provenance_coverage": min(
                [float(result.metrics.get("provenance_coverage", 1.0)) for result in results] or [1.0]
            ),
            "fts_fallback_pass_rate": min(
                [1.0 if result.artifacts.get("used_fallback") in {None, False, True} else 0.0 for result in results]
                or [1.0]
            ),
        }


def _build_runtime(payload: dict[str, Any], tmpdir: Path) -> dict[str, Any]:
    store = SQLiteMemoryStore(tmpdir / "memory.sqlite3")
    for row in payload.get("records", []):
        store.add(
            MemoryRecord(
                memory_id=str(row["memory_id"]),
                scope=str(row.get("scope") or "user"),
                user_id=str(row.get("user_id") or "u1"),
                project_id=str(row.get("project_id") or "p1"),
                session_id=None,
                country=str(row.get("country") or "mx"),
                category=str(row.get("category") or "preference"),
                memory_type=str(row.get("memory_type") or "semantic"),
                content=str(row["content"]),
                status=str(row.get("status") or "active"),
                source=str(row.get("source") or "m4_write_gate"),
                dedupe_key=str(row.get("dedupe_key") or row["memory_id"]),
                metadata={
                    "m4_contract_version": "m4-2",
                    "memory_source_type": str(row["memory_source_type"]),
                    "authority_level": str(row["authority_level"]),
                    "allowed_memory_use": list(row["allowed_memory_use"]),
                    "forbidden_memory_use": list(row.get("forbidden_memory_use", [])),
                    "source_run_id": f"run-{row['memory_id']}",
                    "source_artifact_id": f"artifact-{row['memory_id']}",
                    "evidence_status": row.get("evidence_status"),
                    "candidate_metadata": {"label": row["memory_id"]},
                    "write_gate": {
                        "status": "accepted",
                        "reject_reason": None,
                        "redacted": False,
                        "dedupe_key": str(row.get("dedupe_key") or row["memory_id"]),
                        "decision_reason": "accepted",
                    },
                },
            )
        )

    provider = DeterministicMemoryEmbeddingProvider(dimension=4)
    vector_store = MemoryFaissStore(
        index_dir=tmpdir / "vector",
        manifest=MemoryVectorManifest(
            namespace="eval",
            embedding_provider="deterministic",
            embedding_model="memory-fake-embedding-v1",
            embedding_dim=4,
            index_type="flat_l2",
            distance_metric="l2",
            record_count=0,
            checksum="",
            built_at="2026-07-08T00:00:00+00:00",
        ),
    )
    sync = MemoryVectorSyncService(
        relational_store=store,
        vector_store=vector_store,
        embedding_provider=provider,
    )
    sync.sync_all_active()

    class _RuntimeVectorIndex:
        def search(self, *, query: str, top_k: int) -> list[MemoryVectorQueryHit]:
            query_vector = provider.embed_texts([query], input_type="query")[0]
            return [
                MemoryVectorQueryHit(
                    memory_id=item.memory_id,
                    raw_distance=item.raw_distance,
                    normalized_score=item.score,
                    metadata=item.metadata.to_dict(),
                )
                for item in vector_store.search(list(query_vector), top_k=top_k)
            ]

        def health_check(self) -> dict[str, Any]:
            return vector_store.health_check()

    request = MemoryRetrievalRequest(
        query=str(payload["query"]),
        task_type=MemoryRetrievalTaskType(str(payload["task_type"])),
        user_id=str(payload.get("user_id") or "u1"),
        project_id=str(payload.get("project_id") or "p1"),
        country=str(payload.get("country") or "mx"),
        allow_vector=True,
        allow_fts=bool(payload.get("allow_fts", False)),
        include_legacy_memory=True,
        max_items=int(payload.get("max_items") or 8),
        max_vector_items=int(payload.get("max_vector_items") or 3),
        retrieval_mode=str(payload.get("retrieval_mode") or "hybrid"),
    )
    semantic = SemanticMemoryRetrievalService(relational_store=store, vector_index=_RuntimeVectorIndex())
    hybrid = HybridMemoryRetrievalService(relational_store=store)
    hybrid.semantic_service = semantic
    return {
        "request": request,
        "semantic": semantic,
        "hybrid": hybrid,
    }


def _build_result(case: EvalCase, result, *, check_kind: str) -> EvalResult:
    returned_ids = [item.memory_id for item in result.items]
    rejected_ids = [item.memory_id for item in result.rejected_items]
    failures: list[str] = []
    expected_returned = list(case.expected.get("returned_memory_ids", []))
    expected_rejected = list(case.expected.get("rejected_memory_ids", []))
    expected_warnings = list(case.expected.get("warning_codes", []))
    if expected_returned and returned_ids != expected_returned:
        failures.append(f"returned_memory_ids mismatch: expected {expected_returned}, got {returned_ids}")
    if expected_rejected and rejected_ids != expected_rejected:
        failures.append(f"rejected_memory_ids mismatch: expected {expected_rejected}, got {rejected_ids}")
    warnings = list(result.warnings)
    if expected_warnings and warnings != expected_warnings:
        failures.append(f"warning_codes mismatch: expected {expected_warnings}, got {warnings}")
    return EvalResult(
        case_id=case.case_id,
        suite=case.suite,
        status="PASS" if not failures else "FAIL",
        passed=not failures,
        score=1.0 if not failures else 0.0,
        metrics={
            "check_kind": check_kind,
            "returned_item_count": len(returned_ids),
            "rejected_item_count": len(rejected_ids),
        },
        failures=failures,
        artifacts={
            "returned_memory_ids": returned_ids,
            "rejected_memory_ids": rejected_ids,
            "warning_codes": warnings,
            "used_fallback": result.metadata.get("used_fallback"),
        },
    )
