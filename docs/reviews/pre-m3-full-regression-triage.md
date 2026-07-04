# Pre-M3 Full Regression Triage

## Scope

- triage the failed `pytest -q` run recorded on `codex/pre-m3-final-acceptance-closure`
- do not start M3 runtime work
- do not add new PR-A / PR-B / PR-C features
- focus on acceptance-repair blockers only

## Initial Authoritative Full-Run Result

- command:
  - `pytest -q`
- result:
  - `110 failed, 1462 passed, 11 skipped, 33 warnings`
- status:
  - Pre-M3 final acceptance remains blocked
  - production release remains blocked

## Working Inventory Note

- `.pytest_cache/v/cache/lastfailed` is useful for grouping, but it is not a stable source of truth after targeted repro runs
- after local repro work, the cache currently shows `113` unique node ids because it also retains post-run targeted failures and stale entries
- this document therefore treats `110` as the authoritative full-run failure count and uses the cache only as a working inventory aid

## Initial Failure Groups

### P0. Auth Baseline Regression

- severity:
  - `P0`
- working inventory size:
  - about `88` failures
- representative files:
  - `tests/test_orchestrator_chat_routes.py` (`21`)
  - `data_acquisition_agent/tests/test_e2e_mock_executor.py` (`20`)
  - `data_acquisition_agent/tests/test_api.py` (`10`)
  - `tests/test_analyze_module_endpoint.py` (`9`)
  - `data_acquisition_agent/tests/test_api_v2.py` (`8`)
  - `tests/orchestrator_agent/test_memory_api_sqlite.py` (`5`)
  - `tests/test_analyze_stream_endpoint.py` (`4`)
  - `tests/test_orchestrator_phase3.py` (`3`)
  - `tests/test_trace_analyzer_api.py` (`3`)
  - `tests/test_main_routing_sse.py` (`1`)
  - `data_acquisition_agent/tests/test_e2e_mock_llm.py` (`1`)
- representative symptom:
  - expected business responses are replaced by `401 Unauthorized`
- initial evidence:
  - `pytest data_acquisition_agent/tests/test_api.py::test_generate_422_on_invalid_country_enum -q` -> `401`
  - `AUTH_ENABLED=0 pytest data_acquisition_agent/tests/test_api.py::test_generate_422_on_invalid_country_enum -q` -> pass
  - `pytest tests/test_orchestrator_chat_routes.py::test_create_session_with_initial_message_returns_id_and_iso_created_at -q` -> `401`
  - `AUTH_ENABLED=0 pytest tests/test_orchestrator_chat_routes.py::test_create_session_with_initial_message_returns_id_and_iso_created_at -q` -> pass
- suspected owner:
  - repo-wide test baseline / auth default environment
- introduced-by assessment:
  - not clearly a PR-A / PR-B / PR-C business regression
  - more likely a repo test-baseline drift caused by `.env` loading `AUTH_ENABLED=true`
- fix strategy:
  - restore the historical auth-off baseline for non-auth tests by default
  - keep auth-specific suites responsible for explicitly enabling auth

### P1. Worker Lifecycle / External-Worker Posture Test Drift

- severity:
  - `P1`
- representative file:
  - `tests/risk_knowledge/runtime/test_worker_lifecycle.py`
- representative symptom:
  - test expected manager start/stop, but current external-worker-first default posture returns early
- initial evidence:
  - `pytest tests/risk_knowledge/runtime/test_worker_lifecycle.py::test_worker_lifecycle_start_and_stop_manager_once -q` -> events remain empty
- suspected owner:
  - PR-B runtime posture versus stale lifecycle test assumptions
- introduced-by assessment:
  - related to PR-B posture changes, but likely a stale test precondition rather than a new runtime bug
- fix strategy:
  - update the test to enable the in-process start condition explicitly before asserting lifecycle behavior

### P1. Reranker Environment Leakage

- severity:
  - `P1`
- representative file:
  - `tests/risk_knowledge/reranking/test_dashscope_provider.py`
- representative symptom:
  - missing-key test accidentally uses environment-provided `DASHSCOPE_API_KEY` and performs a real request
- initial evidence:
  - `pytest tests/risk_knowledge/reranking/test_dashscope_provider.py::test_dashscope_provider_requires_api_key -q` triggers a transport error instead of `RerankerProviderConfigError`
- suspected owner:
  - environment-sensitive test setup
- introduced-by assessment:
  - historical environment sensitivity, not a new semantic-validator or release-gate regression
- fix strategy:
  - make the test explicitly clear the configured DashScope API key before exercising the missing-key path

### P2. Local Sample Data / Fixture Availability Gaps

- severity:
  - `P2`
- working inventory size:
  - about `20` failures
- representative files:
  - `tests/test_app_profile_phase1.py`
  - `tests/test_behavior_profile_phase18.py`
  - `tests/test_credit_profile_phase17.py`
  - `tests/test_data_prep_phase16.py`
  - `tests/risk_knowledge/ingestion/test_swxy_parser_dependencies.py`
- representative symptoms:
  - missing local sample files
  - prepared payload assumptions not satisfied in the current local data layout
- initial evidence:
  - `AUTH_ENABLED=0 pytest tests/test_app_profile_phase1.py::AppProfilePhase1Tests::test_data_provider_local_contract -q` -> `data_status` is `missing` because `data/app/by_uid/<uid>.csv` is absent
  - `AUTH_ENABLED=0 pytest tests/test_credit_profile_phase17.py::CreditProfilePhase17Tests::test_data_provider_prepared_json_contract -q` -> prepared payload lacks expected `source_meta`
