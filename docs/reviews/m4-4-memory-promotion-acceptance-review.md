# M4-4 Memory Promotion Policy & Acceptance Review

## Scope

This PR implements M4-4 only.

It does not implement automatic promotion execution, knowledge ingestion,
orchestrator runtime integration, vector memory, dashboards, or whole-repo eval
platform behavior.

## What Changed

- added `app/services/memory/promotion.py` with:
  - `MemoryPromotionTarget`
  - `MemoryPromotionRequest`
  - `MemoryPromotionDecision`
  - `validate_memory_promotion(...)`
  - helper constructors from candidate and retrieved-item contracts
- locked the explicit promotion matrix for:
  - profile results
  - Risk QA answers
  - approved SQL cases
  - failed SQL cases
  - audit events
  - eval cases
- added a minimal consistency fix so grounded Risk QA memories can enter the
  existing eval-candidate retrieval path while unverified ones remain blocked
- extended focused M4 tests for promotion decisions and retrieval alignment

## Promotion Matrix Highlights

- `profile_result -> profile_history` allowed
- `risk_qa_answer -> risk_qa_history` allowed
- `risk_qa_answer -> eval_candidate` allowed only for grounded / reviewed
  evidence posture
- `data_agent_sql_case -> sql_case` allowed only for `human_approved`
- `data_agent_sql_case -> approved_sql_example` allowed only with
  `approved_sql_hash`
- `data_agent_sql_error -> sql_error_case` and `-> eval_candidate` allowed
- `audit_event -> eval_candidate` allowed as candidate-only governance output

Explicit blocked examples:

- `risk_qa_answer -> risk_knowledge_source_document`
- `profile_result -> data_knowledge_authority`
- `profile_result -> approved_strategy_policy`
- `user_preference -> safety_policy`
- `user_preference -> hitl_bypass_policy`
- `data_agent_sql_error -> approved_sql_example`

## Tests Run

- `AUTH_ENABLED=0 pytest tests/test_memory_promotion_policy.py -q`
- `AUTH_ENABLED=0 pytest tests/test_memory_retrieval_boundary.py -q`

## Known Limitations

- no automatic promotion execution
- no Data Knowledge / Risk Knowledge ingestion
- no SQL example publishing workflow
- no golden set write path
- no orchestrator runtime integration
- no vector / embedding memory
- M4 whole-stage acceptance remains pending until this PR is accepted

## Decision

- `M4-1 Memory Type & Isolation Contract: completed`
- `M4-2 Memory Write Gate & Store Metadata: completed`
- `M4-3 Memory Retrieval Boundary & Context Injection: completed`
- `M4-4 Memory Promotion Policy & Acceptance Closure: implemented / pending acceptance`
- `M4 Unified Memory & Memory Isolation: pending M4-4 acceptance`
- proposed post-merge reading:
  - `M4 completed under scoped memory governance definition`
