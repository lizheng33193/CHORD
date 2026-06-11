"""Validate App profile structured output and markdown report contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REQUIRED_TOP_LEVEL_FIELDS = {
    "agent_name",
    "uid",
    "status",
    "activity_level",
    "summary",
    "report_markdown",
    "evidence",
    "metrics",
    "tags",
    "risk_assessment",
    "financial_maturity",
    "consumption_profile",
    "timeline",
    "visuals",
}

REQUIRED_REPORT_SECTIONS = [
    "### 👤 墨西哥用户画像与风控评估报告",
    "#### 1. 风险控制：多头借贷评估",
    "#### 2. 金融成熟度与资质分析",
    "#### 3. 消费能力与偏好评估",
    "#### 4. 综合生活方式标签",
    "#### 5. 最终风控建议",
]


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python app/scripts/validate_app_profile_output.py <json_file>")

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    missing_fields = sorted(REQUIRED_TOP_LEVEL_FIELDS - set(payload.keys()))
    if missing_fields:
        raise SystemExit(f"Missing top-level fields: {missing_fields}")

    report_markdown = str(payload.get("report_markdown", "") or "")
    if f"UID: {payload.get('uid', '')}" not in report_markdown:
        raise SystemExit("report_markdown does not contain the uid in the title")

    missing_sections = [section for section in REQUIRED_REPORT_SECTIONS if section not in report_markdown]
    if missing_sections:
        raise SystemExit(f"Missing required report sections: {missing_sections}")

    print("App profile output validation passed.")


if __name__ == "__main__":
    main()
