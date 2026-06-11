"""Feature builder layer for the trace_analyzer pipeline.

Extracts the 5 rule-layer facts (path graph / friction hotspots / time pattern /
key events tail / churn root cause candidates) and applies the three-tier
token budget guard. See docs/specs/trace-analyzer-design.md §2.Q4 + §2.Q6.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from app.runtime_skills.trace_analyzer._constants import (
    INSUFFICIENT_EVENTS_THRESHOLD,
    KEY_EVENTS_PRE_DROPOFF_N,
    KEY_EVENTS_TAIL_N,
    TIER_2_TOKEN_BUDGET,
    TIER_3_TOKEN_BUDGET,
    TOP_K_FRICTION_HOTSPOTS,
    TOP_N_PAGES,
    TOP_N_TRANSITIONS,
    TOTAL_TOKEN_BUDGET,
)
from app.runtime_skills.trace_analyzer.contracts import (
    TraceFeatureBundle,
    TraceRawData,
    TraceRunContext,
)


class TraceFeatureBuilder:
    """Build deterministic trace features from the raw events DataFrame."""

    # ------- entry -------

    def build(
        self,
        raw_data: TraceRawData,
        context: TraceRunContext,
    ) -> TraceFeatureBundle:
        df: pd.DataFrame = raw_data.get("events_df")
        errors: list[str] = list(raw_data.get("errors", []))

        if raw_data.get("data_status") != "ok" or df is None or len(df) == 0:
            return self._empty_bundle(raw_data["uid"], status="empty", errors=errors)

        if len(df) < INSUFFICIENT_EVENTS_THRESHOLD:
            return self._empty_bundle(
                raw_data["uid"],
                status="insufficient_events",
                errors=errors + [f"insufficient_events:n={len(df)}"],
            )

        path_graph = self._build_path_graph(df)
        friction = self._build_friction_hotspots(df)
        time_pattern = self._build_time_pattern(df)
        tail = self._build_key_events_tail(df, n=KEY_EVENTS_TAIL_N)
        candidates = self._build_churn_candidates(df, path_graph, friction)
        window = self._build_event_window(df)

        bundle: TraceFeatureBundle = {
            "uid": raw_data["uid"],
            "event_window": window,
            "path_graph": path_graph,
            "friction_hotspots": friction[:TOP_K_FRICTION_HOTSPOTS],
            "time_pattern": time_pattern,
            "key_events_tail": tail,
            "churn_root_cause_candidates": candidates,
            "feature_status": "ok",
            "errors": errors,
        }
        self._apply_token_budget(bundle)
        return bundle

    # ------- 1. path graph -------

    def _build_path_graph(self, df: pd.DataFrame) -> dict[str, Any]:
        pages = df["scenetype"].fillna("").astype(str).tolist()
        ts = df["servertimestamp"].astype(str).tolist()

        page_counter = Counter(p for p in pages if p)
        # Average stay per page from consecutive timestamp deltas on same page
        stay_acc: dict[str, list[float]] = defaultdict(list)
        for i in range(len(pages) - 1):
            try:
                delta = (int(ts[i + 1]) - int(ts[i])) / 1000.0
            except ValueError:
                continue
            if pages[i] and 0 <= delta < 3600:  # cap 1h to ignore session breaks
                stay_acc[pages[i]].append(delta)
        top_pages = [
            {
                "page": p,
                "visit_count": int(c),
                "avg_stay_seconds": round(sum(stay_acc[p]) / len(stay_acc[p]), 2)
                if stay_acc[p] else 0.0,
            }
            for p, c in page_counter.most_common(TOP_N_PAGES)
        ]

        transitions: Counter[tuple[str, str]] = Counter()
        for i in range(len(pages) - 1):
            a, b = pages[i], pages[i + 1]
            if a and b and a != b:
                transitions[(a, b)] += 1
        top_transitions = [
            {"from": a, "to": b, "count": int(c)}
            for (a, b), c in transitions.most_common(TOP_N_TRANSITIONS)
        ]
        return {"top_pages": top_pages, "top_transitions": top_transitions}

    # ------- 2. friction hotspots -------

    def _build_friction_hotspots(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        # Group by (scenetype, extend.field). retry_count = field-edit count;
        # error_count = events whose eventname contains 'error'/'fail';
        # avg_stay_seconds = mean delta between this event ts and the next event ts.
        group: dict[tuple[str, str], dict[str, Any]] = {}
        rows = list(df.iterrows())
        for idx, (_, row) in enumerate(rows):
            page = str(row.get("scenetype", "") or "")
            extend_str = str(row.get("extend", "") or "")
            field = ""
            try:
                ext = json.loads(extend_str) if extend_str else {}
                if isinstance(ext, dict):
                    field = str(ext.get("field", "") or "")
            except (ValueError, TypeError):
                pass
            if not page:
                continue
            key = (page, field)
            slot = group.setdefault(key, {
                "step": f"{page}:{field}" if field else page,
                "retry_count": 0,
                "error_count": 0,
                "_stays": [],
            })
            ev = str(row.get("eventname", "") or "").lower()
            if ev == "field-edit":
                slot["retry_count"] += 1
            if "error" in ev or "fail" in ev:
                slot["error_count"] += 1
            if idx + 1 < len(rows):
                try:
                    cur_ts = int(row["servertimestamp"])
                    nxt_ts = int(rows[idx + 1][1]["servertimestamp"])
                    delta = (nxt_ts - cur_ts) / 1000.0
                    if 0 <= delta <= 3600:
                        slot["_stays"].append(delta)
                except (ValueError, KeyError, TypeError):
                    pass

        hotspots = []
        for (page, field), slot in group.items():
            severity = self._severity(slot["retry_count"], slot["error_count"])
            stays = slot["_stays"]
            avg_stay = sum(stays) / len(stays) if stays else 0.0
            hotspots.append({
                "step": slot["step"],
                "retry_count": slot["retry_count"],
                "error_count": slot["error_count"],
                "avg_stay_seconds": round(avg_stay, 3),
                "severity": severity,
            })
        rank = {"high": 3, "medium": 2, "low": 1}
        hotspots.sort(key=lambda h: (-rank[h["severity"]], -h["retry_count"], -h["error_count"]))
        return hotspots

    @staticmethod
    def _severity(retry: int, errors: int) -> str:
        if errors >= 1 or retry >= 5:
            return "high"
        if retry >= 2:
            return "medium"
        return "low"

    # ------- 3. time pattern -------

    def _build_time_pattern(self, df: pd.DataFrame) -> dict[str, Any]:
        hist = [0] * 24
        for ts_str in df["servertimestamp"].astype(str):
            try:
                ts_ms = int(ts_str)
            except ValueError:
                continue
            hour = datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).hour
            hist[hour] += 1
        peak = hist.index(max(hist)) if any(hist) else 0
        if 22 <= peak or peak < 5:
            label = "深夜活跃"
        elif 5 <= peak < 12:
            label = "上午活跃"
        elif 12 <= peak < 18:
            label = "白天活跃"
        else:
            label = "晚间活跃"
        return {"hour_histogram": hist, "active_window_label": label}

    # ------- 4. key events tail (redacted) -------

    def _build_key_events_tail(self, df: pd.DataFrame, *, n: int) -> list[dict[str, Any]]:
        tail = df.tail(n)
        if len(tail) == 0:
            return []
        try:
            t0 = int(tail.iloc[0]["servertimestamp"])
        except (ValueError, KeyError):
            t0 = 0
        events: list[dict[str, Any]] = []
        for _, row in tail.iterrows():
            try:
                ts_offset = (int(row["servertimestamp"]) - t0) / 1000.0
            except ValueError:
                ts_offset = 0.0
            page = self._strip_url_query(str(row.get("scenetype", "") or ""))
            field = ""
            extend_str = str(row.get("extend", "") or "")
            try:
                ext = json.loads(extend_str) if extend_str else {}
                if isinstance(ext, dict):
                    field = str(ext.get("field", "") or "")
            except (ValueError, TypeError):
                pass
            ev: dict[str, Any] = {
                "ts_offset": round(ts_offset, 2),
                "page": page,
                "event": str(row.get("eventname", "") or ""),
            }
            if field:
                ev["field"] = field
            events.append(ev)
        return events

    @staticmethod
    def _strip_url_query(s: str) -> str:
        if "://" not in s:
            return s
        try:
            parsed = urlparse(s)
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        except (ValueError, TypeError):
            return s.split("?")[0]

    # ------- 5. churn prior candidates -------

    def _build_churn_candidates(
        self,
        df: pd.DataFrame,
        path_graph: dict[str, Any],
        friction: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        # Heuristic 1: heavy interest-page visits → interest_perception_high
        interest_visits = sum(
            p["visit_count"] for p in path_graph["top_pages"]
            if "interest" in p["page"].lower() or "rate" in p["page"].lower()
        )
        if interest_visits >= 3:
            out.append({"value": "interest_perception_high", "confidence": 0.6,
                        "reason": f"interest_pages_visits={interest_visits}"})
        # Heuristic 2: high-severity friction → ux_friction
        if any(h["severity"] == "high" for h in friction):
            out.append({"value": "ux_friction", "confidence": 0.7,
                        "reason": "high_severity_hotspot"})
        # Heuristic 3: heavy quota-page visits → credit_limit_unmet
        quota_visits = sum(
            p["visit_count"] for p in path_graph["top_pages"]
            if "quota" in p["page"].lower() or "limit" in p["page"].lower()
        )
        if quota_visits >= 3:
            out.append({"value": "credit_limit_unmet", "confidence": 0.6,
                        "reason": f"quota_pages_visits={quota_visits}"})
        if not out:
            out.append({"value": "no_clear_signal", "confidence": 0.5, "reason": "no_pattern"})
        return out[:2]  # 0-2 candidates

    # ------- 6. event window -------

    def _build_event_window(self, df: pd.DataFrame) -> dict[str, Any]:
        ts_series = pd.to_numeric(df["servertimestamp"], errors="coerce").dropna()
        if len(ts_series) == 0:
            return {"start": "", "end": "", "total_events": int(len(df)), "analyzed_events": int(len(df))}
        start = datetime.fromtimestamp(int(ts_series.min()) / 1000.0, tz=timezone.utc).isoformat()
        end = datetime.fromtimestamp(int(ts_series.max()) / 1000.0, tz=timezone.utc).isoformat()
        return {
            "start": start,
            "end": end,
            "total_events": int(len(df)),
            "analyzed_events": int(len(df)),
        }

    # ------- 7. token budget guard -------

    def _estimate_tokens(self, text: str) -> int:
        ascii_n = sum(1 for ch in text if ord(ch) < 128)
        cjk_n = len(text) - ascii_n
        return int(ascii_n * 0.25 + cjk_n * 1.0)

    def _apply_token_budget(self, bundle: TraceFeatureBundle) -> None:
        # Tier 3: key_events_tail. Halve until under TIER_3 budget.
        while True:
            est3 = self._estimate_tokens(json.dumps(bundle["key_events_tail"], ensure_ascii=False))
            if est3 <= TIER_3_TOKEN_BUDGET or len(bundle["key_events_tail"]) <= 4:
                break
            new_n = max(4, len(bundle["key_events_tail"]) // 2)
            bundle["key_events_tail"] = bundle["key_events_tail"][-new_n:]
            bundle["errors"].append(f"truncated:tier3:N->{new_n}")

        # Tier 2: friction_hotspots. Halve until under TIER_2 budget.
        while True:
            est2 = self._estimate_tokens(json.dumps(bundle["friction_hotspots"], ensure_ascii=False))
            if est2 <= TIER_2_TOKEN_BUDGET or len(bundle["friction_hotspots"]) <= 1:
                break
            new_k = max(1, len(bundle["friction_hotspots"]) // 2)
            bundle["friction_hotspots"] = bundle["friction_hotspots"][:new_k]
            bundle["errors"].append(f"truncated:tier2:K->{new_k}")

        # Final guard — if total still over TOTAL, halve tier 3 again
        full = json.dumps([
            bundle["event_window"], bundle["path_graph"], bundle["friction_hotspots"],
            bundle["time_pattern"], bundle["key_events_tail"],
        ], ensure_ascii=False)
        if self._estimate_tokens(full) > TOTAL_TOKEN_BUDGET and len(bundle["key_events_tail"]) > 4:
            bundle["key_events_tail"] = bundle["key_events_tail"][-(len(bundle["key_events_tail"]) // 2):]
            bundle["errors"].append("truncated:total:tier3_again")

    # ------- helpers -------

    def _empty_bundle(self, uid: str, *, status: str, errors: list[str]) -> TraceFeatureBundle:
        return {
            "uid": uid,
            "event_window": {"start": "", "end": "", "total_events": 0, "analyzed_events": 0},
            "path_graph": {"top_pages": [], "top_transitions": []},
            "friction_hotspots": [],
            "time_pattern": {"hour_histogram": [0] * 24, "active_window_label": ""},
            "key_events_tail": [],
            "churn_root_cause_candidates": [],
            "feature_status": status,
            "errors": errors,
        }
