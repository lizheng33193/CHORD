# M2B-9 Hybrid Enabled Trace Examples

## Success Example

This is a bounded internal audit example. It is not a public API response.

```json
{
  "configured_mode": "hybrid_enabled",
  "effective_mode": "hybrid_enabled",
  "fallback_applied": false,
  "fallback_reason": null,
  "kill_switch_applied": false,
  "rollout_gate_passed": true,
  "eval_gate_passed": true,
  "prompt_injection_mode": "supplemental_candidates_v1",
  "final_generation_pass": "hybrid_enabled",
  "candidate_attempt": {
    "attempted": true,
    "attempted_mode": "hybrid_enabled",
    "discarded": false
  }
}
```

## Rollout Allowlist Fallback

This is a bounded internal audit example. It is not a public API response.

```json
{
  "configured_mode": "hybrid_enabled",
  "effective_mode": "deterministic_only",
  "fallback_applied": true,
  "fallback_reason": "hybrid_enabled_rollout_not_allowlisted",
  "kill_switch_applied": false,
  "rollout_gate_passed": false,
  "eval_gate_passed": true,
  "prompt_injection_mode": "none"
}
```

## Eval Gate Fallback

This is a bounded internal audit example. It is not a public API response.

```json
{
  "configured_mode": "hybrid_enabled",
  "effective_mode": "deterministic_only",
  "fallback_applied": true,
  "fallback_reason": "hybrid_enabled_eval_gate_not_passed",
  "kill_switch_applied": false,
  "rollout_gate_passed": true,
  "eval_gate_passed": false,
  "prompt_injection_mode": "none"
}
```

## No Accepted Supplements Fallback

This is a bounded internal audit example. It is not a public API response.

```json
{
  "configured_mode": "hybrid_enabled",
  "effective_mode": "deterministic_only",
  "fallback_applied": true,
  "fallback_reason": "hybrid_enabled_no_accepted_supplements",
  "prompt_injection_mode": "none",
  "prompt_candidate_count": 0
}
```

## Enabled Attempt Discarded And Deterministic Rerun

This is a bounded internal audit example. It is not a public API response.

```json
{
  "configured_mode": "hybrid_enabled",
  "effective_mode": "deterministic_only",
  "fallback_applied": true,
  "fallback_reason": "post_sql_kind_mismatch",
  "prompt_injection_mode": "none",
  "final_generation_pass": "deterministic_rerun",
  "candidate_attempt": {
    "attempted": true,
    "attempted_mode": "hybrid_enabled",
    "discarded": true,
    "discard_reason": "post_sql_kind_mismatch"
  }
}
```

## Boundary Notes

These examples intentionally do not include:

- full prompt text
- discarded SQL
- accepted supplements detail rows
- raw knowledge documents
- full `retrieval_snapshot_json`
