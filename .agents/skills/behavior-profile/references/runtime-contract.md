# Behavior Profile Runtime Contract

## Scope
- Use this reference when updating the behavior prompt, schema, or preprocessing assumptions.
- Source basis: `app/skills/behavior_profile_agent.py`, `app/prompts/behavior_profile_prompt.md`, `app/schemas/behavior_profile.py`.

## Pipeline
- Load raw behavior data.
- Run preprocessing.
- Build prompt with `uid` and preprocessed behavior data.
- Validate output against `BehaviorProfileStructuredResult`.
- Render charts and markdown report.

## Output Shape
- `summary`: short behavior conclusion.
- `structured_result.agent_name`: `behavior_profile_agent`.
- `structured_result.engagement_level`: top-level behavior label.
- `structured_result.evidence`: processed behavior evidence.
- `structured_result.metrics`: includes engagement-related metrics.
- `structured_result.tags`: compact tags such as preference and engagement.
- `structured_result.status`: `ok`, `data_missing`, or degraded fallback status.

## Safe Change Rules
- Keep prompt placeholders `{{uid}}` and `{{behavior_data}}` intact.
- Preserve `engagement_level` as a stable top-level field.
- New metrics should extend, not replace, the current contract.
