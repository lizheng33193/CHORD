# Maestro Spike 失败记录 — 2026-05-02

## 1) 4 项验证结果

| # | 项 | 结果 | 备注 |
|---|---|---|---|
| 1 | HTTP 200 | 未执行 | 凭据未到 |
| 2 | 协议字段 `content[]` | 未执行 | 凭据未到 |
| 3 | 延迟 ≤ 5s | 未执行 | 凭据未到 |
| 4 | 配额 header | 未执行 | 凭据未到 |

**触发原因**：`MAESTRO_ENDPOINT` + `MAESTRO_TOKEN` 短期内无法从团队管理员处获取（非 Spike 协议失败）。

## 2) 4 项降级动作执行情况

| 动作 | 字面状态 |
|---|---|
| Plan #01 Provider 抽象层 | 不阻塞 — 已落地 (commit 70befee)，零改动 |
| Plan #02 `llm.routes` 8 条 | 保留 — `claude_maestro` 路由通过 ModelClient fallback_chain 自动回退到 `gemini`，无代码改动 |
| Plan #03 Phase 1-4 | 改用 Gemini 2.5 Flash MVP — `SYSTEM_PROMPT_V1` 在 Gemini 上验证 6 工具协议，Spike 重启后只需改 endpoint 一行回切 |
| Plan #04 NL Chat Tab | 推迟 — Plan #03 MVP 跑通后再启动 |

## 3) 重新启动 Spike 的触发条件

任一发生即可重新启动：
- 团队管理员发放 `MAESTRO_ENDPOINT` + `MAESTRO_TOKEN`
- `scratch/spike_maestro.py` 仍保留在工作树（已 ignore），凭据到位后直接：
  1. 原生 PowerShell `$env:MAESTRO_ENDPOINT="..."; $env:MAESTRO_TOKEN="..."`
  2. `python scratch/spike_maestro.py`
  3. 截图 stdout 给用户判 4 项 Gate
- 4 项 Gate 全过 → 改 `config.yaml` 把 `endpoint: "[Spike Pending]"` 替换为真实 URL，commit message：`feat(orchestrator): Maestro Spike passed, claude_maestro endpoint wired`

## 4) Plan #03 后续 6-commit 序列调整

| # | 原计划 | C-1 调整后 |
|---|---|---|
| 1 | ✅ baseline (90ea99d) | ✅ baseline (90ea99d) |
| 2 | Maestro Spike wire-up | **本 commit** — C-1 失败记录 + config.yaml 路由补全 |
| 3-5 | Phase 1-3（Claude Opus 4.7） | Phase 1-3（Gemini 2.5 Flash 跑通 MVP） |
| 6 | Phase 4 [complete] | Phase 4 [complete] |

## 5) 凭据到手后回切清单（一次性 commit）

- 改 `config.yaml`：`endpoint: "[Spike Pending]"` → 真实 URL（1 行）
- 删 `scratch/spike_maestro.py` + `scratch/maestro_credential_request.md`（已 ignore，物理删除）
- 本文件保留作为审计记录
- commit message: `feat(orchestrator): Maestro Spike post-mortem unblocked, switching to claude_maestro`
