# Post-Decomposition Quality Backlog

## Current Baseline

- `agent_loop.py` decomposition complete.
- `Phase 6` and `Phase 7` are complete.
- `S3 Runtime Observability & Trace Quality` is complete, with internal trace metadata landing on `ExecutionTraceRecord.internal_metadata`.
- The current orchestrator is a LangGraph-ready thin shell, not a LangGraph-migrated or multi-agent runtime.
- Post-decomposition work now moves from decomposition to quality backlog planning.
- This phase does not continue splitting orchestrator runtime code.

## Priority Order

1. `D1 Data Agent / Text-to-SQL Quality`
2. `P1 Profile Quality & Review Refinement`
3. `M1 Memory Quality`
4. `LG-0 LangGraph Feasibility Spike`

## D1 Data Agent / Text-to-SQL Quality

Audit surfaces:

- `app/services/orchestrator_agent/execution/data_query_runner.py`
- `app/services/orchestrator_agent/flows/query_data_then_profile.py`
- `app/services/orchestrator_agent/tools` and other query-data related modules
- `tests/orchestrator_agent/test_data_query_runner.py`
- `tests/orchestrator_agent/test_refactor_baseline.py`
- `tests/test_orchestrator_visible_execution.py`

Priority notes:

- `D1.1` and `D1.4` form the first-priority group.
- The recommended first execution slice is `D1-0 + D1.1`, with `D1.4` guard audit in parallel.
- S5 does not implement any D1 item.

### D1-0 Current State Audit

Scope:

- Document the current `QueryDataInput` contract, preview shape, ACK semantics, empty/too-large cohort handling, safety guard location, fake-vs-real Data Agent parity, and flow ownership across query-only, query-profile, and query-repair.

Out of Scope:

- No runtime behavior changes.
- No SQL guard changes.
- No event or payload changes.

Tests:

- Audit-by-reference against current unit, baseline, and visible execution tests.
- Add no new runtime tests in S5.

Acceptance:

- Backlog doc clearly captures current state, known issues, and candidate improvements for query execution.

### D1.1 Query Request Normalization

Scope:

- Normalize time windows, user filters, market/country hints, auto-profile intent, and the distinction between query-only vs query-profile.
- Define clearer `query_request` explainability fields for future implementation planning.

Out of Scope:

- No changes to `QueryDataRunner`.
- No schema change to `query_data` tool args during S5.

Tests:

- Future unit tests for normalized request parsing.
- Future baseline tests for query-only and query-profile routing.
- Future visible execution tests to confirm event order remains stable.

Acceptance:

- Every normalization sub-item has target inputs, expected normalized request shape, intended execution behavior, and named test surfaces.

### D1.4 SQL Safety / Audit

Scope:

- Plan read-only enforcement, forbidden keyword guard, table allowlist/denylist review, limit enforcement, approved SQL audit trace, and safety-focused test coverage.

Out of Scope:

- No direct SQL executor rewrite.
- No ACK contract changes.
- No bypass of `DataQueryRunner`.

Tests:

- Future unit tests for read-only / forbidden-keyword blocking.
- Future runner tests for limit enforcement and dangerous-query rejection.
- Future visible execution tests to confirm blocked/fail behavior remains compatible.

Acceptance:

- Dangerous SQL classes, guard locations, and expected blocked/fail outcomes are explicitly documented.

### D1.3 empty / too-large cohort UX

Scope:

- Plan better empty-cohort messaging, adjustment suggestions, too-large guidance, optional threshold configurability review, and distinct handling between query-only and query-profile outcomes.

Out of Scope:

- No current threshold changes in S5.
- No frontend reducer changes.

Tests:

- Future baseline tests for empty, too-large, and query-only vs query-profile outcomes.
- Future visible execution tests to confirm step/event shape remains stable.

Acceptance:

- Empty cohort remains non-error.
- Too-large cohort remains blocked/fail.
- Planned messaging improvements are documented without changing current public contract.

### D1.2 SQL Preview Explainability

Scope:

- Plan preview summary, filter explanation, risk/cost warnings, expected cohort description, and ACK prompt readability improvements.

Out of Scope:

- No automatic execution.
- No ACK bypass.
- No `awaiting_user_ack` schema changes.

Tests:

- Future visible execution tests for unchanged ACK event shape.
- Future baseline tests for improved preview-facing copy behavior.

Acceptance:

- Planned preview improvements are documented with compatibility constraints preserved.

### D1.5 Vanna Integration Spike

Scope:

