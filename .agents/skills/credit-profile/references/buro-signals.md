# Credit Profile Signals

## Scope
- Use this reference when changing Credit Profile logic, prompt rules, or field interpretation.
- Source basis: `PROJECT_DOCUMENTATION.md`, `app/prompts/credit_profile_prompt.md`, `app/schemas/credit_profile.py`, and the Mexico-market Bur車-oriented solution note.

## Bur車 Data Cleaning
- Clean long Bur車-style JSON before higher-level reasoning.
- Keep only account, delinquency, inquiry, utilization, and summary fields needed for profiling.
- Prefer normalized aggregates over passing raw noisy payloads through the full prompt.

## Core Credit Dimensions
### Debt pressure
- Focus on outstanding balance, estimated monthly payment, credit-card utilization, and concurrent active loan load.
- High utilization and multiple live obligations should raise debt-pressure concern even without severe delinquency.

### Credit stability
- Use delinquency count, max days past due, time since last delinquency, and account age together.
- One historical resolved delinquency is different from recent repeated instability.

### Borrowing hunger
- Recent inquiry volume, especially from multiple consumer-loan sources, is the main hunger signal.
- Treat concentrated recent inquiries as stronger than old scattered inquiries.

## Thin-file Handling
- Mexico-market coverage can be partial.
- If Bur車 data is missing or thin, fall back to conservative labels and lower confidence rather than inventing history.

## Editing Guidance
- Keep credit interpretation explainable with concrete evidence fields.
- Separate `risk level`, `debt pressure`, `stability`, and `borrowing hunger` when possible.
- Put richer Bur車 heuristics in references or prompts, not in `SKILL.md`.
