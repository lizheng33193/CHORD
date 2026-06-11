"""Thailand App Profile country pack."""

from __future__ import annotations

from app.country_packs.mx.app_profile import AppCountryPack

TH_APP_COUNTRY_PACK = AppCountryPack(
    country_code="th",
    display_name="Thailand",
    default_language="zh-CN",
    report_language="zh-CN",
    prompt_language="zh-CN",
)
