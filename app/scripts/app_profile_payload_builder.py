"""Build App profile features, decisions, and prompt payloads."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from math import floor
from typing import Any

from app.country_packs.mx.app_categories import (
    BANK_KEYWORDS,
    CONSUMPTION_KEYWORDS,
    DELIVERY_TRAVEL_KEYWORDS,
    ECOMMERCE_KEYWORDS,
    EDUCATION_KEYWORDS,
    EWALLET_KEYWORDS,
    GAME_KEYWORDS,
    GOV_KEYWORDS,
    LENDING_KEYWORDS,
    REMITTANCE_KEYWORDS,
    SOCIAL_KEYWORDS,
)


LOCALIZED_CATEGORY_ORDER = [
    ("电商消费", "blue"),
    ("出行外卖", "cyan"),
    ("借贷竞争", "amber"),
    ("社交媒体", "indigo"),
    ("银行金融", "green"),
    ("游戏娱乐", "purple"),
    ("教育职业", "slate"),
    ("政府公共服务", "emerald"),
    ("汇款", "rose"),
    ("其他待归类", "gray"),
]
LOCALIZED_CATEGORY_COLORS = {
    "blue": "#3b82f6",
    "cyan": "#06b6d4",
    "amber": "#f59e0b",
    "indigo": "#6366f1",
    "green": "#22c55e",
    "purple": "#8b5cf6",
    "slate": "#64748b",
    "emerald": "#10b981",
    "rose": "#f43f5e",
    "gray": "#94a3b8",
}
LOCALIZED_CATEGORY_BY_LABEL = {
    label: {"label": label, "color_token": color_token}
    for label, color_token in LOCALIZED_CATEGORY_ORDER
}

UNKNOWN_CATEGORY_LABEL = "其他待归类"
PROGRESS_LABEL_MULTI_LOAN = "多头借贷风险"
PROGRESS_LABEL_FINANCIAL = "金融成熟度"
PROGRESS_LABEL_CONSUMPTION = "消费能力"
PROGRESS_LABEL_COMPLETENESS = "数据完整度"

RISK_SCORE_BY_BUCKET = {
    "<=7d": 30,
    "8-30d": 18,
    "31-90d": 5,
    "91-365d": 2,
    ">365d": 1,
    "unknown": 0,
}
ICON_BY_COLOR = {
    "blue": "Smartphone",
    "cyan": "Database",
    "green": "Search",
    "amber": "TrendingUp",
    "slate": "MousePointerClick",
    "indigo": "PieChart",
}


def build_app_profile_payload(
    uid: str,
    raw_app_data: dict[str, Any],
    application_time: str | None,
) -> dict[str, Any]:
    """Backward-compatible wrapper around the new layered App contracts."""
    feature_bundle = build_app_feature_bundle(uid, raw_app_data, application_time)
    decision_result = build_app_decision_result(feature_bundle)
    return build_app_prompt_payload(feature_bundle, decision_result)


def build_app_feature_bundle(
    uid: str,
    raw_app_data: dict[str, Any],
    application_time: str | None,
    *,
    country_code: str = "mx",
    classifier: Any = None,
) -> dict[str, Any]:
    """Build deterministic App features directly from raw records."""
    analysis_dt = _resolve_analysis_time(application_time)
    raw_apps = raw_app_data.get("apps", []) if isinstance(raw_app_data.get("apps"), list) else []
    source_file = str(raw_app_data.get("source_file", "") or "")

    deduped_apps = _dedupe_apps(raw_apps)
    normalized_apps = [_with_time_features(app, analysis_dt, classifier=classifier) for app in deduped_apps]

    raw_category_counter = Counter(
        app["category_label"] for app in normalized_apps if app["category_label"] != "Unknown"
    )
    category_distribution = _counter_to_top_share(raw_category_counter, len(normalized_apps), limit=5)

    localized_counter = Counter(app["localized_category"] for app in normalized_apps)
    localized_distribution = _counter_to_exact_share(localized_counter, len(normalized_apps))

    install_bucket_counter = Counter(app["install_bucket"] for app in normalized_apps)
    install_distribution = [
        {"bucket": bucket, "count": int(install_bucket_counter.get(bucket, 0))}
        for bucket in ("<=7d", "8-30d", "31-90d", "91-365d", ">365d", "unknown")
    ]

    lending_apps = [app for app in normalized_apps if app["signals"]["is_lending_app"]]
    bank_apps = [app for app in normalized_apps if app["signals"]["is_bank_app"]]
    ewallet_apps = [app for app in normalized_apps if app["signals"]["is_ewallet_app"]]
    gov_apps = [app for app in normalized_apps if app["signals"]["is_gov_app"]]
    remittance_apps = [app for app in normalized_apps if app["signals"]["is_remittance_app"]]
    consumption_apps = [app for app in normalized_apps if app["signals"]["is_consumption_app"]]
    recent_7d = [app for app in normalized_apps if _within_days(app, 7)]
    recent_30d = [app for app in normalized_apps if _within_days(app, 30)]
    recent_7d_lending = [app for app in lending_apps if _within_days(app, 7)]
    recent_30d_lending = [app for app in lending_apps if _within_days(app, 30)]
    recent_30d_consumption = [app for app in consumption_apps if _within_days(app, 30)]

    top_category = raw_category_counter.most_common(1)[0][0] if raw_category_counter else "Unknown"
    primary_localized_item = _primary_localized_item(localized_distribution)
    localized_top = primary_localized_item["label"] if primary_localized_item else UNKNOWN_CATEGORY_LABEL
    main_preference_share = int(primary_localized_item["share"]) if primary_localized_item else 0

    raw_counts = _build_raw_counts(raw_apps, normalized_apps)
    install_bucket_details = _build_install_bucket_details(normalized_apps)
    category_app_details = _build_category_app_details(normalized_apps)
    key_app_lists = {
        "recent_7d_lending_apps": [app["app_name"] for app in recent_7d_lending],
        "recent_30d_lending_apps": [app["app_name"] for app in recent_30d_lending],
        "bank_apps": _limit_app_names(bank_apps, 8),
        "ewallet_apps": _limit_app_names(ewallet_apps, 8),
        "gov_apps": _limit_app_names(gov_apps, 8),
        "consumption_apps": _limit_app_names(consumption_apps, 10),
        "remittance_apps": _limit_app_names(remittance_apps, 6),
    }

    risk_level = _derive_multi_loan_risk(
        recent_7d_lending_count=len(recent_7d_lending),
        recent_30d_lending_count=len(recent_30d_lending),
        lending_count=len(lending_apps),
    )
    activity_level = _derive_activity_level(len(recent_30d), len(normalized_apps))

    risk_score = _compute_multi_loan_score(lending_apps, len(recent_7d_lending))
    financial_score = min(
        100,
        len(bank_apps) * 10
        + len(ewallet_apps) * 6
        + len(gov_apps) * 18
        + (8 if bank_apps and gov_apps else 0),
    )
    consumption_diversity = len(
        {
            app["localized_category"]
            for app in consumption_apps
            if app["localized_category"] in {"电商消费", "出行外卖", "银行金融", "汇款"}
        }
    )
    consumption_score = min(
        100,
        len(consumption_apps) * 8 + len(recent_30d_consumption) * 4 + consumption_diversity * 6,
    )
    data_completeness = _data_completeness_score(normalized_apps)

    progress_metrics = [
        _progress_metric(
            PROGRESS_LABEL_MULTI_LOAN,
            risk_score,
            f"近30天借贷新增 {len(recent_30d_lending)} 个 / 近7天 {len(recent_7d_lending)} 个",
            "amber" if risk_level != "low" else "blue",
            "high" if risk_level == "high" else "mid" if risk_level == "medium" else "safe",
        ),
        _progress_metric(
            PROGRESS_LABEL_FINANCIAL,
            financial_score,
            f"银行 {len(bank_apps)} / 钱包 {len(ewallet_apps)} / 政府 {len(gov_apps)}",
            "indigo",
            "low" if gov_apps else "safe",
        ),
        _progress_metric(
            PROGRESS_LABEL_CONSUMPTION,
            consumption_score,
            f"消费相关 App {len(consumption_apps)} 个 / 近30天新增 {len(recent_30d_consumption)} 个",
            "cyan",
            "safe",
        ),
        _progress_metric(
            PROGRESS_LABEL_COMPLETENESS,
            data_completeness,
            f"有效分类与安装时间 {raw_counts['complete_record_count']} / {len(normalized_apps)}",
            "green",
            "safe",
        ),
    ]

    progress_metric_explanations = [
        {
            "key": "multi_loan_risk",
            "label": PROGRESS_LABEL_MULTI_LOAN,
            "score_formula": "<=7d=30, 8-30d=18, 31-90d=5, 91-365d=2, >365d=1；近7天借贷App>=3时至少95分。",
            "meaning": "反映近期是否出现密集安装借贷类应用的信号。",
            "inference_value": f"{risk_score} 分，风险等级 {risk_level}",
            "evidence_lines": [
                f"借贷类 App 总数 {len(lending_apps)} 个，近30天 {len(recent_30d_lending)} 个，近7天 {len(recent_7d_lending)} 个。",
                f"近30天借贷样本：{', '.join(app['app_name'] for app in recent_30d_lending[:5]) or '无'}。",
            ],
        },
        {
            "key": "financial_maturity",
            "label": PROGRESS_LABEL_FINANCIAL,
            "score_formula": "银行App*10 + 钱包App*6 + 政府App*18 + 协同加分8，封顶100。",
            "meaning": "衡量用户与银行、钱包和正式公共服务体系的接入程度。",
            "inference_value": f"{financial_score} 分，成熟度 {_derive_financial_level(len(bank_apps), len(ewallet_apps), len(gov_apps))}",
            "evidence_lines": [
                f"银行 App {len(bank_apps)} 个，钱包 App {len(ewallet_apps)} 个，政府 App {len(gov_apps)} 个。",
                f"代表应用：{', '.join(_limit_app_names(bank_apps + ewallet_apps + gov_apps, 6)) or '无'}。",
            ],
        },
        {
            "key": "consumption_ability",
            "label": PROGRESS_LABEL_CONSUMPTION,
            "score_formula": "消费类App*8 + 近30天新增*4 + 多样性*6，封顶100。",
            "meaning": "反映用户在消费、电商、出行等场景的安装覆盖与近期活跃度。",
            "inference_value": f"{consumption_score} 分，消费水平 {_derive_consumption_level(consumption_score)}",
            "evidence_lines": [
                f"消费相关 App {len(consumption_apps)} 个，近30天新增 {len(recent_30d_consumption)} 个，多样性 {consumption_diversity}。",
                f"代表应用：{', '.join(_limit_app_names(consumption_apps, 6)) or '无'}。",
            ],
        },
        {
            "key": "data_completeness",
            "label": PROGRESS_LABEL_COMPLETENESS,
            "score_formula": "有分类且有安装时间的App数 / 总App数 * 100。",
            "meaning": "衡量当前用户 App 明细是否足够完整。",
            "inference_value": f"{data_completeness} 分",
            "evidence_lines": [
                f"原始行数 {raw_counts['row_count']}，去重后 {raw_counts['deduped_count']}。",
                f"缺失分类 {raw_counts['missing_category_count']}，缺失安装时间 {raw_counts['missing_install_time_count']}。",
            ],
        },
    ]

    aggregate_features = {
        "installed_app_count": len(normalized_apps),
        "recent_install_count_7d": len(recent_7d),
        "recent_install_count_30d": len(recent_30d),
        "activity_level": activity_level,
        "category_distribution": category_distribution,
        "localized_category_distribution": localized_distribution,
        "install_time_distribution": install_distribution,
    }
    signal_features = {
        "lending_app_count": len(lending_apps),
        "recent_7d_lending_count": len(recent_7d_lending),
        "recent_30d_lending_count": len(recent_30d_lending),
        "bank_app_count": len(bank_apps),
        "ewallet_app_count": len(ewallet_apps),
        "gov_app_count": len(gov_apps),
        "consumption_app_count": len(consumption_apps),
        "remittance_app_count": len(remittance_apps),
        "top_category": top_category,
        "localized_top_category": localized_top,
        "main_preference_share": main_preference_share,
    }
    evidence_features = {
        "source_file": source_file,
        "raw_counts": raw_counts,
        "category_distribution": category_distribution,
        "localized_category_distribution": localized_distribution,
        "install_time_distribution": install_distribution,
        "install_bucket_details": install_bucket_details,
        "category_app_details": category_app_details,
        "key_app_lists": key_app_lists,
    }
    visual_features = {
        "timeline_candidates": _build_timeline(
            apps_with_timing=normalized_apps,
            localized_top=localized_top,
            activity_level=activity_level,
            multi_loan_risk=risk_level,
        ),
        "palette_candidates": _palette_for_distribution(localized_distribution),
        "progress_metric_inputs": progress_metrics,
        "progress_metric_explanations": progress_metric_explanations,
    }

    return {
        "uid": uid,
        "country_code": country_code,
        "application_time": analysis_dt.isoformat(),
        "normalized_apps": normalized_apps[:120],
        "aggregate_features": aggregate_features,
        "signal_features": signal_features,
        "evidence_features": evidence_features,
        "visual_features": visual_features,
        "feature_status": "ok" if normalized_apps else "partial",
        "errors": [],
    }


def build_app_decision_result(feature_bundle: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic decisions directly from App features."""
    aggregate = feature_bundle.get("aggregate_features", {})
    signals = feature_bundle.get("signal_features", {})
    evidence = feature_bundle.get("evidence_features", {})
    visual_features = feature_bundle.get("visual_features", {})

    bank_count = int(signals.get("bank_app_count", 0) or 0)
    ewallet_count = int(signals.get("ewallet_app_count", 0) or 0)
    gov_count = int(signals.get("gov_app_count", 0) or 0)
    lending_count = int(signals.get("lending_app_count", 0) or 0)
    recent_7d_lending_count = int(signals.get("recent_7d_lending_count", 0) or 0)
    recent_30d_lending_count = int(signals.get("recent_30d_lending_count", 0) or 0)
    installed_app_count = int(aggregate.get("installed_app_count", 0) or 0)
    recent_install_count_30d = int(aggregate.get("recent_install_count_30d", 0) or 0)
    localized_top = str(signals.get("localized_top_category", UNKNOWN_CATEGORY_LABEL) or UNKNOWN_CATEGORY_LABEL)

    risk_level = _derive_multi_loan_risk(
        recent_7d_lending_count=recent_7d_lending_count,
        recent_30d_lending_count=recent_30d_lending_count,
        lending_count=lending_count,
    )
    financial_level = _derive_financial_level(bank_count, ewallet_count, gov_count)
    consumption_level = _derive_consumption_level(
        _progress_value(visual_features, PROGRESS_LABEL_CONSUMPTION)
    )
    activity_level = str(aggregate.get("activity_level", "unknown") or "unknown")

    key_app_lists = evidence.get("key_app_lists", {}) if isinstance(evidence.get("key_app_lists"), dict) else {}
    risk_reasoning_seed = (
        f"近7天借贷新增 {recent_7d_lending_count} 个，近30天借贷新增 {recent_30d_lending_count} 个，"
        f"历史借贷类 App 总数 {lending_count} 个。"
        f" 关键样本包括 {', '.join(key_app_lists.get('recent_30d_lending_apps', [])[:4]) or '无'}。"
    )
    financial_reasoning_seed = (
        f"银行类 App：{', '.join(key_app_lists.get('bank_apps', [])[:4]) or '无'}；"
        f"钱包类 App：{', '.join(key_app_lists.get('ewallet_apps', [])[:4]) or '无'}；"
        f"政府类 App：{', '.join(key_app_lists.get('gov_apps', [])[:4]) or '无'}。"
    )
    consumption_reasoning_seed = (
        f"消费相关 App 包括 {', '.join(key_app_lists.get('consumption_apps', [])[:5]) or '无'}，"
        f"结合近30天新增 {recent_install_count_30d} 个 App 与类别多样性形成判断。"
    )

    recommendation_action = (
        "reject" if risk_level == "high" else "manual_review" if risk_level == "medium" else "pass"
    )
    recommendation_reason = (
        "近30天借贷安装密度较高，建议优先控制风险。"
        if risk_level == "high"
        else "存在一定借贷安装信号，建议结合更多维度人工复核。"
        if risk_level == "medium"
        else "借贷安装信号较弱，可作为相对稳健用户继续观察。"
    )

    summary_seed = (
        f"该用户共安装 {installed_app_count} 个 App，主要偏好集中在 {localized_top}，"
        f"近30天新增 {recent_install_count_30d} 个 App，多头借贷风险 {risk_level}。"
    )
    app_insight_seed = _build_app_insight(
        installed_count=installed_app_count,
        localized_top=localized_top,
        risk_level=risk_level,
        financial_level=financial_level,
        consumption_level=consumption_level,
        recent_30d_count=recent_install_count_30d,
        recent_30d_lending_count=recent_30d_lending_count,
        lending_names=key_app_lists.get("recent_30d_lending_apps", []),
        bank_names=key_app_lists.get("bank_apps", []),
        consumption_names=key_app_lists.get("consumption_apps", []),
    )

    metrics = {
        "application_time": feature_bundle.get("application_time", ""),
        "installed_app_count": installed_app_count,
        "recent_install_count_30d": recent_install_count_30d,
        "lending_app_count": lending_count,
        "recent_7d_lending_count": recent_7d_lending_count,
        "recent_30d_lending_count": recent_30d_lending_count,
        "bank_app_count": bank_count,
        "ewallet_app_count": ewallet_count,
        "gov_app_count": gov_count,
        "consumption_app_count": int(signals.get("consumption_app_count", 0) or 0),
        "remittance_app_count": int(signals.get("remittance_app_count", 0) or 0),
        "top_category": str(signals.get("top_category", "Unknown") or "Unknown"),
        "localized_top_category": localized_top,
        "multi_loan_risk_level": risk_level,
        "financial_maturity_level": financial_level,
        "consumption_ability_level": consumption_level,
    }
    visuals = {
        "top_category": str(signals.get("top_category", "Unknown") or "Unknown"),
        "installed_app_count": installed_app_count,
        "recent_install_count_30d": recent_install_count_30d,
        "main_preference_share": int(signals.get("main_preference_share", 0) or 0),
        "chart_palette": visual_features.get("palette_candidates", []),
        "progress_metrics": visual_features.get("progress_metric_inputs", []),
        "progress_metric_explanations": visual_features.get("progress_metric_explanations", []),
    }
    tags_rule = _build_display_labels(localized_top, risk_level, financial_level, consumption_level)
    tags_rule.append(
        {
            "high": "安装活跃度高",
            "medium": "安装活跃度中等",
            "low": "安装活跃度较低",
        }.get(activity_level, "安装活跃度待确认")
    )

    return {
        "uid": feature_bundle.get("uid", ""),
        "country_code": feature_bundle.get("country_code", "mx"),
        "decision_status": "ok",
        "summary_seed": summary_seed,
        "app_insight_seed": app_insight_seed,
        "activity_level": activity_level,
        "risk_assessment": {
            "level": risk_level,
            "score": _progress_value(visual_features, PROGRESS_LABEL_MULTI_LOAN),
            "lending_app_count": lending_count,
            "recent_7d_lending_apps": key_app_lists.get("recent_7d_lending_apps", []),
            "recent_30d_lending_apps": key_app_lists.get("recent_30d_lending_apps", []),
            "reasoning_seed": risk_reasoning_seed,
        },
        "financial_maturity": {
            "level": financial_level,
            "score": _progress_value(visual_features, PROGRESS_LABEL_FINANCIAL),
            "has_bank_app": bank_count > 0,
            "has_ewallet": ewallet_count > 0,
            "has_gov_app": gov_count > 0,
            "supporting_apps": (
                key_app_lists.get("bank_apps", [])
                + key_app_lists.get("ewallet_apps", [])
                + key_app_lists.get("gov_apps", [])
            )[:10],
            "reasoning_seed": financial_reasoning_seed,
        },
        "consumption_profile": {
            "level": consumption_level,
            "score": _progress_value(visual_features, PROGRESS_LABEL_CONSUMPTION),
            "preferred_categories": [
                item.get("label", "Unknown")
                for item in aggregate.get("localized_category_distribution", [])[:4]
            ],
            "reasoning_seed": consumption_reasoning_seed,
        },
        "metrics": metrics,
        "tags_rule": tags_rule,
        "recommendation": {
            "action": recommendation_action,
            "reason_seed": recommendation_reason,
        },
        "visuals": visuals,
        "timeline": visual_features.get("timeline_candidates", []),
        "errors": [],
    }


