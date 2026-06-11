"""Registry for Behavior Profile country packs."""

from __future__ import annotations

from app.core.logger import get_logger
from app.country_packs.mx.behavior_profile import (
    BehaviorCountryPack,
    MX_BEHAVIOR_COUNTRY_PACK,
)
from app.country_packs.th.behavior_profile import TH_BEHAVIOR_COUNTRY_PACK


logger = get_logger(__name__)

_BEHAVIOR_COUNTRY_PACKS: dict[str, BehaviorCountryPack] = {
    MX_BEHAVIOR_COUNTRY_PACK.country_code: MX_BEHAVIOR_COUNTRY_PACK,
    TH_BEHAVIOR_COUNTRY_PACK.country_code: TH_BEHAVIOR_COUNTRY_PACK,
}


def load_behavior_country_pack(country_code: str) -> BehaviorCountryPack:
    """Return a supported Behavior country pack and fall back to Mexico."""
    normalized = (
        str(country_code or "").strip().lower()
        or MX_BEHAVIOR_COUNTRY_PACK.country_code
    )
    pack = _BEHAVIOR_COUNTRY_PACKS.get(normalized)
    if pack:
        return pack
    logger.warning(
        "Unsupported Behavior country_code=%s; falling back to %s",
        normalized,
        MX_BEHAVIOR_COUNTRY_PACK.country_code,
    )
    return MX_BEHAVIOR_COUNTRY_PACK
