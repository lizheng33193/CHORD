"""Plan 07 Phase 4 — token 实测落 jsonl，用于事后压缩比分析。

⚠️ Zero Tolerance：写入日志的 query_preview 必须先经 redact()，
   防止 NL query 中可能携带的凭据 / token / phone 等回流到磁盘。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from data_acquisition_agent.redactor import redact


def log_token_usage(
    query: str,
    country: str,
    prompt_tokens: int,
    response_tokens: int = 0,
    files: list[str] | None = None,
) -> None:
    """每次 SQL 生成后写一行 jsonl，便于事后复盘压缩比。

    ⚠️ budget_target = 30_000 是 Spec §5.3 定义的"整体感知预算"
       （含 SYSTEM_PROMPT_ENGINE ~3K + 4 段 md（按 always_inject 后裁剪 ~5-8K）+
       user_block ~2K + 余量），与 router 的 md-only token_budget = TOKEN_LIMIT * 0.03 ≈ 24K
       是不同口径。prompt_tokens 是拼接后全部输入 token，与 budget_target 同口径，
       超过 30K 即记录 exceeded 供事后复盘。
    """
    query_red, _hits = redact(query[:80])
    log_entry = {
        "ts": datetime.now().isoformat(),
        "country": country,
        "query_preview": query_red,
        "prompt_tokens": prompt_tokens,
        "response_tokens": response_tokens,
        "budget_target": 30_000,
        "exceeded": prompt_tokens > 30_000,
        "files": files or [],
    }
    out = Path("outputs/da_token_log.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
