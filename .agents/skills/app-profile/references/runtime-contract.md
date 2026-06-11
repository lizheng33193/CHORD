# App Profile Runtime Contract

## Scope
- Use this reference when touching the App Profile prompt, schema, charts, or report flow.
- Source basis: `app/skills/app_profile_agent.py`, `app/prompts/app_profile_prompt.md`, `app/schemas/app_profile.py`.

## Pipeline
- Load app data.
- Build prompt with `uid` and serialized `app_data`.
- Validate model output against `AppProfileStructuredResult`.
- Render charts and markdown report.

## Output Shape
- `summary`: short human-readable result.
- `structured_result.agent_name`: `app_profile_agent`.
- `structured_result.status`: `ok`, `data_missing`, or degraded fallback status.
- `structured_result.activity_level`: current top-level app activity label.
- `structured_result.evidence`: raw or normalized app evidence.
- `structured_result.metrics`: current emphasis on active days and installed app count.
- `structured_result.tags`: compact profile tags.

## Safe Change Rules
- Do not remove `activity_level`, `metrics`, `tags`, or `status` from the output contract.
- Keep prompt placeholders `{{uid}}` and `{{app_data}}` usable.
- If adding metrics, make them additive and backward-compatible.