def build_app_prompt_payload(
    feature_bundle: dict[str, Any],
    decision_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a prompt payload from feature and decision outputs only."""
    decision_result = decision_result or build_app_decision_result(feature_bundle)
    aggregate = feature_bundle.get("aggregate_features", {})
    signals = feature_bundle.get("signal_features", {})
    evidence = feature_bundle.get("evidence_features", {})
    visuals = decision_result.get("visuals", {})

    return {
        "uid": feature_bundle.get("uid", ""),
        "source_file": evidence.get("source_file", ""),
        "raw_counts": evidence.get("raw_counts", {}),
        "application_time": feature_bundle.get("application_time", ""),
        "app_overview": {
            "installed_app_count": int(aggregate.get("installed_app_count", 0) or 0),
            "recent_install_count_7d": int(aggregate.get("recent_install_count_7d", 0) or 0),
            "recent_install_count_30d": int(aggregate.get("recent_install_count_30d", 0) or 0),
            "top_category": str(signals.get("top_category", "Unknown") or "Unknown"),
            "localized_top_category": str(
                signals.get("localized_top_category", UNKNOWN_CATEGORY_LABEL) or UNKNOWN_CATEGORY_LABEL
            ),
            "main_preference_share": int(signals.get("main_preference_share", 0) or 0),
            "activity_level": str(decision_result.get("activity_level", "unknown") or "unknown"),
        },
        "category_distribution": evidence.get("category_distribution", []),
        "localized_category_distribution": evidence.get("localized_category_distribution", []),
        "install_time_distribution": evidence.get("install_time_distribution", []),
        "install_bucket_details": evidence.get("install_bucket_details", {}),
        "category_app_details": evidence.get("category_app_details", {}),
        "signal_counts": {
            "lending_app_count": int(signals.get("lending_app_count", 0) or 0),
            "recent_7d_lending_count": int(signals.get("recent_7d_lending_count", 0) or 0),
            "recent_30d_lending_count": int(signals.get("recent_30d_lending_count", 0) or 0),
            "bank_app_count": int(signals.get("bank_app_count", 0) or 0),
            "ewallet_app_count": int(signals.get("ewallet_app_count", 0) or 0),
            "gov_app_count": int(signals.get("gov_app_count", 0) or 0),
            "consumption_app_count": int(signals.get("consumption_app_count", 0) or 0),
            "remittance_app_count": int(signals.get("remittance_app_count", 0) or 0),
        },
        "key_app_lists": evidence.get("key_app_lists", {}),
        "default_inference": {
            "summary": decision_result.get("summary_seed", ""),
            "activity_level": decision_result.get("activity_level", "unknown"),
            "multi_loan_risk_level": decision_result.get("risk_assessment", {}).get("level", "unknown"),
            "financial_maturity_level": decision_result.get("financial_maturity", {}).get("level", "unknown"),
            "consumption_ability_level": decision_result.get("consumption_profile", {}).get("level", "unknown"),
            "app_insight": decision_result.get("app_insight_seed", {}),
        },
        "timeline_candidates": decision_result.get("timeline", []),
        "visual_defaults": {
            "top_category": visuals.get("top_category", "Unknown"),
            "installed_app_count": int(visuals.get("installed_app_count", 0) or 0),
            "recent_install_count_30d": int(visuals.get("recent_install_count_30d", 0) or 0),
            "main_preference_share": int(visuals.get("main_preference_share", 0) or 0),
            "chart_palette": visuals.get("chart_palette", []),
            "progress_metrics": visuals.get("progress_metrics", []),
            "progress_metric_explanations": visuals.get("progress_metric_explanations", []),
        },
        "apps": feature_bundle.get("normalized_apps", []),
    }


def _resolve_analysis_time(application_time: str | None) -> datetime:
    if application_time:
        try:
            normalized = application_time.replace("Z", "+00:00")
            return datetime.fromisoformat(normalized).astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _build_raw_counts(raw_apps: list[dict[str, Any]], normalized_apps: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "row_count": len(raw_apps),
        "deduped_count": len(normalized_apps),
        "missing_category_count": sum(
            1 for app in normalized_apps if not app.get("ai_category_level_2_CN") and not app.get("gp_category")
        ),
        "missing_install_time_count": sum(1 for app in normalized_apps if not app.get("install_time_iso")),
        "complete_record_count": sum(
            1
            for app in normalized_apps
            if app.get("install_time_iso") and app.get("category_label") != "Unknown"
        ),
    }


def _dedupe_apps(raw_apps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[str, dict[str, Any]] = {}
    for app in raw_apps:
        if not isinstance(app, dict):
            continue
        package_name = str(app.get("app_package") or "").strip()
        key = package_name or str(app.get("app_name") or "").strip().lower()
        if not key:
            continue
        candidate = dict(app)
        previous = deduped.get(key)
        if previous is None:
            deduped[key] = candidate
            continue

        prev_install = _to_epoch_ms(previous.get("first_install_time"))
        next_install = _to_epoch_ms(candidate.get("first_install_time"))
        prev_update = _to_epoch_ms(previous.get("last_update_time"))
        next_update = _to_epoch_ms(candidate.get("last_update_time"))
        if next_install is not None and (prev_install is None or next_install < prev_install):
            previous["first_install_time"] = candidate.get("first_install_time")
        if next_update is not None and (prev_update is None or next_update > prev_update):
            previous["last_update_time"] = candidate.get("last_update_time")
        if not previous.get("ai_category_level_2_CN") and candidate.get("ai_category_level_2_CN"):
            previous["ai_category_level_2_CN"] = candidate.get("ai_category_level_2_CN")
        if not previous.get("gp_category") and candidate.get("gp_category"):
            previous["gp_category"] = candidate.get("gp_category")
    return list(deduped.values())


def _with_time_features(
    app: dict[str, Any],
    analysis_dt: datetime,
    *,
    classifier: Any = None,
) -> dict[str, Any]:
    install_dt = _to_datetime(app.get("first_install_time"))
    update_dt = _to_datetime(app.get("last_update_time"))
    app_name = str(app.get("app_name") or "").strip()
    package_name = str(app.get("app_package") or "").strip()
    category_label = (
        str(app.get("ai_category_level_2_CN") or "").strip()
        or str(app.get("gp_category") or "").strip()
        or "Unknown"
    )
    days_since_install = max(0, int((analysis_dt - install_dt).total_seconds() // 86400)) if install_dt else None
    localized_category = _infer_localized_category(
        app_name=app_name,
        package_name=package_name,
        ai_category=str(app.get("ai_category_level_2_CN") or ""),
        gp_category=str(app.get("gp_category") or ""),
        classifier=classifier,
    )
    haystack = " ".join(
        [
            app_name.lower(),
            package_name.lower(),
            str(app.get("ai_category_level_2_CN") or "").lower(),
            str(app.get("gp_category") or "").lower(),
        ]
    )
    signals = {
        "is_lending_app": localized_category == "借贷竞争" or _contains_any(haystack, LENDING_KEYWORDS),
        "is_bank_app": localized_category == "银行金融" or _contains_any(haystack, BANK_KEYWORDS),
        "is_ewallet_app": _contains_any(haystack, EWALLET_KEYWORDS),
        "is_gov_app": localized_category == "政府公共服务" or _contains_any(haystack, GOV_KEYWORDS),
        "is_consumption_app": localized_category in {"电商消费", "出行外卖"} or _contains_any(haystack, CONSUMPTION_KEYWORDS),
        "is_remittance_app": localized_category == "汇款" or _contains_any(haystack, REMITTANCE_KEYWORDS),
    }
    return {
        **app,
        "install_time_iso": install_dt.isoformat() if install_dt else "",
        "last_update_time_iso": update_dt.isoformat() if update_dt else "",
        "install_time_display": install_dt.strftime("%Y-%m-%d %H:%M") if install_dt else "Unknown",
        "last_update_time_display": update_dt.strftime("%Y-%m-%d %H:%M") if update_dt else "Unknown",
        "days_since_install": days_since_install,
        "install_bucket": _bucketize_days(days_since_install),
        "category_label": category_label,
        "localized_category": localized_category,
        "localized_color_token": LOCALIZED_CATEGORY_BY_LABEL[localized_category]["color_token"],
        "canonical_category": _canonical_category(localized_category),
        "signals": signals,
        "is_lending_app": signals["is_lending_app"],
        "is_bank_app": signals["is_bank_app"],
        "is_ewallet_app": signals["is_ewallet_app"],
        "is_gov_app": signals["is_gov_app"],
        "is_consumption_app": signals["is_consumption_app"],
        "is_remittance_app": signals["is_remittance_app"],
    }


def _canonical_category(localized_category: str) -> str:
    return {
        "借贷竞争": "loan",
        "银行金融": "bank",
        "汇款": "remittance",
        "政府公共服务": "gov",
        "电商消费": "consumption",
        "出行外卖": "delivery_travel",
        "社交媒体": "social",
        "教育职业": "education",
        "游戏娱乐": "game",
    }.get(localized_category, "other")


def _infer_localized_category(
    *,
    app_name: str,
    package_name: str,
    ai_category: str,
    gp_category: str,
    classifier: Any = None,
) -> str:
    haystack = " ".join(
        [app_name.lower(), package_name.lower(), ai_category.lower(), gp_category.lower()]
    )
    rules = [
        ("汇款", REMITTANCE_KEYWORDS),
        ("借贷竞争", LENDING_KEYWORDS),
        ("政府公共服务", GOV_KEYWORDS),
        ("银行金融", BANK_KEYWORDS + EWALLET_KEYWORDS),
        ("社交媒体", SOCIAL_KEYWORDS),
        ("出行外卖", DELIVERY_TRAVEL_KEYWORDS),
        ("电商消费", ECOMMERCE_KEYWORDS),
        ("教育职业", EDUCATION_KEYWORDS),
        ("游戏娱乐", GAME_KEYWORDS),
    ]
    for label, keywords in rules:
        if _contains_any(haystack, keywords):
            return label

    fallback_haystack = f"{ai_category.lower()} {gp_category.lower()}"
    fallback_rules = [
        ("借贷竞争", ("借贷", "贷款", "credit", "loan", "prestamo")),
        ("银行金融", ("银行", "钱包", "金融", "财务", "bank", "wallet", "financ")),
        ("社交媒体", ("社交", "通讯", "social", "messag")),
        ("出行外卖", ("出行", "导航", "旅行", "地图", "ride", "travel", "food")),
        ("电商消费", ("电商", "购物", "零售", "shopping", "retail", "bnpl")),
        ("游戏娱乐", ("游戏", "entertain", "video game")),
        ("教育职业", ("教育", "求职", "招聘", "学习", "business", "career")),
        ("政府公共服务", ("政府", "公共", "税", "社保", "gov", "public")),
        ("汇款", ("remittance", "汇款", "跨境支付")),
    ]
    for label, keywords in fallback_rules:
        if _contains_any(fallback_haystack, keywords):
            return label

    if classifier is not None:
        try:
            inferred = classifier.classify(
                app_name=app_name,
                package_name=package_name,
                ai_category=ai_category,
                gp_category=gp_category,
            )
        except Exception:  # noqa: BLE001
            inferred = None
        if inferred:
            return inferred

    return UNKNOWN_CATEGORY_LABEL


def _to_datetime(value: Any) -> datetime | None:
    epoch_ms = _to_epoch_ms(value)
    if epoch_ms is None:
        return None
    try:
        return datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _to_epoch_ms(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _bucketize_days(days: int | None) -> str:
    if days is None:
        return "unknown"
    if days <= 7:
        return "<=7d"
    if days <= 30:
        return "8-30d"
    if days <= 90:
        return "31-90d"
    if days <= 365:
        return "91-365d"
    return ">365d"


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords if keyword)


def _within_days(app: dict[str, Any], limit: int) -> bool:
    days = app.get("days_since_install")
    return days is not None and int(days) <= limit


def _counter_to_top_share(
    counter: Counter[str],
    total: int,
    *,
    limit: int,
) -> list[dict[str, Any]]:
    if total <= 0:
        return []
    return [
        {"label": label, "count": int(count), "share": round(count * 100 / total)}
        for label, count in counter.most_common(limit)
    ]


def _counter_to_exact_share(counter: Counter[str], total: int) -> list[dict[str, Any]]:
    if total <= 0:
        return []

    rows: list[dict[str, Any]] = []
    remainders: list[tuple[float, int]] = []
    current_total = 0
    present_rows = []
    for index, (label, color_token) in enumerate(LOCALIZED_CATEGORY_ORDER):
        count = int(counter.get(label, 0))
        if count <= 0:
            continue
        raw_share = count * 100 / total
        share = floor(raw_share)
        current_total += share
        present_rows.append(
            {
                "label": label,
                "count": count,
                "share": share,
                "color_token": color_token,
                "order_index": index,
            }
        )
        remainders.append((raw_share - share, index))

    remainder_points = max(0, 100 - current_total)
    index_by_order = {row["label"]: pos for pos, row in enumerate(present_rows)}
    for _, original_index in sorted(remainders, key=lambda item: (-item[0], item[1]))[:remainder_points]:
        label = LOCALIZED_CATEGORY_ORDER[original_index][0]
        present_rows[index_by_order[label]]["share"] += 1

    for row in sorted(present_rows, key=lambda item: (-item["count"], item["order_index"])):
        row.pop("order_index", None)
        rows.append(row)
    return rows


def _compute_multi_loan_score(lending_apps: list[dict[str, Any]], recent_7d_lending_count: int) -> int:
    score = sum(RISK_SCORE_BY_BUCKET.get(str(app.get("install_bucket", "unknown")), 0) for app in lending_apps)
    if recent_7d_lending_count >= 3:
        score = max(score, 95)
    return min(100, score)


def _derive_activity_level(recent_30d_count: int, installed_count: int) -> str:
    if recent_30d_count >= 10 or installed_count >= 40:
        return "high"
    if recent_30d_count >= 4 or installed_count >= 18:
        return "medium"
    return "low"


def _derive_multi_loan_risk(
    *,
    recent_7d_lending_count: int,
    recent_30d_lending_count: int,
    lending_count: int,
) -> str:
    if recent_7d_lending_count >= 3 or recent_30d_lending_count >= 3:
        return "high"
    if recent_30d_lending_count >= 1 or lending_count >= 4:
        return "medium"
    return "low"


def _derive_consumption_level(consumption_score: int) -> str:
    if consumption_score >= 80:
        return "high"
    if consumption_score >= 60:
        return "medium_high"
    if consumption_score >= 35:
        return "medium"
    return "low"


def _derive_financial_level(bank_count: int, ewallet_count: int, gov_count: int) -> str:
    if bank_count >= 2 or (bank_count >= 1 and gov_count >= 1):
        return "banked"
    if bank_count >= 1 or ewallet_count >= 1:
        return "semi_banked"
    return "non_banked"


def _build_timeline(
    *,
    apps_with_timing: list[dict[str, Any]],
    localized_top: str,
    activity_level: str,
    multi_loan_risk: str,
) -> list[dict[str, Any]]:
    sorted_apps = sorted(
        [app for app in apps_with_timing if app.get("install_time_iso")],
        key=lambda item: item["install_time_iso"],
        reverse=True,
    )
    latest_app = sorted_apps[0] if sorted_apps else {}
    return [
        {
            "time": str(latest_app.get("install_time_display") or "N/A"),
            "title": "最近安装行为",
            "sub": (
                f"最近安装应用：{latest_app.get('app_name')} / {latest_app.get('localized_category')}"
                if latest_app
                else "暂无最近安装时间"
            ),
            "icon": ICON_BY_COLOR["blue"],
            "color_token": "blue",
        },
        {
            "time": "分类聚合",
            "title": "本地化偏好识别",
            "sub": f"主要偏好类别：{localized_top}",
            "icon": ICON_BY_COLOR["cyan"],
            "color_token": "cyan",
        },
        {
            "time": "风险扫描",
            "title": "安装时间衰减评估",
            "sub": f"多头借贷风险：{multi_loan_risk}",
            "icon": ICON_BY_COLOR["amber"],
            "color_token": "amber",
        },
        {
            "time": "画像完成",
            "title": "活跃度与标签生成",
            "sub": f"Activity Level: {activity_level}",
            "icon": ICON_BY_COLOR["slate"],
            "color_token": "slate",
        },
    ]


def _progress_metric(
    label: str,
    value: int,
    text: str,
    color_token: str,
    risk_level: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "value": max(0, min(100, int(value))),
        "text": text,
        "color_token": color_token,
        "risk_level": risk_level,
    }


def _progress_value(visual_features: dict[str, Any], label: str) -> int:
    for item in visual_features.get("progress_metric_inputs", []):
        if str(item.get("label") or "") == label:
            return int(item.get("value", 0) or 0)
    return 0


def _data_completeness_score(apps_with_timing: list[dict[str, Any]]) -> int:
    if not apps_with_timing:
        return 0
    complete_rows = sum(
        1
        for app in apps_with_timing
        if app.get("category_label") != "Unknown" and app.get("install_time_iso")
    )
    return round(complete_rows * 100 / len(apps_with_timing))


def _build_install_bucket_details(apps_with_timing: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for app in sorted(
        apps_with_timing,
        key=lambda item: (item.get("days_since_install") is None, item.get("days_since_install") or 10**9),
    ):
        grouped[str(app.get("install_bucket", "unknown"))][str(app.get("localized_category", UNKNOWN_CATEGORY_LABEL))].append(
            {
                "app_name": app.get("app_name", ""),
                "first_install_time": app.get("install_time_display", "Unknown"),
                "last_update_time": app.get("last_update_time_display", "Unknown"),
            }
        )

    response: dict[str, list[dict[str, Any]]] = {}
    for bucket in ("<=7d", "8-30d", "31-90d", "91-365d", ">365d", "unknown"):
        category_map = grouped.get(bucket, {})
        response[bucket] = [
            {
                "localized_category": label,
                "count": len(category_map[label]),
                "apps": category_map[label],
            }
            for label, _ in LOCALIZED_CATEGORY_ORDER
            if category_map.get(label)
        ]
    return response


def _build_category_app_details(apps_with_timing: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for app in sorted(
        apps_with_timing,
        key=lambda item: (
            item.get("localized_category") == UNKNOWN_CATEGORY_LABEL,
            item.get("days_since_install") is None,
            item.get("days_since_install") or 10**9,
            str(item.get("app_name") or "").lower(),
        ),
    ):
        localized_category = str(app.get("localized_category") or UNKNOWN_CATEGORY_LABEL)
        grouped[localized_category].append(
            {
                "app_name": app.get("app_name", ""),
                "package_name": app.get("app_package", ""),
                "localized_category": localized_category,
                "first_install_time": app.get("install_time_display", "Unknown"),
                "last_update_time": app.get("last_update_time_display", "Unknown"),
                "gp_category": app.get("gp_category", "") or "Unknown",
                "ai_category_level_2_CN": app.get("ai_category_level_2_CN", "") or "Unknown",
            }
        )

    response: dict[str, dict[str, Any]] = {}
    for label, color_token in LOCALIZED_CATEGORY_ORDER:
        apps = grouped.get(label, [])
        if not apps:
            continue
        response[label] = {
            "localized_category": label,
            "color_token": color_token,
            "count": len(apps),
            "apps": apps,
        }
    return response


def _build_app_insight(
    *,
    installed_count: int,
    localized_top: str,
    risk_level: str,
    financial_level: str,
    consumption_level: str,
    recent_30d_count: int,
    recent_30d_lending_count: int,
    lending_names: list[str],
    bank_names: list[str],
    consumption_names: list[str],
) -> dict[str, Any]:
    lending_text = ", ".join(lending_names[:3]) or "无明显借贷类样本"
    bank_text = ", ".join(bank_names[:3]) or "无明显银行类样本"
    consumption_text = ", ".join(consumption_names[:3]) or "无明显消费类样本"
    return {
        "summary": (
            f"该用户当前共安装 {installed_count} 个 App，偏好重点落在 {localized_top}。"
            f" 近30天新增 {recent_30d_count} 个 App，近期借贷新增 {recent_30d_lending_count} 个。"
        ),
        "reasons": [
            f"借贷风险等级为 {_risk_level_cn(risk_level)}，代表样本包括：{lending_text}。",
            f"金融成熟度为 {_financial_level_cn(financial_level)}，支撑应用包括：{bank_text}。",
            f"消费能力判断为 {_consumption_level_cn(consumption_level)}，消费相关应用包括：{consumption_text}。",
        ],
        "labels": _build_display_labels(localized_top, risk_level, financial_level, consumption_level),
    }


def _build_display_labels(
    localized_top: str,
    risk_level: str,
    financial_level: str,
    consumption_level: str,
) -> list[str]:
    labels = [
        {
            "high": "近期多头高风险",
            "medium": "借贷风险中等",
            "low": "借贷风险较低",
        }.get(risk_level, "借贷信号待确认"),
        {
            "banked": "银行化用户",
            "semi_banked": "半银行化用户",
            "non_banked": "非银行化用户",
        }.get(financial_level, "金融成熟度待确认"),
        {
            "high": "高消费能力",
            "medium_high": "中偏上消费能力",
            "medium": "中等消费能力",
            "low": "消费能力偏弱",
        }.get(consumption_level, "消费能力待确认"),
    ]
    if localized_top and localized_top != UNKNOWN_CATEGORY_LABEL:
        labels.insert(0, f"{localized_top}偏好")
    return labels[:4]


def _risk_level_cn(level: str) -> str:
    return {"high": "高", "medium": "中", "low": "低"}.get(level, "待确认")


def _financial_level_cn(level: str) -> str:
    return {
        "banked": "银行化",
        "semi_banked": "半银行化",
        "non_banked": "非银行化",
    }.get(level, "待确认")


def _consumption_level_cn(level: str) -> str:
    return {
        "high": "高",
        "medium_high": "中偏上",
        "medium": "中等",
        "low": "偏弱",
    }.get(level, "待确认")


def _palette_for_distribution(distribution: list[dict[str, Any]]) -> list[str]:
    return [
        LOCALIZED_CATEGORY_COLORS.get(str(item.get("color_token") or "blue"), "#3b82f6")
        for item in distribution
    ] or ["#3b82f6"]


def _limit_app_names(apps: list[dict[str, Any]], limit: int) -> list[str]:
    names: list[str] = []
    for item in apps[:limit]:
        if isinstance(item, dict):
            name = str(item.get("app_name", "") or "").strip()
        else:
            name = str(item or "").strip()
        if name:
            names.append(name)
    return names


def _primary_localized_item(distribution: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in distribution:
        if str(item.get("label") or "") != UNKNOWN_CATEGORY_LABEL:
            return item
    return distribution[0] if distribution else None
