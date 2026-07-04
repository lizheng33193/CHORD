# M3 Implementation Audit

## 1. Audit Scope

- This audit only inspects current repository facts for the M3 Profile Skill DAG area.
- No runtime feature was added.
- No `app/` runtime code was modified.
- No `tests/` code was modified.
- No bug was fixed.
- Status recommendations below are evidence-based only.

## 2. Repository State

- Branch: `codex/pre-m3-regression-triage`
- HEAD: `b745827915fa61d0b163372d165eafd0e33f7a69`
- `git status --short`: clean working tree before this audit document was added
- Dirty files at audit start: none
- Push target check:
  - `origin` -> `git@github.com:lizheng33193/CHORD.git`
- M3 audit scope impact:
  - no pre-existing dirty files were present, so there was no local-only M3 ambiguity to exclude

## 3. Executive Summary

- `M3-1` is real: `app/services/profile_dag/` exists and public profile entrypoints now run through `ProfileDagExecutor`.
- `M3 runtime truth` has moved from direct stage execution to `ProfileDagExecutor`, but `SkillRegistry` still remains the concrete skill registry and lookup layer.
- The six profile nodes are fixed in a static DAG: `app / behavior / credit -> comprehensive -> product / ops`.
- All six runtime skills now have directory-level six-step pipelines plus thin agent wrappers, but these skills are mostly legacy runtime capabilities, not M3-certified deliveries.
- Final output schemas are enforced at assembler/public-shape boundaries with Pydantic, but most internal skill contracts are still `TypedDict`-only and node degradation depends on adapter heuristics rather than one strict cross-skill contract.
- `M3-3` is not complete: repository access is still centered on `LocalUserRepository`, local JSON/CSV, and optional sample fallback; `WarehouseUserRepository` is still a stub.
- `M3-4` is not started for profile runtime: no profile skill imports or consumes M2D Risk Domain Evidence, citations, or evidence trace contracts.
- `M3-5` is only partially present as legacy dashboard/chat UX; frontend still primarily consumes legacy `skill_*` / `profile_module_*` progress, not `profile_node_*` truth.
- `M3-6` and `M3-7` are not complete: there is no profile-specific golden-set/regression pack and no whole-M3 acceptance review beyond `M3-1`.
- Conclusion: M3 is not complete and the repo should not start M4 yet.

## 4. M3 Stage Status Matrix

