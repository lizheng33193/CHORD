"""Decision engine layer for the Behavior profile pipeline."""

from __future__ import annotations

from app.runtime_skills.behavior_profile.contracts import (
    BehaviorDecisionResult,
    BehaviorFeatureBundle,
    BehaviorRunContext,
)


class BehaviorDecisionEngine:
    """Build deterministic Behavior decisions from normalized features."""

    def decide(
        self,
        feature_bundle: BehaviorFeatureBundle,
        _context: BehaviorRunContext,
    ) -> BehaviorDecisionResult:
        prepared = feature_bundle.get("prepared_record", {})
        summary_features = feature_bundle.get("summary_features", {})
        timeline_features = feature_bundle.get("timeline_features", {})
        derived_signals = feature_bundle.get("derived_signals", {})
        source_meta = prepared.get("source_meta", {})
        timeline_sections_raw = list(
            timeline_features.get("timeline_sections_raw", [])
        )
        timeline_sections_compact = list(
            timeline_features.get("timeline_sections_compact", [])
        )
        timeline_narrative_fallback = self._build_timeline_narrative_fallback(
            timeline_sections_compact,
        )

        engagement_profile = self._build_engagement_profile(
            summary_features,
            timeline_features,
        )
        repayment_willingness = self._build_repayment_willingness(
            summary_features,
            prepared,
        )
        product_sensitivity = self._build_product_sensitivity(
            summary_features,
            prepared,
        )
        churn_risk = self._build_churn_risk(
            summary_features,
            prepared,
            timeline_features,
        )
        contact_preference = self._build_contact_preference(prepared)
        behavior_signal_score = self._build_behavior_signal_score(
            engagement_level=str(
                summary_features.get("engagement_level", "light") or "light"
            ),
            repayment_level=str(
                summary_features.get("repayment_willingness_level", "medium") or "medium"
            ),
            churn_level=str(
                summary_features.get("churn_risk_level", "medium") or "medium"
            ),
            journey_risk_count=int(
                timeline_features.get("journey_risk_count", 0) or 0
            ),
        )
        llm_fallback_profile = self._build_llm_fallback_profile(
            feature_bundle,
            engagement_profile=engagement_profile,
            repayment_willingness=repayment_willingness,
            product_sensitivity=product_sensitivity,
            churn_risk=churn_risk,
            contact_preference=contact_preference,
        )

        metrics = {
            "avg_session_minutes": int(
                summary_features.get("avg_session_minutes", 0) or 0
            ),
            "login_days_30d": int(summary_features.get("login_days_30d", 0) or 0),
            "engagement_score": int(
                summary_features.get("engagement_score", 0) or 0
            ),
            "engagement_level": str(
                summary_features.get("engagement_level", "light") or "light"
            ),
            "repayment_willingness_level": str(
                summary_features.get("repayment_willingness_level", "medium")
                or "medium"
            ),
            "product_sensitivity_level": str(
                summary_features.get("product_sensitivity_level", "medium")
                or "medium"
            ),
            "churn_risk_level": str(
                summary_features.get("churn_risk_level", "medium") or "medium"
            ),
            "value_signal_level": str(
                summary_features.get("value_signal_level", "medium") or "medium"
            ),
            "active_trend_level": str(
                summary_features.get("active_trend_level", "medium") or "medium"
            ),
            "contact_recommendation_level": str(
                summary_features.get("contact_recommendation_level", "medium")
                or "medium"
            ),
            "timeline_section_count": int(
                timeline_features.get("timeline_section_count", 0) or 0
            ),
            "timeline_event_count": int(
                timeline_features.get("timeline_event_count", 0) or 0
            ),
            "timeline_event_count_compact": int(
                timeline_features.get("timeline_event_count_compact", 0) or 0
            ),
            "journey_risk_count": int(
                timeline_features.get("journey_risk_count", 0) or 0
            ),
            "page_node_count": int(
                timeline_features.get("timeline_section_count", 0) or 0
            ),
            "interaction_count": int(
                timeline_features.get("timeline_event_count", 0) or 0
            ),
            "abnormal_risk_count": int(
                timeline_features.get("journey_risk_count", 0) or 0
            ),
            "behavior_signal_score": behavior_signal_score,
        }
        evidence_seed = {
            "market_context": "mexico_behavior_timeline_profile",
            "analysis_mode": str(
                prepared.get("engagement_signals", {}).get(
                    "analysis_mode",
                    "prepared_record",
                )
                or "prepared_record"
            ),
            "profile_header": dict(prepared.get("profile_header", {})),
            "global_info": dict(
                prepared.get("profile_header", {}).get("global_info", {})
            ),
            "source_meta": dict(source_meta),
            "contact_preference": contact_preference,
            "behavior_risk_signals": list(
                derived_signals.get("risk_signals", [])
            ),
            "timeline_sections": timeline_sections_compact,
            "timeline_sections_raw": timeline_sections_raw,
            "timeline_sections_compact": timeline_sections_compact,
            "timeline_insights": list(
                timeline_features.get("timeline_insights", [])
            ),
            "journey_summary": {
                "timeline_section_count": int(
                    timeline_features.get("timeline_section_count", 0) or 0
                ),
                "timeline_event_count": int(
                    timeline_features.get("timeline_event_count", 0) or 0
                ),
                "journey_risk_count": int(
                    timeline_features.get("journey_risk_count", 0) or 0
                ),
            },
            "timeline_narrative": timeline_narrative_fallback,
            "behavior_profile_narrative": {
                "behavior_summary": str(
                    llm_fallback_profile.get("behavior_summary", "") or ""
                ),
                "business_advice": str(
                    llm_fallback_profile.get("business_advice", "") or ""
                ),
                "strategy_suggestions": list(
                    llm_fallback_profile.get("strategy_suggestions", [])
                ),
                "journey_insight": str(
                    timeline_features.get("timeline_insights", [""])[0]
                    if timeline_features.get("timeline_insights")
                    else ""
                ),
                "confidence": str(
                    llm_fallback_profile.get("confidence", "") or ""
                ),
            },
            "llm_behavior_profile": llm_fallback_profile,
            "llm_profile": llm_fallback_profile,
            "llm_timeline": timeline_narrative_fallback,
            "used_llm_profile": False,
            "used_llm_timeline": False,
            "fallback_reason": "deterministic_behavior_fallback",
        }

        return {
            "uid": feature_bundle["uid"],
            "country_code": feature_bundle["country_code"],
            "decision_status": "ok",
            "summary_seed": str(llm_fallback_profile.get("behavior_summary", "") or ""),
            "evidence_seed": evidence_seed,
            "engagement_profile": engagement_profile,
            "repayment_willingness": repayment_willingness,
            "product_sensitivity": product_sensitivity,
            "churn_risk": churn_risk,
            "contact_preference": contact_preference,
            "behavior_signal_score": behavior_signal_score,
            "metrics": metrics,
            "tags_rule": self._build_tags(metrics, derived_signals),
            "llm_fallback_profile": llm_fallback_profile,
            "errors": list(feature_bundle.get("errors", [])),
        }

    def build_prompt_payload(
        self,
        feature_bundle: BehaviorFeatureBundle,
        decision_result: BehaviorDecisionResult,
    ) -> dict[str, object]:
        prepared = feature_bundle.get("prepared_record", {})
        timeline_features = feature_bundle.get("timeline_features", {})
        timeline_sections_compact = list(
            timeline_features.get("timeline_sections_compact", [])
        )
        return {
            "uid": feature_bundle["uid"],
            "prepared_behavior_record": dict(prepared),
            "behavior_profile_prompt_input": {
                "metrics": dict(decision_result.get("metrics", {})),
                "summary_features": dict(feature_bundle.get("summary_features", {})),
                "risk_signals": list(
                    feature_bundle.get("derived_signals", {}).get("risk_signals", [])
                ),
                "contact_preference": dict(
                    feature_bundle.get("derived_signals", {}).get(
                        "contact_preference",
                        {},
                    )
                ),
                "timeline_sections_compact": timeline_sections_compact,
                "timeline_insights": list(
                    timeline_features.get("timeline_insights", [])
                ),
            },
            "behavior_timeline_prompt_input": {
                "timeline_sections_compact": timeline_sections_compact,
                "timeline_insights": list(
                    timeline_features.get("timeline_insights", [])
                ),
                "journey_summary": {
                    "timeline_section_count": int(
                        timeline_features.get("timeline_section_count", 0) or 0
                    ),
                    "timeline_event_count": int(
                        timeline_features.get("timeline_event_count", 0) or 0
                    ),
                    "timeline_event_count_compact": int(
                        timeline_features.get("timeline_event_count_compact", 0) or 0
                    ),
                    "journey_risk_count": int(
                        timeline_features.get("journey_risk_count", 0) or 0
                    ),
                },
            },
            "derived_signals": {
                "summary_features": dict(feature_bundle.get("summary_features", {})),
                "timeline_features": dict(
                    feature_bundle.get("timeline_features", {})
                ),
                "risk_signals": list(
                    feature_bundle.get("derived_signals", {}).get(
                        "risk_signals",
                        [],
                    )
                ),
                "contact_preference": dict(
                    feature_bundle.get("derived_signals", {}).get(
                        "contact_preference",
                        {},
                    )
                ),
            },
            "default_inference": {
                "engagement_level": decision_result.get("engagement_profile", {}).get(
                    "level",
                    "light",
                ),
                "repayment_willingness_level": decision_result.get(
                    "repayment_willingness",
                    {},
                ).get("level", "medium"),
                "product_sensitivity_level": decision_result.get(
                    "product_sensitivity",
                    {},
                ).get("level", "medium"),
                "churn_risk_level": decision_result.get("churn_risk", {}).get(
                    "level",
                    "medium",
                ),
                "behavior_signal_score": decision_result.get(
                    "behavior_signal_score",
                    0,
                ),
            },
            "fallback_llm_profile": dict(
                decision_result.get("llm_fallback_profile", {})
            ),
        }

    def _build_engagement_profile(
        self,
        summary_features: dict[str, object],
        timeline_features: dict[str, object],
    ) -> dict[str, object]:
        level = str(summary_features.get("engagement_level", "light") or "light")
        score = int(summary_features.get("engagement_score", 0) or 0)
        return {
            "level": level,
            "display_level": self._display_level(level),
            "engagement_score": score,
            "timeline_section_count": int(
                timeline_features.get("timeline_section_count", 0) or 0
            ),
            "reasoning": "综合活跃天数、会话深度与旅程阶段覆盖度，对用户近端行为投入度进行判断。",
        }

    def _build_repayment_willingness(
        self,
        summary_features: dict[str, object],
        prepared: dict[str, object],
    ) -> dict[str, object]:
        level = str(
            summary_features.get("repayment_willingness_level", "medium")
            or "medium"
        )
        repayment_signals = prepared.get("repayment_signals", {})
        quincena_alignment = str(
            summary_features.get("quincena_alignment", "unknown") or "unknown"
        )
        reasoning = "还款意愿主要参考回访稳定性、会话持续性及是否出现履约相关行为。"
        if quincena_alignment == "strong":
            reasoning += " 还款与 Quincena 发薪周期高度吻合。"
        elif quincena_alignment == "moderate":
            reasoning += " 部分还款与 Quincena 发薪周期吻合。"
        return {
            "level": level,
            "display_level": self._display_level(level),
            "repayment_event_count": int(
                repayment_signals.get("repayment_event_count", 0) or 0
            ),
            "quincena_alignment": quincena_alignment,
            "reasoning": reasoning,
        }

    def _build_product_sensitivity(
        self,
        summary_features: dict[str, object],
        prepared: dict[str, object],
    ) -> dict[str, object]:
        level = str(
            summary_features.get("product_sensitivity_level", "medium")
            or "medium"
        )
        product_signals = prepared.get("product_intent_signals", {})
        return {
            "level": level,
            "display_level": self._display_level(level),
            "purchase_preference": str(
                product_signals.get("purchase_preference", "unknown") or "unknown"
            ),
            "pricing_event_count": int(
                product_signals.get("pricing_event_count", 0) or 0
            ),
            "reasoning": "产品敏感度基于优惠、利率、费用与申请意图类行为综合判断。",
        }

    def _build_churn_risk(
        self,
        summary_features: dict[str, object],
        prepared: dict[str, object],
        timeline_features: dict[str, object],
    ) -> dict[str, object]:
        level = str(summary_features.get("churn_risk_level", "medium") or "medium")
        churn_signals = prepared.get("churn_signals", {})
        return {
            "level": level,
            "display_level": self._display_level(level),
            "warning_event_count": int(
                churn_signals.get("warning_event_count", 0) or 0
            ),
            "dropoff_stage": str(
                churn_signals.get("dropoff_stage", "unknown") or "unknown"
            ),
            "journey_risk_count": int(
                timeline_features.get("journey_risk_count", 0) or 0
            ),
            "reasoning": "流失风险由低频回访、阶段阻塞和旅程告警事件共同驱动。",
        }

    def _build_contact_preference(self, prepared: dict[str, object]) -> dict[str, object]:
        contact_signals = prepared.get("contact_signals", {})
        return {
            "best_channel": str(
                contact_signals.get("best_channel", "WhatsApp") or "WhatsApp"
            ),
            "best_time": str(
                contact_signals.get("best_time", "19:00-21:00")
                or "19:00-21:00"
            ),
            "confidence": str(contact_signals.get("confidence", "low") or "low"),
            "reason": str(contact_signals.get("reason", "") or ""),
            "observed_channels": list(
                contact_signals.get("observed_channels", [])
            ),
        }

    def _build_behavior_signal_score(
        self,
        *,
        engagement_level: str,
        repayment_level: str,
        churn_level: str,
        journey_risk_count: int,
    ) -> int:
        engagement_map = {"light": 28, "balanced": 56, "deep": 82}
        repayment_map = {"low": 25, "medium": 45, "medium_high": 63, "high": 80}
        churn_penalty = {"low": 0, "medium": 12, "high": 24}
        return max(
            0,
            min(
                100,
                int(
                    (
                        engagement_map.get(engagement_level, 40)
                        + repayment_map.get(repayment_level, 45)
                    )
                    / 2
                    - churn_penalty.get(churn_level, 12)
                    - min(journey_risk_count, 5) * 3
                ),
            ),
        )

    def _build_llm_fallback_profile(
        self,
        feature_bundle: BehaviorFeatureBundle,
        *,
        engagement_profile: dict[str, object],
        repayment_willingness: dict[str, object],
        product_sensitivity: dict[str, object],
        churn_risk: dict[str, object],
        contact_preference: dict[str, object],
    ) -> dict[str, object]:
        summary_features = feature_bundle.get("summary_features", {})
        timeline_features = feature_bundle.get("timeline_features", {})
        prepared = feature_bundle.get("prepared_record", {})
        source_variant = str(
            prepared.get("source_meta", {}).get("source_variant", "unknown")
            or "unknown"
        )
        confidence = (
            "high"
            if source_variant in {"prepared_json", "raw_behavior_csv"}
            else "medium"
        )
        timeline_sections = list(timeline_features.get("timeline_sections", []))
        long_gap_hint = self._extract_long_gap_hint(timeline_sections)
        active_trend_level = str(
            summary_features.get("active_trend_level", "medium") or "medium"
        )
        repayment_level = str(
            summary_features.get("repayment_willingness_level", "medium")
            or "medium"
        )
        product_level = str(
            summary_features.get("product_sensitivity_level", "medium")
            or "medium"
        )
        churn_level = str(summary_features.get("churn_risk_level", "medium") or "medium")
        push_open_rate = self._estimate_push_open_rate(
            engagement_level=str(
                summary_features.get("engagement_level", "light") or "light"
            ),
            active_days_30d=int(summary_features.get("login_days_30d", 0) or 0),
        )
        behavior_summary = self._build_behavior_summary_text(
            summary_features,
            timeline_features=timeline_features,
            contact_preference=contact_preference,
        )
        strategy_suggestions = self._build_strategy_suggestions(
            product_sensitivity_level=product_level,
            churn_risk_level=churn_level,
            long_gap_hint=long_gap_hint,
            timeline_sections=timeline_sections,
        )
        return {
            "user_id": feature_bundle["uid"],
            "engagement_profile": engagement_profile,
            "repayment_willingness_proxy": repayment_willingness,
            "product_sensitivity_proxy": product_sensitivity,
            "churn_risk_proxy": churn_risk,
            "contact_preference_proxy": contact_preference,
            "repayment_willingness": {
                "label": self._display_level(repayment_level),
                "score": self._to_star_score(repayment_level),
                "logic_basis": "综合回访稳定性、关键流程持续投入和是否出现履约相关动作，当前更接近规则层代理推断而非直接履约事实。",
            },
            "product_intent": {
                "upgrade_intent": "高" if product_level in {"high", "medium_high"} else "低",
                "reloan_intent": "高" if repayment_level in {"high", "medium_high"} else "中",
                "logic_basis": "结合优惠券、额度选择、申请提交和价格敏感行为，判断用户对提额、续贷与权益包的关注强弱。",
            },
            "churn_risk": {
                "level": self._display_level(churn_level),
                "active_trend": self._display_trend(active_trend_level),
                "last_active_days_ago": long_gap_hint.replace("停顿达 ", "").replace("停顿约 ", ""),
                "last_active_context": self._build_churn_context(
                    long_gap_hint=long_gap_hint,
                    journey_risk_count=int(
                        timeline_features.get("journey_risk_count", 0) or 0
                    ),
                    timeline_sections=timeline_sections,
                ),
            },
            "contact_preference": {
                **contact_preference,
                "push_open_rate": push_open_rate,
            },
            "behavior_summary": behavior_summary,
            "business_advice": "\n".join(
                f"{index + 1}. {item}"
                for index, item in enumerate(strategy_suggestions)
            ),
            "strategy_suggestions": strategy_suggestions,
            "confidence": confidence,
            "risk_signals_display": list(
                feature_bundle.get("derived_signals", {}).get("risk_signals", [])
            ),
        }

    def _build_behavior_summary_text(
        self,
        summary_features: dict[str, object],
        *,
        timeline_features: dict[str, object],
        contact_preference: dict[str, object],
    ) -> str:
        return (
            f"该用户近 30 天活跃天数约 {int(summary_features.get('login_days_30d', 0) or 0)} 天，"
            f"平均单次会话时长约 {int(summary_features.get('avg_session_minutes', 0) or 0)} 分钟，"
            f"行为投入度判断为{self._display_level(str(summary_features.get('engagement_level', 'light') or 'light'))}。"
            f"当前还款意愿为{self._display_level(str(summary_features.get('repayment_willingness_level', 'medium') or 'medium'))}，"
            f"产品敏感度为{self._display_level(str(summary_features.get('product_sensitivity_level', 'medium') or 'medium'))}，"
            f"流失风险为{self._display_level(str(summary_features.get('churn_risk_level', 'medium') or 'medium'))}。"
        )

    def _build_strategy_suggestions(
        self,
        *,
        product_sensitivity_level: str,
        churn_risk_level: str,
        long_gap_hint: str,
        timeline_sections: list[object],
    ) -> list[str]:
        # 规则层只产出**有具体证据支撑**的建议；不再生成「优化产品引导/突出利率解释/
        # 触发保温召回」这类被 prompt 明令禁止的空话模板。无证据时返回空列表，
        # 由 LLM 层 (explainer) 用真正基于该用户旅程的差异化建议填充。
        suggestions: list[str] = []
        if long_gap_hint:
            suggestions.append(
                f"用户在流程中出现{long_gap_hint}，建议在回流窗口前增加提醒和人工跟进。"
            )
        if any(
            isinstance(section, dict)
            and str(section.get("journey_bucket", "")) == "bank_retry"
            for section in timeline_sections
        ):
            suggestions.append(
                "银行卡绑卡阶段建议增加格式实时校验、自动去空格与示例提示，降低账号长度错误带来的阻塞。"
            )
        return suggestions

    def _extract_long_gap_hint(self, timeline_sections: list[object]) -> str:
        for section in timeline_sections:
            if not isinstance(section, dict):
                continue
            if str(section.get("journey_bucket", "")) == "dormancy_return":
                return str(section.get("duration_hint", "") or "")
        return ""

    def _estimate_push_open_rate(
        self,
        *,
        engagement_level: str,
        active_days_30d: int,
    ) -> str:
        if engagement_level == "deep" or active_days_30d >= 18:
            return "高"
        if active_days_30d >= 8:
            return "中"
        return "低"

    def _to_star_score(self, level: str) -> str:
        return {
            "low": "★☆☆☆☆",
            "medium": "★★★☆☆",
            "medium_high": "★★★★☆",
            "high": "★★★★★",
            "light": "★★☆☆☆",
            "balanced": "★★★☆☆",
            "deep": "★★★★☆",
        }.get(level, "N/A")

    def _display_trend(self, level: str) -> str:
        return {
            "low": "偏弱",
            "medium": "平稳",
            "high": "上升",
        }.get(level, level or "未知")

    def _build_churn_context(
        self,
        *,
        long_gap_hint: str,
        journey_risk_count: int,
        timeline_sections: list[object],
    ) -> str:
        latest_title = ""
        for section in reversed(timeline_sections):
            if isinstance(section, dict) and section.get("title"):
                latest_title = str(section.get("title"))
                break
        if long_gap_hint:
            return (
                f"流程中出现{long_gap_hint}后再次回流，说明用户对授信结果仍有关注，"
                "但中途存在明显流失窗口。"
            )
        if journey_risk_count > 0:
            return (
                f"最近旅程在“{latest_title or '关键阶段'}”出现异常或重试，需重点关注该节点的流失风险。"
            )
        return f"当前行为旅程相对连续，最近活跃阶段位于“{latest_title or '当前流程'}”。"

    def _build_timeline_narrative_fallback(
        self,
        timeline_sections: list[dict[str, object]],
    ) -> dict[str, object]:
        section_summaries: list[dict[str, object]] = []
        for section in timeline_sections:
            if not isinstance(section, dict):
                continue
            events = [
                event
                for event in section.get("events", [])
                if isinstance(event, dict)
            ]
            key_actions = [
                str(event.get("action", "") or "").strip()
                for event in events[:3]
                if str(event.get("action", "") or "").strip()
            ]
            section_summaries.append(
                {
                    "section_id": str(section.get("id", "") or ""),
                    "title": str(section.get("title", "") or ""),
                    "duration_hint": str(section.get("duration_hint", "") or ""),
                    "summary": self._fallback_section_summary(section, events),
                    "key_actions": key_actions,
                    "warning_count": int(section.get("warning_count", 0) or 0),
                }
            )

        return {
            "summary": "时间线当前采用规则压缩结果，已保留关键推进、异常阻塞与回流节点。",
            "sections": section_summaries,
            "insights": [
                item["summary"]
                for item in section_summaries[:4]
                if str(item.get("summary", "") or "").strip()
            ],
            "used_llm": False,
        }

    def _fallback_section_summary(
        self,
        section: dict[str, object],
        events: list[dict[str, object]],
    ) -> str:
        title = str(section.get("title", "该阶段") or "该阶段")
        duration = str(section.get("duration_hint", "") or "")
        warning_count = int(section.get("warning_count", 0) or 0)
        compact_event_count = len(events)
        if warning_count > 0:
            return (
                f"{title}阶段压缩后保留 {compact_event_count} 个关键动作，"
                f"共识别 {warning_count} 个异常或阻塞信号，耗时提示为“{duration or '未标注'}”。"
            )
        return (
            f"{title}阶段压缩后保留 {compact_event_count} 个关键动作，"
            f"主要用于还原顺畅推进路径，耗时提示为“{duration or '未标注'}”。"
        )

    def _build_tags(
        self,
        metrics: dict[str, object],
        derived_signals: dict[str, object],
    ) -> list[str]:
        tags = [
            f"engagement-{str(metrics.get('engagement_level', 'light')).replace('_', '-')}",
            f"behavior-{str(metrics.get('engagement_score', 0))}",
            f"product-sensitivity-{str(metrics.get('product_sensitivity_level', 'medium')).replace('_', '-')}",
            f"churn-{str(metrics.get('churn_risk_level', 'medium')).replace('_', '-')}",
            f"value-{str(metrics.get('value_signal_level', 'medium')).replace('_', '-')}",
            f"trend-{str(metrics.get('active_trend_level', 'medium')).replace('_', '-')}",
        ]
        tags.extend(
            str(signal).replace("_", "-")
            for signal in derived_signals.get("risk_signals", [])[:4]
        )
        return sorted(set(tags))

    def _display_level(self, level: str) -> str:
        return {
            "light": "轻度",
            "balanced": "均衡",
            "deep": "深度",
            "low": "低",
            "medium": "中等",
            "medium_high": "中高",
            "high": "高",
        }.get(level, level or "未知")
