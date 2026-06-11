"""Plan 05 v6.1 §4.4 — TH country pack hard-gate.

Exit 0 当两道闸门均通过；任何失败 exit 1 + 打印失败原因。

Gate 1 — 静态扫描：TH country pack 相关代码 / prompt / 知识文件中
        不允许出现 "National Credit Bureau" / "NCB" / "DEV-PLACEHOLDER"
        （TH 业务数据是风控特征聚合表，不是 NCB 信用局报告）。

Gate 2 — 运行时断言：load_credit_country_pack("th") 返回的 pack 必须满足
        v6.1 §2.3 / §2.5 / §2.6 业务契约。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

# 仅扫描 TH-scoped 代码与提示词，避免 mx pack / 历史文档误伤。
TH_SCAN_TARGETS: tuple[Path, ...] = (
    REPO_ROOT / "app" / "country_packs" / "th",
    REPO_ROOT / "app" / "prompts" / "credit_profile_th_prompt.md",
)

FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("National Credit Bureau", re.compile(r"National\s+Credit\s+Bureau", re.IGNORECASE)),
    ("NCB",                   re.compile(r"\bNCB\b")),
    ("DEV-PLACEHOLDER",       re.compile(r"DEV-?PLACEHOLDER", re.IGNORECASE)),
)


def _iter_files(target: Path):
    if target.is_file():
        yield target
        return
    if target.is_dir():
        for p in target.rglob("*"):
            if p.is_file() and p.suffix in {".py", ".md", ".txt", ".json", ".yaml", ".yml"}:
                yield p


def gate1_forbidden_terms() -> list[str]:
    """Return list of failure messages; empty list = pass."""
    failures: list[str] = []
    for target in TH_SCAN_TARGETS:
        if not target.exists():
            failures.append(f"[Gate 1] missing scan target: {target.relative_to(REPO_ROOT)}")
            continue
        for path in _iter_files(target):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for label, pattern in FORBIDDEN_PATTERNS:
                m = pattern.search(text)
                if m:
                    line_no = text[: m.start()].count("\n") + 1
                    failures.append(
                        f"[Gate 1] forbidden term '{label}' found in "
                        f"{path.relative_to(REPO_ROOT)}:{line_no} → {m.group(0)!r}"
                    )
    return failures


def gate2_runtime_pack_contract() -> list[str]:
    """Return list of failure messages; empty list = pass."""
    failures: list[str] = []
    sys.path.insert(0, str(REPO_ROOT))
    from app.country_packs.credit_profile import load_credit_country_pack

    pack = load_credit_country_pack("th")

    if pack.profile_mode != "risk_features":
        failures.append(
            f"[Gate 2] th pack.profile_mode expected 'risk_features', got {pack.profile_mode!r}"
        )
    if pack.score_band_thresholds != ():
        failures.append(
            f"[Gate 2] th pack.score_band_thresholds expected (), got {pack.score_band_thresholds!r}"
        )
    if pack.account_type_labels != {}:
        failures.append(
            f"[Gate 2] th pack.account_type_labels expected {{}}, got {pack.account_type_labels!r}"
        )
    expected_source = "风控特征聚合表（泰国）"
    if pack.source_display_name != expected_source:
        failures.append(
            f"[Gate 2] th pack.source_display_name expected {expected_source!r}, "
            f"got {pack.source_display_name!r}"
        )
    if not getattr(pack, "risk_feature_labels", None):
        failures.append("[Gate 2] th pack.risk_feature_labels must be non-empty")
    if not getattr(pack, "sentinel_values", None):
        failures.append("[Gate 2] th pack.sentinel_values must be non-empty")

    return failures


def main() -> int:
    all_failures: list[str] = []
    all_failures.extend(gate1_forbidden_terms())
    all_failures.extend(gate2_runtime_pack_contract())

    if all_failures:
        print("v6.1 hard-gate: FAIL")
        for msg in all_failures:
            print(f"  - {msg}")
        return 1

    print("v6.1 hard-gate: PASS")
    print("  - Gate 1: no forbidden terms (NCB / National Credit Bureau / DEV-PLACEHOLDER) in TH scope")
    print("  - Gate 2: th credit pack contract OK (profile_mode=risk_features, score_band=(), account_type={}, source='风控特征聚合表（泰国）', risk_feature_labels & sentinel_values non-empty)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
