# Credit Profile Runtime Contract

## Scope
- Use this reference when modifying the credit runtime path.
- Source basis: `app/skills/credit_profile_agent.py`, `app/prompts/credit_profile_prompt.md`, `app/schemas/credit_profile.py`.

## Pipeline
- Load credit data.
- Build prompt with `uid` and serialized `credit_data`.
- Validate output against `CreditProfileStructuredResult`.
- Render charts and markdown report.

## Output Shape
- `summary`: short credit-risk summary.
- `structured_result.agent_name`: `credit_profile_agent`.
- `structured_result.evidence`: raw or normalized credit evidence.
- `structured_result.metrics`: currently centered on `credit_score_band`, `repayment_status`, and `risk_level`.
- `structured_result.tags`: compact credit/risk tags.
- `structured_result.status`: `ok`, `data_missing`, or degraded fallback status.

## Safe Change Rules
- Keep prompt placeholders `{{uid}}` and `{{credit_data}}` intact.
- Preserve backward-compatible top-level metrics for UI and final aggregation.
- Additive metrics are safer than changing existing key names.
