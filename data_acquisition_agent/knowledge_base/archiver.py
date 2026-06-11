"""Auto-archive successful SQL examples to learned/{country}/v1/ (Plan 07 Phase 3).

Zero Tolerance:
- 三个 gate 默认 False (fail-safe): sql_judge_l1_pass / sql_judge_l2_pass / user_acked
- build_table_script 类 SQL 必须落在 manifest.analyst_private_prefix 下，否则拒绝归档
- learned/ 路径在 data_acquisition_agent/learned/{country}/v1/，不放 configs/ 下（避免污染原 yaml manifest）
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional
from uuid import uuid4

from data_acquisition_agent.manifest import REPO_ROOT, load_manifest


MAX_TOKENS_PER_EXAMPLE = 1000
LEARNED_ROOT = REPO_ROOT / "data_acquisition_agent" / "learned"

_DDL_RE = re.compile(
    r"^\s*CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([^\s\(]+)",
    re.IGNORECASE | re.MULTILINE,
)


def _ddl_target_starts_with(sql: str, prefix: str) -> bool:
    """检查 DDL 目标 schema/table 是否以 analyst_private_prefix 开头。
    若 SQL 不是 DDL，返回 True（非 build_table_script 路径，跳过本检查）。
    """
    m = _DDL_RE.search(sql)
    if not m:
        return True
    target = m.group(1).strip("`\"'")
    return target.startswith(prefix.rstrip("."))


def _indent(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line for line in text.splitlines())


def archive_example(
    nl_query: str,
    generated_sql: str,
    country: str,
    sql_judge_l1_pass: bool = False,
    sql_judge_l2_pass: bool = False,
    user_acked: bool = False,
    execution_success: Optional[bool] = None,
    keywords: Optional[list[str]] = None,
) -> Optional[str]:
    """归档一条 NL→SQL 成功 case 到 learned/{country}/v1/

    Returns: 归档文件绝对路径 / None（任何 gate 不过时）
    """
    if not (sql_judge_l1_pass and sql_judge_l2_pass and user_acked):
        return None

    estimated_tokens = (len(nl_query) + len(generated_sql)) // 3
    if estimated_tokens > MAX_TOKENS_PER_EXAMPLE:
        return None

    try:
        manifest = load_manifest(country)
        prefix = manifest.analyst_private_prefix
    except Exception:
        return None
    if not _ddl_target_starts_with(generated_sql, prefix):
        return None

    ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    suffix = uuid4().hex[:8]
    out_dir = LEARNED_ROOT / country / "v1"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"example_{ts}_{suffix}.md"

    nl_query_json = json.dumps(nl_query, ensure_ascii=False)
    title = nl_query.replace("\n", " ")[:50]

    md = f"""---
nl_query: {nl_query_json}
generated_sql: |
{_indent(generated_sql, 2)}
keywords: {json.dumps(keywords or [], ensure_ascii=False)}
sql_judge_l1_pass: {str(sql_judge_l1_pass).lower()}
sql_judge_l2_pass: {str(sql_judge_l2_pass).lower()}
user_acked: {str(user_acked).lower()}
user_acked_at: "{datetime.now().isoformat()}"
execution_success: {str(execution_success).lower() if execution_success is not None else 'null'}
---

# Example: {title}

## NL Query
{nl_query}

## Generated SQL
```sql
{generated_sql}
```
"""
    out_path.write_text(md, encoding="utf-8")
    return str(out_path)
