"""Plan 07 Phase 4 Task 4.0 —— 守护 redactor 不被旁路 + TOKEN_LIMIT 不被删除。

⚠️ Phase 0 Task 0.1 已实测：
    data_acquisition_agent.schemas.GenerateRequest 含字段
     - natural_language_request: str
     - target_country: TargetCountry  (Enum，传 .value 得字符串如 "mexico")
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from data_acquisition_agent.manifest import load_manifest
from data_acquisition_agent.prompt_assembler import (
    TOKEN_LIMIT,
    assemble_prompt,
)
from data_acquisition_agent.schemas import GenerateRequest, TargetCountry


@pytest.fixture
def mexico_manifest():
    return load_manifest("mexico")


def _build_request(query: str = "查找最近 7 天活跃用户的 top 10") -> GenerateRequest:
    return GenerateRequest(
        natural_language_request=query,
        target_country=TargetCountry.MEXICO,
    )


def test_redactor_called_per_md_file(mexico_manifest):
    """assemble_prompt 必须对每个被选中的 md 调用 redact()，不能整体或 0 次"""
    with patch(
        "data_acquisition_agent.prompt_assembler.redact",
        wraps=lambda raw: (raw, 0),
    ) as mock_redact:
        prompt, tokens, files, hits = assemble_prompt(_build_request(), mexico_manifest)
    assert mock_redact.call_count >= 3, (
        f"redact() must be called for each selected md file (got {mock_redact.call_count})"
    )


def test_token_limit_still_raises_when_exceeded(mexico_manifest):
    """伪造 estimate_tokens 让 prompt 超 TOKEN_LIMIT，必须触发 ValueError"""
    with patch(
        "data_acquisition_agent.prompt_assembler.estimate_tokens",
        return_value=TOKEN_LIMIT + 1,
    ):
        with pytest.raises(ValueError, match=r"prompt_too_large:\s*\d+\s*>\s*\d+"):
            assemble_prompt(_build_request(), mexico_manifest)


def test_returns_4tuple(mexico_manifest):
    """signature 不能从 4-tuple 退化"""
    result = assemble_prompt(_build_request(), mexico_manifest)
    assert isinstance(result, tuple) and len(result) == 4
    prompt, tokens, files, hits = result
    assert isinstance(prompt, str) and len(prompt) > 0
    assert isinstance(tokens, int) and tokens > 0
    assert isinstance(files, list) and len(files) >= 1
    assert isinstance(hits, int) and hits >= 0
