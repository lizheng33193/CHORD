# Pre-M3 Risk QA Production Gate Acceptance Review

## Acceptance Decision

PR-A is implemented and ready for final review.

The implementation preserves the existing `risk_knowledge_answer` public path and `RiskKnowledgeService` facade while adding internal Risk QA pipeline modules for context isolation, evidence selection, sufficiency checking, answer generation, and citation validation.

The new gates are fail-closed:

- insufficient evidence returns a safe refusal before grounded answer generation
- invalid citations prevent grounded answers from being returned
- non-risk-domain sources are blocked from authoritative Risk QA citations

Targeted verification passed:

- 19 PR-A and non-regression tests passed
- `compileall` passed
- `git diff --check` passed

Known limitation:

- full repository regression was not run
- PR-B worker/observability, PR-C eval/semantic validator, and full M3 Profile Skill DAG remain out of scope

## Branch Boundary

GitHub verification shows the following merge history:

- `PR #51 feat: complete m2d15 production hardening` merged on `2026-07-04` and did not include the PR-A `qa/context/evidence` runtime files
- `PR #52 docs: reconcile m2d15 final status` merged on `2026-07-04` as docs-only reconciliation
- `PR #53 feat: add risk qa production gate` merged on `2026-07-04` and is the runtime landing point for PR-A

The current branch:

- `codex/pre-m3-risk-qa-production-gate`

is a post-merge docs and acceptance narrative reconciliation branch. PR-A must not be reviewed under the old `M2D-15 docs-only reconciliation` narrative.

## Implementation Summary

PR-A upgrades the existing `risk_knowledge_answer` route into a production-gated Risk QA flow while keeping public entrypoints stable.

Implemented changes:

- kept `risk_knowledge_answer` as the public orchestrator intent
- kept `RiskKnowledgeService.answer()` as the public facade
- added internal `qa/`, `context/`, and `evidence/manager.py` modules under `app/risk_knowledge`
- added additive answer metadata:
  - `schema_version`
  - `grounding_status`
  - `evidence_trace`
  - `retrieval_snapshot_id`
  - `blocked_context_sources`
  - `context_hash`
  - `warnings`
- enforced fail-closed sufficiency and citation validation
- persisted structured risk knowledge artifacts and trace metadata from `RiskKnowledgeAnswerFlow`

## Risk QA Route Acceptance

Accepted route behavior:

- explicit risk concept questions continue to route to `risk_knowledge_answer`
- SQL / cohort / workspace-follow-up requests continue to avoid the Risk QA path
- `RiskKnowledgeAnswerFlow` remains isolated from tool registry and Data Agent execution

## Context Isolation Acceptance

Accepted isolation behavior:

- `risk_knowledge_answer` allows `risk_domain_knowledge` only
- Risk QA blocks:
  - `data_knowledge`
  - `sql_examples`
  - `sql_error_cases`
  - `catalog_grounding`
  - `memory_as_authority`
- data-side context policy continues to block `risk_domain_knowledge_as_field_grounding`

## Evidence And Citation Acceptance

Accepted gate behavior:

- insufficient evidence is a pre-generation hard stop
- refusal path skips answer generation
- grounded answers require citation ids that resolve to selected evidence
- citation validation blocks non-selected or cross-source evidence
- additive evidence trace metadata is returned in the answer artifact

## Trace And Artifact Acceptance

Accepted trace metadata:

- `context_hash`
- `retrieval_snapshot_id`
- `selected_evidence_ids`
- `selected_chunk_ids`
- `blocked_context_sources`
- `grounding_status`
- `warning_codes`
- `citation_count`
- `evidence_count`

Accepted final artifact shape:

- `type = risk_knowledge_answer`
- `schema_version = risk_knowledge_answer.v1`
- structured citations
- structured evidence trace
- context isolation metadata

## Data Agent Non-Regression

This PR does not change:

- Data Agent execution flow
- SQL HITL lifecycle
- Data Knowledge prompt context behavior
- public Data Agent routes

Targeted non-regression checks for data-side prompt context still pass.

## Verification Results

Executed verification:

- `pytest tests/risk_knowledge/service/test_risk_knowledge_service.py tests/risk_knowledge/test_context_builder_isolation.py tests/risk_knowledge/test_citation_validation.py tests/orchestrator_agent/test_risk_knowledge_flow.py tests/data_knowledge/test_prompt_context.py tests/test_orchestrator_visible_execution.py::test_risk_knowledge_normalize_request_routes_explicit_risk_concept_question tests/test_orchestrator_visible_execution.py::test_risk_knowledge_normalize_request_does_not_steal_data_or_workspace_queries -q`
  - result: `19 passed`
- `python -m compileall -q app tests`
  - result: passed
- `git diff --check`
  - result: passed

## Final Acceptance Closure Attempt

Executed on `2026-07-04` from `codex/pre-m3-final-acceptance-closure`:

- `pytest -q`
  - result: `110 failed, 1462 passed, 11 skipped, 33 warnings`
- `python -m compileall -q app tests`
  - result: passed
- `git diff --check`
  - result: passed

Representative failing areas in the full-repository run included:

- `data_acquisition_agent/tests/test_api.py`
- `data_acquisition_agent/tests/test_api_v2.py`
- `data_acquisition_agent/tests/test_e2e_mock_executor.py`
- `tests/test_analyze_module_endpoint.py`
- `tests/test_orchestrator_chat_routes.py`

Acceptance outcome:

- PR-A remains `implemented; pending final acceptance`
- Pre-M3 acceptance is not closed
- Pre-M3 gates are not yet ready for M3 entry

## Known Limitations

- public route names remain `risk_knowledge_*` for compatibility; no naming migration is included in PR-A
- answer generation remains deterministic-first; no real LLM answer provider rollout is added here
- retrieval candidate normalization is still built on top of the current M2D retrieval/evidence stack rather than a new standalone retriever service
- warnings from third-party dependencies remain outside the scope of this PR
- full repository regression was run during final acceptance closure and failed

## Next Phase Dependencies

Future work can build on PR-A without reopening public compatibility:

- stronger partial-evidence answer shaping
- richer evaluation coverage for artifact metadata
- optional public API expansion for Risk QA artifacts
- later naming normalization only after production stabilization
