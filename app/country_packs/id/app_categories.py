"""
Indonesia market APP classification keyword dictionaries.

Data sources:
- Google Play Store Indonesia top apps (2025)
- OJK (Otoritas Jasa Keuangan) registered fintech list
- Common Indonesian e-commerce and mobility apps

Confidence: medium (formal app ecosystem well-documented; informal apps may be missing)
"""

from app.country_packs.base_app_categories import BaseAppCategories


class IndonesiaAppCategories(BaseAppCategories):
    LENDING_KEYWORDS = ("pinjaman", "kredit", "akulaku", "kredivo", "tunaiku", "julo", "cashcepat", "loan", "cash")
    BANK_KEYWORDS = ("bca", "mandiri", "bri", "bni", "bank", "jago", "blu", "seabank", "bank neo")
    EWALLET_KEYWORDS = ("gopay", "ovo", "dana", "shopeepay", "linkaja", "dompet", "wallet")
    GOV_KEYWORDS = ("pemerintah", "pajak", "bpjs", "dukcapil", "gov")
    CONSUMPTION_KEYWORDS = ("tokopedia", "shopee", "lazada", "bukalapak", "blibli", "grab", "gojek", "belanja")
    REMITTANCE_KEYWORDS = ("wise", "remitly", "western union", "ria", "remesa")
    SOCIAL_KEYWORDS = ("whatsapp", "instagram", "tiktok", "facebook", "telegram", "twitter")
    GAME_KEYWORDS = ("mobile legends", "free fire", "pubg", "roblox", "candy crush", "game")
    EDUCATION_KEYWORDS = ("ruangguru", "zenius", "coursera", "linkedin", "indeed", "job", "kerja")
    DELIVERY_TRAVEL_KEYWORDS = ("grab", "gojek", "traveloka", "tiket", "maxim", "food", "delivery", "travel")
    ECOMMERCE_KEYWORDS = ("tokopedia", "shopee", "lazada", "bukalapak", "blibli", "ecommerce")


# Backward-compatible module-level re-exports
LENDING_KEYWORDS = IndonesiaAppCategories.LENDING_KEYWORDS
BANK_KEYWORDS = IndonesiaAppCategories.BANK_KEYWORDS
EWALLET_KEYWORDS = IndonesiaAppCategories.EWALLET_KEYWORDS
GOV_KEYWORDS = IndonesiaAppCategories.GOV_KEYWORDS
CONSUMPTION_KEYWORDS = IndonesiaAppCategories.CONSUMPTION_KEYWORDS
REMITTANCE_KEYWORDS = IndonesiaAppCategories.REMITTANCE_KEYWORDS
SOCIAL_KEYWORDS = IndonesiaAppCategories.SOCIAL_KEYWORDS
GAME_KEYWORDS = IndonesiaAppCategories.GAME_KEYWORDS
EDUCATION_KEYWORDS = IndonesiaAppCategories.EDUCATION_KEYWORDS
DELIVERY_TRAVEL_KEYWORDS = IndonesiaAppCategories.DELIVERY_TRAVEL_KEYWORDS
ECOMMERCE_KEYWORDS = IndonesiaAppCategories.ECOMMERCE_KEYWORDS