| stage | expected goal | runtime evidence | tests evidence | docs evidence | current status | blocker | recommendation |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `M3-1 Profile DAG Runtime Skeleton` | one profile runtime truth, static DAG, status/event contract, public API compatibility | `app/services/profile_dag/contracts.py`, `node_registry.py`, `events.py`, `adapters.py`, `executor.py`; `app/services/orchestrator.py` routes `analyze()`, `analyze_module()`, `run_profile_request()` through `self.profile_dag.run(...)` | `tests/test_profile_dag_runtime.py`, `tests/test_orchestrator_progress.py`, `tests/orchestrator_agent/test_profile_runner.py`, `tests/test_analyze_stream_endpoint.py`, `tests/test_analyze_module_endpoint.py` all pass | `PLANNING.md` 2026-06-30 section, `TASK.md` `M3-1` entry, `docs/specs/m3-profile-dag-runtime-contract.md`, `docs/plans/m3-1-profile-dag-runtime-skeleton-plan.md`, `docs/reviews/m3-1-profile-dag-runtime-acceptance-review.md` | `completed` | none for `M3-1` scope | keep as completed; do not inflate it to whole-M3 completion |
| `M3-2 Core Profile Skills` | production-grade core profile skills on top of M3 contracts | six skill directories exist under `app/runtime_skills/*`; each has `contracts/data_access/feature_builder/decision_engine/explainer/assembler`; thin wrappers exist in `*_agent.py` | `tests/test_app_profile_phase1.py`, `tests/test_behavior_profile_phase18.py`, `tests/test_credit_profile_phase17.py`, `tests/test_comprehensive_phase1.py`, `tests/test_product_advice_phase1.py`, `tests/test_ops_advice_phase1.py` pass | `PLANNING.md` and `TASK.md` still say `M3-2` not started; no dedicated `M3-2` plan/review found | `implemented but not M3-certified` | runtime skills exist, but inter-skill contract completeness, production data integration, and profile evidence contract are still incomplete | treat current skills as legacy implemented runtime, not as completed `M3-2` |
| `M3-3 Profile Data Access Integration` | stable production data access path for profile skills | `app/runtime_skills/*/data_access.py` exists, but orchestrator still defaults to `LocalUserRepository`; `app/repositories/warehouse_repository.py` is placeholder-only | profile tests pass mostly against local/sample/prepared-file paths | no dedicated `M3-3` plan/review found; `M3-1` follow-up mentions later persistence/audit hardening only | `incomplete` | no connected warehouse repository; local file/sample path still central; strict production data path is not the runtime default | finish production data integration before calling M3 complete |
| `M3-4 Risk Domain Evidence Integration` | profile explanation grounded by M2D risk-domain evidence with citations/trace | no `risk_knowledge` / citation / selected evidence imports in `app/runtime_skills/*` or `app/services/profile_dag/*` | no profile tests assert risk-domain evidence or citations | no dedicated `M3-4` plan/review found | `not started` | profile runtime does not consume M2D evidence pipeline | add explicit profile evidence contract instead of relying on ad hoc `structured_result.evidence` |
| `M3-5 Profile Result UI` | dashboard shows profile DAG progress, evidence, degraded state | dashboard exists under `app/static/js/components/DashboardView.jsx`; `ProgressView.jsx` exists; panel UIs show some evidence fields | frontend/chat/analyze-stream tests pass, but they cover legacy progress and panel rendering, not DAG-truth UI | `docs/specs/sse-progress-design.md` is pre-M3 and legacy-`SkillRegistry` oriented; no `M3-5` review found | `partially implemented` | frontend still mainly consumes `skill_*` / `profile_module_*`; no proof that `profile_node_*` is the UI truth; no DAG-node degraded/evidence provenance view | do not mark UI phase complete; treat current dashboard as legacy/partial |
| `M3-6 Profile Golden Set & Regression` | profile-specific golden set, schema regression, evidence/citation regression | no profile golden-set package comparable to `app/risk_knowledge/evaluation`; only generic/older fixtures exist under `tests/fixtures/golden/behavior_profile` and `tests/fixtures/golden/comprehensive_profile` | repository regression is green, but there is no M3 profile golden gate | no dedicated `M3-6` plan/review found | `not started` | full `pytest` green is not a substitute for profile golden, contract, or evidence regression | create a dedicated profile regression gate before M4 |
| `M3-7 Profile Acceptance Review` | explicit whole-M3 acceptance closure | only `M3-1` acceptance exists | full regression passes, but no whole-M3 acceptance checklist exists | `docs/reviews/m3-1-profile-dag-runtime-acceptance-review.md` only; no whole-M3 review found | `not started` | there is no reconciled whole-M3 status artifact | add one M3 closure review after gaps are fixed |

## 5. DAG Runtime Findings

### 5.1 What is implemented

- `ProfileDagExecutor` exists at `app/services/profile_dag/executor.py`.
- Fixed node registry exists at `app/services/profile_dag/node_registry.py`.
- Runtime contracts exist at `app/services/profile_dag/contracts.py`:
  - `ProfileRun`
  - `ProfileNodeRun`
  - `ProfileRunResultSnapshot`
- Event builders exist at `app/services/profile_dag/events.py`.
- Compatibility adapters exist at `app/services/profile_dag/adapters.py`.

### 5.2 Runtime truth has moved

- `AnalysisOrchestrator.analyze()` now calls `self.profile_dag.run(...)` in `app/services/orchestrator.py`.
- `AnalysisOrchestrator.analyze_module()` now calls the same executor with `requested_modules=[module]`.
- chat `run_profile` goes through:
  - `app/services/orchestrator_agent/tools/run_profile.py`
  - `AnalysisOrchestrator.run_profile_request()`
  - `self.profile_dag.run(...)`
- This matches the `M3-1` contract and acceptance review.

