"""Plan 07 Phase 1 收尾 — 批量按 estimate_tokens 实测值回写所有 INDEX.md 的 token_estimate 字段。

用法：python scripts/plan_07_fill_index_token_estimate.py
副作用：原地改写 V1 双国 INDEX.md（数据采集子项目内部）。
V1 范围：mexico + thailand。未来扩展 indonesia / pakistan / philippines 时把 country code
加入 COUNTRIES，COUNTRY_CN_MAP 已预留 5 国映射。
"""

from __future__ import annotations

import re

from data_acquisition_agent.knowledge_base.index_parser import parse_index_md
from data_acquisition_agent.manifest import REPO_ROOT
from data_acquisition_agent.prompt_assembler import estimate_tokens


COUNTRIES = ["mexico", "thailand"]
COUNTRY_CN_MAP = {
    "mexico": "墨西哥",
    "thailand": "泰国",
    "indonesia": "印尼",
    "pakistan": "巴铁",
    "philippines": "菲律宾",
}


def fix_one(country: str) -> None:
    entries = parse_index_md(country)
    index_md_path = REPO_ROOT / f"data_acquisition_agent/demo0/各国数据知识库汇总/{COUNTRY_CN_MAP[country]}/INDEX.md"
    content = index_md_path.read_text(encoding="utf-8")

    for e in entries:
        file_path = REPO_ROOT / e["file"]
        if not file_path.exists():
            print(f"[{country}] SKIP missing file: {e['file']}")
            continue

        actual = estimate_tokens(file_path.read_text(encoding="utf-8"))
        pattern = re.compile(
            rf"(- \*\*path\*\*: {re.escape(e['file'])}.*?- \*\*token_estimate\*\*: )\d+",
            re.DOTALL,
        )
        new_content, n = pattern.subn(rf"\g<1>{actual}", content, count=1)
        if n == 1:
            content = new_content
            print(f"[{country}] {e['file']} -> {actual}")
        else:
            print(f"[{country}] WARN no token_estimate match for {e['file']}")

    index_md_path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    for c in COUNTRIES:
        fix_one(c)
