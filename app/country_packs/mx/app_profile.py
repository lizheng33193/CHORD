"""Mexico App Profile country pack."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppCountryPack:
    """Static country configuration used by the App profile pipeline."""

    country_code: str
    display_name: str
    default_language: str
    report_language: str
    prompt_language: str


MX_APP_COUNTRY_PACK = AppCountryPack(
    country_code="mx",
    display_name="Mexico",
    default_language="zh-CN",
    report_language="zh-CN",
    prompt_language="zh-CN",
)