### 5.3 `SkillRegistry` is no longer the public profile runtime truth

- `SkillRegistry` still exists in `app/runtime_skills/base.py`.
- `AnalysisOrchestrator._build_registry()` still registers all concrete skills there.
- `ProfileDagExecutor` is constructed from `skill_map={name: self.registry.get(name) ...}` in `app/services/orchestrator.py`.
- Conclusion:
  - `SkillRegistry` still matters as concrete skill registration/storage.
  - It is no longer the accepted public execution truth for `/api/analyze`, `/api/analyze-module`, or chat `run_profile`.

### 5.4 DAG shape is fixed and matches the M3-1 contract

- `app`, `behavior`, `credit` are stage `0` roots in `app/services/profile_dag/node_registry.py`.
- `comprehensive` is stage `1` and depends on `app / behavior / credit`.
- `product` and `ops` are stage `2` and depend on `comprehensive`.
- `resolve_execution_closure(...)` recursively adds upstream dependencies for requested modules.

### 5.5 Status and event semantics are real

- Node statuses in `app/services/profile_dag/contracts.py`:
  - `pending`
  - `running`
  - `completed`
  - `failed`
  - `skipped`
  - `degraded`
- Run statuses in `app/services/profile_dag/contracts.py`:
  - `pending`
  - `running`
  - `completed`
  - `completed_with_degradation`
  - `failed`
  - `cancelled`
- New runtime events exist:
  - `profile_run_started`
  - `profile_node_started`
  - `profile_node_completed`
  - `profile_node_failed`
  - `profile_node_skipped`
  - `profile_run_completed`
  - `profile_run_failed`
- Legacy compatibility also exists:
  - `profile_node_* -> skill_started / skill_completed / skill_failed` via `profile_event_to_legacy_skill_events(...)`
  - requested-module `profile_node_*` -> `profile_module_*` via `profile_event_to_legacy_module_event(...)`

### 5.6 Bypass-path conclusion

- No bypass path was found for the accepted public profile entrypoints:
  - `/api/analyze`
  - `/api/analyze-module`
  - chat `run_profile`
- `SkillRegistry.run_all(...)` still exists and is still directly testable, but it is not the accepted path for those public profile entrypoints anymore.

### 5.7 Important limitation: node degradation is inferred heuristically

- `app/services/profile_dag/adapters.py::classify_module_payload(...)` infers node status from:
  - `structured_result.status`
  - a short list of degraded status strings
  - `model_trace.fallback_reason`
  - `model_trace.degraded`
  - `model_trace.model_unavailable`
- This means node degradation is not driven by one strict per-skill schema contract.
- `M3-1` runtime truth is real, but skill-level output normalization is still partly heuristic.

## 6. Skill Internal Pipeline Findings

### 6.1 Audit table

| skill_name | runtime_path | registered_in_skill_registry | dag_node_key | stage | depends_on | has_contracts_py | has_data_access_py | has_feature_builder_py | has_decision_engine_py | has_explainer_py | has_assembler_py | has_agent_wrapper | has_schema_model | has_prompt | has_tests | output_contract_enforced | degraded_output_supported | deterministic_rule_layer_supported | llm_explainer_only_or_decision_maker | user_data_evidence_supported | risk_domain_evidence_supported | production_ready_assessment |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `app_profile` | `app/runtime_skills/app_profile/` | yes | `app` | `0` | `[]` | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | final output yes; internal layers mostly `TypedDict` only | yes | yes | mostly explainer-only, but feature layer has `AppCategoryLLMClassifier` fallback | yes | no | usable legacy runtime; not M3-certified |
| `behavior_profile` | `app/runtime_skills/behavior_profile/` | yes | `behavior` | `0` | `[]` | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | final output yes; internal layers mostly `TypedDict` only | yes | yes | explainer-only for LLM; deterministic decision core | yes | no | usable legacy runtime; not M3-certified |
| `credit_profile` | `app/runtime_skills/credit_profile/` | yes | `credit` | `0` | `[]` | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | final output yes; internal layers mostly `TypedDict` only | yes | yes | explainer-only for LLM; deterministic decision core | yes | no | usable legacy runtime; not M3-certified |
| `comprehensive_profile` | `app/runtime_skills/comprehensive/` | yes | `comprehensive` | `1` | `["app_profile","behavior_profile","credit_profile"]` | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | final output yes; internal layers mostly `TypedDict` only | yes | yes | explainer-only for LLM; deterministic decision core | limited | no | runtime works, but downstream contract is incomplete |
| `product_advice` | `app/runtime_skills/product_advice/` | yes | `product` | `2` | `["comprehensive_profile"]` | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | final output yes; internal layers mostly `TypedDict` only | yes | yes | explainer-only for LLM; deterministic rule lookup core | indirect only | no | runtime works, but upstream contract coverage is partial |
| `ops_advice` | `app/runtime_skills/ops_advice/` | yes | `ops` | `2` | `["comprehensive_profile"]` | yes | yes | yes | yes | yes | yes | yes | yes | yes | yes | final output yes; internal layers mostly `TypedDict` only | yes | yes | explainer-only for LLM; deterministic rule lookup core | indirect only | no | runtime works, but upstream contract coverage is partial |

