"""
Indonesia behavior profile constants.

Pay cycle data sources:
- Bank Indonesia 2023 wage survey: monthly pay dominant in formal sector
- Industry convention: payroll typically processed 25th-end of month
- Confidence: medium (formal sector); informal sector varies significantly

Primary channel rationale:
- WhatsApp 在印尼渗透率 >80%，是主流 messaging 入口

TODO(country-pack): validate against actual user transaction data once available.
"""

ID_PAY_WINDOW = frozenset({25, 26, 27, 28, 29, 30, 31, 1, 2, 3})
ID_PAY_CYCLE_NAME = "Gajian"
ID_PRIMARY_CHANNEL = "WhatsApp"
ID_PAY_CYCLE_DESCRIPTION = "每月25-31号发薪"
