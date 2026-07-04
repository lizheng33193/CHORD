# Pre-M3 PR-C Eval Regression + M2C Essential Semantic Validator + Release Gate Plan

## 1. Summary

- Status for this PR:
  - `Approved for PR-C1 docs-only planning execution.`
  - `Runtime implementation must not start in PR-C1.`
- PR-C is the final Pre-M3 production gate after PR-A Risk QA and PR-B Indexing Worker.
- PR-C plans:
  - Risk QA regression
  - context-isolation regression
  - citation-grounding regression
  - M2C essential SQL semantic validation
  - Pre-M3 release gate
  - release / rollback runbook requirements
- PR-C must reuse existing harness seams rather than introduce a new general-purpose eval platform.

## 2. Baseline And Branch Boundary

- Fixed baseline for this planning PR:
  - latest `main` after the PR-B docs-only follow-up landed as commit `09ce55b`
  - `origin/main` previously pointed to `deed80f` for `PR #56`; PR-B acceptance docs follow-up was merged into `main` before PR-C1 planning began
  - `49f32c9` was the PR-B docs-only follow-up commit on `codex/pre-m3-indexing-worker-runtime` and is now reconciled into `main`
- PR-C1 execution branch:
  - `codex/pre-m3-eval-semantic-release-gate`
- PR-C1 may modify only:
  - `docs/plans/pre-m3-eval-semantic-release-gate-plan.md`
  - `docs/reviews/pre-m3-eval-semantic-release-gate-acceptance-review.md`
  - `PLANNING.md`
  - `TASK.md`
- PR-C1 must not modify:
  - `app/`
  - `tests/`
  - `scripts/`
  - `migrations/`
  - `docs/runbooks/`

## 3. Current Main Truth After PR-A And PR-B

- `PR-A Risk QA + Context Isolation + Evidence/Citation Production Gate` remains:
  - `implemented; pending final acceptance`
  - runtime landed via `PR #53`
  - public route and facade remain `risk_knowledge_answer` and `RiskKnowledgeService`
- `PR-B Indexing Worker + Job Observability Gate` remains:
  - `implemented; pending final acceptance`
  - planning landed via `PR #55`
  - runtime landed via `PR #56`
  - docs-only follow-up now reconciled onto `main`
- Current `main` already contains:
  - Risk QA runtime gate behavior
  - external-worker-first indexing facades
  - manifest activation / rollback facade
  - worker health surface
  - targeted PR-A and PR-B runtime test coverage on their respective branches
- What is still missing before Pre-M3 production readiness:
  - repeatable PR-A regression evidence
  - deterministic SQL semantic validation as an independent runtime gate
  - a single release-gate decision point that aggregates readiness signals

## 4. Scope

- Extend existing `app/risk_knowledge/evaluation/` seams for PR-A regression.
- Plan a deterministic SQL semantic validator under `app/data_agent/semantic_validation/`.
- Plan a formal release gate under `app/release/` with entrypoint `python -m app.release.pre_m3_gate`.
- Define runtime contracts, runtime test plan, acceptance criteria, and no-go criteria for PR-C2.
- Define release / rollback runbook requirements for PR-C2 runtime implementation.

## 5. Explicit Out Of Scope

- runtime implementation in this PR
- changes under `app/`, `tests/`, `scripts/`, `migrations/`, or `docs/runbooks/`
- M3 Profile Skill DAG runtime work
- LangGraph migration
- full Memory Platform
- SSE / WebSocket
- full dashboard or observability platform work
- Data Agent rewrite
- PR-A Risk QA rewrite
- PR-B worker rewrite
- release gate implementation
- SQL semantic validator implementation
- runtime test execution beyond `git diff --check`

## 6. Selected Approach

### 6.1 Additive Reuse Of Existing Harness Seams

- PR-C extends existing harness boundaries instead of introducing a new top-level eval subsystem.
- Risk QA regression extends the current `RiskKnowledgeService` / `risk_knowledge_answer` runtime truth rather than replacing it.
- SQL semantic validation is added as a dedicated deterministic gate rather than folded into prompt logic or existing safety scanning.
- Release gate aggregates existing and future checks into an application-level production decision point.

### 6.2 Risk QA Eval Under `app/risk_knowledge/evaluation`

