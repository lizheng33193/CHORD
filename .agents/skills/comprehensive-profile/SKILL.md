---
name: comprehensive-profile
description: Use when working on the runtime Comprehensive Profile module that combines App Profile, Behavior Profile, and Credit Profile outputs into a final user profile or summary. Do not use for single-module changes that only touch app, behavior, or credit logic in isolation, and do not use for frontend-only UI work.
---

# Comprehensive Profile

Use this skill for final aggregation and cross-module profile synthesis.

Preserve clear boundaries between upstream module outputs and the final comprehensive result.
Avoid pulling unrelated UI or single-module logic into this layer.

## Scripts

Use `scripts/build_prompt_input.py` to combine app, behavior, and credit upstream outputs into one prompt-ready payload.
Use `scripts/validate_output.py` and `scripts/check_chart_payload.py` to verify final synthesis outputs.
These scripts are skill-side helpers only; detailed rules stay in `references/`.
