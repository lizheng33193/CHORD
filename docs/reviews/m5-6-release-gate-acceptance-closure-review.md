# M5-6 Release Gate & Acceptance Closure Review

## What Changed
- promoted `production_release` from smoke-only to the full deterministic 7-suite M5 release gate
- kept `pr_acceptance` on the same ordered 7-suite list
- added shared eval preflight CLI commands:
  - `python -m app.eval.runner --list-suites`
  - `python -m app.eval.runner --list-profiles`
- verified release-gate report fields remain sufficient without shared-foundation refactor

## Final Profile Definitions
- `pr_acceptance`
  - `release_gate_smoke`
  - `memory_governance`
  - `data_agent_sql_safety`
  - `data_agent_sql_grounding`
  - `risk_qa_groundedness`
  - `profile_dag_contract`
  - `profile_memory_snapshot`
- `production_release`
  - `release_gate_smoke`
  - `memory_governance`
  - `data_agent_sql_safety`
  - `data_agent_sql_grounding`
  - `risk_qa_groundedness`
  - `profile_dag_contract`
  - `profile_memory_snapshot`

## Guardrails Preserved
- no new domain suites
- no Memory, Data Agent, Risk QA, or Profile DAG runtime behavior changes
- no dashboard, CI integration, online monitoring, LangGraph migration, or production deployment work
- no evaluator/case/metric rewrites

## Verification
- final shared-eval profile results:
  - `python -m app.eval.runner --profile pr_acceptance --output-dir /tmp/m5_6_eval/pr_acceptance`
    - exit code: `0`
    - overall status: `WARN`
    - reports:
      - `/tmp/m5_6_eval/pr_acceptance/shared_eval_20260708T065051Z.json`
      - `/tmp/m5_6_eval/pr_acceptance/shared_eval_20260708T065051Z.md`
  - `python -m app.eval.runner --profile production_release --strict --output-dir /tmp/m5_6_eval/production_release`
    - exit code: `0`
    - overall status: `PASS`
    - reports:
      - `/tmp/m5_6_eval/production_release/shared_eval_20260708T065051Z.json`
      - `/tmp/m5_6_eval/production_release/shared_eval_20260708T065051Z.md`
- See `docs/reviews/m5-acceptance-closure.md` for the full command log and targeted regression evidence.

## Final State
- `M5 completed`
- `M6 not started`
