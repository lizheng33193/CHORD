# Comprehensive Runtime Contract

## Scope
- Use this reference when changing the final aggregation prompt, schema, or output assumptions.
- Source basis: `app/skills/comprehensive_agent.py`, `app/prompts/comprehensive_prompt.md`, `app/schemas/comprehensive_profile.py`.

## Pipeline
- Receive `app_result`, `behavior_result`, and `credit_result`.
- Build deterministic fallback structure first.
- Prompt the model only with upstream outputs.
- Validate against `ComprehensiveProfileStructuredResult`.

## Output Shape
- `summary`: final human-readable profile summary.
- `structured_result.agent_name`: `comprehensive_profile_agent`.
- `structured_result.persona`: top-level final persona string.
- `structured_result.upstream_summaries`: summary-only view of upstream modules.
- `structured_result.metrics`: includes final risk level and dimension scores.
- `structured_result.tags`: merged tags from upstream modules.
- `structured_result.status`: `ok` or `data_missing` style status.

## Safe Change Rules
- Keep this layer upstream-only; do not re-read raw data here.
- Preserve merged tags and upstream summaries for explainability.
- New final metrics should remain backward-compatible with existing UI expectations.
