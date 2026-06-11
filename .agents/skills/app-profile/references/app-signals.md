# App Profile Signals

## Scope
- Use this reference when changing App Profile runtime logic, prompt wording, or rule interpretation.
- Source basis: `PROJECT_DOCUMENTATION.md`, `app/prompts/app_profile_prompt.md`, `app/schemas/app_profile.py`, and the Mexico-market solution note.

## Current Runtime Contract
- Input comes from app-side sample data loaded by `app/skills/app_profile_agent.py`.
- Required structured fields are `activity_level`, `evidence`, `metrics`, `tags`, and `status`.
- The current fallback metrics emphasize `active_days_30d` and `installed_app_count`.

## Mexico-Market Signal Priorities
### Installation time decay
- Treat recently installed apps as stronger intent signals than old installs.
- Recommended priority window: `<=7d` strongest, `8-30d` high, `31-90d` medium, `91-365d` low, `>365d` background only.
- If runtime data lacks install timestamps, keep the rule as design intent and do not fabricate recency values.

### Multi-loan risk
- Focus on lending-tool apps and especially newly installed competitor lending apps.
- Multiple recent lending-app installs should increase concern for multi-head borrowing risk.
- Long-installed finance apps alone should not be treated as acute multi-head risk.

### Consumption ability
- E-commerce, food delivery, ride-hailing, and wallet usage can support lightweight consumption-level inference.
- Prefer stable app-category combinations over single-app guesses.
- Keep conclusions conservative when category coverage is sparse.

### Financial maturity
- Banking apps, wallets, and government-service apps can indicate financial maturity and formalization.
- Separate `financial maturity` from `consumption ability`; they are related but not identical.
- If evidence is thin, prefer `unknown` or weak tags over overconfident labeling.

## Editing Guidance
- Preserve the existing API-facing output shape.
- Put detailed heuristics in runtime prompts or references, not directly in `SKILL.md`.
- Keep fallback behavior deterministic when model output is unavailable.
