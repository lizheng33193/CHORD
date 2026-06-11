"""Build standardized Behavior prepared records from local or upstream payloads."""

from __future__ import annotations

import csv
import json
import re
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.country_packs.behavior_profile import load_behavior_country_pack
from app.scripts.behavior_preprocessor import preprocess_behavior_data


BEHAVIOR_PREPARED_SCHEMA_VERSION = "behavior-prepared-v1"
MEXICO_OFFSET = timezone(timedelta(hours=-6))
_PREPARED_REQUIRED_KEYS = {
    "uid",
    "country_code",
    "schema_version",
    "profile_header",
    "session_summary",
    "engagement_signals",
    "repayment_signals",
    "product_intent_signals",
    "churn_signals",
    "contact_signals",
    "timeline_sections",
    "timeline_sections_raw",
    "timeline_sections_compact",
    "timeline_insights",
    "source_meta",
}


def is_behavior_prepared_record(payload: Any) -> bool:
    """Return whether the payload already matches the prepared-record contract."""
    if not isinstance(payload, dict):
        return False
    if payload.get("schema_version") != BEHAVIOR_PREPARED_SCHEMA_VERSION:
        return False
    return _PREPARED_REQUIRED_KEYS.issubset(set(payload.keys()))


def prepare_behavior_record_from_csv_file(
    file_path: Path,
    uid: str,
    *,
    country_code: str = "mx",
) -> tuple[dict[str, Any], list[str]]:
    """Parse a uid-scoped raw behavior CSV file into a prepared record."""
    rows: list[dict[str, Any]] = []
    try:
        with Path(file_path).open("r", encoding="utf-8-sig", newline="") as csv_file:
            rows = list(csv.DictReader(csv_file))
    except Exception as exc:  # pylint: disable=broad-except
        return {}, [f"csv_read_failed:{exc}"]

    if not rows:
        return {}, ["behavior_csv_empty"]

    return prepare_behavior_record_from_payload(
        uid,
        {
            "uid": uid,
            "source_kind": "raw_behavior_csv",
            "source_type": "local_file",
            "source_file": str(file_path),
            "rows": rows,
        },
        country_code=country_code,
    )


def prepare_behavior_record_from_payload(
    uid: str,
    payload: dict[str, Any],
    *,
    country_code: str = "mx",
) -> tuple[dict[str, Any], list[str]]:
    """Convert repository payload variants into a standardized prepared record."""
    normalized_uid = str(uid or "").strip()
    if not isinstance(payload, dict):
        return {}, ["behavior_payload_not_object"]

    if is_behavior_prepared_record(payload):
        prepared = deepcopy(payload)
        prepared["uid"] = normalized_uid or str(prepared.get("uid", "") or "")
        prepared["country_code"] = str(
            prepared.get("country_code", country_code) or country_code
        ).lower()
        return prepared, []

    if payload.get("schema_version"):
        return {}, ["prepared_schema_mismatch"]

    source_kind = str(payload.get("source_kind", "") or "").strip().lower()
    if source_kind == "raw_behavior_csv" or isinstance(payload.get("rows"), list):
        return _prepare_from_raw_behavior_payload(
            normalized_uid,
            payload,
            country_code=country_code,
        )

    return _prepare_from_legacy_summary(
        normalized_uid,
        payload,
        country_code=country_code,
    )


