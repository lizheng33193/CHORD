# M2B-9 Hybrid Enabled Rollout Matrix

This matrix is the contract for `hybrid_enabled` rollout behavior during `M2B-9.1`.

| Scenario | configured_mode | Condition | expected effective_mode | fallback_reason | prompt_injection_mode |
| --- | --- | --- | --- | --- | --- |
| Global disabled | `hybrid_enabled` | `HYBRID_RETRIEVAL_ENABLED=false` | `deterministic_only` | `hybrid_disabled` | `none` |
| Kill switch | `hybrid_enabled` | `HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH=true` | `deterministic_only` | `hybrid_enabled_kill_switch_applied` | `none` |
| Rollout allowlist empty | `hybrid_enabled` | `HYBRID_RETRIEVAL_HYBRID_ENABLED_PROJECTS=""` | `deterministic_only` | `hybrid_enabled_rollout_not_allowlisted` | `none` |
| Project ID miss | `hybrid_enabled` | normalized `ctx.project_id` not in rollout allowlist | `deterministic_only` | `hybrid_enabled_rollout_not_allowlisted` | `none` |
| Eval gate false | `hybrid_enabled` | `HYBRID_RETRIEVAL_HYBRID_ENABLED_EVAL_GATE=false` | `deterministic_only` | `hybrid_enabled_eval_gate_not_passed` | `none` |
| Non-MX | `hybrid_enabled` | `country != mx` | `deterministic_only` | `hybrid_enabled_scope_not_supported` | `none` |
| Non-cohort query | `hybrid_enabled` | `run_type != cohort_query` | `deterministic_only` | `hybrid_enabled_scope_not_supported` | `none` |
| Non-query-only scope | `hybrid_enabled` | request-scope `sql_kind != query_only` | `deterministic_only` | `hybrid_enabled_scope_not_supported` | `none` |
| No accepted supplements | `hybrid_enabled` | post-trace accepted supplements empty | `deterministic_only` | `hybrid_enabled_no_accepted_supplements` | `none` |
| Vector unavailable | `hybrid_enabled` | vector artifact unreadable or unavailable | `deterministic_only` | `hybrid_enabled_vector_unavailable` | `none` |
| Audit unavailable | `hybrid_enabled` | audit trace unavailable or unserializable | `deterministic_only` | `hybrid_enabled_audit_unavailable` | `none` |
| All gates pass | `hybrid_enabled` | pre-trace and post-trace gates all pass | `hybrid_enabled` | `null` | `supplemental_candidates_v1` |

## Notes

- `configured_mode=hybrid_enabled` never guarantees runtime success by itself.
- pre-trace gate only decides whether enabled mode may be attempted.
- post-trace gate may still downgrade final `effective_mode` to `deterministic_only`.
- this matrix does not expand rollout scope beyond `MX + cohort_query + query_only`.
