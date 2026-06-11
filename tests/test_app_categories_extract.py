"""Tests for extracting APP category keyword dictionaries to country_packs/mx/."""

from __future__ import annotations


def test_import():
    from app.country_packs.mx import app_categories  # noqa: F401

    assert app_categories is not None


def test_all_keyword_lists_non_empty():
    from app.country_packs.mx.app_categories import (
        BANK_KEYWORDS,
        CONSUMPTION_KEYWORDS,
        DELIVERY_TRAVEL_KEYWORDS,
        ECOMMERCE_KEYWORDS,
        EDUCATION_KEYWORDS,
        EWALLET_KEYWORDS,
        GAME_KEYWORDS,
        GOV_KEYWORDS,
        LENDING_KEYWORDS,
        REMITTANCE_KEYWORDS,
        SOCIAL_KEYWORDS,
    )

    for name, value in [
        ("LENDING_KEYWORDS", LENDING_KEYWORDS),
        ("BANK_KEYWORDS", BANK_KEYWORDS),
        ("EWALLET_KEYWORDS", EWALLET_KEYWORDS),
        ("GOV_KEYWORDS", GOV_KEYWORDS),
        ("CONSUMPTION_KEYWORDS", CONSUMPTION_KEYWORDS),
        ("REMITTANCE_KEYWORDS", REMITTANCE_KEYWORDS),
        ("SOCIAL_KEYWORDS", SOCIAL_KEYWORDS),
        ("GAME_KEYWORDS", GAME_KEYWORDS),
        ("EDUCATION_KEYWORDS", EDUCATION_KEYWORDS),
        ("DELIVERY_TRAVEL_KEYWORDS", DELIVERY_TRAVEL_KEYWORDS),
        ("ECOMMERCE_KEYWORDS", ECOMMERCE_KEYWORDS),
    ]:
        assert isinstance(value, tuple), f"{name} must be tuple"
        assert len(value) > 0, f"{name} must be non-empty"
        assert all(isinstance(k, str) for k in value), f"{name} entries must be str"


def test_values_match_payload_builder():
    from app.country_packs.mx import app_categories as mx
    from app.scripts import app_profile_payload_builder as pb

    names = [
        "LENDING_KEYWORDS",
        "BANK_KEYWORDS",
        "EWALLET_KEYWORDS",
        "GOV_KEYWORDS",
        "CONSUMPTION_KEYWORDS",
        "REMITTANCE_KEYWORDS",
        "SOCIAL_KEYWORDS",
        "GAME_KEYWORDS",
        "EDUCATION_KEYWORDS",
        "DELIVERY_TRAVEL_KEYWORDS",
        "ECOMMERCE_KEYWORDS",
    ]
    for name in names:
        mx_value = getattr(mx, name)
        pb_value = getattr(pb, name)
        assert mx_value == pb_value, f"{name} mismatch between mx and payload_builder"
