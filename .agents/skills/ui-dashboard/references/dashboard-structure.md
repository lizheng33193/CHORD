# UI Dashboard Structure

## Scope
- Use this reference when changing dashboard presentation or frontend templates.
- Source basis: `app/ui/live_frontend.py`, `app/ui/mock_frontend.py`, `app/schemas/final_response.py`, and project documentation.

## Page Flow
- Home view supports single-uid analysis and file upload analysis.
- Loading view shows staged progress text for four profiling modules.
- Dashboard view displays one selected user result at a time.

## Four-Tab Layout
- `comprehensive`: final fused profile and top-level tags.
- `app`: app profile metrics, preference view, timeline, and prediction card.
- `behavior`: behavior/value cards, risk bars, timeline, and prediction card.
- `credit`: risk structure and credit-history metrics.

## Rendering Conventions
- The frontend reads `summary`, `structured_result`, `charts`, and `report_markdown` from each module output.
- Tabs should be resilient to missing fields by using fallbacks rather than crashing.
- Visual polish can change, but the four-tab information architecture should stay stable unless explicitly redesigned.
