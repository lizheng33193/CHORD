# M4-4 Memory Promotion Policy

## Purpose

M4-4 closes the scoped M4 governance surface by defining promotion
eligibility.

This stage exists to answer:

- which memory source types may promote into which higher-order targets
- which paths are always blocked even if a memory record exists
- which targets remain candidate-only and still require later governance
- how M4 can be accepted without introducing automatic promotion execution

## Scope

- `MemoryPromotionTarget`
- `MemoryPromotionStatus`
- `MemoryPromotionBlockReason`
- `MemoryPromotionRequest`
- `MemoryPromotionDecision`
- `promotion_request_from_candidate(...)`
- `promotion_request_from_retrieved_item(...)`
- `validate_memory_promotion(...)`
- focused promotion policy tests
- M4 scoped acceptance closure docs

## Non-Goals

- no automatic promotion execution
- no Data Knowledge ingestion
- no Risk Knowledge ingestion
- no SQL example table writes
- no golden set writes
- no production policy writes
- no orchestrator runtime integration
- no vector memory
- no embedding retrieval
- no dashboard

## Contracts

`MemoryPromotionTarget` is intentionally separate from `MemoryUsePurpose`.

`MemoryUsePurpose` answers:

- how an existing memory record may be used at runtime

`MemoryPromotionTarget` answers:

- whether that memory record is eligible to become a higher-order candidate

`MemoryPromotionDecision.allowed=True` means only:

- this memory is eligible as a promotion candidate

It must not be interpreted as:

- knowledge ingestion already executed
- production policy already approved
- SQL example already published
- HITL / safety / governance already bypassed

## Promotion Boundary

Locked targets:

- `profile_history`
- `risk_qa_history`
- `sql_case`
- `sql_error_case`
- `eval_candidate`
- `approved_sql_example`
- `risk_knowledge_source_document`
- `risk_knowledge_document_evidence`
- `data_knowledge_authority`
- `approved_strategy_policy`
- `safety_policy`
- `hitl_bypass_policy`

Locked allow matrix:

- `profile_result -> profile_history`
- `risk_qa_answer -> risk_qa_history`
- `risk_qa_answer -> eval_candidate` only when evidence is grounded / reviewed
- `data_agent_sql_case -> sql_case` only when `human_approved`
- `data_agent_sql_case -> approved_sql_example` only when `human_approved` and `approved_sql_hash` exists
- `data_agent_sql_error -> sql_error_case`
- `data_agent_sql_error -> eval_candidate`
- `audit_event -> eval_candidate` as governance/evaluation candidate only
- `eval_case -> eval_candidate`

Locked blocked boundary:

- `profile_result` must not promote into Data / Risk / strategy / safety authority paths
- `risk_qa_answer` must not promote into Risk Knowledge source-document authority
- `data_agent_sql_error` must not promote into approved SQL examples
- `user_preference` must not promote into safety / HITL / authority / strategy targets
- `conversation` must not promote into authority / knowledge / policy targets
- `audit_event` must not promote into knowledge-source or policy targets

## Governance Interpretation

Some targets may return `allowed=True` while still requiring later governance.

`approved_sql_example` is the canonical example:

- `allowed=True` means only `eligible as approved_sql_example candidate`
- the decision reason must still say `requires governance ingestion`

Dangerous authority targets remain blocked in this stage rather than becoming
candidate paths.

## Stage Status

- `M4-1 Memory Type & Isolation Contract: completed`
- `M4-2 Memory Write Gate & Store Metadata: completed`
- `M4-3 Memory Retrieval Boundary & Context Injection: completed`
- `M4-4 Memory Promotion Policy & Acceptance Closure: implemented / pending acceptance`
- `M4 Unified Memory & Memory Isolation: pending M4-4 acceptance`
- `M5 Eval / Regression Platform: next`
