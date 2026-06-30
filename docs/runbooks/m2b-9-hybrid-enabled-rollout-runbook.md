# M2B-9 Hybrid Enabled Rollout Runbook

## Purpose

`M2B-9.1` is operational readiness for `hybrid_enabled`, not runtime expansion.

This runbook explains:

- how to enable `hybrid_enabled`
- how to confirm it is really effective
- how to confirm it did not misfire
- how to inspect fallback reasons
- how to roll back safely

## Default-Safe Behavior

`hybrid_enabled` remains default-off.

`configured_mode=hybrid_enabled` does not mean `effective_mode=hybrid_enabled`.

Runtime only allows `effective_mode=hybrid_enabled` when all of the following are true:

- `HYBRID_RETRIEVAL_ENABLED=true`
- `HYBRID_RETRIEVAL_MODE=hybrid_enabled`
- `HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH=false`
- `HYBRID_RETRIEVAL_HYBRID_ENABLED_EVAL_GATE=true`
- `country=mx`
- `run_type=cohort_query`
- request-scope `sql_kind=query_only`
- normalized `ctx.project_id` hits both runtime allowlists
- vector artifact is readable
- accepted supplements are non-empty
- audit trace remains writable/serializable

Otherwise runtime must fall back to `deterministic_only`.

## Required Env Config

Minimum rollout config:

```bash
HYBRID_RETRIEVAL_ENABLED=true
HYBRID_RETRIEVAL_MODE=hybrid_enabled
HYBRID_RETRIEVAL_HYBRID_ENABLED_PROJECTS=MEX017
HYBRID_RETRIEVAL_HYBRID_ENABLED_EVAL_GATE=true
HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH=false
```

Normal rollout also requires the existing hybrid runtime config to remain valid, including:

- `HYBRID_RETRIEVAL_SOURCE_NAMESPACE`
- `HYBRID_RETRIEVAL_VECTOR_INDEX_PATH`
- `HYBRID_RETRIEVAL_ALLOW_COUNTRIES`
- `HYBRID_RETRIEVAL_ALLOW_PROJECT_IDS`

## Project ID Allowlist Rule

`HYBRID_RETRIEVAL_HYBRID_ENABLED_PROJECTS` matches normalized `ctx.project_id` exact match only.

It does not match:

- `project_code`
- `apply_source`
- alias values
- wildcard values
- prefix values
- contains/fuzzy matches

If `ctx.project_id` is empty or not matched, runtime must fall back with:

```text
effective_mode=deterministic_only
fallback_reason=hybrid_enabled_rollout_not_allowlisted
```

## Activation Checklist

Before rollout:

- confirm runtime is on merged `M2B-9` or later
- confirm hybrid rollout tests pass
- confirm `docs/knowledge-base` still contains only `README.md`
- confirm request is `MX + cohort_query + query_only`
- confirm `ctx.project_id` is the exact normalized allowlisted value
- confirm kill switch is off
- confirm eval gate is on
- confirm vector artifact path is valid

## How To Confirm Effective Mode

Successful enabled rollout must show:

```text
effective_mode=hybrid_enabled
prompt_injection_mode=supplemental_candidates_v1
final_generation_pass=hybrid_enabled
candidate_attempt.attempted_mode=hybrid_enabled
```

It should also show:

```text
kill_switch_applied=false
rollout_gate_passed=true
eval_gate_passed=true
fallback_applied=false
fallback_reason=null
```

## How To Inspect Fallback Reason

If rollout does not activate, inspect `hybrid_trace.fallback_reason`.

Common examples:

- `hybrid_enabled_rollout_not_allowlisted`
- `hybrid_enabled_eval_gate_not_passed`
- `hybrid_enabled_kill_switch_applied`
- `hybrid_enabled_scope_not_supported`
- `hybrid_enabled_vector_unavailable`
- `hybrid_enabled_no_accepted_supplements`
- `hybrid_enabled_audit_unavailable`

Interpretation rule:

- pre-trace reasons explain why enabled attempt was never allowed
- post-trace reasons explain why enabled attempt was allowed but downgraded

## Rollback Procedure

Use the safest rollback order first.

### 1. Enabled-specific kill switch

Set:

```bash
HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH=true
```

Expected outcome:

```text
effective_mode=deterministic_only
fallback_reason=hybrid_enabled_kill_switch_applied
prompt_injection_mode=none
```

### 2. Force retrieval mode to deterministic-only

Set:

```bash
HYBRID_RETRIEVAL_MODE=deterministic_only
```

Expected outcome:

```text
effective_mode=deterministic_only
fallback_reason=mode_forced_deterministic
prompt_injection_mode=none
```

### 3. Disable hybrid retrieval globally

Set:

```bash
HYBRID_RETRIEVAL_ENABLED=false
```

Expected outcome:

```text
effective_mode=deterministic_only
fallback_reason=hybrid_disabled
prompt_injection_mode=none
```

## Troubleshooting

If rollout did not activate:

- check whether request scope is really `query_only`
- check whether `ctx.project_id` exactly matches the normalized allowlist value
- check whether `HYBRID_RETRIEVAL_ALLOW_PROJECT_IDS` also includes the same project
- check whether the vector artifact path is readable
- check whether accepted supplements are empty
- check whether audit trace serialization failed

If rollout activated unexpectedly:

- verify `ctx.project_id` normalization logic
- verify country is really `mx`
- verify run type is really `cohort_query`
- verify kill switch value
- verify effective trace came from internal audit storage, not public API

## Do-Not-Do List

Do not:

- treat `configured_mode=hybrid_enabled` as proof rollout is active
- use `project_code` or `apply_source` as rollout matching input
- expose `hybrid_trace` through public API
- expose accepted supplements details, full prompts, discarded SQL, or full `retrieval_snapshot_json`
- expand rollout beyond `MX + cohort_query + query_only` in this stage
- use this stage to change SQL HITL, approve/execute, or orchestrator behavior
