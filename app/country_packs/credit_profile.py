"""Registry for Credit Profile country packs."""

from __future__ import annotations

from app.core.logger import get_logger
from app.country_packs.mx.credit_profile import CreditCountryPack, MX_CREDIT_COUNTRY_PACK
from app.country_packs.th.credit_profile import TH_CREDIT_COUNTRY_PACK


logger = get_logger(__name__)

_CREDIT_COUNTRY_PACKS: dict[str, CreditCountryPack] = {
    MX_CREDIT_COUNTRY_PACK.country_code: MX_CREDIT_COUNTRY_PACK,
    TH_CREDIT_COUNTRY_PACK.country_code: TH_CREDIT_COUNTRY_PACK,
}


def load_credit_country_pack(country_code: str) -> CreditCountryPack:
    """Return a supported Credit country pack and fall back to Mexico."""
    normalized = str(country_code or "").strip().lower() or MX_CREDIT_COUNTRY_PACK.country_code
    pack = _CREDIT_COUNTRY_PACKS.get(normalized)
    if pack:
        return pack
    logger.warning(
        "Unsupported Credit country_code=%s; falling back to %s",
        normalized,
        MX_CREDIT_COUNTRY_PACK.country_code,
    )
    return MX_CREDIT_COUNTRY_PACK
