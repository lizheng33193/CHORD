# M5 Release Gate Policy

## Summary
- `M5-6` closes the shared eval platform by promoting `production_release` from smoke-only to the full deterministic M5 regression gate.
- `pr_acceptance` and `production_release` now reference the same ordered 7-suite list.
- `production_release` is strict-by-default and documented as strict-required for release-gate usage.

## Profiles
- `pr_acceptance`
  - purpose: PR regression profile
  - strict default: `false`
  - suites:
    - `release_gate_smoke`
    - `memory_governance`
    - `data_agent_sql_safety`
    - `data_agent_sql_grounding`
    - `risk_qa_groundedness`
    - `profile_dag_contract`
    - `profile_memory_snapshot`
- `production_release`
  - purpose: deterministic release-gate profile
  - strict default: `true`
  - suites:
    - `release_gate_smoke`
    - `memory_governance`
    - `data_agent_sql_safety`
    - `data_agent_sql_grounding`
    - `risk_qa_groundedness`
    - `profile_dag_contract`
    - `profile_memory_snapshot`

## Gate Semantics
- Effective strictness remains `args.strict or profile.strict_by_default`.
- All 7 suites are treated as blocking in `M5-6`.
- Shared runner exit behavior remains:
  - `0` for `PASS` or non-strict `WARN`
  - `1` for `FAIL`, `BLOCKED`, or strict `WARN`
  - `2` for runner configuration or execution errors
- `M5-6` does not add a new policy engine; it documents and validates current runner semantics.

## Preflight CLI
- `python -m app.eval.runner --list-suites`
  - prints current suite registry
  - exits `0`
  - does not execute evaluators
  - does not read case files
  - does not write reports or output directories
- `python -m app.eval.runner --list-profiles`
  - prints current profile registry and ordered suite lists
  - exits `0`
  - does not execute evaluators
  - does not read case files
  - does not write reports or output directories

## Report Contract
- Shared eval reports must surface:
  - `profile`
  - `strict`
  - `selected_suites`
  - `suite_summaries`
  - `suite_metrics`
  - `overall_status`
  - per-case warning and failure text
- `M5-6` only permits additive report readability fixes if verification reveals a real gap.

## Non-Goals
- No new domain eval suites.
- No Memory, Data Agent, Risk QA, or Profile DAG runtime changes.
- No dashboard, CI integration, online monitoring, LangGraph migration, or production deployment work.
- `M6` is not started in this phase.
