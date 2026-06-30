"""Conservative route policy for M2D-12 risk knowledge answering."""

from __future__ import annotations

import re

from app.risk_knowledge.service.schemas import RiskKnowledgeQuery, RouteDecision


_BLOCKER_PATTERNS = (
    re.compile(r"\b(sql|uid|cohort|trace|run_trace|data agent)\b", re.IGNORECASE),
    re.compile(r"(统计|查询|拉取|找出|筛选|一批|批量|用户\d+|workspace|画像数据)"),
)
_EXPLICIT_RISK_PATTERNS = (
    re.compile(r"(什么是|为何|为什么|如何解释|解释)"),
    re.compile(r"(多头借贷|贷前风控|贷中风控|贷后风控|风险指标|风险策略|高频申请|申请频率|欺诈风险|风控)"),
)


class RiskKnowledgeRoutePolicy:
    def decide(self, query: RiskKnowledgeQuery) -> RouteDecision:
        text = query.query.strip()
        if query.intent == "profile_explanation":
            return RouteDecision(
                should_route=True,
                reason="profile_explanation",
                target_kb_id=query.kb_id,
            )
        for pattern in _BLOCKER_PATTERNS:
            if pattern.search(text):
                return RouteDecision(
                    should_route=False,
                    reason="data_or_profile_query",
                    target_kb_id=query.kb_id,
                )
        if all(pattern.search(text) for pattern in _EXPLICIT_RISK_PATTERNS):
            return RouteDecision(
                should_route=True,
                reason="risk_concept",
                target_kb_id=query.kb_id,
            )
        return RouteDecision(
            should_route=False,
            reason="general_or_ambiguous",
            target_kb_id=query.kb_id,
        )
