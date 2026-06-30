"""DashScope HTTP reranker provider for M2D-11."""

from __future__ import annotations

import json
from urllib import error, request

from app.core.config import settings
from app.risk_knowledge.reranking.errors import (
    InvalidRerankRequestError,
    RerankerProviderConfigError,
    RerankerProviderError,
)
from app.risk_knowledge.reranking.schemas import RerankItem, RerankRequest, RerankResult

_DASHSCOPE_RERANK_ENDPOINT = "https://dashscope.aliyuncs.com/api/v1/services/rerank/text-rerank/text-rerank"


class DashScopeRerankerProvider:
    provider_name = "dashscope"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        endpoint: str | None = None,
        timeout_seconds: int | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.dashscope_api_key
        self.model = model if model is not None else settings.risk_knowledge_reranker_model
        self.endpoint = endpoint if endpoint is not None else (
            settings.risk_knowledge_reranker_http_base_url or _DASHSCOPE_RERANK_ENDPOINT
        )
        self.timeout_seconds = (
            timeout_seconds if timeout_seconds is not None else settings.risk_knowledge_reranker_timeout_seconds
        )

    def rerank(self, request_model: RerankRequest) -> RerankResult:
        if not request_model.candidates:
            raise InvalidRerankRequestError("rerank candidates must not be empty")
        if not self.api_key:
            raise RerankerProviderConfigError("DASHSCOPE_API_KEY is missing")
        payload = {
            "model": self.model,
            "input": {
                "query": request_model.query,
                "documents": [candidate.text for candidate in request_model.candidates],
            },
            "parameters": {},
        }
        if request_model.top_n is not None:
            payload["parameters"]["top_n"] = request_model.top_n

        try:
            response = self._post_rerank_request(payload)
        except Exception as exc:  # pylint: disable=broad-except
            raise RerankerProviderError(
                f"dashscope reranker request failed: {self._sanitize_error_message(str(exc))}"
            ) from exc

        items: list[RerankItem] = []
        for rank, item in enumerate(response.get("output", {}).get("results", []), start=1):
            index = int(item.get("index", -1))
            if index < 0 or index >= len(request_model.candidates):
                raise RerankerProviderError(f"dashscope reranker returned invalid index: {index}")
            candidate = request_model.candidates[index]
            items.append(
                RerankItem(
                    candidate_index=index,
                    candidate_id=candidate.candidate_id,
                    chunk_id=candidate.chunk_id,
                    rerank_score=float(item.get("relevance_score", 0.0)),
                    rerank_rank=rank,
                )
            )

        return RerankResult(provider=self.provider_name, model=self.model, items=items)

    def _post_rerank_request(self, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(detail) from exc

    def _sanitize_error_message(self, message: str) -> str:
        if self.api_key:
            return message.replace(self.api_key, "[redacted]")
        return message