### 6.2 Skill-by-skill notes

#### `app_profile`

- Thin orchestrator wrapper is in `app/runtime_skills/app_profile_agent.py`.
- Final schema is enforced by `AppPageAssembler` with `model_validate_compat(AppProfileStructuredResult, ...)`.
- Deterministic rule layer is real:
  - `feature_builder.py`
  - `decision_engine.py`
- LLM is mostly explanatory, but not purely explanatory:
  - `feature_builder.py` can initialize `AppCategoryLLMClassifier`
  - `category_llm_classifier.py` can classify app categories when keyword rules miss
- User data evidence exists in `structured_result.evidence`.
- No risk-domain evidence or citation contract is wired in.

#### `behavior_profile`

- Thin wrapper is in `app/runtime_skills/behavior_profile_agent.py`.
- Final schema is enforced by `BehaviorPageAssembler` with `BehaviorProfileStructuredResult`.
- Deterministic core is real:
  - prepared-record normalization in `data_access.py`
  - feature derivation in `feature_builder.py`
  - rule decision in `decision_engine.py`
- LLM is explanatory:
  - profile narrative
  - timeline narrative
- Evidence fields are rich user-data evidence:
  - `timeline_sections`
  - `timeline_sections_raw`
  - `timeline_sections_compact`
  - `timeline_insights`
  - `behavior_profile_narrative`
- No risk-domain evidence or citations are present.

#### `credit_profile`

- Thin wrapper is in `app/runtime_skills/credit_profile_agent.py`.
- Final schema is enforced by `CreditPageAssembler`.
- Deterministic core is real for both branches:
  - Buró branch
  - `risk_features` branch for TH
- LLM is explanatory only at page layer.
- User-data evidence exists:
  - profile header
  - report date
  - risk flags
  - repayment timeline
  - account details
- No M2D risk-domain evidence or citations are integrated.

#### `comprehensive_profile`

- Thin wrapper is in `app/runtime_skills/comprehensive_agent.py`.
- It truly consumes upstream structured outputs through `ComprehensiveUpstreamProvider.fetch(...)`.
- Deterministic decision rules are real.
- Final schema is validated in `ComprehensivePageAssembler`.
- Important gap:
  - its flattened metrics only contain `segment`, `risk_level`, `value_signal_level`, `confidence_level`, `dimension_scores`, and conflict info
  - it does not emit the fuller downstream advisory contract expected by `product_advice` / `ops_advice` data-access layers

#### `product_advice`

- Thin wrapper is in `app/runtime_skills/product_advice_agent.py`.
- Final schema is enforced by `ProductAdvicePageAssembler`.
- Decision engine is deterministic S1-S6 rule lookup.
- LLM only adds a small explanation payload.
- Important gap:
  - `ProductAdviceUpstreamProvider` expects fields like `behavior_tags`, `financial_tags`, `overall_risk`, `overall_value`, `confidence`, and `data_completeness`
  - real `comprehensive` runtime currently does not emit most of those fields
