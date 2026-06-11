"""Mexico Credit Profile country pack."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class CreditCountryPack:
    """Static country configuration used by the Credit profile pipeline."""

    country_code: str
    display_name: str
    default_language: str
    report_language: str
    prompt_language: str
    currency_code: str
    source_display_name: str
    score_band_thresholds: tuple[tuple[str, int], ...]
    account_type_labels: dict[str, str] = field(default_factory=dict)
    profile_mode: Literal["buro", "risk_features"] = "buro"
    risk_feature_labels: dict[str, str] = field(default_factory=dict)
    sentinel_values: dict[str, tuple[str, ...]] = field(default_factory=dict)


MX_CREDIT_COUNTRY_PACK = CreditCountryPack(
    country_code="mx",
    display_name="墨西哥",
    default_language="zh-CN",
    report_language="zh-CN",
    prompt_language="zh-CN",
    currency_code="MXN",
    source_display_name="Buró de Crédito（墨西哥）",
    score_band_thresholds=(
        ("A", 700),
        ("B", 580),
        ("C", 460),
        ("D", 0),
    ),
    account_type_labels={
        "CC": "信用卡",
        "TC": "信用卡",
        "TDC": "信用卡",
        "F": "零售信贷",
        "M": "个人贷款",
        "PL": "个人贷款",
        "AUTO": "车贷",
        "HOME": "房贷",
    },
)
