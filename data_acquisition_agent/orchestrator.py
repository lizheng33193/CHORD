"""End-to-end pipeline. See Design Doc §6.2."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from app.core.logger import get_logger
from app.core.model_client import ModelClient
from .manifest import load_manifest, ManifestNotImplemented
from .prompt_assembler import assemble_prompt, estimate_tokens
from .output_scanner import scan_credentials, scan_python_dangerous, check_sql_policy
from .schemas import (GenerateRequest, GenerateResponse, AuditReport, GenerateMetadata,
                      TokensUsed, ErrorType)

logger = get_logger(__name__)


class OrchestratorError(Exception):
    def __init__(self, error_type: ErrorType, message: str, request_id: str = ""):
        super().__init__(message)
        self.error_type = error_type
        self.message = message
        self.request_id = request_id


_LLM_SCHEMA_HINTS = ("json_parse", "json_repair_failed", "schema_validation_failed")
_RESPONSE_SCHEMA = {"type": "object", "properties": {
    "reasoning_summary": {"type": "string"}, "sql": {"type": ["string", "null"]},
    "sql_kind": {"type": ["string", "null"]}, "python": {"type": ["string", "null"]},
    "audit_report": {"type": "object"}},
    "required": ["reasoning_summary", "sql", "sql_kind", "python", "audit_report"]}

# NL→sql_kind 一致性：build_table_script 仅当用户原文显式表达建表/物化意图时合法。
_BUILD_INTENT_PATTERN = re.compile(
    r"(create\s+(a\s+)?table|build\s+(a\s+)?(result\s+)?table|persist|materiali[sz]e"
    r"|save\s+.*\b(table|cohort)\b|建表|建一[张个]表|物化|落表|存表|保存.*表)",
    re.IGNORECASE,
)


class DataAcquisitionOrchestrator:
    def __init__(self, model_client=None):
        self.model_client = model_client or ModelClient()

    def generate(self, request: GenerateRequest, *, retrieved_context=None) -> GenerateResponse:
        rid = str(uuid.uuid4())
        try:
            manifest = load_manifest(request.target_country.value)
        except ManifestNotImplemented as e:
            raise OrchestratorError(ErrorType.BAD_REQUEST, str(e), request_id=rid)
        try:
            prompt, token_estimate, files, redaction_hits = assemble_prompt(
                request,
                manifest,
                retrieved_context=retrieved_context,
            )
        except ValueError:
            raise OrchestratorError(ErrorType.PROMPT_TOO_LARGE,
                                    "prompt exceeds token budget", request_id=rid)
        fallback = {"reasoning_summary": "", "sql": None, "sql_kind": None, "python": None,
                    "audit_report": {"high_risk_ddl": False, "final_verdict": ""}}
        mr = self.model_client.generate_structured(skill_name="data_acquisition",
            prompt=prompt, fallback_result=fallback, response_schema=_RESPONSE_SCHEMA)
        if mr.get("status") != "ok":
            err = str(mr.get("structured_result", {}).get("model_error", ""))
            if any(h in err for h in _LLM_SCHEMA_HINTS):
                raise OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED,
                                        "model output failed schema validation",
                                        request_id=rid)
            raise OrchestratorError(ErrorType.UPSTREAM_LLM_ERROR,
                                    "model unavailable", request_id=rid)
        payload = mr["structured_result"]
        self._enforce_nl_sql_kind_consistency(request, payload, rid)
        danger_events = self._enforce_output_policies(payload, manifest, rid)
        return self._build_response(rid, request, payload, mr, token_estimate, files,
                                    redaction_hits, danger_events)

    # 6.1 最小 stub —— 6.2 / 6.3 会扩展
    def _enforce_output_policies(self, payload, manifest, rid: str) -> int:
        py = payload.get("python") or ""
        combined = (payload.get("sql") or "") + "\n" + py
        danger_events = 0
        cred_hits = scan_credentials(combined)
        if cred_hits:
            raise OrchestratorError(ErrorType.CREDENTIAL_LEAK,
                                    "credential pattern in artifact", request_id=rid)
        if py:
            py_hits = scan_python_dangerous(py)
            if py_hits:
                raise OrchestratorError(ErrorType.DANGEROUS_CODE,
                                        "blacklist hit in python", request_id=rid)
        sql = payload.get("sql"); kind = payload.get("sql_kind")
        if sql and kind:
            try:
                check_sql_policy(sql, kind, manifest.analyst_private_prefix)
            except ValueError:
                raise OrchestratorError(ErrorType.DDL_POLICY_VIOLATION,
                                        "artifact failed SQL policy", request_id=rid)
        return danger_events  # V1 当前为 0；保留位以便后续累计 warning 类命中

    # 注：danger_scan_events 仅出现在成功响应的 metadata，表示成功 artifact 内 L2 命中数；V1 在
    # 命中（凭据 / 黑名单 / DDL 违规）时直接 raise OrchestratorError，不在 ErrorResponse 暴露 hit 计数。

    def _enforce_nl_sql_kind_consistency(self, request, payload, rid: str) -> None:
        # NL→sql_kind 一致性硬拒：用户原文无建表/物化意图但 LLM 返回 build_table_script
        # 时直接拒绝，避免 LLM 自由扩张范围导致非预期 DDL artifact 进入审核流程。
        if payload.get("sql_kind") != "build_table_script":
            return
        if _BUILD_INTENT_PATTERN.search(request.natural_language_request or ""):
            return
        raise OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED,
                                "response payload failed schema validation",
                                request_id=rid)

    def _build_response(self, rid, request, payload, mr, token_estimate, files,
                        redaction_hits, danger_events):
        # Real LLM 偶发省略 python / audit_report / sql_kind 等键。仅补缺失/None/空字段，
        # 不覆盖已有值；Pydantic schema 与 validators 不变。
        if payload.get("reasoning_summary") is None:
            payload["reasoning_summary"] = ""
        if "sql" not in payload:
            payload["sql"] = None
        if "python" not in payload:
            payload["python"] = None
        if not payload.get("sql_kind"):
            payload["sql_kind"] = "query_only"
        ar = payload.get("audit_report")
        if ar is None or ar == {}:
            payload["audit_report"] = {"high_risk_ddl": False, "final_verdict": ""}
        elif isinstance(ar, dict):
            ar.setdefault("high_risk_ddl", False)
            ar.setdefault("final_verdict", "")
        try:
            return GenerateResponse(
                request_id=rid, target_country=request.target_country,
                reasoning_summary=payload.get("reasoning_summary", ""),
                sql=payload.get("sql"), sql_kind=payload.get("sql_kind"),
                python=payload.get("python"),
                audit_report=AuditReport(**payload.get("audit_report", {})),
                metadata=GenerateMetadata(
                    model=mr.get("model_name", ""), tokens_used=None,
                    token_estimate=token_estimate, knowledge_files_loaded=files,
                    redaction_events=redaction_hits,
                    danger_scan_events=danger_events,
                    generated_at=datetime.now(timezone.utc).isoformat()))
        except Exception:
            raise OrchestratorError(ErrorType.SCHEMA_VALIDATION_FAILED,
                                    "response payload failed schema validation",
                                    request_id=rid)
