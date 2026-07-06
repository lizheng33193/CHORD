from __future__ import annotations

from app.services.memory.adapters import profile_snapshot_to_memory_candidate
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore
from app.services.profile_dag.contracts import ProfileNodeRun, ProfileRun, ProfileRunResultSnapshot, utcnow
from app.services.profile_dag.memory_snapshot import build_profile_memory_snapshot


def _node_run(node_key: str, status: str) -> ProfileNodeRun:
    now = utcnow()
    return ProfileNodeRun(
        node_run_id=f"pnr_{node_key}",
        profile_run_id="pr_test",
        uid="U1",
        node_key=node_key,
        skill_name=f"{node_key}_skill",
        stage=0,
        depends_on=[],
        upstream_node_run_ids=[],
        status=status,
        attempt=1,
        started_at=now,
        finished_at=now,
        result_status="ok" if status in {"completed", "degraded"} else "failed",
    )


def _profile_run() -> ProfileRun:
    now = utcnow()
    return ProfileRun(
        run_id="pr_test",
        source="test",
        uids=["U1"],
        requested_modules=["comprehensive"],
        country_code="mx",
        application_time="2026-04-15T12:00:00",
        strict_data_mode=True,
        status="completed",
        trace_id=None,
        session_id=None,
        turn_id=None,
        request_id=None,
        created_at=now,
        started_at=now,
        finished_at=now,
    )


def _profile_snapshot() -> dict[str, object]:
    snapshot = ProfileRunResultSnapshot(
        uid="U1",
        requested_modules=["comprehensive"],
        module_outputs={
            "comprehensive": {
                "summary": "stable summary",
                "structured_result": {
                    "uid": "U1",
                    "status": "ok",
                    "summary": "stable summary",
                    "segment": "S2",
                    "overall_risk": "medium",
                    "overall_value": "high",
                    "confidence": "medium",
                    "metrics": {
                        "segment": "S2",
                        "overall_risk": "medium",
                        "overall_value": "high",
                        "confidence": "medium",
                    },
                },
                "charts": [],
                "report_markdown": "",
            },
        },
        node_runs=[_node_run("comprehensive", "completed")],
    )
    return build_profile_memory_snapshot(_profile_run(), snapshot)


def test_sqlite_adapter_persists_m4_metadata_envelope(tmp_path) -> None:
    from app.services.memory.store_adapter import SQLiteV1MemoryStoreAdapter
    from app.services.memory.write_gate import MemoryWriteGate

    db_path = tmp_path / "memory.sqlite3"
    candidate = profile_snapshot_to_memory_candidate(_profile_snapshot(), user_id="u1", project_id="p1", country="mx")
    store = SQLiteV1MemoryStoreAdapter(db_path=db_path)
    gate = MemoryWriteGate(store=store, allow_store_write=True)

    decision = gate.write(candidate)

    assert decision.memory_id is not None
    assert decision.persisted is True

    sqlite_store = SQLiteMemoryStore(db_path)
    stored = sqlite_store.get(decision.memory_id, user_id="u1", project_id="p1", country="mx")

    assert stored is not None
    assert stored["source"] == "m4_write_gate"
    assert stored["metadata"]["m4_contract_version"] == "m4-2"
    assert stored["metadata"]["memory_source_type"] == "profile_result"
    assert stored["metadata"]["authority_level"] == "system_generated"
    assert stored["metadata"]["write_gate"]["status"] == "accepted"
    assert stored["metadata"]["write_gate"]["dedupe_key"] == decision.dedupe_key


def test_sqlite_adapter_keeps_legacy_store_compatibility(tmp_path) -> None:
    from app.services.memory.store_adapter import SQLiteV1MemoryStoreAdapter
    from app.services.memory.write_gate import MemoryWriteGate

    db_path = tmp_path / "memory.sqlite3"
    candidate = profile_snapshot_to_memory_candidate(_profile_snapshot(), user_id="u1", project_id="p1", country="mx")
    gate = MemoryWriteGate(store=SQLiteV1MemoryStoreAdapter(db_path=db_path), allow_store_write=True)

    first = gate.write(candidate)
    second = gate.write(candidate)

    sqlite_store = SQLiteMemoryStore(db_path)
    rows = sqlite_store.list_records(user_id="u1", project_id="p1", country="mx", limit=10)

    assert first.memory_id is not None
    assert second.memory_id is None
    assert len(rows) == 1
    assert rows[0]["category"] in {"insight", "reference", "task", "preference"}
