# Pre-M3 Eval Regression + M2C Essential Semantic Validator + Release Gate Contract

## Status

Current phase:

> `PR-C Eval Regression + M2C Essential Semantic Validator + Release Gate implementation in progress`

This contract defines the runtime boundary for PR-C2 after PR-C1 docs-only planning was merged.

## 1. Goal

PR-C2 closes the final Pre-M3 production gate before M3 runtime work by adding:

- Risk QA regression over the existing PR-A runtime path
- deterministic SQL semantic validation over the existing Data Agent planning / review path
- a Pre-M3 release gate that aggregates readiness checks into a structured decision
- release / rollback runbook support

PR-C2 does not start M3 runtime work and does not reopen PR-A or PR-B architecture.

## 2. Risk QA Regression Boundary

The canonical PR-C Risk QA regression logic extends:

- `app/risk_knowledge/evaluation`

It does not introduce:

- `app/evaluation`
- LLM-as-judge answer scoring
- a second public Risk QA route

Risk QA regression must evaluate the existing public runtime surfaces only:

- orchestrator intent: `risk_knowledge_answer`
- public facade: `RiskKnowledgeService.answer()`
- trace seam: `RiskKnowledgeService.answer_with_trace()`

## 3. Risk QA Golden Set Case Contract

PR-C extends the existing golden-set contract additively for PR-A regression needs.

Each PR-C Risk QA case must support at least:

- `case_id`
- `query`
- `kb_id`
- `expected_route`
- `expected_grounding_status`
- `expected_refusal`
- `required_evidence_keywords`
- `forbidden_source_types`
- `min_citation_count`
- `must_include_warning_codes`
- `notes`

The runtime evaluator must not require exact natural-language answer matching.

Acceptance is based on:

- route correctness
- grounding status correctness
- refusal correctness
- evidence-source correctness
- citation validity
- context isolation

## 4. Risk QA Regression Metrics

PR-C must report at least:

- `retrieval_hit_rate`
- `citation_validity_rate`
- `grounded_answer_rate`
- `insufficient_evidence_refusal_rate`
- `context_isolation_pass_rate`

Hard production-oriented thresholds:

- `citation_validity_rate = 100%`
- `context_isolation_pass_rate = 100%`

PR-C may keep some thresholds advisory during PR acceptance mode, but release-gate production mode must treat hard-threshold violations as blocking.

## 5. Context Isolation And Citation Contract

Risk QA regression must prove that `risk_knowledge_answer` remains isolated from:

- `data_knowledge`
- SQL examples
- approved SQL artifacts
- catalog-grounding sources
- memory-as-authority

Grounded Risk QA output may cite only selected `risk_domain_knowledge` evidence.

The regression layer must fail closed when:

- citations point to non-selected evidence
- citations reference forbidden source types
- grounded conclusions are returned without valid citation coverage

## 6. SQL Semantic Validator Boundary

The canonical PR-C SQL semantic validator lives under:

- `app/data_agent/semantic_validation`

It is:

- deterministic
- structured
- runtime-owned

It is not:

- prompt-only
- LLM self-judgment
- a replacement for the current execution permission model
- a bypass around existing HITL approval / execution confirmation
- a simple overload of `run_sql_safety_gate`

## 7. SQL Semantic Validator Input Contract

The semantic validator request must support at least:

- `query`
- `sql`
- `structured_sql_plan`
- `business_context`
- `expected_country`
- `expected_uid_scope`
- `expected_time_window`
- `allowed_tables`
- `canonical_field_policy_refs`

`structured_sql_plan` is the preferred primary input.

Raw SQL may be used as fallback context, but the validator must not rely only on keyword scanning.

## 8. SQL Semantic Validator Output Contract

Top-level output fields:

- `validation_status`
- `violations`
- `requires_human_review`

Allowed `validation_status` values:

- `passed`
- `blocked`
- `warning`
- `needs_human_review`

Each violation must include:

- `code`
- `severity`
- `message`
- `field`
- `table`
- `suggestion`
- `blocking`

## 9. Required Validator Families

PR-C must implement deterministic checks for:

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

## 10. Data Agent Integration Boundary

The semantic validator runs after existing planning / review seams are available, including:

- `structured_sql_plan`
- deterministic plan review output
- existing safety gate inputs

Required semantics:

- `blocked` SQL must not become executable or approvable
- `needs_human_review` SQL must remain inside existing HITL
- `passed` SQL becomes eligible for the existing approval / confirmation path only

PR-C must not:

- auto-execute SQL after semantic validation
- bypass the current SQL approval model
- bypass `approved_sql` / `approved_by` governance

## 11. Release Gate Boundary

The authoritative runtime entrypoint is:

- `python -m app.release.pre_m3_gate`

The canonical package lives under:

- `app/release`

Future `scripts/` wrappers are optional and must remain thin delegators.

The release gate aggregates readiness evidence but does not replace `pytest` as the source of test-execution truth.

## 12. Release Gate Report Contract

The release gate report must include at least:

- `release_gate_status`
- `checks`
- `failed_checks`
- `warnings`
- `recommendation`

Each check result must support:

- `check_name`
- `category`
- `status`
- `summary`
- `blocking`
- `details`

## 13. Release Gate Status Semantics

Allowed release-gate statuses:

- `PASS`
- `WARN`
- `FAIL`
- `BLOCKED`

Interpretation:

- `PASS`: all required checks passed
- `WARN`: non-blocking checks failed or evidence is incomplete for PR acceptance mode
- `FAIL`: required runtime checks failed
- `BLOCKED`: production release must not proceed

## 14. Full Regression Policy

`full repository regression not run` must be treated as:

- `WARN` for PR acceptance
- `BLOCKED` for production release

This policy must be encoded in the release-gate decision layer rather than left as documentation only.

## 15. Runbook Requirement

PR-C must add:

- `docs/runbooks/pre-m3-release-gate-runbook.md`

The runbook must cover:

- Risk QA regression execution
- SQL semantic validator execution
- worker health verification
- manifest activation verification
- stale / failed job handling
- rollback procedure
- confirmation that Data Agent HITL boundaries remain intact

## 16. Out Of Scope

PR-C does not include:

- M3 Profile DAG runtime
- LangGraph migration
- PR-A Risk QA rewrite
- PR-B worker rewrite
- dashboard rewrite
- SSE / WebSocket
- Data Agent HITL bypass
- LLM-as-judge semantic validator
