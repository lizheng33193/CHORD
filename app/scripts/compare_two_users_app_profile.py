"""Run AppProfileSkill on two contrasting uids and dump a side-by-side diff.

Usage:
    python -m app.scripts.compare_two_users_app_profile [uid_a] [uid_b]

Defaults pick a finance-heavy user vs a more diversified user from the
local data/app/by_uid corpus.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.model_client import ModelClient
from app.repositories.local_repository import LocalUserRepository
from app.runtime_skills.app_profile_agent import AppProfileSkill
from app.scripts.app_profile_payload_builder import (
    UNKNOWN_CATEGORY_LABEL,
    _infer_localized_category,
)


CACHE_PATH = PROJECT_ROOT / "outputs" / "cache" / "app_category_cache.json"


def _load_cache_size() -> int:
    if not CACHE_PATH.exists():
        return 0
    try:
        return len(json.loads(CACHE_PATH.read_text(encoding="utf-8")) or {})
    except Exception:  # pylint: disable=broad-except
        return 0


def _summarize(uid: str, result: dict) -> dict:
    structured = result.get("structured_result") or result
    risk = structured.get("multi_loan_risk", {}) or {}
    fin = structured.get("financial_maturity", {}) or {}
    cons = structured.get("consumption_profile", {}) or {}

    dist = (
        structured.get("evidence", {}).get("localized_category_distribution")
        or risk.get("localized_category_distribution")
        or []
    )

    return {
        "uid": uid,
        "multi_loan_risk_level": risk.get("level"),
        "financial_maturity_level": fin.get("level"),
        "consumption_ability_level": cons.get("level"),
        "has_bank_app": fin.get("has_bank_app"),
        "has_ewallet": fin.get("has_ewallet"),
        "has_gov_app": fin.get("has_gov_app"),
        "lending_app_count": risk.get("lending_app_count"),
        "supporting_apps": (fin.get("supporting_apps") or [])[:5],
        "localized_category_distribution": dist[:8],
    }


def _print_side_by_side(a: dict, b: dict) -> None:
    keys = [
        "multi_loan_risk_level",
        "financial_maturity_level",
        "consumption_ability_level",
        "lending_app_count",
        "has_bank_app",
        "has_ewallet",
        "has_gov_app",
    ]
    print("\n=== Side-by-side metrics ===")
    print(f"{'metric':<28} | {'A=' + a['uid']:<32} | {'B=' + b['uid']:<32}")
    print("-" * 100)
    for k in keys:
        print(f"{k:<28} | {str(a.get(k)):<32} | {str(b.get(k)):<32}")

    print("\n=== A localized_category_distribution ===")
    print(json.dumps(a["localized_category_distribution"], ensure_ascii=False, indent=2))
    print("\n=== B localized_category_distribution ===")
    print(json.dumps(b["localized_category_distribution"], ensure_ascii=False, indent=2))

    print("\n=== A supporting_apps (top 5) ===")
    print(a["supporting_apps"])
    print("\n=== B supporting_apps (top 5) ===")
    print(b["supporting_apps"])


def main() -> int:
    uid_a = sys.argv[1] if len(sys.argv) > 1 else "824812551379353600"
    uid_b = sys.argv[2] if len(sys.argv) > 2 else "824848564055179264"
    application_time = "2026-04-15T12:00:00Z"

    repository = LocalUserRepository()
    model_client = ModelClient()
    skill = AppProfileSkill(model_client)

    cache_before = _load_cache_size()

    print(f"Running AppProfileSkill in mode={getattr(model_client, 'mode', '?')}", flush=True)
    print(f"Cache entries before: {cache_before}", flush=True)

    classifier = getattr(skill.feature_builder, "_classifier", None)

    def _prefetch(uid: str) -> int:
        if classifier is None:
            return 0
        data = repository.get_app_data(uid) or {}
        apps = data.get("apps") or []
        misses: list[dict[str, str]] = []
        for app in apps:
            app_name = str(app.get("app_name") or "")
            package = str(app.get("app_package") or "")
            ai_cat = str(app.get("ai_category_level_2_CN") or "")
            gp_cat = str(app.get("gp_category") or "")
            inferred = _infer_localized_category(
                app_name=app_name, package_name=package,
                ai_category=ai_cat, gp_category=gp_cat,
                classifier=None,
            )
            if inferred == UNKNOWN_CATEGORY_LABEL:
                misses.append({
                    "app_name": app_name, "package_name": package,
                    "ai_category": ai_cat, "gp_category": gp_cat,
                })
        if misses:
            classifier.prefetch_many(misses, max_workers=10)
        return len(misses)

    import time
    t0 = time.perf_counter()
    print(f"\n>>> prefetch uid_A = {uid_a}", flush=True)
    n_a = _prefetch(uid_a)
    print(f"    {n_a} unknown-rule apps queued for concurrent LLM classify", flush=True)
    print(f">>> prefetch uid_B = {uid_b}", flush=True)
    n_b = _prefetch(uid_b)
    print(f"    {n_b} unknown-rule apps queued for concurrent LLM classify", flush=True)
    t_pf = time.perf_counter() - t0
    print(f"    Prefetch total: {t_pf:.1f}s; cache size now = {_load_cache_size()}", flush=True)

    t0 = time.perf_counter()
    print(f"\n>>> analyze uid_A = {uid_a}", flush=True)
    res_a = skill.analyze(uid=uid_a, repository=repository, application_time=application_time)
    t1 = time.perf_counter()
    print(f"    uid_A done in {t1 - t0:.1f}s", flush=True)
    print(f">>> analyze uid_B = {uid_b}", flush=True)
    res_b = skill.analyze(uid=uid_b, repository=repository, application_time=application_time)
    t2 = time.perf_counter()
    print(f"    uid_B done in {t2 - t1:.1f}s; total = {t2 - t0:.1f}s", flush=True)

    cache_after = _load_cache_size()
    print(f"\nCache entries after: {cache_after}  (delta = {cache_after - cache_before})")

    sa = _summarize(uid_a, res_a)
    sb = _summarize(uid_b, res_b)
    _print_side_by_side(sa, sb)

    out_dir = PROJECT_ROOT / "outputs" / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"compare_{uid_a}_vs_{uid_b}.json").write_text(
        json.dumps({"A": sa, "B": sb}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved: outputs/reports/compare_{uid_a}_vs_{uid_b}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
