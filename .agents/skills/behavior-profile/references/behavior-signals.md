# Behavior Profile Signals

## Scope
- Use this reference when changing Behavior Profile logic or prompt interpretation.
- Source basis: `PROJECT_DOCUMENTATION.md`, `app/prompts/behavior_profile_prompt.md`, `app/schemas/behavior_profile.py`, `app/scripts/behavior_preprocessor.py`, and the Mexico-market solution note.

## Current Runtime Contract
- Behavior data is preprocessed before prompting.
- Required structured fields are `engagement_level`, `evidence`, `metrics`, `tags`, and `status`.
- Current fallback metrics emphasize `avg_session_minutes`, `login_days_30d`, and `engagement_score`.

## Mexico Cash-Loan Behavior Focus
### Event analysis for cash-loan scenarios
- Prioritize repayment-page visits, product-detail browsing, rate-calculator usage, loan re-entry, and incomplete application flows.
- Keep analysis tied to a recent behavior window rather than lifetime totals.

### Repayment willingness
- Repayment-related page revisits, timely repayment actions, and pre-due-date activity are positive willingness signals.
- Repeated avoidance, high friction before repayment, or last-minute only behavior can weaken the signal.

### Activity level
- Use recency, session depth, and login-day consistency together.
- Avoid equating raw volume with healthy engagement if it is driven by distress behavior.

### Product sensitivity
- Frequent pricing, rate, or comparison interactions suggest strong product sensitivity.
- Sensitivity can reflect either healthy shopping behavior or stress-driven searching; interpret with surrounding context.

### Behavioral risk signals
- Repeated borrowing-related exploration, support escalation, abnormal nighttime activity, and churn-like drop-offs are useful risk signals.
- Keep risk signals separate from value signals so the final profile can explain both.

## Editing Guidance
- Preserve preprocessing as a first-class step.
- Add new behavior rules in prompts or references first, then wire them into fallback metrics if needed.
- Do not collapse repayment willingness, activity, and product sensitivity into a single opaque score.
