"""Offline evaluation runner for the SQLite Orchestrator memory subsystem."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.services.orchestrator_agent.memory_policy import build_memory_record
from app.services.orchestrator_agent.memory_store import SQLiteMemoryStore


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = REPO_ROOT / "tests" / "fixtures" / "golden" / "memory" / "eval_set.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "outputs" / "evals" / "memory"
DEFAULT_USER = "memory-eval-user"
DEFAULT_PROJECT = "memory-eval-project"
DEFAULT_COUNTRY = "mx"


def run_eval(
    *,
    dataset_path: Path = DEFAULT_DATASET,
    db_path: Path | None = None,
    report_dir: Path | None = DEFAULT_REPORT_DIR,
    write_report: bool = True,
) -> dict[str, Any]:
    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    cases = dataset.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("memory eval dataset must contain a cases list")

    if db_path is not None:
        result = _run_cases(cases, SQLiteMemoryStore(db_path))
    else:
        with tempfile.TemporaryDirectory(prefix="memory-eval-") as tmp:
            result = _run_cases(cases, SQLiteMemoryStore(Path(tmp) / "memory.sqlite3"))

    result["dataset"] = str(dataset_path)
    result["version"] = dataset.get("version")
    result["passed"] = _passes_thresholds(result["metrics"])

    if write_report and report_dir is not None:
        report_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_path = report_dir / f"memory_eval_{stamp}.json"
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["report_path"] = str(report_path)
    return result


def _run_cases(cases: list[dict[str, Any]], store: SQLiteMemoryStore) -> dict[str, Any]:
    counters = {
        "policy_total": 0,
        "policy_correct": 0,
        "recall_total": 0,
        "recall_hits": 0,
        "leak_total": 0,
        "leak_pass": 0,
        "redaction_total": 0,
        "redaction_pass": 0,
        "management_total": 0,
        "management_pass": 0,
    }
    failures: list[dict[str, Any]] = []

    for case in cases:
        kind = case.get("kind")
        if kind in {"policy", "policy_recall"}:
            _run_policy_case(case, store, counters, failures)
        elif kind == "isolation":
            _run_isolation_case(case, store, counters, failures)
        elif kind == "management":
            _run_management_case(case, store, counters, failures)
        else:
            failures.append({"case_id": case.get("case_id"), "reason": "unknown_kind"})

    metrics = {
        "policy_accuracy": _ratio(counters["policy_correct"], counters["policy_total"]),
        "recall_at_8": _ratio(counters["recall_hits"], counters["recall_total"]),
        "no_leak_rate": _ratio(counters["leak_pass"], counters["leak_total"]),
        "redaction_pass_rate": _ratio(counters["redaction_pass"], counters["redaction_total"]),
        "management_pass_rate": _ratio(counters["management_pass"], counters["management_total"]),
    }
    return {"metrics": metrics, "counters": counters, "failures": failures}


def _run_policy_case(
    case: dict[str, Any],
    store: SQLiteMemoryStore,
    counters: dict[str, int],
    failures: list[dict[str, Any]],
) -> None:
    counters["policy_total"] += 1
    decision = build_memory_record(
        content=case["content"],
        category=case["category"],
        user_id=DEFAULT_USER,
        project_id=DEFAULT_PROJECT,
        country=DEFAULT_COUNTRY,
        source=case.get("source", "memory_admin"),
    )
    expected_accept = bool(case.get("expected_accept"))
    if decision.accepted == expected_accept:
        counters["policy_correct"] += 1
    else:
        failures.append({
            "case_id": case.get("case_id"),
            "reason": "policy_mismatch",
            "expected_accept": expected_accept,
            "actual_accept": decision.accepted,
            "policy_reason": decision.reason,
        })

    secret = case.get("secret")
    if secret:
        counters["leak_total"] += 1
        if not decision.record or secret not in decision.record.content:
            counters["leak_pass"] += 1
        else:
            failures.append({"case_id": case.get("case_id"), "reason": "secret_leaked"})

    if case.get("expect_redacted"):
        counters["redaction_total"] += 1
        if (
            decision.accepted
            and decision.record
            and decision.redaction_hits > 0
            and secret
            and secret not in decision.record.content
        ):
            counters["redaction_pass"] += 1
        else:
            failures.append({"case_id": case.get("case_id"), "reason": "redaction_failed"})

    if not decision.accepted or decision.record is None:
        return

    record = store.add(decision.record)
    if case.get("query"):
        counters["recall_total"] += 1
        results = store.search(
            case["query"],
            user_id=DEFAULT_USER,
            project_id=DEFAULT_PROJECT,
            country=DEFAULT_COUNTRY,
            top_k=8,
        )
        expected = str(case.get("expected_substring") or "")
        if any(expected in str(item.get("content", "")) for item in results):
            counters["recall_hits"] += 1
        else:
            failures.append({
                "case_id": case.get("case_id"),
                "reason": "recall_miss",
                "memory_id": record.memory_id,
            })


def _run_isolation_case(
    case: dict[str, Any],
    store: SQLiteMemoryStore,
    counters: dict[str, int],
    failures: list[dict[str, Any]],
) -> None:
    checks = 4
    counters["management_total"] += checks
    decision = build_memory_record(
        content=case["content"],
        category=case["category"],
        user_id="memory-eval-isolated",
        project_id=DEFAULT_PROJECT,
        country=DEFAULT_COUNTRY,
        source="memory_admin",
    )
    if not decision.accepted or decision.record is None:
        failures.append({"case_id": case.get("case_id"), "reason": "isolation_seed_rejected"})
        return
    store.add(decision.record)
    query = case["query"]
    visible = store.search(query, user_id="memory-eval-isolated", project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY)
    hidden_user = store.search(query, user_id="memory-eval-other", project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY)
    hidden_project = store.search(query, user_id="memory-eval-isolated", project_id="other-project", country=DEFAULT_COUNTRY)
    hidden_country = store.search(query, user_id="memory-eval-isolated", project_id=DEFAULT_PROJECT, country="th")
    passed = [bool(visible), hidden_user == [], hidden_project == [], hidden_country == []]
    counters["management_pass"] += sum(1 for item in passed if item)
    if not all(passed):
        failures.append({"case_id": case.get("case_id"), "reason": "identity_isolation_failed"})


def _run_management_case(
    case: dict[str, Any],
    store: SQLiteMemoryStore,
    counters: dict[str, int],
    failures: list[dict[str, Any]],
) -> None:
    checks = 6
    counters["management_total"] += checks
    user_id = "memory-eval-admin"
    decision = build_memory_record(
        content=case["content"],
        category=case["category"],
        user_id=user_id,
        project_id=DEFAULT_PROJECT,
        country=DEFAULT_COUNTRY,
        source="memory_admin",
    )
    if not decision.accepted or decision.record is None:
        failures.append({"case_id": case.get("case_id"), "reason": "management_seed_rejected"})
        return
    record = store.add(decision.record)

    update_decision = build_memory_record(
        content=case["updated_content"],
        category=case["category"],
        user_id=user_id,
        project_id=DEFAULT_PROJECT,
        country=DEFAULT_COUNTRY,
        source="memory_admin",
    )
    if not update_decision.accepted or update_decision.record is None:
        failures.append({"case_id": case.get("case_id"), "reason": "management_update_rejected"})
        return
    update_decision.record.memory_id = record.memory_id
    update_decision.record.status = "active"
    store.update(update_decision.record)

    old_hidden = store.search(case["old_query"], user_id=user_id, project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY) == []
    new_visible = bool(store.search(case["new_query"], user_id=user_id, project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY))
    archived = store.set_status(record.memory_id, status="archived", user_id=user_id, project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY)
    archived_hidden = store.search(case["new_query"], user_id=user_id, project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY) == []
    restored = store.set_status(record.memory_id, status="active", user_id=user_id, project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY)
    restored_visible = bool(store.search(case["new_query"], user_id=user_id, project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY))
    deleted = store.set_status(record.memory_id, status="deleted", user_id=user_id, project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY)
    deleted_hidden = store.search(case["new_query"], user_id=user_id, project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY) == []

    passed = [
        old_hidden,
        new_visible,
        archived["status"] == "archived" and archived_hidden,
        restored["status"] == "active" and restored_visible,
        deleted["status"] == "deleted" and deleted_hidden,
        bool(store.list_records(user_id=user_id, project_id=DEFAULT_PROJECT, country=DEFAULT_COUNTRY, status="deleted")),
    ]
    counters["management_pass"] += sum(1 for item in passed if item)
    if not all(passed):
        failures.append({"case_id": case.get("case_id"), "reason": "management_lifecycle_failed"})


def _ratio(num: int, den: int) -> float:
    if den == 0:
        return 1.0
    return round(num / den, 6)


def _passes_thresholds(metrics: dict[str, float]) -> bool:
    return (
        metrics["policy_accuracy"] >= 1.0
        and metrics["no_leak_rate"] >= 1.0
        and metrics["redaction_pass_rate"] >= 1.0
        and metrics["management_pass_rate"] >= 1.0
        and metrics["recall_at_8"] >= 0.9
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--db-path", type=Path, default=None)
    parser.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT_DIR)
    parser.add_argument("--no-report", action="store_true")
    args = parser.parse_args(argv)

    result = run_eval(
        dataset_path=args.dataset,
        db_path=args.db_path,
        report_dir=args.report_dir,
        write_report=not args.no_report,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
