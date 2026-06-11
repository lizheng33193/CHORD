"""Mexico market APP classification keyword dictionaries. Extracted from app_profile_payload_builder.py for Country Pack architecture."""

from __future__ import annotations

from app.country_packs.base_app_categories import BaseAppCategories


class MexicoAppCategories(BaseAppCategories):
    """Mexico-specific APP classification keywords."""

    LENDING_KEYWORDS = (
    "借贷",
    "贷款",
    "loan",
    "cash",
    "credit",
    "kueski",
    "baubap",
    "tala",
    "moneyman",
    "creditea",
    "dineria",
    "okdinero",
    "okredito",
    "plapla",
    "mexdin",
    "didi prestamos",
    "prestamo",
    "prestamos",
    "coppel",
)
    BANK_KEYWORDS = (
        "银行",
        "bank",
        "bbva",
        "banorte",
        "santander",
        "banco",
        "nu",
        "uala",
        "stori",
        "mercado pago",
        "spin",
        "banregio",
    )
    EWALLET_KEYWORDS = ("钱包", "wallet", "mercado pago", "spin", "uala", "digital", "billetera")
    GOV_KEYWORDS = ("sat", "imss", "政府", "税", "公共", "beca")
    CONSUMPTION_KEYWORDS = (
        "电子商务",
        "购物",
        "零售",
        "食品",
        "外卖",
        "出行",
        "旅游",
        "mercado libre",
        "amazon",
        "shein",
        "temu",
        "uber",
        "didi",
        "rappi",
        "airbnb",
        "booking",
    )
    REMITTANCE_KEYWORDS = ("remitly", "wise", "western union", "remesa")
    SOCIAL_KEYWORDS = ("facebook", "whatsapp", "tiktok", "instagram", "messenger", "telegram")
    GAME_KEYWORDS = ("free fire", "mobile legends", "clash royale", "roblox", "candy crush", "game")
    EDUCATION_KEYWORDS = ("coursera", "linkedin", "platzi", "indeed", "computrabajo", "job", "recluta")
    DELIVERY_TRAVEL_KEYWORDS = (
        "uber",
        "uber eats",
        "didi",
        "rappi",
        "indrive",
        "booking",
        "airbnb",
        "food",
        "travel",
        "trip",
        "delivery",
    )
    ECOMMERCE_KEYWORDS = ("mercado libre", "amazon", "shein", "temu", "liverpool", "ecommerce")


# Backward-compatible module-level re-exports (payload_builder.py imports these)
LENDING_KEYWORDS = MexicoAppCategories.LENDING_KEYWORDS
BANK_KEYWORDS = MexicoAppCategories.BANK_KEYWORDS
EWALLET_KEYWORDS = MexicoAppCategories.EWALLET_KEYWORDS
GOV_KEYWORDS = MexicoAppCategories.GOV_KEYWORDS
CONSUMPTION_KEYWORDS = MexicoAppCategories.CONSUMPTION_KEYWORDS
REMITTANCE_KEYWORDS = MexicoAppCategories.REMITTANCE_KEYWORDS
SOCIAL_KEYWORDS = MexicoAppCategories.SOCIAL_KEYWORDS
GAME_KEYWORDS = MexicoAppCategories.GAME_KEYWORDS
EDUCATION_KEYWORDS = MexicoAppCategories.EDUCATION_KEYWORDS
DELIVERY_TRAVEL_KEYWORDS = MexicoAppCategories.DELIVERY_TRAVEL_KEYWORDS
ECOMMERCE_KEYWORDS = MexicoAppCategories.ECOMMERCE_KEYWORDS
