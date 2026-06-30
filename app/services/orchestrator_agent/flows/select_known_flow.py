"""Selector for migrated known-intent flows.

Unmigrated intents return None and are handled by the legacy agent_loop path.
"""

from __future__ import annotations

from app.services.orchestrator_agent.flows.answer_workspace import AnswerWorkspaceFlow
from app.services.orchestrator_agent.flows.clarify_data_request import ClarifyDataRequestFlow
from app.services.orchestrator_agent.flows.clarify_scope import ClarifyScopeFlow
from app.services.orchestrator_agent.flows.base import KnownFlow
from app.services.orchestrator_agent.flows.data_agent_run import DataAgentRunFlow
from app.services.orchestrator_agent.flows.general_chat import GeneralChatFlow
from app.services.orchestrator_agent.flows.profile import ProfileFlow
from app.services.orchestrator_agent.flows.query_data_then_profile import QueryDataThenProfileFlow
from app.services.orchestrator_agent.flows.risk_knowledge_answer import RiskKnowledgeAnswerFlow
from app.services.orchestrator_agent.flows.run_trace import RunTraceFlow
from app.services.orchestrator_agent.schemas import NormalizedRequest


def select_known_flow(request: NormalizedRequest) -> KnownFlow | None:
    if request.intent == "answer_from_workspace":
        return AnswerWorkspaceFlow()
    if request.intent == "risk_knowledge_answer":
        return RiskKnowledgeAnswerFlow()
    if request.intent == "need_clarification":
        return ClarifyScopeFlow()
    if request.intent == "clarify_data_request":
        return ClarifyDataRequestFlow()
    if request.intent == "create_data_agent_run":
        return DataAgentRunFlow()
    if request.intent in {"profile_uid", "profile_batch"}:
        return ProfileFlow()
    if request.intent == "query_data_then_profile":
        return QueryDataThenProfileFlow()
    if request.intent == "run_trace":
        return RunTraceFlow()
    if request.intent == "general_chat":
        return GeneralChatFlow()
    return None
