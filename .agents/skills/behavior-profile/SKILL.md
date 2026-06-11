---
name: behavior-profile
description: Use when working on the runtime Behavior Profile module, especially behavior-event ingestion, embedded analytics, engagement signals, value estimation, or prompt/template updates tied to behavior profiling. Do not use for app-install profiling, credit-report interpretation, comprehensive aggregation, or purely visual dashboard polish without behavior-module changes.
---

# Behavior Profile

Use this skill for behavior-driven profiling changes based on event and engagement data.

Keep runtime logic, prompts, and outputs aligned with the existing Behavior Profile module.
Avoid mixing behavior logic with app, credit, or dashboard-only concerns.

## Scripts

Use `scripts/build_prompt_input.py` or `scripts/preprocess_behavior.py` first when you need behavior-ready input.
Use `scripts/summarize_behavior_signals.py`, `scripts/validate_output.py`, and `scripts/check_chart_payload.py` to inspect behavior signals and verify outputs.
These scripts support the skill workflow only; detailed rules stay in `references/`.
