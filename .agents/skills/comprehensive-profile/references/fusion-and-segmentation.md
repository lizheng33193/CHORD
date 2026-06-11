# Comprehensive Fusion And Segmentation

## Scope
- Use this reference when editing the final synthesis layer.
- Source basis: `PROJECT_DOCUMENTATION.md`, `app/prompts/comprehensive_prompt.md`, `app/schemas/comprehensive_profile.py`, `app/skills/comprehensive_agent.py`, and the Mexico-market segmentation note.

## Three-Dimension Fusion Logic
- Comprehensive Profile should consume upstream results only, not raw app, behavior, or credit source data directly.
- The three core dimensions are app signals, behavior signals, and credit signals.
- Prefer explicit merge logic over hidden narrative-only synthesis.

## Signal Conflict Interpretation
- If credit looks healthy but app signals show recent multi-loan installs, treat app-side pressure as an early warning, not automatic hard-risk proof.
- If credit is missing, rely more on app and behavior but lower confidence.
- If behavior is active and price-sensitive while app data shows competitor installs, explain it as possible comparison shopping rather than defaulting to severe risk.
- Record meaningful conflicts in a dedicated explanation path whenever possible.

## S1-S6 Segment Guidance
- `S1`: high value, low risk, strong growth potential.
- `S2`: stable, manageable risk, good operating value.
- `S3`: price-sensitive, competitive, likely to compare offers.
- `S4`: potential churn, declining engagement, needs retention focus.
- `S5`: multi-loan high-risk, pressure and urgency signals are both elevated.
- `S6`: quiet or wait-and-see users, low activity but not necessarily bad credit.

## Editing Guidance
- Keep segment assignment explainable.
- Do not let a single weak signal override all other dimensions without explanation.
- Preserve a place for both `overall risk/value` and `conflict explanation`.
