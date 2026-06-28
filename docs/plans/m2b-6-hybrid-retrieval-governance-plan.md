# M2B-6 Hybrid Retrieval Governance Plan

## Summary

- 本阶段只做 hybrid runtime-facing governance design，不做 runtime implementation。
- 目标是把 `M2B-5` 的 offline `primary_merge_v1` hybrid baseline，收敛成 future runtime 接入前必须具备的治理合同。
- 首个实际 rollout 只收口在 `MX + query_only + cohort_query`；`MX bucket_writeback` 与 `TH cohort_query` 仅保留 future gate。

## Implementation

- 新增治理 spec：
  - `docs/specs/m2b-6-hybrid-retrieval-governance-spec.md`
  - `docs/specs/m2b-6-hybrid-runtime-contract.md`
  - `docs/specs/m2b-6-hybrid-audit-schema.md`
  - `docs/specs/m2b-6-hybrid-eval-gate.md`
- 新增设计结果总结：
  - `docs/reviews/m2b-6-hybrid-retrieval-governance-results.md`
- 更新：
  - `PLANNING.md`
  - `TASK.md`

## Design Checklist

- retrieval mode enum 明确：
  - `deterministic_only`
  - `hybrid_shadow`
  - `hybrid_candidate`
  - `hybrid_enabled`
- `configured_mode` / `effective_mode` 降级规则明确
- config contract 采用 env-backed settings 风格，默认 `enabled=false`
- fallback policy 明确，任何 hybrid/vector 异常默认回退 deterministic
- audit trace schema 明确，且不包含 offline expected/matched/missing labels
- rollout scope matrix 明确：
  - `MX cohort_query` = first runtime-facing scope
  - `MX bucket_writeback` = design only / future gated
  - `TH cohort_query` = design only / future gated
  - `TH bucket_writeback` = out of scope
- eval gate matrix 明确
- SQL safety boundary 明确，hybrid 不得绕过 SQL HITL / approve / execute

## M2B-7 Boundary

M2B-7 或后续 runtime PR 才允许实现：

- runtime hybrid mode wiring
- retrieval snapshot hybrid trace writes
- prompt context hybrid candidate injection
- allowlist / sample-rate runtime enforcement

M2B-7 仍然不是：

- SQL HITL 改造
- auto approve / auto execute
- vector infra 升级
- seed / embedding / index 重构

## Validation

```bash
python -m compileall -q app data_acquisition_agent tests scripts
git diff --check
git ls-files docs/knowledge-base
```

## Success Criteria

- diff 只包含 M2B-6 docs、`PLANNING.md`、`TASK.md`
- 不出现 runtime 文件变更
- `docs/knowledge-base` 仍只追踪 `docs/knowledge-base/README.md`
- 设计文档足够支撑后续 `M2B-7` runtime implementation 单独开 PR
