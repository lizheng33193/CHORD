# M2B-9 Hybrid Enabled Acceptance Checklist

## Pre-Rollout Checklist

- [ ] mainline runtime includes merged `M2B-9`
- [ ] targeted hybrid rollout tests pass
- [ ] `docs/knowledge-base` contains only `README.md`
- [ ] `HYBRID_RETRIEVAL_ENABLED=true`
- [ ] `HYBRID_RETRIEVAL_MODE=hybrid_enabled`
- [ ] `HYBRID_RETRIEVAL_HYBRID_ENABLED_PROJECTS` exactly matches normalized `ctx.project_id`
- [ ] `HYBRID_RETRIEVAL_HYBRID_ENABLED_EVAL_GATE=true`
- [ ] `HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH=false`
- [ ] request country is `mx`
- [ ] request run type is `cohort_query`
- [ ] request scope is `query_only`

## During-Rollout Checklist

- [ ] `effective_mode=hybrid_enabled`
- [ ] `prompt_injection_mode=supplemental_candidates_v1`
- [ ] `final_generation_pass=hybrid_enabled`
- [ ] `candidate_attempt.attempted_mode=hybrid_enabled`
- [ ] `source_context=hybrid_enabled_attempt`
- [ ] public API does not expose `hybrid_trace`
- [ ] public API does not expose `retrieval_snapshot_json`
- [ ] public API does not expose accepted supplements or discarded SQL
- [ ] SQL HITL approval flow is unchanged
- [ ] approve / execute semantics are unchanged

## Rollback Checklist

- [ ] first try `HYBRID_RETRIEVAL_HYBRID_ENABLED_KILL_SWITCH=true`
- [ ] if broader rollback is needed, set `HYBRID_RETRIEVAL_MODE=deterministic_only`
- [ ] only if full hybrid shutdown is needed, set `HYBRID_RETRIEVAL_ENABLED=false`
- [ ] confirm runtime falls back to `deterministic_only`
- [ ] confirm `prompt_injection_mode=none`

## Post-Rollback Verification

- [ ] `effective_mode=deterministic_only`
- [ ] `fallback_applied=true`
- [ ] fallback reason matches the rollback control used
- [ ] no supplemental prompt section is injected
- [ ] public API boundary remains unchanged
