"""Base interface for country-specific APP classification keyword lists.

Each country pack should define a subclass with country-specific keywords.
See app/country_packs/mx/app_categories.py for the Mexico implementation.
"""

from __future__ import annotations


class BaseAppCategories:
    """Protocol for APP category keyword tuples.

    All attributes are tuple[str, ...] defaulting to empty tuple.
    Country-specific subclasses override with actual keyword lists.
    """

    LENDING_KEYWORDS: tuple[str, ...] = ()
    BANK_KEYWORDS: tuple[str, ...] = ()
    EWALLET_KEYWORDS: tuple[str, ...] = ()
    GOV_KEYWORDS: tuple[str, ...] = ()
    CONSUMPTION_KEYWORDS: tuple[str, ...] = ()
    REMITTANCE_KEYWORDS: tuple[str, ...] = ()
    SOCIAL_KEYWORDS: tuple[str, ...] = ()
    GAME_KEYWORDS: tuple[str, ...] = ()
    EDUCATION_KEYWORDS: tuple[str, ...] = ()
    DELIVERY_TRAVEL_KEYWORDS: tuple[str, ...] = ()
    ECOMMERCE_KEYWORDS: tuple[str, ...] = ()
