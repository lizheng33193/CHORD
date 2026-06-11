# CLAUDE.md

## 历史兼容说明
- 本仓库现在是 Codex-first。
- `AGENTS.md` 是唯一的项目级开发指南主入口。
- Claude Code 可能会自动读取本文件，但 Codex 不应依赖本文件作为主规则源。
- 本文件只作为 Claude Code 历史兼容桥，避免旧工作流和 Codex 主规则漂移。

## 读取顺序
- 先读 `AGENTS.md`，获取项目规则、边界、安全约束和工作流。
- 涉及架构、跨层行为、模块边界或已知约束时，再读 `PLANNING.md`。
- 涉及任务状态、待办或开发中发现时，再读 `TASK.md`。
- 只在任务相关时读取具体的 `docs/specs/` 和 `docs/plans/`。

## 不重复规则
- 不在本文件复制长篇开发规范。
- 项目指导原则变化时，优先更新 `AGENTS.md`。
- 架构或已知约束变化时，更新 `PLANNING.md`。
- 任务状态变化时，更新 `TASK.md`。

## Claude Code 兼容规则
- Claude Code 应把 `AGENTS.md` 中的规则视为本文件规则。
- 历史文档中的 Claude 专属措辞只作为历史上下文，不强于当前 `AGENTS.md`。
- 如果历史 Plan 写着 “CLAUDE.md constraint”，按当前 `AGENTS.md` 和 `PLANNING.md` 解释。