def _prepare_from_raw_behavior_payload(
    uid: str,
    payload: dict[str, Any],
    *,
    country_code: str,
) -> tuple[dict[str, Any], list[str]]:
    pack = load_behavior_country_pack(country_code)
    warnings: list[str] = []
    rows = [row for row in payload.get("rows", []) if isinstance(row, dict)]
    if not rows and isinstance(payload.get("row"), dict):
        rows = [payload["row"]]
    if not rows:
        return {}, ["behavior_csv_rows_missing"]

    scoped_rows = _filter_rows_by_uid(rows, uid)
    if not scoped_rows:
        return {}, ["behavior_csv_rows_missing"]

    first_row = scoped_rows[0]
    if _looks_like_legacy_summary_row(first_row):
        legacy_payload = dict(first_row)
        legacy_payload.update(
            {
                "uid": uid,
                "source_type": payload.get("source_type", "local_file"),
                "source_kind": "legacy_behavior_summary_csv",
                "source_file": payload.get("source_file", ""),
            }
        )
        return _prepare_from_legacy_summary(uid, legacy_payload, country_code=country_code)

    normalized_events = [_normalize_event_row(row, pack=pack) for row in scoped_rows]
    normalized_events = [event for event in normalized_events if event]
    if not normalized_events:
        return {}, ["behavior_events_empty_after_normalization"]

    normalized_events.sort(key=lambda item: item["event_dt"])
    total_events = len(normalized_events)
    unique_days = sorted({item["event_dt"].date().isoformat() for item in normalized_events})
    active_days_30d = _count_active_days_30d(normalized_events)
    session_summary = _build_session_summary(normalized_events)
    purchase_preference = _derive_purchase_preference(normalized_events)
    proxy_profile = preprocess_behavior_data(
        {
            "avg_session_minutes": session_summary["avg_session_minutes"],
            "login_days_30d": active_days_30d,
            "purchase_preference": purchase_preference,
        }
    )
    timeline_sections_raw = _build_timeline_sections(normalized_events, pack=pack)
    timeline_sections_compact = _build_compact_timeline_sections(
        timeline_sections_raw,
        pack=pack,
    )
    timeline_sections = timeline_sections_compact
    timeline_insights = _build_timeline_insights(
        normalized_events,
        proxy_profile,
        timeline_sections_compact,
        pack=pack,
    )
    contact_signals = _build_contact_signals(normalized_events, proxy_profile, pack=pack)
    global_info = _build_global_info(normalized_events, uid)
    engagement_signals = {
        "engagement_score": int(proxy_profile.get("engagement_score", 0) or 0),
        "engagement_level": str(proxy_profile.get("engagement_level", "light") or "light"),
        "active_days_30d": active_days_30d,
        "session_count": session_summary["session_count"],
        "avg_session_minutes": session_summary["avg_session_minutes"],
        "deep_session_count": session_summary["deep_session_count"],
        "recent_7d_event_count": session_summary["recent_7d_event_count"],
        "analysis_mode": "raw_event_timeline",
    }
    repayment_signals = {
        "repayment_willingness_level": str(
            proxy_profile.get("repayment_willingness", "medium") or "medium"
        ),
        "repayment_event_count": _count_events_by_stage(normalized_events, "repayment"),
        "has_overdue_signal": any(
            event["is_warning"] and event["stage"] == "repayment"
            for event in normalized_events
        ),
        "evidence": _collect_stage_actions(normalized_events, "repayment"),
    }
    product_intent_signals = {
        "product_sensitivity_level": str(
            proxy_profile.get("product_sensitivity", "medium") or "medium"
        ),
        "purchase_preference": purchase_preference,
        "pricing_event_count": _count_pricing_events(normalized_events),
        "apply_event_count": _count_stage_keyword_events(
            normalized_events,
            "application",
            ("apply", "submit", "申请"),
        ),
    }
    churn_signals = {
        "churn_risk_level": str(proxy_profile.get("churn_risk", "medium") or "medium"),
        "warning_event_count": sum(1 for event in normalized_events if event["is_warning"]),
        "dropoff_stage": _infer_dropoff_stage(normalized_events),
        "risk_signals": list(proxy_profile.get("behavior_risk_signals", [])),
    }
    profile_header = {
        "uid": uid,
        "event_span_start": normalized_events[0]["event_dt"].isoformat(),
        "event_span_end": normalized_events[-1]["event_dt"].isoformat(),
        "event_days": len(unique_days),
        "channel": contact_signals["best_channel"],
        "global_info": global_info,
    }
    source_meta = {
        "source_type": str(payload.get("source_type", "local_file") or "local_file"),
        "origin_ref": str(
            payload.get("source_file", "") or payload.get("source_ref", "") or ""
        ),
        "source_variant": "raw_behavior_csv",
        "source_display_name": pack.source_display_name,
        "event_count": total_events,
        "timeline_section_count": len(timeline_sections_compact),
    }

    if total_events < 5:
        warnings.append("behavior_event_volume_low")
    if not _count_events_by_stage(normalized_events, "repayment"):
        warnings.append("repayment_signal_missing")
    if not _detect_contact_channels(normalized_events, pack=pack):
        warnings.append("contact_channel_inferred_from_pack_default")

    prepared = {
        "uid": uid,
        "country_code": pack.country_code,
        "schema_version": BEHAVIOR_PREPARED_SCHEMA_VERSION,
        "profile_header": profile_header,
        "session_summary": {
            **session_summary,
            "active_days_30d": active_days_30d,
            "total_events": total_events,
        },
        "engagement_signals": engagement_signals,
        "repayment_signals": repayment_signals,
        "product_intent_signals": product_intent_signals,
        "churn_signals": churn_signals,
        "contact_signals": contact_signals,
        "timeline_sections": timeline_sections,
        "timeline_sections_raw": timeline_sections_raw,
        "timeline_sections_compact": timeline_sections_compact,
        "timeline_insights": timeline_insights,
        "source_meta": source_meta,
    }
    return prepared, warnings


