"""
Pakistan behavior profile constants.

Pay cycle data sources:
- SBP (State Bank of Pakistan) employment reports: monthly pay common
- Industry variation: varies by employer; formal sector often pays 1st of month
- Confidence: low-medium (significant informal sector not captured)

Primary channel rationale:
- WhatsApp 在巴基斯坦是主导 messaging 平台

TODO(country-pack): validate against actual user transaction data once available.
"""

PK_PAY_WINDOW = frozenset({1, 2, 3, 28, 29, 30, 31})
PK_PAY_CYCLE_NAME = "Tankhwah"
PK_PRIMARY_CHANNEL = "WhatsApp"
PK_PAY_CYCLE_DESCRIPTION = "每月月底至次月初发薪"
