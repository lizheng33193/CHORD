"""Registry for App Profile country packs."""

from __future__ import annotations

from app.core.logger import get_logger
from app.country_packs.mx.app_profile import AppCountryPack, MX_APP_COUNTRY_PACK
from app.country_packs.th.app_profile import TH_APP_COUNTRY_PACK


logger = get_logger(__name__)

_APP_COUNTRY_PACKS: dict[str, AppCountryPack] = {
    MX_APP_COUNTRY_PACK.country_code: MX_APP_COUNTRY_PACK,
    TH_APP_COUNTRY_PACK.country_code: TH_APP_COUNTRY_PACK,
}


def load_app_country_pack(country_code: str) -> AppCountryPack:
    """Return a supported App country pack and fall back to Mexico for now."""
    normalized = str(country_code or "").strip().lower() or MX_APP_COUNTRY_PACK.country_code
    pack = _APP_COUNTRY_PACKS.get(normalized)
    if pack:
        return pack
    logger.warning(
        "Unsupported App country_code=%s; falling back to %s",
        normalized,
        MX_APP_COUNTRY_PACK.country_code,
    )
    return MX_APP_COUNTRY_PACK