- Evaluate whether Vanna could act as an optional SQL generation candidate, how it fits MySQL/schema sources, and whether existing ACK preview plus safety guard semantics could be preserved.

Out of Scope:

- No production replacement of `DataQueryRunner`.
- No change to `QueryDataThenProfileFlow`.
- No Vanna dependency on the main runtime path.

Tests:

- Future spike validation only.
- No production test expansion in S5.

Acceptance:

- Backlog records expected spike questions, adoption criteria, migration cost, and go/no-go output expectations.

## P1 Profile Quality & Review Refinement

Audit surfaces:

- `app/services/orchestrator_agent/flows/profile.py`
- `app/services/orchestrator_agent/execution/profile_runner.py`
- `app/services/orchestrator_agent/review`
- `app/services/orchestrator_agent/finalization`
- `tests/orchestrator_agent/test_profile_runner.py`
- `tests/orchestrator_agent/test_refactor_baseline.py`
- `tests/test_orchestrator_visible_execution.py`

### P1.1 Partial / Blocked Final Message Refinement

Scope:

- Plan clearer final-message templates for `partial_unavailable`, `blocked_unavailable`, repair-after-partial warnings, capability unavailable messaging, and unsupported-country messaging.

Out of Scope:

- No `review_result.status` changes.
- No visible execution schema changes.
- No assistant-message count changes.

Tests:

- Future baseline tests for partial, blocked, and repair-adjacent final copy.
- Future visible execution tests to confirm final emission count and event order stay stable.

Acceptance:

- Final-message refinement targets are documented without breaking current review/final contract.

### P1.2 Review Issue Schema Stabilization

Scope:

- Define an issue type registry, severity guidance, confidence-impact guidance, and blocked-vs-warning separation.

Out of Scope:

- No breaking `review_result` schema changes.
- No deletion of existing issue types.
- No semantic redefinition of existing issue fields.

Tests:

- Future schema compatibility tests.
- Future frontend compatibility tests for additive issue types.
- Future baseline tests for stabilized issue payloads.

Acceptance:

- Compatibility rules are explicit: additive only, no issue removal, no semantic breakage, unknown issue types must remain frontend-safe.

### P1.4 Repair UX Refinement

Scope:

- Plan better repair ACK messaging, non-approved/cancelled messaging, repair-failed terminal copy, post-repair partial warnings, and clearer alignment between internal repair metadata and final user-facing copy.

Out of Scope:

- No ACK event shape changes.
- No change to cancel semantics.
- No runner ownership changes.

Tests:

- Future baseline and visible execution tests for approved, rejected, expired, cancelled, failed, and post-repair partial paths.
- Future cleanup tests for `pending_ack` and `ToolCallRecord` terminal states.

Acceptance:

- Repair UX backlog covers the full repair lifecycle while preserving existing HITL and terminal semantics.

### P1.3 Batch Profile Grouping Explainability

Scope:

- Plan batch grouping summaries, per-module coverage summaries, per-UID partial reason summaries, and frontend module-status alignment guidance.

Out of Scope:

- No change to `execution_groups`.
- No visible execution shape changes.

Tests:

- Future batch baseline tests.
- Future frontend rendering compatibility tests where needed.

Acceptance:

- Backlog clearly defines how batch coverage should become easier to understand without rewriting grouping logic.

## M1 Memory Quality

Audit surfaces:

- `app/services/orchestrator_agent/flows/general_chat.py`
- memory-related runtime modules
- `app/services/orchestrator_agent/agent_loop.py` via `_build_memory_facade`
- `tests/orchestrator_agent/test_agent_loop_memory_sqlite.py`
- `tests/orchestrator_agent/test_refactor_baseline.py`

Cross-cutting boundary:

- Memory work must respect privacy and sensitive-data boundaries.
- `memory_write` should not store sensitive or transient content unless the user explicitly asks.
- Memory scope metadata must remain internal-only.
- Memory scope details must not leak to SSE, frontend payloads, or public responses.

### M1.1 Scope / Isolation Hardening

Scope:

- Plan `user_id`, `project_id`, and country fallback isolation tests, including cross-session read/write boundaries and scope documentation.

Out of Scope:

- No storage backend replacement.
- No scope model redesign in S5.

Tests:

- Future `memory_sqlite` isolation and cross-session tests.
- Future regression tests for country fallback behavior.

Acceptance:

- Isolation guarantees and missing-test areas are documented with clear follow-up items.

### M1.2 memory_write Content Classification

Scope:

- Plan write-intent classification, sensitive/transient filtering, duplicate handling, and confirmation consistency.

Out of Scope:

- No prompt or tool contract change in S5.
- No direct-final policy change during this phase.

Tests:

- Future tests for explicit-write prompts vs ordinary chat.
- Future sensitive-content and duplicate-filter tests.

Acceptance:

- Backlog clearly defines when memory should be written and when it should not.

### M1.3 memory_read Ranking / Summarization

Scope:

- Plan recency ranking, relevance ranking, empty-result messaging, multi-memory summarization, and context-fit handling.

Out of Scope:

- No retrieval backend replacement.
- No public response shape changes.

Tests:

- Future retrieval ranking tests.
- Future empty-result and multi-result continuation tests.

Acceptance:

- Backlog defines how memory recall quality should improve while keeping current runtime boundaries intact.

### M1.4 Memory Observability

Scope:

- Plan internal-only metadata for `memory_operation`, result counts, scope diagnostics, and terminal reasons.

Out of Scope:

- No SSE exposure.
- No public response exposure.
- No new observability framework.

Tests:

- Future internal metadata tests only.
- Future leakage checks to ensure memory diagnostics stay internal.

Acceptance:

- Observability follow-up stays aligned with the S3 internal-only metadata rule.

## LG-0 LangGraph Feasibility Spike

This is spike-only work. It is not a migration plan.

Future deliverable:

- `docs/spikes/langgraph-feasibility.md`

S5 does not create that spike report.

### LG-0.1 Graph State Mapping

Scope:

- Plan a draft graph state that can represent `FlowContext`, normalized request state, session/run identifiers, pending ACK/resolution state, trace state, and terminal outcome state.

Out of Scope:

- No actual LangGraph runtime execution.
- No production state migration.

Tests:

- Future design review only.

Acceptance:

- The backlog states what must map cleanly before any prototype begins.

### LG-0.2 ProfileFlow No-Repair Success Prototype

Scope:

- Plan a minimal prototype around the simplest `ProfileFlow` success path: single UID, `mx`, capability enabled, data available, no repair.

Out of Scope:

- No `uid_file`.
- No repair.
- No query-data bridge.
- No production path wiring.

Tests:

- Future isolated spike validation only.

Acceptance:

- Prototype target is narrowly defined and intentionally disconnected from production ownership.

### LG-0.3 Checkpoint / Resume Assessment

Scope:

- Evaluate whether checkpoint/resume semantics would actually simplify `pending_ack`, repair ACK, query ACK, clarification resume, and cancel handling.

Out of Scope:

- No checkpoint implementation.
- No session-store rewrite.

Tests:

- Future spike analysis only.

Acceptance:

- Backlog defines the decision questions needed to judge checkpoint value vs migration cost.

### LG-0.4 Decision Report

Scope:

- Plan a future decision report covering feasibility, benefits, cost, risks, and recommendation: reject, limited pilot, or formal planning.

Out of Scope:

- No go-live migration path.
- No production dependency addition.

Tests:

- Future spike review only.

Acceptance:

- The backlog specifies the output format and the required go/no-go conclusion.

## Cross-Cutting Constraints

- No public API changes.
- No SSE event type or payload shape changes.
- No frontend reducer/input shape changes.
- No new multi-agent architecture.
- No production LangGraph migration in this backlog phase.
- No direct Vanna replacement in this backlog phase.
- No movement of already-owned flow logic back into `agent_loop.py`.
- Security, privacy, and internal-only observability boundaries remain mandatory.

## Regression Requirements

- Future D1 work should cover unit, baseline, visible execution, and safety-focused tests.
- Future P1 work should cover baseline, visible execution, and frontend compatibility where issue rendering is affected.
- Future M1 work should extend `memory_sqlite` isolation and retrieval tests and preserve general-chat compatibility.
- Future LG-0 work should stay isolated from production regression gates until a separate migration plan exists.
- Any future route that changes active behavior must keep `PLANNING.md`, `TASK.md`, and relevant design/plan docs in sync.

## Out of Scope

- S5 does not implement D1, P1, M1, or LG-0.
- S5 does not modify `DataQueryRunner`, `ProfileFlow`, `GeneralChatFlow`, or memory runtime behavior.
- S5 does not add LangGraph to the production dependency path.
- S5 does not change public API, SSE schema, frontend shape, or baseline runtime semantics.

## Recommended Next Phase

- Recommended next execution phase: `D1 Data Agent / Text-to-SQL Quality`
- Recommended first slice: `D1-0 + D1.1`
- Run `D1.4 SQL Safety / Audit` guard audit in parallel with the first D1 slice.
- Do not start with Vanna replacement or LangGraph migration.
