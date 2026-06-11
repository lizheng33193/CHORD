"""Decision engine layer for the Credit profile pipeline."""

from __future__ import annotations

from app.runtime_skills.credit_profile.contracts import (
    CreditDecisionResult,
    CreditFeatureBundle,
    CreditRunContext,
)


class CreditDecisionEngine:
    """Build deterministic Credit decisions from normalized features."""

    def decide(
        self,
        feature_bundle: CreditFeatureBundle,
        context: CreditRunContext,
    ) -> CreditDecisionResult:
        """v6.1 路径 Q：按 profile_mode 分支。"""
        if context.get("profile_mode") == "risk_features":
            return self._decide_risk_features(feature_bundle, context)
        return self._decide_buro(feature_bundle, context)

    def _decide_buro(
        self,
        feature_bundle: CreditFeatureBundle,
        _context: CreditRunContext,
    ) -> CreditDecisionResult:
        prepared = feature_bundle.get("prepared_record", {})
        summary_features = feature_bundle.get("summary_features", {})
        account_features = feature_bundle.get("account_features", {})
        derived_signals = feature_bundle.get("derived_signals", {})
        source_meta = prepared.get("source_meta", {})

        financial_maturity = self._build_financial_maturity(summary_features, account_features)
        debt_pressure = self._build_debt_pressure(summary_features)
        credit_stability = self._build_credit_stability(summary_features, prepared)
        borrowing_urgency = self._build_borrowing_urgency(summary_features, prepared)
        risk_flags = self._build_risk_flags(summary_features, account_features)
        credit_signal_score = self._build_credit_signal_score(
            risk_level=str(summary_features.get("risk_level", "unknown") or "unknown"),
            credit_score_band=str(summary_features.get("credit_score_band", "unknown") or "unknown"),
            score_value=int(summary_features.get("score_value", 0) or 0),
            credit_stability_level=str(summary_features.get("credit_stability_level", "medium") or "medium"),
        )
        llm_fallback_profile = self._build_llm_fallback_profile(
            feature_bundle,
            financial_maturity=financial_maturity,
            debt_pressure=debt_pressure,
            credit_stability=credit_stability,
            borrowing_urgency=borrowing_urgency,
            risk_flags=risk_flags,
        )

        metrics = {
            "credit_score_band": str(summary_features.get("credit_score_band", "unknown") or "unknown"),
            "repayment_status": str(summary_features.get("repayment_status", "unknown") or "unknown"),
            "risk_level": str(summary_features.get("risk_level", "unknown") or "unknown"),
            "debt_pressure_level": str(summary_features.get("debt_pressure_level", "unknown") or "unknown"),
            "credit_stability_level": str(summary_features.get("credit_stability_level", "unknown") or "unknown"),
            "credit_stability_grade": str(summary_features.get("credit_stability_grade", "unknown") or "unknown"),
            "borrowing_hunger_level": str(summary_features.get("borrowing_hunger_level", "unknown") or "unknown"),
            "borrowing_urgency_level": str(summary_features.get("borrowing_urgency_level", "unknown") or "unknown"),
            "financial_maturity_level": str(summary_features.get("financial_maturity_level", "unknown") or "unknown"),
            "buro_cleaning_status": str(
                derived_signals.get("buro_cleaning", {}).get("status", "unknown") or "unknown"
            ),
            "score_model": str(prepared.get("score", {}).get("score_model", "unknown") or "unknown"),
            "score_value": int(summary_features.get("score_value", 0) or 0),
            "credit_signal_score": credit_signal_score,
            "radar_scores": dict(derived_signals.get("radar_scores", {})),
            "repayment_timeline": list(prepared.get("repayment_timeline", [])),
            "repayment_amount_timeline": list(prepared.get("repayment_amount_timeline", [])),
            "repayment_amount_notes": list(prepared.get("repayment_amount_notes", [])),
            "total_outstanding_debt_mxn": int(summary_features.get("total_outstanding_debt_mxn", 0) or 0),
            "monthly_payment_estimate_mxn": int(summary_features.get("monthly_payment_estimate_mxn", 0) or 0),
            "oldest_account_age_months": int(summary_features.get("oldest_account_age_months", 0) or 0),
            "inquiries_last_3_months": int(summary_features.get("inquiries_last_3_months", 0) or 0),
            "inquiries_last_6_months": int(summary_features.get("inquiries_last_6_months", 0) or 0),
            "inquiries_last_12_months": int(summary_features.get("inquiries_last_12_months", 0) or 0),
            "total_accounts": int(account_features.get("total_accounts", 0) or 0),
            "active_accounts": int(account_features.get("active_accounts", 0) or 0),
            "high_utilization_accounts": int(account_features.get("high_utilization_accounts", 0) or 0),
        }

        evidence_seed = {
            "market_context": "mexico_buro_credit_profile",
            "analysis_mode": str(source_meta.get("source_variant", "prepared_record") or "prepared_record"),
            "profile_header": dict(prepared.get("profile_header", {})),
            "credit_report_date": str(source_meta.get("credit_report_date", "") or ""),
            "input_summary": {
                "summary": dict(prepared.get("summary", {})),
                "delinquency": dict(prepared.get("delinquency", {})),
                "inquiries": dict(prepared.get("inquiries", {})),
            },
            "source_meta": dict(source_meta),
            "risk_flags": risk_flags,
            "radar_scores": dict(derived_signals.get("radar_scores", {})),
            "repayment_timeline": list(prepared.get("repayment_timeline", [])),
            "repayment_amount_timeline": list(prepared.get("repayment_amount_timeline", [])),
            "repayment_amount_notes": list(prepared.get("repayment_amount_notes", [])),
            "account_details": list(prepared.get("account_details", [])),
            "llm_credit_profile": llm_fallback_profile,
        }

        return {
            "uid": feature_bundle["uid"],
            "country_code": feature_bundle["country_code"],
            "decision_status": "ok",
            "summary_seed": str(llm_fallback_profile.get("credit_summary", "") or ""),
            "evidence_seed": evidence_seed,
            "financial_maturity": financial_maturity,
            "debt_pressure": debt_pressure,
            "credit_stability": credit_stability,
            "borrowing_urgency": borrowing_urgency,
            "credit_signal_score": credit_signal_score,
            "metrics": metrics,
            "tags_rule": self._build_tags(metrics, risk_flags),
            "llm_fallback_profile": llm_fallback_profile,
            "errors": list(feature_bundle.get("errors", [])),
        }

    def build_prompt_payload(
        self,
        feature_bundle: CreditFeatureBundle,
        decision_result: CreditDecisionResult,
    ) -> dict[str, object]:
        prepared = feature_bundle.get("prepared_record", {})
        profile_mode = decision_result.get("metrics", {}).get("profile_mode", "buro")
        risk_features_record = decision_result.get("evidence_seed", {}).get("risk_features_record", {}) or {}
        return {
            "uid": feature_bundle["uid"],
            "prepared_credit_record": dict(prepared),
            "derived_signals": {
                "summary_features": dict(feature_bundle.get("summary_features", {})),
                "account_features": dict(feature_bundle.get("account_features", {})),
                "radar_scores": dict(feature_bundle.get("derived_signals", {}).get("radar_scores", {})),
                "trend_flags": dict(feature_bundle.get("derived_signals", {}).get("trend_flags", {})),
            },
            "default_inference": {
                "risk_level": decision_result.get("metrics", {}).get("risk_level", "unknown"),
                "debt_pressure_level": decision_result.get("metrics", {}).get("debt_pressure_level", "unknown"),
                "credit_stability_level": decision_result.get("metrics", {}).get("credit_stability_level", "unknown"),
                "borrowing_urgency_level": decision_result.get("metrics", {}).get("borrowing_urgency_level", "unknown"),
                "financial_maturity_level": decision_result.get("metrics", {}).get("financial_maturity_level", "unknown"),
                "credit_signal_score": decision_result.get("credit_signal_score", 0),
            },
            "fallback_llm_profile": dict(decision_result.get("llm_fallback_profile", {})),
            "profile_mode": profile_mode,
            "risk_features_record": dict(risk_features_record) if isinstance(risk_features_record, dict) else {},
        }

    def _build_financial_maturity(
        self,
        summary_features: dict[str, object],
        account_features: dict[str, object],
    ) -> dict[str, object]:
        level = str(summary_features.get("financial_maturity_level", "thin_file") or "thin_file")
        oldest_months = int(summary_features.get("oldest_account_age_months", 0) or 0)
        has_bank_credit_card = bool(account_features.get("has_bank_credit_card", False))
        label = {
            "mature": "成熟型",
            "growing": "成长型",
            "thin_file": "薄征信",
        }.get(level, "未知")
        reasoning = (
            f"最老账户账龄为 {oldest_months} 个月，"
            f"{'已具备' if has_bank_credit_card else '暂未形成'}银行系信用卡足迹。"
        )
        return {
            "level": level,
            "display_level": label,
            "credit_history_years": round(oldest_months / 12, 1),
            "has_bank_credit_card": has_bank_credit_card,
            "reasoning": reasoning,
        }

    def _build_debt_pressure(self, summary_features: dict[str, object]) -> dict[str, object]:
        level = str(summary_features.get("debt_pressure_level", "medium") or "medium")
        return {
            "level": level,
            "display_level": self._display_level(level),
            "total_debt_mxn": int(summary_features.get("total_outstanding_debt_mxn", 0) or 0),
            "monthly_payment_mxn": int(summary_features.get("monthly_payment_estimate_mxn", 0) or 0),
            "avg_credit_utilization": f"{int(summary_features.get('avg_credit_utilization_pct', 0) or 0)}%",
            "reasoning": (
                "负债压力综合参考当前总负债、估算月还款以及额度使用率，"
                "用于判断用户短期资金承压情况。"
            ),
        }

    def _build_credit_stability(
        self,
        summary_features: dict[str, object],
        prepared: dict[str, object],
    ) -> dict[str, object]:
        level = str(summary_features.get("credit_stability_level", "medium") or "medium")
        grade = str(summary_features.get("credit_stability_grade", "fair") or "fair")
        delinquency = prepared.get("delinquency", {})
        return {
            "level": level,
            "display_level": self._display_level(level),
            "grade": grade,
            "total_delinquencies": int(delinquency.get("total_delinquent_accounts", 0) or 0),
            "max_dpd": int(delinquency.get("max_delinquency_days", 0) or 0),
            "months_since_last_delinquency": 0,
            "reasoning": "信用稳定性主要基于逾期深度、逾期账户数量以及当前账户状态综合判断。",
        }

    def _build_borrowing_urgency(
        self,
        summary_features: dict[str, object],
        prepared: dict[str, object],
    ) -> dict[str, object]:
        level = str(summary_features.get("borrowing_urgency_level", "medium") or "medium")
        inquiries = prepared.get("inquiries", {})
        inquiry_sources = inquiries.get("inquiry_sources", [])
        inquiry_source_type = "mixed" if len(inquiry_sources) > 1 else "single" if inquiry_sources else "unknown"
        return {
            "level": level,
            "display_level": self._display_level(level),
            "inquiries_3m": int(summary_features.get("inquiries_last_3_months", 0) or 0),
            "inquiries_6m": int(summary_features.get("inquiries_last_6_months", 0) or 0),
            "inquiry_sources_type": inquiry_source_type,
            "reasoning": "借贷饥渴度主要结合近 3 至 6 个月查询热度判断，用于识别短期融资活跃度。",
        }

    def _build_risk_flags(
        self,
        summary_features: dict[str, object],
        account_features: dict[str, object],
    ) -> list[str]:
        flags: list[str] = []
        if int(summary_features.get("score_value", 0) or 0) > 0:
            flags.append(f"Score value {int(summary_features.get('score_value', 0) or 0)}")
        if int(summary_features.get("oldest_account_age_months", 0) or 0) < 6:
            flags.append("Very short credit history")
        if int(account_features.get("high_utilization_accounts", 0) or 0) > 0:
            flags.append("High utilization account present")
        if int(summary_features.get("inquiries_last_3_months", 0) or 0) >= 3:
            flags.append("High inquiry heat in last 3 months")
        if str(summary_features.get("risk_level", "unknown") or "unknown") == "high":
            flags.append("Overall credit risk resolved as high")
        return flags or ["No major credit risk flags were detected from the prepared record."]

    def _build_credit_signal_score(
        self,
        *,
        risk_level: str,
        credit_score_band: str,
        score_value: int,
        credit_stability_level: str,
    ) -> int:
        risk_buffer = {"low": 78, "medium": 52, "high": 28}.get(risk_level, 40)
        band_bonus = {"A": 12, "B": 6, "C": 0, "D": -8}.get(credit_score_band, 0)
        stability_bonus = {"high": 10, "medium_high": 6, "medium": 0, "low": -8}.get(
            credit_stability_level,
            0,
        )
        score_hint = max(0, min(100, round(score_value / 9))) if score_value > 0 else 35
        return max(0, min(100, int((risk_buffer + score_hint) / 2 + band_bonus + stability_bonus)))

    def _build_llm_fallback_profile(
        self,
        feature_bundle: CreditFeatureBundle,
        *,
        financial_maturity: dict[str, object],
        debt_pressure: dict[str, object],
        credit_stability: dict[str, object],
        borrowing_urgency: dict[str, object],
        risk_flags: list[str],
    ) -> dict[str, object]:
        summary_features = feature_bundle.get("summary_features", {})
        prepared = feature_bundle.get("prepared_record", {})
        source_variant = str(prepared.get("source_meta", {}).get("source_variant", "unknown") or "unknown")
        confidence = "high" if source_variant in {"prepared_json", "raw_credit_csv"} else "medium"
        credit_summary = self._build_credit_summary_text(
            summary_features,
            financial_maturity=financial_maturity,
            debt_pressure=debt_pressure,
            credit_stability=credit_stability,
            borrowing_urgency=borrowing_urgency,
            risk_flags=risk_flags,
        )
        return {
            "user_id": feature_bundle["uid"],
            "financial_maturity": financial_maturity,
            "debt_pressure": debt_pressure,
            "credit_stability": credit_stability,
            "borrowing_urgency": borrowing_urgency,
            "credit_summary": credit_summary,
            "confidence": confidence,
            "risk_flags": risk_flags,
            "risk_flags_display": [self._translate_risk_flag(flag) for flag in risk_flags],
        }

    def _build_credit_summary_text(
        self,
        summary_features: dict[str, object],
        *,
        financial_maturity: dict[str, object],
        debt_pressure: dict[str, object],
        credit_stability: dict[str, object],
        borrowing_urgency: dict[str, object],
        risk_flags: list[str],
    ) -> str:
        risk_level = str(summary_features.get("risk_level", "unknown") or "unknown")
        score_value = int(summary_features.get("score_value", 0) or 0)
        total_debt = int(summary_features.get("total_outstanding_debt_mxn", 0) or 0)
        monthly_payment = int(summary_features.get("monthly_payment_estimate_mxn", 0) or 0)
        inquiries_12m = int(summary_features.get("inquiries_last_12_months", 0) or 0)
        oldest_months = int(summary_features.get("oldest_account_age_months", 0) or 0)
        risk_label = self._display_level(risk_level)
        financial_maturity_label = str(financial_maturity.get("display_level", "未知") or "未知")
        debt_pressure_label = str(debt_pressure.get("display_level", "未知") or "未知")
        credit_stability_label = str(credit_stability.get("display_level", "未知") or "未知")
        borrowing_urgency_label = str(borrowing_urgency.get("display_level", "未知") or "未知")
        flags_text = "；".join(self._translate_risk_flag(flag) for flag in risk_flags[:5])
        segment = self._profile_segment_text(
            financial_maturity_level=str(financial_maturity.get("level", "") or ""),
            debt_pressure_level=str(debt_pressure.get("level", "") or ""),
            credit_stability_level=str(credit_stability.get("level", "") or ""),
        )
        recommendation = self._risk_recommendation_text(
            risk_level=risk_level,
            debt_pressure_level=str(debt_pressure.get("level", "") or ""),
            borrowing_urgency_level=str(borrowing_urgency.get("level", "") or ""),
        )
        return (
            f"该用户当前征信画像基于标准化 Buró 征信记录生成，整体风险水平为{risk_label}，"
            f"更接近“{segment}”特征。当前评分值为 {score_value} 分，金融成熟度判断为{financial_maturity_label}，"
            f"说明其信用基础仍偏早期，抗风险缓冲能力需要结合后续履约表现持续观察。"
            "\n\n"
            f"从结构化证据看，最老账户账龄约 {oldest_months} 个月，总负债约 {total_debt} MXN，"
            f"估算月还款约 {monthly_payment} MXN，近 12 个月查询次数为 {inquiries_12m} 次。"
            f"四维评估中，负债压力为{debt_pressure_label}、信用稳定性为{credit_stability_label}、"
            f"借贷饥渴度为{borrowing_urgency_label}。这些信号共同说明，当前征信并非空白，"
            f"但仍存在需要重点跟踪的边界条件。"
            "\n\n"
            f"建议层面，{recommendation} 现阶段应重点关注的风险提示包括：{flags_text}。"
            "如果后续还款表现稳定、查询热度回落、额度使用率逐步下降，则画像可向更稳健方向修正。"
        )

    def _build_tags(self, metrics: dict[str, object], risk_flags: list[str]) -> list[str]:
        tags = [
            f"risk-{str(metrics.get('risk_level', 'unknown')).replace('_', '-')}",
            f"credit-{str(metrics.get('credit_score_band', 'unknown')).lower()}",
            f"debt-pressure-{str(metrics.get('debt_pressure_level', 'unknown')).replace('_', '-')}",
            f"stability-{str(metrics.get('credit_stability_level', 'unknown')).replace('_', '-')}",
            f"borrowing-urgency-{str(metrics.get('borrowing_urgency_level', 'unknown')).replace('_', '-')}",
            f"financial-maturity-{str(metrics.get('financial_maturity_level', 'unknown')).replace('_', '-')}",
        ]
        if str(metrics.get("risk_level", "unknown")) == "high":
            tags.append("collection-watch")
        if str(metrics.get("financial_maturity_level", "unknown")) == "thin_file":
            tags.append("credit-footprint-thin")
        tags.extend(flag.lower().replace(" ", "-") for flag in risk_flags[:4])
        return sorted(set(tags))

    def _display_level(self, level: str) -> str:
        return {
            "low": "低",
            "medium": "中",
            "medium_high": "中高",
            "high": "高",
            "thin_file": "薄征信",
            "growing": "成长型",
            "mature": "成熟型",
        }.get(level, level or "未知")

    def _translate_risk_flag(self, flag: str) -> str:
        text = str(flag or "").strip()
        if text.startswith("Score value "):
            score_value = text.replace("Score value ", "").strip()
            return f"评分值偏低（{score_value} 分）"

        mapping = {
            "Very short credit history": "信用历史极短",
            "High utilization account present": "存在高使用率账户",
            "High inquiry heat in last 3 months": "近 3 个月查询热度偏高",
            "Overall credit risk resolved as high": "整体征信风险偏高",
            "No major credit risk flags were detected from the prepared record.": "当前未识别出显著征信风险信号",
        }
        return mapping.get(text, text or "当前暂无额外风险提示")

    def _profile_segment_text(
        self,
        *,
        financial_maturity_level: str,
        debt_pressure_level: str,
        credit_stability_level: str,
    ) -> str:
        if financial_maturity_level == "thin_file" and debt_pressure_level in {"medium", "high"}:
            return "薄征信起步型客群"
        if debt_pressure_level == "high":
            return "高负债承压型客群"
        if credit_stability_level == "high":
            return "履约相对稳定型客群"
        return "信用观察期客群"

    def _risk_recommendation_text(
        self,
        *,
        risk_level: str,
        debt_pressure_level: str,
        borrowing_urgency_level: str,
    ) -> str:
        if risk_level == "high":
            return "建议以审慎授信和短周期复核为主，初始额度不宜激进，并对查询热度和逾期信号设置更严格阈值。"
        if debt_pressure_level == "high" or borrowing_urgency_level == "high":
            return "建议采用分层额度与动态监控策略，重点观察近期资金周转压力及新增借贷动作。"
        return "建议在常规风控阈值下稳健评估授信，同时继续观察其还款连续性和征信结构改善情况。"

    def _decide_risk_features(
        self,
        feature_bundle: CreditFeatureBundle,
        _context: CreditRunContext,
    ) -> CreditDecisionResult:
        """v6.1 路径 Q：TH 风控特征 V1 极简决策（不分等级，不打分）。"""
        risk_record = feature_bundle.get("derived_signals", {}).get("risk_features_record", {})
        return {
            "uid": feature_bundle["uid"],
            "country_code": feature_bundle["country_code"],
            "decision_status": "ok" if risk_record else "missing",
            "summary_seed": "TH 风控特征聚合 V1 — 由 LLM explainer 解读 11 维原始信号",
            "evidence_seed": {"risk_features_record": risk_record},
            "financial_maturity": {},
            "debt_pressure": {},
            "credit_stability": {},
            "borrowing_urgency": {},
            "credit_signal_score": 0,
            "metrics": {"profile_mode": "risk_features"},
            "tags_rule": [],
            "llm_fallback_profile": {"summary": "", "tags": [], "report_markdown": ""},
            "errors": list(feature_bundle.get("errors", [])),
        }
