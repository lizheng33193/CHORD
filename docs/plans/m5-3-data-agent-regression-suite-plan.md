# M5-3 Data Agent Regression Suite Plan

## Goal
- Land deterministic Data Agent safety and grounding regression suites on the shared eval platform.

## Deliverables
- `app/eval/evaluators/data_agent.py`
- `data_agent_sql_safety` and `data_agent_sql_grounding` suite registration
- deterministic eval case files for both suites
- `pr_acceptance` profile expansion only
- targeted `tests/eval/` coverage plus Data Agent deterministic non-regression verification

## Explicit Constraints
- Reuse deterministic runtime seams first, thin adapters second, eval-only last resort.
- Do not call LLM-backed planning flows.
- Do not connect to real DBs or execute SQL.
- Do not persist real SQL example or error-case rows.
- Preserve raw runtime codes alongside normalized eval codes.
- Keep `production_release` smoke-only in `M5-3`.
