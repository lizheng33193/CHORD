# Pre-M3 PR-C Eval Regression + M2C Essential Semantic Validator + Release Gate Review

## 1. Review Scope

- runtime acceptance hardening snapshot after the merged PR-C2 runtime slice
- this review records implementation readiness and targeted verification evidence
- final production release acceptance remains out of scope until broader regression and deployment evidence are complete

## 2. Baseline

- latest `main` after the PR-C2 runtime merge via `PR #58`
- merge commit: `323711e03577c979736b3fcb4c71842ccbe78e88`
- `PR-A` remains frozen as `implemented; pending final acceptance`
- `PR-B` remains frozen as `implemented; pending final acceptance`

## 3. Planning Decision

- `PR-C Eval Regression + M2C Essential Semantic Validator + Release Gate planned; implementation not started`
- `PR-C1` planning landed via `PR #57`
- the planning boundary remains additive reuse of existing harness seams rather than a new top-level eval platform

## 4. Runtime Implementation Status

- `PR-C Eval Regression + M2C Essential Semantic Validator + Release Gate implemented; pending final acceptance`
- merged runtime slice includes:
  - Risk QA regression extensions under `app/risk_knowledge/evaluation/`
  - deterministic SQL semantic validation under `app/data_agent/semantic_validation/`
  - Data Agent SQL review integration that preserves existing HITL approval boundaries
  - release gate package under `app/release/`
  - formal release-gate entrypoint `python -m app.release.pre_m3_gate`
  - contract spec, runbook, and targeted tests

## 5. Runtime Verification

- targeted runtime verification executed:
  - `pytest tests/risk_knowledge/evaluation tests/risk_knowledge/test_citation_validation.py tests/risk_knowledge/test_context_builder_isolation.py tests/risk_knowledge/service/test_risk_knowledge_service.py tests/data_agent/test_api.py tests/data_agent/test_safety.py tests/data_agent/test_plan_review.py tests/data_agent/test_sql_plan.py tests/data_agent/test_semantic_validation.py tests/release/test_pre_m3_gate.py -q`
- targeted runtime result:
  - `93 passed, 6 warnings`
- release gate CLI smoke executed:
  - `python -m app.release.pre_m3_gate --profile pr_acceptance --output-json /tmp/pre_m3_gate_pr_acceptance.json`
  - result: exit `0`, release-gate status `WARN`
  - `python -m app.release.pre_m3_gate --profile production_release --strict --output-json /tmp/pre_m3_gate_production_release.json`
  - result: exit `1`, release-gate status `BLOCKED`
- PR-B non-regression verification executed:
  - `pytest tests/risk_knowledge/test_indexing_worker.py tests/risk_knowledge/test_indexing_job_api.py tests/risk_knowledge/test_manifest_activation_rollback.py tests/risk_knowledge/test_stale_job_detection.py tests/risk_knowledge/test_indexing_job_idempotency.py -q`
  - result: `7 passed, 6 warnings`
- additional verification:
  - `python -m compileall -q app tests`
  - `git diff --check`

## 5A. Final Acceptance Closure Attempt

- executed on `2026-07-04` from `codex/pre-m3-final-acceptance-closure`
- full-repository regression:
  - `pytest -q`
  - result: `110 failed, 1462 passed, 11 skipped, 33 warnings`
- representative failing areas included:
  - `data_acquisition_agent/tests/test_api.py`
  - `data_acquisition_agent/tests/test_api_v2.py`
  - `data_acquisition_agent/tests/test_e2e_mock_executor.py`
  - `tests/test_analyze_module_endpoint.py`
  - `tests/test_orchestrator_chat_routes.py`
  - `tests/risk_knowledge/reranking/test_dashscope_provider.py`
  - `tests/risk_knowledge/runtime/test_worker_lifecycle.py`
- acceptance outcome:
  - PR-C remains `implemented; pending final acceptance`
  - Pre-M3 gates are not ready for M3 entry

## 6. Production Risk Checks

- semantic validation is deterministic and structured; it is not prompt-only and not LLM self-judgment
- semantic validation prefers `structured_sql_plan` when available and uses raw SQL only as fallback context
- blocked SQL is surfaced as non-approvable and does not bypass the existing HITL execution boundary
- `build_table_script` remains `review_only`; semantic validation does not expand execution permission
- release gate aggregates structured check results and does not replace `pytest` as the source of test-execution truth
- full repository regression not run is currently:
  - `WARN` for `pr_acceptance`
  - `BLOCKED` for `production_release`

## 7. Known Limitations

- full repository regression was run during final acceptance closure and failed
- final production release acceptance remains pending
- the current semantic validator is a deterministic v1 slice; deeper catalog-aware or policy-catalog validation remains future enhancement
- the runbook records operator procedures and rollback expectations but does not automate deployment orchestration by itself
- the current release-gate CLI default runner is still report-driven and reports `full repository regression not run` unless real regression results are wired into its check inputs

## 8. Next Step

- resolve the repository-level regression failures
- wire final regression evidence into the production release decision path if a stricter end-to-end release-gate contract is required
- retry final acceptance closure only after the broader repository regression baseline is green