- Result:
  - the module runs
  - but the real cross-skill contract is only partially landed

#### `ops_advice`

- Thin wrapper is in `app/runtime_skills/ops_advice_agent.py`.
- Final schema is enforced by `OpsAdvicePageAssembler`.
- Decision engine is deterministic S1-S6 rule lookup with churn escalation and root-cause adaptation.
- LLM only adds outreach script / retention phrasing.
- Important gap is the same as `product_advice`:
  - expected upstream contract is richer than the current `comprehensive` output
  - so runtime can fall back to generic/default ops fields even when `comprehensive` succeeded

### 6.3 Real downstream contract mismatch

- `app/runtime_skills/comprehensive/decision_engine.py::_flatten_metrics(...)` emits:
  - `segment`
  - `risk_level`
  - `value_signal_level`
  - `confidence_level`
  - `dimension_scores`
  - conflict fields
- `app/runtime_skills/product_advice/data_access.py` and `app/runtime_skills/ops_advice/data_access.py` expect:
  - `recommended_segment` or `segment`
  - `segment_name`
  - `overall_risk`
  - `overall_value`
  - `behavior_tags`
  - `financial_tags`
  - `confidence`
  - `data_completeness`
- Therefore:
  - downstream advice modules are not consuming a fully realized comprehensive contract
  - current unit tests for product/ops use synthetic `_comp_result(...)` fixtures that contain fields not emitted by the real comprehensive runtime
  - `tests/test_product_advice_phase1.py` and `tests/test_ops_advice_phase1.py` validate the modules in isolation, not the real comprehensive-to-advice runtime contract

## 7. Contract / Evidence Findings

### 7.1 What exists

- `ProfileRun`, `ProfileNodeRun`, and `ProfileRunResultSnapshot` exist in `app/services/profile_dag/contracts.py`.
- Public shapes still remain:
  - `app/schemas/final_response.py::UserAnalysisResult`
  - `app/schemas/final_response.py::AnalyzeResponse`
- Final assembled skill outputs are validated with skill-specific Pydantic models in assembler layers.

### 7.2 What is only partially landed

- Most internal skill contracts are `TypedDict`, not runtime-enforced models.
- Internal layer boundaries such as:
  - raw data
  - feature bundle
  - decision result
  - explanation result
  are mostly type-hint contracts plus local defensive checks, not uniformly validated runtime schemas.
- Node degradation is inferred by `classify_module_payload(...)`, which is a compatibility heuristic rather than a strict cross-skill contract.

### 7.3 Downstream consumption status

- `comprehensive` truly consumes app/behavior/credit structured outputs.
- `product` and `ops` do consume `comprehensive`, but only partially:
  - current real comprehensive payload lacks several fields their data-access layers expect
  - so the contract is not fully stabilized

### 7.4 Evidence status

- User data evidence exists today as per-skill `structured_result.evidence` dictionaries.
- This evidence is ad hoc and skill-specific, not a unified profile evidence framework.
- No distinction is implemented between:
  - User Data Evidence
  - Risk Domain Evidence
- No profile-side Evidence Manager was found.
- No profile-side citation contract was found.
- No profile-side evidence trace contract was found.

### 7.5 M3 vs Pre-M3 classification

- Missing Risk Domain Evidence integration is an `M3` incomplete item, not a mere documentation gap.
- M2D risk evidence runtime exists elsewhere in the repo, but profile runtime does not consume it yet.
- Missing warehouse-backed/profile-production data access is an `M3-3` incomplete item, not just a pre-M3 concern.

## 8. Test Evidence

### 8.1 Commands executed

```bash
python -m compileall -q app data_acquisition_agent tests scripts
AUTH_ENABLED=0 pytest tests/test_profile_dag_runtime.py tests/test_orchestrator_progress.py tests/orchestrator_agent/test_profile_runner.py tests/test_analyze_stream_endpoint.py tests/test_analyze_module_endpoint.py -q
AUTH_ENABLED=0 pytest tests/test_app_profile_phase1.py tests/test_behavior_profile_phase18.py tests/test_credit_profile_phase17.py tests/test_behavior_credit_schema.py tests/test_comprehensive_phase1.py tests/test_product_advice_phase1.py tests/test_ops_advice_phase1.py -q
AUTH_ENABLED=0 pytest -q
git diff --check
```

