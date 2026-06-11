"""Mexico segment enumeration shared by Product Advice and Ops Advice rules."""

from __future__ import annotations

from typing import Final

# S1-S6 customer segments per the Mexico solution doc §八.
MX_SEGMENTS: Final[tuple[str, ...]] = ("S1", "S2", "S3", "S4", "S5", "S6")

MX_SEGMENT_NAMES: Final[dict[str, str]] = {
    "S1": "优质成长客",
    "S2": "稳健经营客",
    "S3": "价格敏感客",
    "S4": "潜在流失客",
    "S5": "多头高风客",
    "S6": "沉默观望客",
}