- suspected owner:
  - local data fixture completeness / environment setup
- introduced-by assessment:
  - likely historical or environment-dependent rather than directly caused by PR-A / PR-B / PR-C
- fix strategy:
  - separate fixture/data-availability failures from true runtime regressions
  - decide whether to restore missing sample fixtures, harden fixtures, or mark clearly environment-bound

## Priority Order

1. collapse the auth-baseline regression first because it unlocks the largest cluster
2. fix worker lifecycle and reranker environment leakage next
3. then rerun targeted groups to see which failures remain real runtime regressions
4. only after that, triage the local-data / fixture-dependent profile failures

## Initial Acceptance Impact

- PR-A / PR-B / PR-C remain `implemented; pending final acceptance`
- Pre-M3 final acceptance remains blocked
- Pre-M3 gates are not ready for M3 entry
- production release remains blocked

## Next Repair Steps

1. restore the non-auth test baseline
2. re-run targeted `orchestrator`, `data_acquisition_agent`, `risk_knowledge/runtime`, and `reranking` suites
3. refresh the triage counts after those P0/P1 fixes
4. only then decide whether remaining failures are:
   - true PR-A / PR-B / PR-C regressions
   - historical pre-existing failures
   - environment dependencies
   - flaky tests
5. later, wire the release gate to consume real full-regression status instead of only reporting `not_run`

## Initial Repair Progress

- implemented:
  - repo-root `conftest.py` to keep non-auth tests on the historical auth-off baseline by default
  - lifecycle test precondition update for the external-worker-first posture
  - reranker missing-key test hardening against environment-provided DashScope credentials
- targeted verification after those changes:
  - `pytest tests/test_orchestrator_chat_routes.py data_acquisition_agent/tests/test_api.py data_acquisition_agent/tests/test_api_v2.py data_acquisition_agent/tests/test_e2e_mock_executor.py data_acquisition_agent/tests/test_e2e_mock_llm.py -q`
    - result: `52 passed, 6 warnings`
  - `pytest tests/risk_knowledge/runtime/test_worker_lifecycle.py tests/risk_knowledge/reranking/test_dashscope_provider.py -q`
    - result: `5 passed, 6 warnings`
  - `pytest tests/test_analyze_module_endpoint.py tests/test_analyze_stream_endpoint.py tests/test_analyze_stream_timeout.py tests/test_main_routing_sse.py tests/test_orchestrator_phase3.py tests/test_trace_analyzer_api.py tests/orchestrator_agent/test_memory_api_sqlite.py tests/orchestrator_agent/test_trace_metadata.py -q`
    - result: `66 passed, 32 warnings`
- current reading:
  - the first-pass P0/P1 auth-baseline and environment-sensitive blockers are materially reduced
  - full-repository regression has not yet been re-run after these repairs
  - P2 fixture/data-availability failures still need separate triage

## Acceptance Repair Completion

- additional repairs completed:
  - deterministic test-local fixture seeding for `app_profile`, `behavior_profile`, and `credit_profile` regression suites
  - `data_prep` sample-regression hardening so clean clones no longer depend on untracked local data
  - SWXY chunker dependency test hardening so missing optional `tika` reports `SwxyParserUnavailableError` instead of a false environment-specific failure
  - release-gate CLI support for `--full-regression-status not_run|passed|failed`
  - release-gate JSON report now records `full_regression_status`
- targeted verification after the acceptance-repair slice:
  - `pytest tests/release/test_pre_m3_gate.py tests/test_app_profile_phase1.py tests/test_behavior_profile_phase18.py tests/test_credit_profile_phase17.py tests/test_data_prep_phase16.py tests/risk_knowledge/ingestion/test_swxy_parser_dependencies.py -q`
    - result: `73 passed`
  - `python -m compileall -q app tests data_acquisition_agent conftest.py`
    - result: passed
  - `git diff --check`
    - result: passed

## Final Full-Run Result After Repairs

- command:
  - `pytest -q`
- result:
  - `1575 passed, 11 skipped, 33 warnings`
- delta versus the original blocked run:
  - failures reduced from `110` to `0`
  - the main repaired clusters were:
    - auth-baseline drift from local `.env` auth enablement
    - worker-lifecycle and reranker environment-sensitive tests
    - profile fixture / sample-data availability gaps
    - SWXY optional-dependency coupling

## Release-Gate Closure Evidence

- PR-acceptance profile:
  - `python -m app.release.pre_m3_gate --profile pr_acceptance --full-regression-status passed --output-json /tmp/pre_m3_gate_pr_acceptance_passed.json`
  - result: `PASS`
- production-release profile:
  - `python -m app.release.pre_m3_gate --profile production_release --strict --full-regression-status passed --output-json /tmp/pre_m3_gate_production_release_passed.json`
  - result: `PASS`

## Final Acceptance Outcome

- PR-A is accepted for Pre-M3 scope
- PR-B is accepted for Pre-M3 scope
- PR-C is accepted for Pre-M3 scope
- Pre-M3 final acceptance is closed
- Pre-M3 gates are ready for M3 entry
- this branch remains acceptance-repair closure only; it does not start M3 runtime work
