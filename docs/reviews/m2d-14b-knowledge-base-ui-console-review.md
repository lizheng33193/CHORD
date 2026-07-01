# M2D-14B Knowledge Base UI Console Review

## Summary

`M2D-14B` adds a minimal frontend Knowledge Base UI Console on top of the accepted `M2D-14A` Admin API baseline.

Delivered frontend surfaces:

- guarded dashboard `knowledge` tab
- risk knowledge admin API client
- KB list / create UI
- document list / create UI
- version upload / index / rebuild / activate / retry UI
- job status display with light polling
- retrieval-only debug panel

## Engineering Notes

- the console is implemented inside the existing React dashboard shell rather than a standalone admin app
- the frontend client reuses `httpClient`, auth token, `X-Project-ID`, and `X-Country`
- users without `project:manage` do not see the `knowledge` tab
- `?tab=knowledge` falls back to `comprehensive` for unauthorized users
- job polling only runs while the `knowledge` tab is active, the page is visible, and tracked jobs are still `pending` or `running`
- dangerous actions require confirmation before `rebuild`, `retry`, and `activate`
- `debug/retrieve` remains retrieval-only v1 and does not surface answer/evidence/rerank fields

## Runtime Boundaries

Still not started in `M2D-14B`:

- backend runtime expansion
- production worker queue
- SSE / WebSocket
- Data Agent RAG mixing
- evidence / answer debug
- production hardening
- advanced observability

`index` / `rebuild` continue to reuse the current in-process runtime from `M2D-14A`.

## Validation

- `pytest -q tests/frontend/test_risk_knowledge_ui_console.py tests/frontend/test_risk_knowledge_ui_console_api.py`
- `pytest -q tests/frontend`
- `pytest -q tests/risk_knowledge/admin tests/knowledge_base`
- `python app/ui/build_frontend.py`
- `python -m compileall -q app/risk_knowledge app/knowledge_base tests/risk_knowledge tests/knowledge_base tests/frontend`
- `git diff --check`
- full repository regression was not run for `M2D-14B`

## Acceptance Posture

`M2D-14B` is accepted at stage level after targeted Knowledge Base UI Console validation; full production hardening, worker queue, advanced governance, and observability remain future stages.