- PR-C extends `app/risk_knowledge/evaluation/`.
- PR-C does not introduce `app/evaluation/`.
- Risk QA regression does not require exact natural-language answer matching.
- Regression must validate:
  - route selection
  - grounding status
  - evidence source correctness
  - citation validity
  - refusal behavior for insufficient evidence
  - context isolation from Data Agent / SQL example knowledge

### 6.3 SQL Semantic Validator Under `app/data_agent/semantic_validation`

- PR-C plans a dedicated deterministic semantic-validation module under `app/data_agent/semantic_validation/`.
- The semantic validator:
  - is deterministic and structured
  - is not prompt-only
  - is not LLM self-judgment
  - must not be collapsed into `run_sql_safety_gate`
  - should prefer `structured_sql_plan` as primary input
  - may use raw SQL as fallback context, but must not rely on keyword scanning alone
  - runs after existing planning / review seams are available
  - must not change SQL execution permissions
  - must not bypass existing HITL confirmation

### 6.4 Release Gate Under `app/release`

- Formal runtime entrypoint:
  - `python -m app.release.pre_m3_gate`
- `scripts/` is not the authoritative runtime boundary.
- A future script wrapper is optional and must remain a thin wrapper that delegates to `app.release.pre_m3_gate`.
- The release gate aggregates check results and emits a structured report.
- The release gate does not replace `pytest` as the source of test-execution truth.

## 7. Risk QA Regression Plan

### 7.1 Golden Set Case Schema

- Minimum planned case fields:
  - `case_id`
  - `question`
  - `expected_route`
  - `expected_grounding_status`
  - `expected_refusal`
  - `required_evidence_keywords`
  - `forbidden_source_types`
  - `min_citation_count`
  - `must_include_warning_codes`
  - `notes`
- Case categories should cover:
  - grounded concept explanation
  - risk-cause analysis
  - overdue / fraud / multi-loan / collection / post-loan topics
  - evidence-required questions
  - insufficient-evidence refusal cases
  - Data Agent confusion boundary cases
  - SQL confusion boundary cases

### 7.2 Grounding / Refusal / Citation Expectations

- PR-C regression validates:
  - only risk-domain evidence is eligible for grounded citations
  - citation references remain valid and traceable to selected evidence
  - insufficient evidence triggers refusal rather than unsupported answer generation
  - Data Agent knowledge, SQL examples, and approved SQL sources must not appear as Risk QA evidence

### 7.3 Context Isolation Regression

- Context-isolation regression must prove that `risk_knowledge_answer` does not mix:
  - Data Agent table grounding
  - SQL example retrieval
  - approved SQL sources
  - general chat fallback content that bypasses Risk QA evidence boundaries

### 7.4 Metrics And Thresholds

- Minimum metrics to plan:
  - retrieval hit rate
  - citation validity rate
  - grounded answer rate
  - insufficient-evidence refusal rate
  - context-isolation pass rate
- Minimum threshold posture to plan:
  - citation validity target: `100%`
  - context-isolation pass target: `100%`
  - insufficient-evidence refusal target: high-confidence threshold with explicit runtime acceptance floor
- Full metric and threshold values must be finalized in the PR-C2 contract spec before code changes.

## 8. M2C Essential SQL Semantic Validator Plan

### 8.1 Validator Input Contract

- Planned semantic-validator input fields:
  - `query`
  - `sql`
  - `structured_sql_plan`
  - `business_context`
  - `expected_country`
  - `expected_uid_scope`
  - `expected_time_window`
  - `allowed_tables`
  - `canonical_field_policy_refs`

### 8.2 Validator Output Contract

- Top-level output fields:
  - `validation_status`: `passed | blocked | warning | needs_human_review`
  - `violations`
  - `requires_human_review`
- Each violation must include:
  - `code`
  - `severity`
  - `message`
  - `field`
  - `table`
  - `suggestion`
  - `blocking`

### 8.3 Validator List

- Required validator coverage:
  - Country Scope
  - UID Boundary
  - Time Window
  - Partition vs Business Time
  - Join Key
  - Table Grain
  - Metric Definition
  - Writeback Boundary
  - Broad Scan
  - Risky SQL Operation

### 8.4 Data Agent Integration Boundary

