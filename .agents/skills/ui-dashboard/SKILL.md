---
name: ui-dashboard
description: Use when working on the repository's dashboard or page presentation layer, including layout, view composition, display widgets, and frontend templates that visualize profiling results. Do not use for backend profiling logic, runtime data parsing, prompt-template authoring, or API behavior changes unless the task is explicitly about the UI consuming those results.
---

# UI Dashboard

Use this skill for dashboard and page-layer changes that present profiling outputs.

Change backend capabilities before UI when both are needed.
Keep UI work separate from runtime profiling and prompt logic.

## Scripts

Use `scripts/validate_result_payload.py` before wiring backend results into the page.
Use `scripts/check_chart_payload.py` and `scripts/map_dashboard_fields.py` to verify chart contracts and field mapping for the four tabs.
These scripts are skill-side helpers only; detailed rules stay in `references/`.
