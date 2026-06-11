"""Assembly layer for the App profile pipeline."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.core.model_client import ModelClient
from app.schemas.app_profile import AppProfileStructuredResult
from app.scripts.chart_builder import build_app_charts
from app.runtime_skills.app_profile.contracts import (
    AppDecisionResult,
    AppExplanationResult,
    AppFeatureBundle,
    AppPageResult,
    AppRawData,
    AppRunContext,
)
from app.utils.pydantic_compat import model_dump_compat, model_validate_compat


REPORT_STATUS_RULE = "规则降级输出"
REPORT_STATUS_LLM = "LLM 推理完成"


class AppPageAssembler:
    """Merge rule outputs and explanation outputs into the final App page payload."""

    def __init__(self, model_client: ModelClient) -> None:
        self.model_client = model_client

    def build_missing_output(
        self,
        uid: str,
        context: AppRunContext,
        *,
        data_status: str = "missing",
        errors: list[str] | None = None,
    ) -> AppPageResult:
        fallback_reason = "invalid_app_data" if data_status == "invalid" else "missing_app_data"
        insight_summary = (
            "检测到该 uid 的 App 文件存在但内容无效，暂时无法生成稳定画像。"
            if data_status == "invalid"
            else "未找到该用户的 App 安装明细，暂时无法生成有效洞察。"
        )
        reasoning_line = (
            "当前 App 数据文件存在结构异常或解析失败，建议先排查原始数据质量。"
            if data_status == "invalid"
            else "当前缺少 App 明细数据，无法识别借贷、银行和消费类安装轨迹。"
        )
        report_markdown = self._render_business_report(
            uid=uid,
            report_status=REPORT_STATUS_RULE,
            risk_level_cn="低",
            lending_app_count=0,
            recent_lending_count=0,
            risk_reasoning=reasoning_line,
            maturity_level_cn="非银行化用户",
            has_gov_signal=False,
            supporting_apps=[],
            consumption_level_cn="低",
            consumption_reasoning="当前没有足够的 App 明细支撑消费偏好与消费能力分析。",
            lifestyle_tags=["数据不足", "建议人工复核", "App 数据缺失"],
            recommendation="人工复核",
            recommendation_reason=reasoning_line,
        )

        structured = AppProfileStructuredResult(
            uid=uid,
            status="data_missing",
            summary="No app sample data was found for this uid.",
            tags=["app-data-missing"],
            app_insight={
                "summary": insight_summary,
                "reasons": [reasoning_line],
                "labels": ["数据不足", "建议人工复核"],
            },
            model_trace={
                "mode": self.model_client.mode,
                "used_llm": False,
                "model_name": self.model_client.model_name,
                "fallback_reason": fallback_reason,
            },
            report_markdown=report_markdown,
            evidence={
                "source_file": "",
                "application_time": context.get("application_time", ""),
                "raw_counts": {},
                "category_distribution": [],
                "localized_category_distribution": [],
                "install_time_distribution": [],
                "install_bucket_details": {},
                "category_app_details": {},
                "key_app_lists": {},
                "errors": errors or [],
            },
        )
        return self._build_output(uid, model_dump_compat(structured))

    def build_fallback_structured(
        self,
        uid: str,
        raw_data: AppRawData,
        feature_bundle: AppFeatureBundle,
        decision_result: AppDecisionResult,
    ) -> dict[str, Any]:
        evidence = feature_bundle.get("evidence_features", {})
        metrics = decision_result.get("metrics", {})
        risk_assessment = decision_result.get("risk_assessment", {})
        financial_maturity = decision_result.get("financial_maturity", {})
        consumption_profile = decision_result.get("consumption_profile", {})

        structured = AppProfileStructuredResult(
            uid=uid,
            status="ok",
            activity_level=str(decision_result.get("activity_level", "unknown") or "unknown"),
            summary=str(decision_result.get("summary_seed", "") or ""),
            evidence={
                "source_file": evidence.get("source_file", raw_data["source_meta"].get("origin_ref", "")),
                "application_time": feature_bundle.get("application_time", ""),
                "raw_counts": evidence.get("raw_counts", {}),
                "category_distribution": evidence.get("category_distribution", []),
                "localized_category_distribution": evidence.get("localized_category_distribution", []),
                "install_time_distribution": evidence.get("install_time_distribution", []),
                "install_bucket_details": evidence.get("install_bucket_details", {}),
                "category_app_details": evidence.get("category_app_details", {}),
                "key_app_lists": evidence.get("key_app_lists", {}),
            },
            metrics=metrics,
            tags=[str(tag) for tag in decision_result.get("tags_rule", []) if str(tag).strip()],
            risk_assessment={
                "level": str(risk_assessment.get("level", "unknown") or "unknown"),
                "lending_app_count": int(risk_assessment.get("lending_app_count", 0) or 0),
                "recent_7d_lending_apps": risk_assessment.get("recent_7d_lending_apps", []),
                "recent_30d_lending_apps": risk_assessment.get("recent_30d_lending_apps", []),
                "reasoning": str(risk_assessment.get("reasoning_seed", "") or ""),
            },
            financial_maturity={
                "level": str(financial_maturity.get("level", "unknown") or "unknown"),
                "has_bank_app": bool(financial_maturity.get("has_bank_app")),
                "has_ewallet": bool(financial_maturity.get("has_ewallet")),
                "has_gov_app": bool(financial_maturity.get("has_gov_app")),
                "supporting_apps": financial_maturity.get("supporting_apps", []),
                "reasoning": str(financial_maturity.get("reasoning_seed", "") or ""),
            },
            consumption_profile={
                "level": str(consumption_profile.get("level", "unknown") or "unknown"),
                "preferred_categories": consumption_profile.get("preferred_categories", []),
                "reasoning": str(consumption_profile.get("reasoning_seed", "") or ""),
            },
            app_insight=decision_result.get("app_insight_seed", {}),
            model_trace={
                "mode": self.model_client.mode,
                "used_llm": False,
                "model_name": self.model_client.model_name,
                "fallback_reason": "",
            },
            timeline=decision_result.get("timeline", []),
            visuals=decision_result.get("visuals", {}),
            report_markdown="",
        )
        return model_dump_compat(structured)

    def assemble(
        self,
        uid: str,
        fallback_structured: dict[str, Any],
        explanation_result: AppExplanationResult,
    ) -> AppPageResult:
        structured = deepcopy(fallback_structured)
        self._apply_explanation(structured, explanation_result)

        explanation_status = explanation_result.get("explanation_status", "skipped")
        if structured.get("status") != "data_missing":
            structured["status"] = "model_unavailable" if explanation_status == "model_unavailable" else "ok"

        structured["model_trace"] = explanation_result.get("model_trace", structured.get("model_trace", {}))
        if not structured.get("summary"):
            structured["summary"] = self._build_summary(structured)
        structured["report_markdown"] = self._finalize_report_markdown(uid, structured)

        validated = model_dump_compat(model_validate_compat(AppProfileStructuredResult, structured))
        return self._build_output(uid, validated)

    def _apply_explanation(
        self,
        structured: dict[str, Any],
        explanation_result: AppExplanationResult,
    ) -> None:
        if explanation_result.get("summary"):
            structured["summary"] = str(explanation_result["summary"])

        tags = explanation_result.get("tags", [])
        if isinstance(tags, list) and tags:
            existing_tags = [str(tag) for tag in structured.get("tags", []) if str(tag).strip()]
            structured["tags"] = self._dedupe_strings(existing_tags + [str(tag) for tag in tags])

        app_insight = explanation_result.get("app_insight", {})
        if isinstance(app_insight, dict) and app_insight:
            structured["app_insight"] = app_insight

        reasoning_texts = explanation_result.get("reasoning_texts", {})
        if isinstance(reasoning_texts, dict):
            if reasoning_texts.get("risk_assessment_reasoning"):
                structured.setdefault("risk_assessment", {})["reasoning"] = str(
                    reasoning_texts["risk_assessment_reasoning"]
                )
            if reasoning_texts.get("financial_maturity_reasoning"):
                structured.setdefault("financial_maturity", {})["reasoning"] = str(
                    reasoning_texts["financial_maturity_reasoning"]
                )
            if reasoning_texts.get("consumption_profile_reasoning"):
                structured.setdefault("consumption_profile", {})["reasoning"] = str(
                    reasoning_texts["consumption_profile_reasoning"]
                )

        if explanation_result.get("report_markdown"):
            structured["report_markdown"] = str(explanation_result["report_markdown"])

    def _build_output(self, uid: str, structured: dict[str, Any]) -> AppPageResult:
        summary = str(structured.get("summary") or self._build_summary(structured))
        charts = build_app_charts(structured) if structured.get("status") != "data_missing" else []
        report_markdown = str(structured.get("report_markdown") or self._build_report_markdown(uid, structured))
        return {
            "summary": summary,
            "structured_result": structured,
            "charts": charts,
            "report_markdown": report_markdown,
        }

    def _build_summary(self, structured: dict[str, Any]) -> str:
        metrics = structured.get("metrics", {})
        return (
            f"该用户共安装 {metrics.get('installed_app_count', 0)} 个 App，"
            f"主要偏好为 {metrics.get('localized_top_category', metrics.get('top_category', 'Unknown'))}，"
            f"多头借贷风险 {metrics.get('multi_loan_risk_level', 'unknown')}，"
            f"金融成熟度 {metrics.get('financial_maturity_level', 'unknown')}。"
        )

    def _build_report_markdown(self, uid: str, structured: dict[str, Any]) -> str:
        metrics = structured.get("metrics", {})
        risk_assessment = structured.get("risk_assessment", {})
        financial_maturity = structured.get("financial_maturity", {})
        consumption_profile = structured.get("consumption_profile", {})
        tags = structured.get("tags", [])
        key_app_lists = (
            structured.get("evidence", {}).get("key_app_lists", {})
            if isinstance(structured.get("evidence"), dict)
            else {}
        )
        model_trace = structured.get("model_trace", {})
        report_status = REPORT_STATUS_LLM if bool(model_trace.get("used_llm")) else REPORT_STATUS_RULE

        return self._render_business_report(
            uid=uid,
            report_status=report_status,
            risk_level_cn=self._cn_risk_level(
                str(risk_assessment.get("level", metrics.get("multi_loan_risk_level", "unknown")))
            ),
            lending_app_count=int(risk_assessment.get("lending_app_count", metrics.get("lending_app_count", 0)) or 0),
            recent_lending_count=int(metrics.get("recent_30d_lending_count", 0) or 0),
            risk_reasoning=str(risk_assessment.get("reasoning", "") or "暂无明确借贷行为依据。"),
            maturity_level_cn=self._cn_maturity_level(
                str(financial_maturity.get("level", metrics.get("financial_maturity_level", "unknown")))
            ),
            has_gov_signal=bool(financial_maturity.get("has_gov_app")),
            supporting_apps=financial_maturity.get("supporting_apps", []),
            consumption_level_cn=self._cn_consumption_level(
                str(consumption_profile.get("level", metrics.get("consumption_ability_level", "unknown")))
            ),
            consumption_reasoning=(
                str(consumption_profile.get("reasoning", "") or "")
                or f"识别到的消费相关 App 包括：{', '.join(key_app_lists.get('consumption_apps', [])[:5]) or '无'}。"
            ),
            lifestyle_tags=[str(tag) for tag in tags[:3]] or ["画像标签待补充"],
            recommendation=self._build_recommendation(str(risk_assessment.get("level", "unknown"))),
            recommendation_reason=self._build_recommendation_reason(structured),
        )

    def _render_business_report(
        self,
        *,
        uid: str,
        report_status: str,
        risk_level_cn: str,
        lending_app_count: int,
        recent_lending_count: int,
        risk_reasoning: str,
        maturity_level_cn: str,
        has_gov_signal: bool,
        supporting_apps: list[str],
        consumption_level_cn: str,
        consumption_reasoning: str,
        lifestyle_tags: list[str],
        recommendation: str,
        recommendation_reason: str,
    ) -> str:
        gov_text = "有" if has_gov_signal else "无"
        support_text = ", ".join(supporting_apps[:6]) if supporting_apps else "无明确支撑 App"
        tags_lines = "\n".join(f"- {tag}" for tag in lifestyle_tags[:3])
        return (
            f"### 墨西哥用户画像与风控评估报告 (UID: {uid})\n\n"
            f"**当前结果状态**：{report_status}\n\n"
            f"#### 1. 风险控制：多头借贷评估\n"
            f"- **风险等级**：{risk_level_cn}\n"
            f"- **借贷 App 总数**：{lending_app_count}\n"
            f"- **近30天新增借贷 App**：{recent_lending_count}\n"
            f"- **判断依据**：{risk_reasoning}\n\n"
            f"#### 2. 金融成熟度与资质分析\n"
            f"- **成熟度标签**：{maturity_level_cn}\n"
            f"- **正规就业/公共服务信号**：{gov_text}\n"
            f"- **支撑 App**：{support_text}\n\n"
            f"#### 3. 消费能力与偏好评估\n"
            f"- **消费水平**：{consumption_level_cn}\n"
            f"- **分析说明**：{consumption_reasoning}\n\n"
            f"#### 4. 综合生活方式标签\n"
            f"{tags_lines}\n\n"
            f"#### 5. 最终风控建议\n"
            f"- **建议操作**：{recommendation}\n"
            f"- **核心理由**：{recommendation_reason}\n"
        )

    def _cn_risk_level(self, level: str) -> str:
        return {"high": "高", "medium": "中", "low": "低", "unknown": "低"}.get(level, "低")

    def _cn_maturity_level(self, level: str) -> str:
        return {
            "banked": "银行化用户",
            "semi_banked": "半银行化用户",
            "non_banked": "非银行化用户",
            "unknown": "非银行化用户",
        }.get(level, "非银行化用户")

    def _cn_consumption_level(self, level: str) -> str:
        return {
            "high": "高",
            "medium_high": "中偏上",
            "medium": "中",
            "low": "低",
            "unknown": "中",
        }.get(level, "中")

    def _build_recommendation(self, risk_level: str) -> str:
        if risk_level == "high":
            return "建议拒绝"
        if risk_level == "medium":
            return "人工复核"
        return "优先通过"

    def _build_recommendation_reason(self, structured: dict[str, Any]) -> str:
        metrics = structured.get("metrics", {})
        risk_level = str(metrics.get("multi_loan_risk_level", "unknown") or "unknown")
        maturity_level = self._cn_maturity_level(
            str(metrics.get("financial_maturity_level", "unknown") or "unknown")
        )
        top_category = str(
            metrics.get("localized_top_category", metrics.get("top_category", "Unknown")) or "Unknown"
        )
        if risk_level == "high":
            return f"近30天借贷类应用安装密度较高，且主要偏好集中在 {top_category}，需要优先控制风险。"
        if risk_level == "medium":
            return f"存在一定借贷安装信号，但仍需结合 {maturity_level} 与消费能力做人工判断。"
        return f"借贷风险较低，且画像显示为 {maturity_level}，整体可作为较稳健用户处理。"

    def _finalize_report_markdown(self, uid: str, structured: dict[str, Any]) -> str:
        model_trace = structured.get("model_trace", {}) if isinstance(structured.get("model_trace"), dict) else {}
        used_llm = bool(model_trace.get("used_llm"))
        report = str(structured.get("report_markdown") or "")
        report_status = REPORT_STATUS_LLM if used_llm else REPORT_STATUS_RULE

        if not used_llm or not report.strip():
            return self._build_report_markdown(uid, structured)
        return self._normalize_report_status_line(report, report_status=report_status)

    def _normalize_report_status_line(self, report_markdown: str, *, report_status: str) -> str:
        status_line = f"**当前结果状态**：{report_status}"
        lines = report_markdown.splitlines()
        for index, line in enumerate(lines):
            if "当前结果状态" in line:
                lines[index] = status_line
                return "\n".join(lines)

        if lines and lines[0].startswith("### "):
            return "\n".join([lines[0], "", status_line, "", *lines[1:]])
        return "\n".join([status_line, "", report_markdown])

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = str(value or "").strip()
            if not cleaned or cleaned in seen:
                continue
            seen.add(cleaned)
            deduped.append(cleaned)
        return deduped