- Semantic validation runs after existing planning / review seams are available, including `structured_sql_plan` and deterministic review outputs.
- Semantic validation is a pre-execution semantic gate only.
- `blocked` SQL must not become executable or approvable.
- `needs_human_review` SQL remains inside the existing HITL path.
- `passed` SQL becomes eligible for the existing confirmation / approval path only; validator success does not grant execution authority by itself.

## 9. Release Gate Plan

### 9.1 Formal Entrypoint

- Formal runtime entrypoint:
  - `python -m app.release.pre_m3_gate`

### 9.2 Release Gate Report Contract

- Planned report fields:
  - `release_gate_status`
  - `checks`
  - `failed_checks`
  - `warnings`
  - `recommendation`
- Planned check categories:
  - Risk QA regression
  - context isolation
  - citation grounding
  - indexing worker health
  - manifest activation / rollback smoke
  - SQL semantic validator coverage
  - configuration safety defaults
  - full regression posture

### 9.3 PASS / WARN / FAIL / BLOCKED Semantics

- `PASS`:
  - all required checks passed
- `WARN`:
  - non-blocking checks failed or required production evidence is incomplete for PR acceptance mode
- `FAIL`:
  - required runtime checks failed
- `BLOCKED`:
  - production release must not proceed

### 9.4 Full Regression Policy

- `full repository regression not run` must be treated as:
  - `WARN` for PR acceptance
  - `BLOCKED` for production release

## 10. Release / Rollback Runbook Requirements

- PR-C2 must add a dedicated runbook at:
  - `docs/runbooks/pre-m3-release-gate-runbook.md`
- Planned runbook content:
  - how to run Risk QA regression
  - how to run SQL semantic validation
  - how to inspect worker health
  - how to verify active manifest state
  - how to retry failed indexing jobs
  - how to handle stale jobs
  - how to roll back manifest activation
  - how to verify in-process fallback remains disabled unless explicitly required
  - how to confirm Data Agent HITL boundaries remain intact

## 11. Runtime Spec Requirement

- PR-C2 must add or update a dedicated contract spec before code changes:
  - `docs/specs/pre-m3-eval-semantic-release-gate-contract.md`
- That spec must lock:
  - Risk QA eval case schema
  - SQL semantic validation result contract
  - release gate report contract
  - release gate status semantics
  - Data Agent integration boundary

## 12. Runtime Test Plan

- Planned targeted runtime verification for PR-C2:
  - Risk QA evaluation tests
  - citation validation and context-isolation tests
  - SQL semantic validator tests by validator family
  - release-gate aggregation and status-semantics tests
  - PR-A non-regression checks
  - PR-B non-regression checks
  - `python -m compileall -q app tests`
  - `git diff --check`
- The release gate may aggregate test outcomes and smoke-check outputs, but it must not replace `pytest` as execution truth.

## 13. Acceptance Criteria

- PR-C1 acceptance requires:
  - explicit baseline and branch boundary
  - explicit scope and non-scope
  - fixed additive-reuse architecture decisions
  - fixed Risk QA regression boundary
  - fixed SQL semantic validator boundary
  - fixed release-gate boundary and status semantics
  - explicit PR-C2 runtime spec requirement
  - no runtime behavior changes in this PR

## 14. No-Go Criteria

- PR-C1 must not be accepted if:
  - planning starts before PR-B docs-only follow-up reaches `main`
  - files outside the four allowed docs/status files are changed
  - runtime implementation language appears in PR-C1 status
  - release gate, validator, or runbook is implemented in this PR
  - runtime tests are executed in this PR
  - the plan reopens PR-A or PR-B runtime scope
  - the plan expands into M3, LangGraph migration, Memory Platform, dashboard rewrite, or Data Agent rewrite

## 15. Known Limitations

- PR-C1 is docs-only and does not change runtime behavior.
- PR-C1 does not add the PR-C2 spec, runtime module skeletons, tests, or runbook.
- Full repository regression is not part of this PR-C1 planning PR.
- Final threshold values and exact runtime report shapes remain to be fixed in the PR-C2 contract spec before implementation.

## 16. Implementation Readiness Decision

- Decision for this PR:
  - `PR-C Eval Regression + M2C Essential Semantic Validator + Release Gate planned; implementation not started`
- PR-C2 runtime implementation may begin only after:
  - PR-C1 planning is accepted and merged
  - the dedicated PR-C2 contract spec is added or updated before code changes
