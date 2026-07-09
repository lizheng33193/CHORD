# M6A Memory Vector Shadow Index Review

## Scope Review

M6A landed as a shadow-only layer:

- SQLite remains source of truth
- FTS5 remains production retrieval
- FAISS is used only for CLI/debug semantic shadow search
- no prompt injection was added

## Implemented Areas

- `app/services/orchestrator_agent/memory_vector/`
- `app/services/orchestrator_agent/memory_store.py`
- `app/core/config.py`
- new orchestrator-agent memory vector tests
- README / PLANNING / TASK updates

## Verification Expectations

Required evidence for acceptance:

- targeted M6A tests pass
- affected existing memory/orchestrator tests pass
- `python -m app.eval.runner --suite memory_governance` passes
- `python -m app.eval.runner --profile pr_acceptance` passes
- no diff/check formatting errors

## Non-Goals Confirmed

- no HTTP debug API
- no vector prompt injection
- no vector + FTS fusion
- no M4 requested-use semantic policy integration
- no M6B context injection work

## Readiness Decision

M6A is the foundation only.
M6B should start only after shadow search and sync behavior are accepted with regression evidence.
