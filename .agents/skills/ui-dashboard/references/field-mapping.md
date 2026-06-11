# UI Field Mapping

## Scope
- Use this reference when mapping backend fields into dashboard widgets.
- Source basis: `app/schemas/final_response.py`, module schemas, and `app/ui/live_frontend.py`.

## Shared API Shape
- `results[]` contains one object per user.
- Each user object contains `uid`, `app_profile`, `behavior_profile`, `credit_profile`, and `comprehensive_profile`.
- Each module output contains `summary`, `structured_result`, `charts`, and `report_markdown`.

## Tab-Level Mapping
### Comprehensive tab
- Main inputs: `structured_result.persona`, `structured_result.tags`, `structured_result.metrics.risk_level`, `summary`.

### App tab
- Main inputs: `structured_result.activity_level`, `structured_result.evidence`, `structured_result.metrics`, `structured_result.tags`, `summary`.

### Behavior tab
- Main inputs: `structured_result.engagement_level`, `structured_result.evidence`, `structured_result.metrics`, `summary`.

### Credit tab
- Main inputs: `structured_result.metrics.credit_score_band`, `structured_result.metrics.repayment_status`, `structured_result.metrics.risk_level`, `summary`.

## Chart Payload Convention
- Charts use the unified `ChartData` shape from `app/schemas/final_response.py`.
- Expect `chart_type`, `title`, optional axes or indicators, `series`, and optional `meta`.
- Prefer additive chart metadata over one-off frontend-only parsing rules.

## Safe Change Rules
- Do not rename API fields only for presentation convenience.
- If UI needs new values, extend backend schema and keep old fields compatible.
- Keep display fallback strings for missing module outputs.
