# M5 Acceptance Closure

## M5 Goal
- Upgrade CHORD from manual milestone judgment to a shared deterministic eval, regression, and release-gate platform.

## Completed Stages
- `M5-1` Eval Regression Foundation
- `M5-2` Memory Governance Eval Suite
- `M5-3` Data Agent Regression Suite
- `M5-4` Risk QA Groundedness Eval Suite
- `M5-5` Profile DAG Regression Suite
- `M5-6` Release Gate & Acceptance Closure

## Runnable Shared Suites
- `release_gate_smoke`
- `memory_governance`
- `data_agent_sql_safety`
- `data_agent_sql_grounding`
- `risk_qa_groundedness`
- `profile_dag_contract`
- `profile_memory_snapshot`

## Final Release Profiles
- `pr_acceptance`
  - strict default: `false`
  - suites: all 7 deterministic M5 shared eval suites
- `production_release`
  - strict default: `true`
  - suites: all 7 deterministic M5 shared eval suites

## What M5 Proves
- Memory governance boundaries are regression-tested.
- Data Agent SQL safety and grounding contracts are regression-tested.
- Risk QA groundedness, citation, refusal, and source-boundary contracts are regression-tested.
- Profile DAG execution, adapter, snapshot, and memory-boundary contracts are regression-tested.
- Deterministic suite evidence can be surfaced in shared JSON/Markdown reports and used as PR/release gate input.

## What M5 Does Not Do
- No dashboard
- No CI integration
- No online monitoring
- No LangGraph migration
- No production deployment
- No LLM-as-judge
- No real DB, vector store, worker, or indexing execution in shared eval

## Acceptance Commands And Results
- `python -m compileall -q app tests scripts`
  - result: `pass`
- `python -m app.eval.runner --list-suites`
  - result: `exit 0`
  - confirmed 7 registered suites, all blocking, all mapped into both profiles
- `python -m app.eval.runner --list-profiles`
  - result: `exit 0`
  - confirmed:
    - `pr_acceptance strict_by_default=False`
    - `production_release strict_by_default=True`
    - both profiles use the same ordered 7-suite list
- single-suite shared runner smoke:
  - `python -m app.eval.runner --suite release_gate_smoke --output-dir /tmp/m5_6_eval/release_gate_smoke` -> `exit 0`
  - `python -m app.eval.runner --suite memory_governance --output-dir /tmp/m5_6_eval/memory_governance` -> `exit 0`
  - `python -m app.eval.runner --suite data_agent_sql_safety --output-dir /tmp/m5_6_eval/data_agent_sql_safety` -> `exit 0`
  - `python -m app.eval.runner --suite data_agent_sql_grounding --output-dir /tmp/m5_6_eval/data_agent_sql_grounding` -> `exit 0`
  - `python -m app.eval.runner --suite risk_qa_groundedness --output-dir /tmp/m5_6_eval/risk_qa_groundedness` -> `exit 0`
  - `python -m app.eval.runner --suite profile_dag_contract --output-dir /tmp/m5_6_eval/profile_dag_contract` -> `exit 0`
  - `python -m app.eval.runner --suite profile_memory_snapshot --output-dir /tmp/m5_6_eval/profile_memory_snapshot` -> `exit 0`
- profile shared runner checks:
  - `python -m app.eval.runner --profile pr_acceptance --output-dir /tmp/m5_6_eval/pr_acceptance`
    - result: `exit 0`
    - overall status: `WARN`
  - `python -m app.eval.runner --profile production_release --strict --output-dir /tmp/m5_6_eval/production_release`
    - result: `exit 0`
    - overall status: `PASS`
- `pytest tests/eval -q`
  - result: `49 passed, 1 warning`
- `pytest tests/test_memory_type_isolation_contract.py -q`
  - result: `18 passed`
- `pytest tests/data_agent/test_safety.py tests/data_agent/test_sql_plan.py tests/data_agent/test_plan_review.py tests/data_agent/test_semantic_validation.py tests/data_agent/test_repair.py -q`
  - result: `28 passed, 1 warning`
- `pytest tests/risk_knowledge/test_citation_validation.py tests/risk_knowledge/test_context_builder_isolation.py tests/risk_knowledge/service/test_risk_knowledge_service.py tests/risk_knowledge/evaluation/test_evaluator.py -q`
  - result: `12 passed`
- `pytest tests/test_profile_dag_runtime.py tests/orchestrator_agent/test_profile_runner.py tests/test_profile_memory_snapshot.py -q`
  - result: `16 passed`
- `git diff --check`
  - result: `pass`

## Report Artifacts
- `pr_acceptance`
  - JSON: `/tmp/m5_6_eval/pr_acceptance/shared_eval_20260708T065051Z.json`
  - Markdown: `/tmp/m5_6_eval/pr_acceptance/shared_eval_20260708T065051Z.md`
  - overall status: `WARN`
  - strict: `False`
- `production_release`
  - JSON: `/tmp/m5_6_eval/production_release/shared_eval_20260708T065051Z.json`
  - Markdown: `/tmp/m5_6_eval/production_release/shared_eval_20260708T065051Z.md`
  - overall status: `PASS`
  - strict: `True`

## Known Limitations
- Existing warning: `PydanticDeprecatedSince20` from `data_acquisition_agent/schemas.py::AuditReport` remains outside M5-6 scope.
- `pr_acceptance` currently retains the advisory `release_gate_smoke` default behavior, so the profile run exits `0` but surfaces overall status `WARN` rather than `PASS`.

## M6 Entry
- `M6` is not started.
- The next phase may build dashboarding, CI integration, report retention, release automation, and trend/observability workflows on top of the completed M5 deterministic shared eval platform.
