---
name: credit-profile
description: Use when working on the runtime Credit Profile module, including credit-data parsing, risk interpretation, credit-related feature extraction, or prompt/template updates tied to credit profiling. Do not use for app usage profiling, behavior-event analysis, comprehensive orchestration, or frontend-only adjustments unrelated to credit runtime behavior.
---

# Credit Profile

Use this skill for changes in the credit-oriented profiling path.

Keep risk logic explicit, deterministic where possible, and separated from other profiling modules.
Prefer focused updates in runtime code and prompt templates only.

## Scripts

Use `scripts/build_prompt_input.py` to assemble credit prompt input from a `uid`.
Use `scripts/validate_output.py` and `scripts/check_chart_payload.py` after changing credit output logic.
These scripts are skill-side helpers only; detailed rules stay in `references/`.
