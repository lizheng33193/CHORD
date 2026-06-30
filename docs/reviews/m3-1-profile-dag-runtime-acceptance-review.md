# M3-1 Profile DAG Runtime Acceptance Review

## 1. Scope
- Review type: `M3-1 post-implementation acceptance closure`
- Review goal:
  - verify `ProfileDagExecutor` is the profile runtime truth
  - verify public API and legacy event compatibility remain intact
  - verify node/run status semantics are explicit
  - verify acceptance evidence, dirty-file boundary, and commit boundary
- Out of scope:
  - `M3-2` UI/SSE implementation
  - LangGraph
  - DB persistence
  - retry/cache/resume hardening
  - Data Agent / Hybrid Retrieval / TraceAnalyzer changes

## 2. Implementation Summary
- `M3-1` introduced a dedicated `app/services/profile_dag/` layer with:
  - domain contracts
  - fixed node registry
  - profile node/run event builders
  - compatibility adapters
  - `ProfileDagExecutor`
- `AnalysisOrchestrator.analyze()` now runs through `ProfileDagExecutor`.
- `AnalysisOrchestrator.analyze_module()` now runs through the same executor with `requested_modules=[module]`.
- chat `run_profile` now routes through `AnalysisOrchestrator.run_profile_request()` and the same executor.
- Public output shapes remain unchanged through adapters:
  - `AnalyzeResponse`
  - `UserAnalysisResult`
  - `/api/analyze-module` response payload
  - `RunProfileOutput.results`

## 3. Runtime Truth Verification
- Verified runtime truth source:
  - `app/services/profile_dag/executor.py::ProfileDagExecutor`
- Verified shared entrypoints:
  - `AnalysisOrchestrator.analyze()` -> `self.profile_dag.run(...)`
  - `AnalysisOrchestrator.analyze_module()` -> `self.profile_dag.run(...)`
  - chat `run_profile()` -> `AnalysisOrchestrator.run_profile_request()` -> `self.profile_dag.run(...)`
- Verified scheduler semantics:
  - static node graph is defined in `app/services/profile_dag/node_registry.py`
  - dependency closure is derived by `resolve_execution_closure(...)`
- Verified non-truth layers:
  - `SkillRegistry` now serves as concrete skill registration / lookup
  - legacy events remain consumers / adapters, not runtime truth
- No bypass path was found among the accepted profile entrypoints above.

## 4. Public API Compatibility
- `/api/analyze`
  - compatibility covered by `tests/test_orchestrator_progress.py`
  - `analysis_progress` payload still carries serialized `UserAnalysisResult`
- `/api/analyze-stream`
  - compatibility covered by `tests/test_analyze_stream_endpoint.py`
  - legacy stream still emits `analysis_started`, `skill_started`, `skill_completed`, `analysis_progress`, `analysis_completed`
- `/api/analyze-module`
  - compatibility covered by `tests/test_analyze_module_endpoint.py`
  - response shape remains `uid / module / status / data / error`
- chat `run_profile`
  - compatibility covered by `tests/orchestrator_agent/test_profile_runner.py`
  - result shape remains `results / cache_hits / cache_misses`

## 5. Event Compatibility
- New runtime truth events:
  - `profile_run_started`
  - `profile_node_started`
  - `profile_node_completed`
  - `profile_node_failed`
  - `profile_node_skipped`
  - `profile_run_completed`
  - `profile_run_failed`
- Legacy compatibility preserved:
  - analyze path maps `profile_node_*` to `skill_started / skill_completed / skill_failed`
  - chat `run_profile` maps requested-module node events to `profile_module_started / profile_module_completed / profile_module_error`
  - `tool_progress` compatibility remains exercised via `tests/orchestrator_agent/test_profile_runner.py`
- Coverage evidence:
  - `tests/test_profile_dag_runtime.py::test_orchestrator_analyze_emits_profile_node_events_and_keeps_legacy_skill_events`
  - `tests/test_profile_dag_runtime.py::test_run_profile_tool_emits_profile_node_events_and_preserves_legacy_module_progress`

## 6. `analyze_module` Semantics
- Source nodes:
  - `app / behavior / credit` run only the requested node because their closure contains no dependencies.
- Dependent nodes:
  - `comprehensive / product / ops` execute the minimal dependency closure required by the static M3-1 DAG.
- This behavior is implemented by:
  - `AnalysisOrchestrator.analyze_module()` passing `requested_modules=[module]`
  - `resolve_execution_closure(...)` recursively adding upstream dependencies
- Conclusion:
  - `analyze_module` is a compatibility endpoint backed by the static profile DAG
  - it is not a general-purpose DAG execution API

## 7. Node Status Semantics
- Node statuses are explicitly modeled as:
  - `pending`
  - `running`
  - `completed`
  - `failed`
  - `skipped`
  - `degraded`
- Semantics verified from implementation and targeted tests:
  - same-stage siblings do not block one another
  - nodes outside the requested closure become `skipped` with `skip_reason=not_requested`
  - downstream nodes run on upstream `completed` or `degraded`
  - `comprehensive` treats `app / behavior / credit` as soft-required in `M3-1`
  - `comprehensive failed -> product / ops skipped`
