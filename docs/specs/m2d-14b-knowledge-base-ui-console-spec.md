# M2D-14B Knowledge Base UI Console Spec

## Summary

`M2D-14B` starts from the accepted `M2D-14A` baseline:

- source branch: `codex/m2d-14a-knowledge-base-admin-api`
- baseline head: `71fa018`
- delivery shape: frontend-only Knowledge Base UI Console

This phase adds a minimal management console inside the existing FastAPI-served React dashboard.

## Locked Decisions

- entry is a guarded dashboard tab: `knowledge`
- users without `project:manage` do not see the tab
- unauthorized deep-link `?tab=knowledge` falls back to `comprehensive`
- job status uses light polling only
- `debug/retrieve` stays retrieval-only v1
- frontend reuses existing `httpClient`, auth token, `X-Project-ID`, and `X-Country`

## UI Surface

The console is split into four in-dashboard sections:

- `Knowledge Bases`
- `Documents`
- `Versions & Jobs`
- `Retrieval Debug`

Supported actions:

- list / create KBs
- list / create documents
- upload versions
- trigger `index`
- trigger `rebuild`
- trigger `activate`
- retry failed jobs
- inspect version / job state
- run retrieval-only debug

## Runtime Boundaries

`M2D-14B` does not change the `M2D-14A` backend runtime contract.

Still out of scope:

- standalone admin app
- dual-entry navigation
- worker queue
- SSE / WebSocket
- Data Agent RAG mixing
- answer / evidence debug
- production hardening
- advanced observability

`debug/retrieve` remains limited to:

- `query`
- `kb_id`
- `scope`
- `candidates`
- `diagnostics`

It does not display:

- answer
- evidence
- rerank output
- citations
- gate decision

## Implementation Notes

- frontend bundle model stays `app/ui/build_frontend.py` inline React + Babel
- `riskKnowledgeAdminApi.js` must reuse `httpClient.js`
- upload remains `FormData`-based
- upload metadata is a lightweight JSON textarea
- dangerous actions require confirmation before `rebuild`, `retry`, and `activate`
- job polling runs only when:
  - the active dashboard tab is `knowledge`
  - `document.visibilityState === "visible"`
  - tracked jobs still include `pending` or `running`

## Validation Target

Required validation for `M2D-14B` closure:

- `pytest -q tests/frontend/test_risk_knowledge_ui_console.py tests/frontend/test_risk_knowledge_ui_console_api.py`
- `pytest -q tests/risk_knowledge/admin tests/knowledge_base`
- `python app/ui/build_frontend.py`
- `python -m compileall -q app/risk_knowledge app/knowledge_base tests/risk_knowledge tests/knowledge_base tests/frontend`
- `git diff --check`
