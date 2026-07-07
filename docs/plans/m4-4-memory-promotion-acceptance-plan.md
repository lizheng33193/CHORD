# M4-4 Memory Promotion Policy & Acceptance Closure Plan

## Goal

Implement a promotion eligibility layer for M4 memory records, lock explicit
blocked authority paths, and close M4 under the scoped memory governance
definition without introducing any automatic promotion execution.

## Implementation Steps

1. Add `app/services/memory/promotion.py` with promotion target, request,
   decision, and validator contracts.
2. Reuse existing M4 source-type and authority contracts rather than introducing
   a new runtime memory model.
3. Lock the explicit promotion matrix for profile, Risk QA, SQL case, SQL
   error, audit, and eval memory sources.
4. Add the minimal consistency fix for `risk_qa_answer -> eval_candidate` in:
   - `app/services/memory/policy.py`
   - `app/services/memory/retrieval_policy.py`
5. Export the new promotion surface from `app/services/memory/__init__.py`.
6. Add focused tests:
   - `tests/test_memory_promotion_policy.py`
   - focused retrieval alignment in `tests/test_memory_retrieval_boundary.py`
7. Add M4-4 docs and acceptance-closure docs.
8. Update `PLANNING.md` and `TASK.md` with `implemented / pending acceptance`
   wording for M4-4.

## Files To Change

- `app/services/memory/promotion.py`
- `app/services/memory/policy.py`
- `app/services/memory/retrieval_policy.py`
- `app/services/memory/__init__.py`
- `tests/test_memory_promotion_policy.py`
- `tests/test_memory_retrieval_boundary.py`
- `docs/specs/m4-4-memory-promotion-policy.md`
- `docs/plans/m4-4-memory-promotion-acceptance-plan.md`
- `docs/reviews/m4-4-memory-promotion-acceptance-review.md`
- `docs/reviews/m4-acceptance-closure-review.md`
- `PLANNING.md`
- `TASK.md`

## Test Plan

- `AUTH_ENABLED=0 pytest tests/test_memory_promotion_policy.py -q`
- `AUTH_ENABLED=0 pytest tests/test_memory_retrieval_boundary.py -q`
- `AUTH_ENABLED=0 pytest tests/test_memory_type_isolation_contract.py tests/test_memory_write_gate.py tests/test_memory_store_metadata.py tests/test_memory_retrieval_boundary.py tests/test_memory_context_builder.py tests/test_profile_memory_snapshot.py tests/test_memory_promotion_policy.py -q`
- `python -m compileall -q app data_acquisition_agent tests scripts`
- `git diff --check`

## Non-Goals

- no automatic promotion execution
- no knowledge-store writes
- no orchestrator runtime integration
- no vector memory
- no embedding retrieval
- no dashboard
- no whole-repo regression as a hard stage requirement

## Acceptance Criteria

- allowed decisions remain candidate-only
- dangerous authority and policy promotion paths are explicitly blocked
- approved SQL example promotion requires both `human_approved` and
  `approved_sql_hash`
- unverified Risk QA answers do not enter the eval-candidate promotion path
- focused M4 tests remain green after the additive policy changes