- Coverage evidence:
  - `tests/test_profile_dag_runtime.py::test_profile_dag_executor_marks_comprehensive_degraded_and_unrequested_nodes_skipped`
  - `tests/test_profile_dag_runtime.py::test_profile_dag_executor_skips_product_and_ops_when_comprehensive_fails`
  - `tests/test_profile_dag_runtime.py::test_profile_dag_executor_event_contract_contains_fixed_fields`

## 8. ProfileRun Status Aggregation
- Run statuses are explicitly modeled as:
  - `pending`
  - `running`
  - `completed`
  - `completed_with_degradation`
  - `failed`
  - `cancelled`
- Current aggregation behavior:
  - all requested nodes `completed` -> `completed`
  - any requested node `degraded / skipped / failed`, while result remains displayable -> `completed_with_degradation`
  - all requested nodes `failed` -> `failed`
- Coverage evidence:
  - degraded comprehensive path returns `completed_with_degradation`
  - comprehensive failure with downstream skips also returns `completed_with_degradation`

## 9. Verification Evidence
- Passed:
  - `python -m compileall -q app data_acquisition_agent tests scripts`
  - `git diff --check`
  - `AUTH_ENABLED=0 pytest tests/test_profile_dag_runtime.py tests/test_orchestrator_progress.py tests/orchestrator_agent/test_profile_runner.py tests/test_analyze_stream_endpoint.py tests/test_analyze_module_endpoint.py -q`
    - result: `35 passed`
- Full regression:
  - `AUTH_ENABLED=0 pytest -q`
  - result: `1 failed, 1334 passed, 6 skipped`
  - blocker:
    - `tests/frontend/test_chat_phase3_capabilities.py::test_chat_panel_uses_memory_drawer_instead_of_inline_block`
  - failure summary:
    - assertion expects `text-[11px]` not to appear in `ChatPanel.jsx`
    - failing path is outside `M3-1` touched runtime files
- Warning scope:
  - observed warnings were existing deprecation warnings from FastAPI / passlib / pkg_resources / Pydantic and one existing golden-test warning

## 10. Auth Test Scope
- `M3-1` did not modify:
  - auth middleware
  - permission checks
  - auth runtime behavior
- Acceptance regression used `AUTH_ENABLED=0` to match the existing API test harness and avoid coupling profile runtime acceptance to unrelated auth gate behavior.
- `AUTH_ENABLED=1` smoke was not executed in this review.
- This is a test-scope decision, not a claim that auth-enabled runtime behavior was re-verified here.

## 11. Dirty Files Boundary
- Current local dirty files:
  - `app/ui/build_frontend.py`
  - `tests/frontend/test_auth_gate_ui.py`
- Boundary findings:
  - `git status --short` shows both files are local uncommitted modifications
  - `git show --name-only 833f535 -- app/ui/build_frontend.py tests/frontend/test_auth_gate_ui.py` returned no paths
  - `git show --name-only 0683e49 -- app/ui/build_frontend.py tests/frontend/test_auth_gate_ui.py` returned no paths
- Conclusion:
  - these files were not included in the `M3-1` implementation commit
  - they were not included in the final pushed head
  - they are local-only unrelated dirty files and remain outside `M3-1` scope

## 12. Commit Boundary
- `M3-1` implementation commit:
  - `833f535 feat: add profile dag runtime skeleton`
- Final pushed head used for this review:
  - `0683e49 Merge remote-tracking branch 'origin/main'`
- Commits between implementation and final head:
  - `0683e49 Merge remote-tracking branch 'origin/main'`
  - `e192201 Merge pull request #31 from lizheng33193/codex/m2b-9-1-hybrid-enabled-rollout-observability-acceptance`
  - `28543f1 docs: add m2b-9.1 rollout observability artifacts`
- Range classification:
  - `833f535^..833f535` contains only M3-1 runtime files and docs
  - `833f535..0683e49` contains only M2B-9.1 docs and observability tests
  - no additional M3-1 runtime behavior change was introduced after `833f535`
- Conclusion:
  - final head includes post-implementation upstream merges, but no unreported M3-1 behavior delta

## 13. Must-fix Issues
- Full regression is not yet green.
  - blocking test:
    - `tests/frontend/test_chat_phase3_capabilities.py::test_chat_panel_uses_memory_drawer_instead_of_inline_block`
  - scope classification:
    - acceptance blocker for promotion to `completed`
    - not evidence of a direct `M3-1` runtime regression

## 14. Should-fix Issues
- Decide whether to run a separate `AUTH_ENABLED=1` smoke in a later acceptance pass or continue treating auth-enabled behavior as out of scope for profile runtime acceptance.
- Clean up or isolate the local-only dirty files before the next major acceptance pass to keep workspace state easier to reason about.

## 15. Final Decision
- Decision:
  - keep `M3-1 Profile DAG Runtime Skeleton` at `implemented / pending final acceptance`
- Reason:
  - runtime truth verification passed
  - public API compatibility evidence passed
  - event compatibility evidence passed
  - node/run status semantics are now explicit
  - dirty-file boundary and commit boundary are clear
  - `M3-2` has not started
  - full repository regression is not yet fully green
- Promotion rule:
  - after the repo-wide regression blocker is resolved, rerun `AUTH_ENABLED=0 pytest -q`
  - if full regression passes and no new `must-fix` issue appears, `M3-1` can be promoted to `completed`