def _prepare_from_legacy_summary(
    uid: str,
    payload: dict[str, Any],
    *,
    country_code: str,
) -> tuple[dict[str, Any], list[str]]:
    pack = load_behavior_country_pack(country_code)
    proxy_profile = preprocess_behavior_data(payload)
    avg_session_minutes = int(proxy_profile.get("avg_session_minutes", 0) or 0)
    login_days_30d = int(proxy_profile.get("login_days_30d", 0) or 0)
    purchase_preference = str(
        proxy_profile.get("purchase_preference", "unknown") or "unknown"
    )
    contact_preference = dict(proxy_profile.get("contact_preference", {}))
    warnings = ["legacy_behavior_summary_only", "timeline_not_available"]
    prepared = {
        "uid": uid,
        "country_code": pack.country_code,
        "schema_version": BEHAVIOR_PREPARED_SCHEMA_VERSION,
        "profile_header": {
            "uid": uid,
            "event_span_start": "",
            "event_span_end": "",
            "event_days": 0,
            "channel": str(
                contact_preference.get("best_channel", pack.default_contact_channel)
                or pack.default_contact_channel
            ),
        },
        "session_summary": {
            "avg_session_minutes": avg_session_minutes,
            "session_count": max(1, login_days_30d // 2) if login_days_30d else 0,
            "deep_session_count": 1 if avg_session_minutes >= 45 else 0,
            "recent_7d_event_count": min(login_days_30d, 7),
            "active_days_30d": login_days_30d,
            "total_events": max(login_days_30d, 1) if login_days_30d or avg_session_minutes else 0,
        },
        "engagement_signals": {
            "engagement_score": int(proxy_profile.get("engagement_score", 0) or 0),
            "engagement_level": str(
                proxy_profile.get("engagement_level", "light") or "light"
            ),
            "active_days_30d": login_days_30d,
            "session_count": max(1, login_days_30d // 2) if login_days_30d else 0,
            "avg_session_minutes": avg_session_minutes,
            "deep_session_count": 1 if avg_session_minutes >= 45 else 0,
            "recent_7d_event_count": min(login_days_30d, 7),
            "analysis_mode": "proxy_from_sample_metrics",
        },
        "repayment_signals": {
            "repayment_willingness_level": str(
                proxy_profile.get("repayment_willingness", "medium") or "medium"
            ),
            "repayment_event_count": 0,
            "has_overdue_signal": False,
            "evidence": [],
        },
        "product_intent_signals": {
            "product_sensitivity_level": str(
                proxy_profile.get("product_sensitivity", "medium") or "medium"
            ),
            "purchase_preference": purchase_preference,
            "pricing_event_count": 0,
            "apply_event_count": 0,
        },
        "churn_signals": {
            "churn_risk_level": str(proxy_profile.get("churn_risk", "medium") or "medium"),
            "warning_event_count": 0,
            "dropoff_stage": "unknown",
            "risk_signals": list(proxy_profile.get("behavior_risk_signals", [])),
        },
        "contact_signals": {
            "best_channel": str(
                contact_preference.get("best_channel", pack.default_contact_channel)
                or pack.default_contact_channel
            ),
            "best_time": str(
                contact_preference.get("best_time", pack.default_contact_time)
                or pack.default_contact_time
            ),
            "confidence": str(contact_preference.get("confidence", "low") or "low"),
            "reason": str(
                contact_preference.get(
                    "reason",
                    "缺少直接渠道事件，沿用墨西哥市场默认触达建议。",
                )
                or "缺少直接渠道事件，沿用墨西哥市场默认触达建议。"
            ),
            "observed_channels": [],
        },
        "timeline_sections": [],
        "timeline_sections_raw": [],
        "timeline_sections_compact": [],
        "timeline_insights": [
            "当前行为画像来自摘要代理指标，尚未接入完整事件流时间线。",
            "可用于综合画像和策略提示，但旅程细节与阶段时长置信度较低。",
        ],
        "source_meta": {
            "source_type": str(payload.get("source_type", "") or "legacy_summary"),
            "origin_ref": str(
                payload.get("source_file", "") or payload.get("source_ref", "") or ""
            ),
            "source_variant": str(
                payload.get("source_kind", "") or "legacy_behavior_summary"
            ),
            "source_display_name": pack.source_display_name,
            "event_count": 0,
            "timeline_section_count": 0,
        },
    }
    return prepared, warnings


def _filter_rows_by_uid(rows: list[dict[str, Any]], uid: str) -> list[dict[str, Any]]:
    matched: list[dict[str, Any]] = []
    for row in rows:
        row_uid = str(
            row.get("uid", "")
            or row.get("user_uuid", "")
            or row.get("user_id", "")
            or row.get("userid", "")
            or row.get("userId", "")
        ).strip()
        if not row_uid or row_uid == uid:
            matched.append(row)
    return matched or rows


def _looks_like_legacy_summary_row(row: dict[str, Any]) -> bool:
    fieldnames = {str(key).strip() for key in row.keys()}
    return {"avg_session_minutes", "login_days_30d", "purchase_preference"}.issubset(
        fieldnames
    )


def _parse_extend_payload(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
        return payload if isinstance(payload, dict) else {"_value": payload}
    except Exception:  # pylint: disable=broad-except
        return {"_raw": text}


def _extract_route(raw_url: str) -> str:
    text = str(raw_url or "").strip()
    if not text:
        return ""
    if text == "from native":
        return "from-native"
    try:
        parsed = urlparse(text)
        route = parsed.fragment or parsed.path
        if route.startswith("/"):
            decoded = unquote(route)
        elif route:
            decoded = unquote(f"/{route}")
        else:
            decoded = unquote(text)
        if decoded.startswith("/return-refresh-path") and parsed.query:
            next_path = parse_qs(parsed.query).get("nextpath", [])
            if next_path:
                return unquote(next_path[0])
        if decoded.startswith("/return-refresh-path") and "nextpath=" in decoded:
            next_value = decoded.split("nextpath=", 1)[1].split("&", 1)[0]
            return unquote(next_value)
        return decoded
    except Exception:  # pylint: disable=broad-except
        return text


def _compose_page_name(scene_name: str, process_name: str, route: str) -> str:
    route_name = route.rsplit("/", 1)[-1] if route else ""
    parts = [
        part
        for part in (
            scene_name.replace("Activity", "").strip(),
            process_name.strip(),
            route_name.strip(),
        )
        if part
    ]
    return " / ".join(parts[:3])


def _build_raw_event_note(row: dict[str, Any], extend_payload: dict[str, Any]) -> str:
    direct_note = _pick_first(row, "note", "message", "remark", "detail")
    if direct_note:
        return direct_note

    field_name = _pick_first(extend_payload, "field", "prop")
    message = _pick_first(extend_payload, "message", "msg")
    source = _pick_first(extend_payload, "source")
    value_len = _pick_first(extend_payload, "value_len")
    pieces: list[str] = []
    if field_name:
        pieces.append(f"字段: {field_name}")
    if message:
        pieces.append(message)
    if source:
        pieces.append(f"接口: {source}")
    if value_len:
        pieces.append(f"长度: {value_len}")
    if pieces:
        return " | ".join(pieces[:3])
    return ""


def _build_event_action_label(
    *,
    event_name: str,
    scene_name: str,
    process_name: str,
    route: str,
    note: str,
    extend_payload: dict[str, Any],
) -> str:
    event_key = str(event_name or "").strip()
    lower_key = event_key.lower()
    field_name = _pick_first(extend_payload, "field", "prop")
    message = _pick_first(extend_payload, "message", "msg")
    route_tail = route.rsplit("/", 1)[-1] if route else ""

    if "click_login" in lower_key:
        return "登录成功: click_login"
    if lower_key == "page:view":
        return f"进入页面: {route_tail or scene_name or process_name or '未知页面'}"
    if lower_key == "page:leave":
        return f"离开页面: {route_tail or scene_name or process_name or '当前流程'}"
    if "apply:click" in lower_key or "normal-apply" in lower_key:
        return "开始申请: 点击申请入口"
    if "submit" in lower_key and "userinfo" in lower_key:
        return "提交基础资料"
    if lower_key == "form-item-err":
        error_target = field_name or scene_name or process_name or "表单字段"
        if message:
            return f"校验失败: {error_target}"
        return f"表单异常: {error_target}"
    if "ocr-result-field:edit" == lower_key:
        return f"OCR识别后手动修正: {field_name or '证件字段'}"
    if lower_key == "field-edit":
        return f"手动编辑字段: {field_name or '未知字段'}"
    if lower_key == "field-click":
        return f"点击字段: {field_name or '未知字段'}"
    if "accountnumber" in lower_key:
        return "填写银行卡号"
    if "phoneinput" in lower_key:
        return "填写手机号"
    if "whatsapp" in lower_key:
        return "填写 WhatsApp 联系方式"
    if "curp" in lower_key:
        return "填写 CURP 信息"
    if "coupon" in lower_key:
        return "查看优惠券/优惠弹窗"
    if "refresh-btn:click" in lower_key:
        return "主动刷新审批结果"
    if "identity-face" in route or "identity-face" in lower_key:
        return "进入人脸识别/身份确认"
    if "bankinfo-submit-button:click" in lower_key:
        return "提交银行卡绑定"
    if "api:result" == lower_key:
        status_text = message or _pick_first(extend_payload, "status", "code")
        source = _pick_first(extend_payload, "source")
        if source:
            return f"接口返回: {source}"
        if status_text:
            return f"接口结果: {status_text}"
        return "接口结果返回"
    if "page_onresume" in lower_key:
        return "页面恢复前台"
    if "page_onpause" in lower_key:
        return "页面切到后台"
    if lower_key == "load":
        return f"页面加载完成: {route_tail or scene_name or process_name or '当前页面'}"
    if note:
        return f"{event_key or scene_name or process_name}: {note}"
    return event_key or route_tail or scene_name or process_name or "unknown_event"


def _classify_journey_bucket(
    *,
    event_name: str,
    scene_name: str,
    process_name: str,
    route: str,
    note: str,
    extend_payload: dict[str, Any],
    pack: Any,
) -> str:
    del pack  # reserved for future country-specific routing
    haystack = " ".join(
        [
            str(event_name or ""),
            str(scene_name or ""),
            str(process_name or ""),
            str(route or ""),
            str(note or ""),
            str(_pick_first(extend_payload, "field", "prop") or ""),
            str(_pick_first(extend_payload, "message", "msg") or ""),
        ]
    ).lower()

    if "bankinfo" in haystack or "accountnumber" in haystack:
        return "bank_retry"
    if "contactinfo" in haystack or "get-contacts" in haystack:
        if _is_warning_text(haystack):
            return "correction_retry"
        return "contact_entry"
    if any(keyword in haystack for keyword in ("identity-face", "ocr", "curp", "idinfo")):
        return "correction_retry" if _is_warning_text(haystack) or "ocr" in haystack else "basic_profile"
    if "userinfo" in haystack or "personalinfo" in haystack:
        return "basic_profile"
    if any(keyword in haystack for keyword in ("coupon", "choose-period", "choose-term", "select-picker", "index | process", "index process")):
        return "offer_decision"
    if any(keyword in haystack for keyword in ("login", "home", "verifycodeactivity", "apply:click", "normal-apply")):
        return "init"
    if _is_warning_text(haystack):
        return "correction_retry"
    return "unknown"


def _normalize_event_row(row: dict[str, Any], *, pack: Any) -> dict[str, Any]:
    extend_payload = _parse_extend_payload(
        _pick_first(row, "extend", "extra", "payload", "metadata")
    )
    event_name = _pick_first(
        row,
        "event_name",
        "eventname",
        "action",
        "event",
        "event_type",
        "name",
    )
    scene_name = _pick_first(row, "scenetype", "scene", "screen", "page", "page_name")
    process_name = _pick_first(row, "processtype", "process", "stage", "flow")
    route = _extract_route(_pick_first(row, "url", "page_url", "route"))
    page_name = _compose_page_name(scene_name, process_name, route)
    status = (
        _pick_first(row, "status", "result", "outcome", "error_code")
        or _pick_first(extend_payload, "status", "result")
    )
    note = _build_raw_event_note(row, extend_payload)
    timestamp_raw = _pick_first(
        row,
        "event_time",
        "timestamp_",
        "servertimestamp",
        "timestamp",
        "ts",
        "time",
        "created_at",
    )
    event_dt = _parse_event_datetime(timestamp_raw)
    if not event_dt:
        return {}

    action = _build_event_action_label(
        event_name=event_name,
        scene_name=scene_name,
        process_name=process_name,
        route=route,
        note=note,
        extend_payload=extend_payload,
    )
    stage = _classify_stage(action, page_name, note, pack=pack)
    journey_bucket = _classify_journey_bucket(
        event_name=event_name,
        scene_name=scene_name,
        process_name=process_name,
        route=route,
        note=note,
        extend_payload=extend_payload,
        pack=pack,
    )
    is_warning = _is_warning_text(f"{status} {note} {action}")
    channel = _infer_contact_channel(event_name, page_name, note, pack=pack)
    stage_label = pack.stage_labels.get(stage, pack.stage_labels["unknown"])
    journey_label = pack.journey_section_labels.get(
        journey_bucket,
        pack.journey_section_labels["unknown"],
    )
    field_name = _pick_first(extend_payload, "field", "prop")
    message = _pick_first(extend_payload, "message", "msg")
    return {
        "event_dt": event_dt,
        "event_time": event_dt.isoformat(),
        "stage": stage,
        "stage_label": stage_label,
        "journey_bucket": journey_bucket,
        "journey_label": journey_label,
        "action": action,
        "page_name": page_name,
        "route": route,
        "scene_name": scene_name,
        "process_name": process_name,
        "status": status,
        "note": note,
        "field_name": field_name,
        "message": message,
        "channel": channel,
        "is_warning": is_warning,
        "clientmodel": _pick_first(row, "clientmodel", "device_model"),
        "clientosversion": _pick_first(row, "clientosversion", "osversion"),
        "ip": _pick_first(row, "ip"),
        "extend_payload": extend_payload,
    }


def _parse_event_datetime(raw: str) -> datetime | None:
    text = str(raw or "").strip()
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    if text.isdigit():
        try:
            numeric = float(text)
            if numeric > 10_000_000_000:
                numeric = numeric / 1000
            return datetime.fromtimestamp(numeric, tz=timezone.utc).astimezone(MEXICO_OFFSET)
        except Exception:  # pylint: disable=broad-except
            return None
    try:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=MEXICO_OFFSET)
        return parsed.astimezone(MEXICO_OFFSET)
    except Exception:  # pylint: disable=broad-except
        pass
    formats = (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text[: len(fmt)], fmt).replace(tzinfo=MEXICO_OFFSET)
        except Exception:  # pylint: disable=broad-except
            continue
    try:
        numeric = float(text)
        if numeric > 10_000_000_000:
            numeric = numeric / 1000
        return datetime.fromtimestamp(numeric, tz=timezone.utc).astimezone(MEXICO_OFFSET)
    except Exception:  # pylint: disable=broad-except
        return None


def _classify_stage(action: str, page_name: str, note: str, *, pack: Any) -> str:
    haystack = f"{action} {page_name} {note}".lower()
    for stage, keywords in pack.stage_keywords.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            return stage
    return "unknown"


def _is_warning_text(text: str) -> bool:
    haystack = str(text or "").lower()
    keywords = (
        "error",
        "fail",
        "reject",
        "timeout",
        "risk",
        "drop",
        "异常",
        "失败",
        "拒绝",
        "超时",
        "阻断",
        "逾期",
        "催收",
    )
    return any(keyword in haystack for keyword in keywords)


def _infer_contact_channel(event_name: str, page_name: str, note: str, *, pack: Any) -> str:
    haystack = f"{event_name} {page_name} {note}".lower()
    for label, keywords in pack.contact_channel_keywords.items():
        if any(keyword.lower() in haystack for keyword in keywords):
            return label
    return ""


def _build_session_summary(events: list[dict[str, Any]]) -> dict[str, int]:
    session_count = 0
    deep_session_count = 0
    total_minutes = 0
    recent_7d_event_count = 0
    latest_dt = events[-1]["event_dt"]
    last_event_dt: datetime | None = None
    session_events = 0
    session_start: datetime | None = None

    for event in events:
        event_dt = event["event_dt"]
        if latest_dt.date() - event_dt.date() <= timedelta(days=6):
            recent_7d_event_count += 1
        if last_event_dt is None or (event_dt - last_event_dt) > timedelta(minutes=30):
            if session_start is not None and last_event_dt is not None:
                duration = max(
                    3,
                    min(
                        45,
                        int((last_event_dt - session_start).total_seconds() / 60)
                        + session_events * 2,
                    ),
                )
                total_minutes += duration
                if duration >= 30:
                    deep_session_count += 1
            session_count += 1
            session_start = event_dt
            session_events = 1
        else:
            session_events += 1
        last_event_dt = event_dt

    if session_start is not None and last_event_dt is not None:
        duration = max(
            3,
            min(
                45,
                int((last_event_dt - session_start).total_seconds() / 60)
                + session_events * 2,
            ),
        )
        total_minutes += duration
        if duration >= 30:
            deep_session_count += 1

    avg_session_minutes = int(round(total_minutes / session_count)) if session_count else 0
    return {
        "avg_session_minutes": avg_session_minutes,
        "session_count": session_count,
        "deep_session_count": deep_session_count,
        "recent_7d_event_count": recent_7d_event_count,
    }


def _count_active_days_30d(events: list[dict[str, Any]]) -> int:
    latest_dt = events[-1]["event_dt"]
    unique_days = {
        event["event_dt"].date().isoformat()
        for event in events
        if latest_dt - event["event_dt"] <= timedelta(days=30)
    }
    return len(unique_days)


def _derive_purchase_preference(events: list[dict[str, Any]]) -> str:
    haystack = " ".join(
        f"{event['action']} {event['page_name']} {event['note']}".lower()
        for event in events
    )
    if any(
        keyword in haystack
        for keyword in ("coupon", "discount", "promo", "fee", "rate", "优惠", "折扣", "利率")
    ):
        return "discount_value"
    if any(keyword in haystack for keyword in ("vip", "premium", "upgrade", "优先", "会员")):
        return "premium_quality"
    if any(keyword in haystack for keyword in ("cash", "loan", "disburse", "放款", "借款", "提现")):
        return "instant_cash"
    return "standard_browse"


def _build_timeline_sections(events: list[dict[str, Any]], *, pack: Any) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    previous_event_dt: datetime | None = None
    for event in events:
        bucket = str(event.get("journey_bucket", "unknown") or "unknown")
        gap_hours = None
        if previous_event_dt is not None:
            gap_hours = (event["event_dt"] - previous_event_dt).total_seconds() / 3600
        if gap_hours is not None and gap_hours >= 72:
            bucket = "dormancy_return"
            event["journey_bucket"] = bucket
            event["journey_label"] = pack.journey_section_labels.get(
                bucket,
                pack.journey_section_labels["unknown"],
            )

        keep_current_bucket = False
        if current is not None:
            current_bucket = str(current.get("journey_bucket", "") or "")
            current_scene = str(current.get("scene_name", "") or "")
            same_scene_family = current_scene == str(event.get("scene_name", "") or "")
            keep_current_bucket = (
                current_bucket == "correction_retry"
                and bucket in {"contact_entry", "basic_profile"}
                and same_scene_family
            )

        if current is None or (
            current["journey_bucket"] != bucket and not keep_current_bucket
        ):
            if current is not None:
                current["duration_hint"] = _resolve_section_duration_hint(current)
                current["warning_count"] = sum(
                    1 for item in current["events"] if item["is_warning"]
                )
                sections.append(current)
            current = {
                "id": f"section-{len(sections) + 1}",
                "stage": event["stage"],
                "journey_bucket": bucket,
                "title": str(
                    event.get("journey_label")
                    or pack.journey_section_labels.get(bucket, pack.journey_section_labels["unknown"])
                ),
                "scene_name": str(event.get("scene_name", "") or ""),
                "duration_hint": "",
                "gap_hours": gap_hours if bucket == "dormancy_return" else None,
                "warning_count": 0,
                "events": [],
            }
        current["events"].append(
            {
                "time": event["event_dt"].strftime("%Y-%m-%d %H:%M"),
                "action": event["action"],
                "note": _build_event_note(event),
                "kind": "event",
                "is_warning": event["is_warning"],
                "field_name": str(event.get("field_name", "") or ""),
                "scene_name": str(event.get("scene_name", "") or ""),
                "process_name": str(event.get("process_name", "") or ""),
                "status": str(event.get("status", "") or ""),
                "message": str(event.get("message", "") or ""),
            }
        )
        previous_event_dt = event["event_dt"]
    if current is not None:
        current["duration_hint"] = _resolve_section_duration_hint(current)
        current["warning_count"] = sum(1 for item in current["events"] if item["is_warning"])
        sections.append(current)
    return _compress_timeline_sections(sections)


def _build_event_note(event: dict[str, Any]) -> str:
    parts = [
        part
        for part in (event.get("page_name"), event.get("status"), event.get("note"))
        if str(part or "").strip()
    ]
    return " | ".join(str(part).strip() for part in parts[:3])


def _build_duration_hint(events: list[dict[str, Any]]) -> str:
    if not events:
        return ""
    if len(events) == 1:
        return "单次关键动作"
    first_dt = datetime.strptime(events[0]["time"], "%Y-%m-%d %H:%M")
    last_dt = datetime.strptime(events[-1]["time"], "%Y-%m-%d %H:%M")
    minutes = int((last_dt - first_dt).total_seconds() / 60)
    if minutes <= 0:
        return f"连续 {len(events)} 个事件"
    if minutes < 60:
        return f"约 {minutes} 分钟"
    hours = round(minutes / 60, 1)
    return f"约 {hours} 小时"


def _resolve_section_duration_hint(section: dict[str, Any]) -> str:
    gap_hours = section.get("gap_hours")
    if section.get("journey_bucket") == "dormancy_return" and gap_hours:
        if gap_hours >= 24:
            days = max(1, round(float(gap_hours) / 24))
            return f"停顿达 {days} 天"
        return f"停顿约 {int(gap_hours)} 小时"
    return _build_duration_hint(section.get("events", []))


def _compress_timeline_sections(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for section in sections:
        if not merged:
            merged.append(section)
            continue

        previous = merged[-1]
        previous_bucket = str(previous.get("journey_bucket", "") or "")
        current_bucket = str(section.get("journey_bucket", "") or "")
        gap_minutes = _section_gap_minutes(previous, section)

        should_merge_unknown = current_bucket == "unknown" and gap_minutes <= 20
        should_merge_similar = (
            previous_bucket == current_bucket
            or (
                previous_bucket in {"init", "offer_decision"}
                and current_bucket in {"init", "offer_decision"}
                and gap_minutes <= 30
            )
            or (
                previous_bucket in {"basic_profile", "contact_entry"}
                and current_bucket in {"basic_profile", "contact_entry"}
                and gap_minutes <= 30
            )
            or (
                previous_bucket == "correction_retry"
                and current_bucket in {"basic_profile", "contact_entry", "unknown"}
                and gap_minutes <= 20
            )
        )

        if should_merge_unknown or should_merge_similar:
            previous["events"].extend(section.get("events", []))
            previous["warning_count"] = int(previous.get("warning_count", 0) or 0) + int(
                section.get("warning_count", 0) or 0
            )
            previous["duration_hint"] = _resolve_section_duration_hint(previous)
            continue

        merged.append(section)

    for index, section in enumerate(merged, start=1):
        section["id"] = f"section-{index}"
        section["duration_hint"] = _resolve_section_duration_hint(section)
        section["warning_count"] = sum(
            1 for item in section.get("events", []) if item.get("is_warning")
        )
    return merged


def _build_compact_timeline_sections(
    sections: list[dict[str, Any]],
    *,
    pack: Any,
) -> list[dict[str, Any]]:
    compact_sections: list[dict[str, Any]] = []
    for index, section in enumerate(sections, start=1):
        raw_events = [
            dict(event)
            for event in section.get("events", [])
            if isinstance(event, dict)
        ]
        compact_events = _compress_section_events(raw_events, pack=pack)
        compact_section = {
            **section,
            "id": f"section-{index}",
            "events": compact_events,
            "raw_event_count": len(raw_events),
            "compact_event_count": len(compact_events),
            "warning_count": sum(
                1 for item in compact_events if bool(item.get("is_warning"))
            ),
        }
        compact_sections.append(compact_section)
    return compact_sections


def _compress_section_events(
    events: list[dict[str, Any]],
    *,
    pack: Any,
) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    index = 0
    while index < len(events):
        current = events[index]
        key = _event_compaction_key(current)
        if not key or current.get("is_warning"):
            compact.append(_sanitize_compact_event(current))
            index += 1
            continue

        group = [current]
        cursor = index + 1
        while cursor < len(events):
            candidate = events[cursor]
            if candidate.get("is_warning"):
                break
            if _event_compaction_key(candidate) != key:
                break
            if not _events_close_enough(group[-1], candidate):
                break
            group.append(candidate)
            cursor += 1

        if len(group) == 1:
            compact.append(_sanitize_compact_event(current))
        else:
            compact.append(_summarize_event_group(group, key, pack=pack))
        index = cursor
    return compact


def _event_compaction_key(event: dict[str, Any]) -> str:
    action = str(event.get("action", "") or "").strip()
    note = str(event.get("note", "") or "").strip()
    lower_action = action.lower()
    lower_note = note.lower()
    field_name = str(event.get("field_name", "") or "").strip().lower()
    scene_name = str(event.get("scene_name", "") or "").strip().lower()

    lifecycle_prefixes = (
        "page_oncreate",
        "page_onresume",
        "page_onpause",
        "result_onloadresource",
        "result_setfbck",
        "resource-position:show",
        "dialog-close-button:click",
        "k-select-float-layout-click:click",
        "carousel:show",
        "process-line-normal",
    )
    if lower_action.startswith("页面切到后台") or lower_action.startswith("页面恢复前台"):
        return f"lifecycle::{scene_name or lower_note}"
    if any(lower_action.startswith(prefix) for prefix in lifecycle_prefixes):
        return f"lifecycle::{scene_name or lower_note}"
    if lower_action.startswith("页面加载完成:") or lower_action.startswith("进入页面:"):
        return f"page-nav::{scene_name or lower_note}"
    if lower_action.startswith("接口返回:"):
        endpoint = action.split("接口返回:", 1)[-1].strip()
        return f"api::{endpoint}"
    if (
        ":input" in lower_action
        or ":focus" in lower_action
        or ":blur" in lower_action
        or ":change" in lower_action
        or lower_action.startswith("手动编辑字段:")
        or lower_action.startswith("点击字段:")
        or "长度:" in action
    ):
        label = _resolve_field_compaction_label(action, note, field_name)
        return f"field::{label}"
    if lower_action.startswith("填写 "):
        return f"field::{action}"
    if lower_action.startswith("ocr识别后手动修正:"):
        label = action.split(":", 1)[-1].strip() or field_name or action
        return f"field-fix::{label}"
    if lower_action.startswith("校验失败:"):
        label = action.split(":", 1)[-1].strip() or field_name or action
        return f"validation::{label}"
    if lower_action == "开始申请: 点击申请入口":
        return "apply-entry"
    if lower_action == "result_data report":
        return "data-report"
    return ""


def _resolve_field_compaction_label(action: str, note: str, field_name: str) -> str:
    haystack = " ".join(
        item.lower()
        for item in (action, note, field_name)
        if str(item or "").strip()
    )
    if "whatsapp" in haystack:
        return "填写 WhatsApp 联系方式"
    if "phone" in haystack:
        return "填写手机号"
    if "curp" in haystack:
        return "填写 CURP 信息"
    if "accountnumber" in haystack or "银行卡号" in haystack:
        return "填写银行卡号"
    if "facebook" in haystack:
        return "填写 Facebook 信息"
    if field_name:
        return f"填写 {field_name}"
    return "连续填写表单"


def _events_close_enough(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    try:
        previous_time = datetime.strptime(
            str(previous.get("time", "")),
            "%Y-%m-%d %H:%M",
        )
        current_time = datetime.strptime(
            str(current.get("time", "")),
            "%Y-%m-%d %H:%M",
        )
    except Exception:  # pylint: disable=broad-except
        return True
    return int((current_time - previous_time).total_seconds()) <= 180


def _sanitize_compact_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in event.items()
        if key
        in {
            "time",
            "action",
            "note",
            "kind",
            "is_warning",
            "field_name",
            "scene_name",
            "process_name",
            "status",
            "message",
        }
    }


def _summarize_event_group(
    group: list[dict[str, Any]],
    key: str,
    *,
    pack: Any,
) -> dict[str, Any]:
    first = group[0]
    last = group[-1]
    prefix = key.split("::", 1)[0]
    action = str(first.get("action", "") or "")
    note = str(first.get("note", "") or "")
    summary_action = action
    summary_note = note

    if prefix == "field":
        label = key.split("::", 1)[-1]
        max_length = _extract_max_length(group)
        summary_action = label
        summary_note = (
            f"连续输入/聚焦/失焦共 {len(group)} 个动作"
            + (f" | 最终长度: {max_length}" if max_length else "")
        )
    elif prefix == "field-fix":
        label = key.split("::", 1)[-1]
        summary_action = f"连续修正 {label}"
        summary_note = f"短时间内围绕同一字段连续修正/重输 {len(group)} 次。"
    elif prefix == "validation":
        label = key.split("::", 1)[-1]
        summary_action = f"连续触发校验: {label}"
        summary_note = f"短时间内重复出现 {len(group)} 次同类校验失败或阻塞提示。"
    elif prefix == "lifecycle":
        summary_action = "页面加载与生命周期完成"
        summary_note = _build_group_note(group, fallback="完成页面初始化、资源回调与前后台切换。")
    elif prefix == "page-nav":
        page_targets = _distinct_values(
            _extract_page_target(event) for event in group
        )
        summary_action = f"连续进入页面: {' -> '.join(page_targets[:3])}" if page_targets else "连续页面跳转"
        summary_note = f"短时间内连续完成 {len(group)} 个页面导航或渲染动作。"
    elif prefix == "api":
        endpoint = key.split("::", 1)[-1]
        summary_action = f"接口回调集中出现: {endpoint}"
        summary_note = f"短时间内累计 {len(group)} 次同类接口回调。"
    elif prefix == "apply-entry":
        summary_action = "连续触达申请入口"
        summary_note = f"短时间内重复触发申请入口 {len(group)} 次，显示较强的申请推进意图。"
    elif prefix == "data-report":
        summary_action = "行为快照集中上报"
        summary_note = f"短时间内累计 {len(group)} 次数据快照/埋点上报。"

    return {
        "time": str(first.get("time", "") or ""),
        "action": summary_action,
        "note": summary_note,
        "kind": "macro_event",
        "is_warning": False,
        "source_event_count": len(group),
        "source_actions": [str(item.get("action", "") or "") for item in group[:6]],
        "field_name": str(first.get("field_name", "") or ""),
        "scene_name": str(first.get("scene_name", "") or ""),
        "process_name": str(first.get("process_name", "") or ""),
        "status": str(last.get("status", "") or ""),
        "message": str(last.get("message", "") or ""),
    }


def _build_group_note(group: list[dict[str, Any]], *, fallback: str) -> str:
    page_targets = _distinct_values(
        _extract_page_target(event) for event in group
    )
    if page_targets:
        return f"{fallback} 关联页面: {' / '.join(page_targets[:3])}。"
    return fallback


def _extract_page_target(event: dict[str, Any]) -> str:
    note = str(event.get("note", "") or "")
    if not note:
        return ""
    return note.split("|", 1)[0].strip()


def _extract_max_length(group: list[dict[str, Any]]) -> int:
    max_length = 0
    for item in group:
        for haystack in (str(item.get("action", "") or ""), str(item.get("note", "") or "")):
            matched = re.search(r"长度:\s*(\d+)", haystack)
            if matched:
                max_length = max(max_length, int(matched.group(1)))
    return max_length


def _distinct_values(values: list[str] | Any) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _section_gap_minutes(previous: dict[str, Any], current: dict[str, Any]) -> int:
    previous_events = previous.get("events", [])
    current_events = current.get("events", [])
    if not previous_events or not current_events:
        return 0
    try:
        previous_time = datetime.strptime(
            str(previous_events[-1].get("time", "")),
            "%Y-%m-%d %H:%M",
        )
        current_time = datetime.strptime(
            str(current_events[0].get("time", "")),
            "%Y-%m-%d %H:%M",
        )
    except Exception:  # pylint: disable=broad-except
        return 0
    return max(0, int((current_time - previous_time).total_seconds() / 60))


def _build_timeline_insights(
    events: list[dict[str, Any]],
    proxy_profile: dict[str, Any],
    timeline_sections: list[dict[str, Any]],
    *,
    pack: Any,
) -> list[str]:
    insights: list[str] = []
    warning_count = sum(1 for event in events if event["is_warning"])
    if warning_count:
        insights.append(
            f"旅程中共出现 {warning_count} 个阻塞或风险事件，需重点关注触发阶段与后续回访节奏。"
        )
    if _count_pricing_events(events) >= 2:
        insights.append(
            "用户多次查看利率、优惠或费用相关信息，价格敏感度较高，策略上更适合强调利益点与费用解释。"
        )
    if _count_events_by_stage(events, "repayment") >= 1:
        insights.append("行为流中已出现还款相关动作，可将其视为弱履约意愿正向信号。")
    else:
        insights.append("当前事件流未覆盖显式还款动作，还款意愿仍需更多履约数据佐证。")
    if proxy_profile.get("engagement_level") == "deep":
        insights.append("整体会话深度较高，说明用户对产品流程和授信信息投入了较多注意力。")
    if timeline_sections:
        insights.append(
            f"本次标准化旅程共拆解为 {len(timeline_sections)} 个阶段段落，可直接供后续策略 Agent 或 LangGraph 编排消费。"
        )
    channels = _detect_contact_channels(events, pack=pack)
    if channels:
        insights.append(f"观察到的触达渠道偏好为：{' / '.join(channels[:3])}。")
    return insights[:6]


def _build_contact_signals(
    events: list[dict[str, Any]],
    proxy_profile: dict[str, Any],
    *,
    pack: Any,
) -> dict[str, Any]:
    observed_channels = _detect_contact_channels(events, pack=pack)
    best_channel = observed_channels[0] if observed_channels else pack.default_contact_channel
    best_time = (
        "19:00-21:00"
        if int(proxy_profile.get("login_days_30d", 0) or 0) >= 15
        else "12:00-14:00"
    )
    confidence = "medium" if observed_channels else "low"
    reason = (
        "事件流中已观察到直接渠道行为。"
        if observed_channels
        else "缺少显式渠道事件，沿用墨西哥市场默认的 WhatsApp 建议。"
    )
    return {
        "best_channel": best_channel,
        "best_time": best_time,
        "confidence": confidence,
        "reason": reason,
        "observed_channels": observed_channels,
    }


def _build_global_info(events: list[dict[str, Any]], uid: str) -> dict[str, str]:
    latest_event = events[-1] if events else {}
    extend_payload = (
        latest_event.get("extend_payload", {})
        if isinstance(latest_event.get("extend_payload", {}), dict)
        else {}
    )
    return {
        "UID": uid,
        "手机机型": _pick_first(latest_event, "clientmodel") or "未知",
        "系统版本": _pick_first(latest_event, "clientosversion", "osversion") or "未知",
        "网络IP": _pick_first(latest_event, "ip") or "未知",
        "App版本": _pick_first(extend_payload, "av", "app_version") or "未知",
    }


def _detect_contact_channels(events: list[dict[str, Any]], *, pack: Any) -> list[str]:
    channels: list[str] = []
    seen: set[str] = set()
    for event in events:
        channel = str(event.get("channel", "") or "").strip()
        if channel and channel not in seen:
            seen.add(channel)
            channels.append(channel)
    if channels:
        return _rank_contact_channels(channels)

    for event in events:
        haystack = f"{event['action']} {event['page_name']} {event['note']}".lower()
        for label, keywords in pack.contact_channel_keywords.items():
            if label in seen:
                continue
            if any(keyword.lower() in haystack for keyword in keywords):
                seen.add(label)
                channels.append(label)
    return _rank_contact_channels(channels)


def _rank_contact_channels(channels: list[str]) -> list[str]:
    priority = {"WhatsApp": 0, "短信": 1, "电话": 2, "App Push": 3}
    return sorted(
        list(dict.fromkeys(channels)),
        key=lambda item: (priority.get(item, 99), item),
    )


def _count_events_by_stage(events: list[dict[str, Any]], stage: str) -> int:
    return sum(1 for event in events if event["stage"] == stage)


def _count_stage_keyword_events(
    events: list[dict[str, Any]],
    stage: str,
    keywords: tuple[str, ...],
) -> int:
    count = 0
    for event in events:
        if event["stage"] != stage:
            continue
        haystack = f"{event['action']} {event['page_name']} {event['note']}".lower()
        if any(keyword.lower() in haystack for keyword in keywords):
            count += 1
    return count


def _count_pricing_events(events: list[dict[str, Any]]) -> int:
    keywords = ("coupon", "discount", "promo", "rate", "fee", "优惠", "折扣", "利率")
    count = 0
    for event in events:
        haystack = f"{event['action']} {event['page_name']} {event['note']}".lower()
        if any(keyword.lower() in haystack for keyword in keywords):
            count += 1
    return count


def _collect_stage_actions(events: list[dict[str, Any]], stage: str) -> list[str]:
    return [str(event["action"]) for event in events if event["stage"] == stage][:6]


def _infer_dropoff_stage(events: list[dict[str, Any]]) -> str:
    if not events:
        return "unknown"
    last_event = events[-1]
    if last_event["is_warning"]:
        return str(last_event["stage"])
    stage_counts: dict[str, int] = {}
    for event in events:
        stage = str(event["stage"])
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    sorted_counts = sorted(stage_counts.items(), key=lambda item: (-item[1], item[0]))
    return sorted_counts[0][0] if sorted_counts else "unknown"


def _pick_first(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(source.get(key, "") or "").strip()
        if value:
            return value
    return ""