### 8.2 Results

- `python -m compileall -q app data_acquisition_agent tests scripts`
  - passed
- targeted DAG/runtime/API set
  - `35 passed, 6 warnings`
- targeted profile skill set
  - `118 passed`
- full regression
  - `1575 passed, 11 skipped, 33 warnings`
- `git diff --check`
  - passed before this audit document was added

### 8.3 Test interpretation

- The repository is currently regression-green.
- This proves the current implementation is internally consistent enough to pass the existing suite.
- This does not prove:
  - full M3 completion
  - strong inter-skill production contracts
  - risk-domain evidence integration
  - profile golden-set acceptance

## 9. Gap Analysis

### P0: must be fixed before M4

- Normalize one strict profile output/degraded contract across all skills.
  - Evidence: `app/services/profile_dag/adapters.py::classify_module_payload(...)` currently uses heuristic status mapping.
- Finish the real `comprehensive -> product/ops` contract.
  - Evidence: `app/runtime_skills/comprehensive/decision_engine.py::_flatten_metrics(...)` does not emit the richer fields expected by `product_advice/data_access.py` and `ops_advice/data_access.py`.
  - Evidence: product/ops phase tests rely on synthetic `_comp_result(...)` fixtures that include fields not emitted by real comprehensive runtime.
- Finish production data-access integration for profiles.
  - Evidence: `app/repositories/warehouse_repository.py` is still `NotImplementedError`.
  - Evidence: orchestrator defaults to `LocalUserRepository`.
- Add explicit profile evidence contract with User Data Evidence vs Risk Domain Evidence separation.
  - Evidence: no profile skill imports `risk_knowledge` or citation contracts.
- Add profile-specific regression/acceptance gate.
  - Evidence: no `M3-6` or whole-`M3-7` artifact exists.

### P1: should be fixed before final M3 sign-off

- Make frontend consume `profile_node_*` as the primary DAG progress truth instead of relying mainly on legacy `skill_*` / `profile_module_*`.
- Decide whether profile result payloads should expose a stable degraded/public-status contract instead of relying on node-level adapter inference.
- Add persistent/auditable storage or explicit non-goal closure for `ProfileRun` / `ProfileNodeRun` records beyond in-memory execution.

### P2: later enhancement

- Revisit richer profile-node provenance and cache provenance only after P0/P1 contracts are stable.
- Revisit LangGraph only after M3 contracts are complete; current repo still correctly treats it as out of scope.

## 10. Decision

- Decision: `Option D：只完成 M3-1，不足以进入 M4。`

### Why

- `M3-1` is complete and real.
- Core skills are implemented and tested, but they are not yet M3-certified as one strict production-grade DAG contract system.
- `M3-3`, `M3-4`, `M3-6`, and `M3-7` are incomplete or not started.
- The biggest immediate blocker is not test failure; it is contract completeness:
  - degraded semantics are heuristic
  - comprehensive-to-advice contract is partial
  - profile evidence/citation grounding is absent
  - production repository integration is incomplete

## 11. Recommended Next PR

- Recommended next PR package:
  - `M3 completion gate: normalize profile contracts, finish comprehensive->advice contract, lock production data access, and add profile regression/acceptance`

### Why this should be one big package instead of many tiny PRs

- The main blockers are coupled:
  - output contract normalization
  - downstream contract completion
  - production data-source truth
  - evidence contract
  - regression gate
- Fixing them separately risks temporarily “green but misleading” states where:
  - the DAG works
  - the tests stay green
  - but the real M3 contract is still incomplete

### Suggested contents of that PR

- unify profile skill terminal status/degraded contract
- make `comprehensive` emit the exact downstream advisory contract it claims to provide
- back profile data access with the intended production repository boundary
- define and implement a profile evidence contract:
  - user-data evidence
  - risk-domain evidence
  - optional citation/evidence trace seam
- add a dedicated profile regression/acceptance gate that proves the real inter-skill contract, not only isolated module behavior
