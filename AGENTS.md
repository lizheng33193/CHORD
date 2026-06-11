# AGENTS.md

## 用途
- 本文件是本仓库的 Codex 项目级开发指南，也是 Codex 的默认主入口。
- 本文件不是运行时业务 Prompt，不能注入用户画像的 LLM Prompt。
- `CLAUDE.md` 仅作为 Claude Code 历史兼容入口，必须回指本文件。
- 本项目服务墨西哥优先、多国家扩展的用户画像系统。

## 信息源优先级
- `AGENTS.md`：Codex 开发规则、边界、工作流和项目宪法。
- `PLANNING.md`：当前架构、已知约束、Surgical Boundary、扩展方向。
- `TASK.md`：任务状态、待办事项、开发中发现的问题。
- `docs/specs/`：非平凡能力的设计文档。
- `docs/plans/`：已确认设计的执行计划。
- `docs/reviews/`：审计、复盘、评审报告。
- `.codex/config.toml`：只放 Codex 配置，不承载长篇开发规范。

## Harness Engineering 宪法
- 把本项目当作一个 Agent Harness，而不是脚本、页面、Prompt 的零散集合。
- Agent 质量来自 `Model + Harness`：模型调用、Prompt、工具、编排、记忆/状态、验证、恢复、观测必须一起演进。
- 每个非平凡改动都要先判断影响的 Harness 层：
  `信息边界`、`工具接口`、`执行编排`、`记忆/状态`、`评估/观测`、`约束/恢复`。
- 不要用“只改 Prompt”掩盖系统问题；如果问题属于数据、契约、编排、校验、降级、测试或观测，就应该改对应层。
- 优先扩展现有契约、注册表、六步管线、Schema、测试和评估；避免新增一次性逻辑。
- 跨层改动、公共契约变化、新模块、新路由、Prompt 契约变化，必须先更新或新增 `docs/specs/` 与 `docs/plans/`。
- 详细方法论见 `docs/specs/harness-engineering-governance.md`，只在需要架构判断或复杂改动时读取。

## 每次改动前的 Harness Gate
- 这次改动属于小修、模块内改动，还是跨层改动？
- 它影响哪些 Harness 层？
- 应该复用哪个现有入口、契约、管线、注册表或测试？
- 需要更新 `PLANNING.md`、`TASK.md`、Design Doc 或 Plan 吗？
- 如何验证：单测、Golden Test、API smoke、前端验证、日志/降级路径？
- 如果失败，系统如何降级、阻断、回滚或提示用户？

## 项目结构边界
- `app/`：运行时业务代码。
- `app/runtime_skills/`：后端画像 Skill，不是 Codex 技能。
- `app/prompts/`：运行时 LLM Prompt 模板。
- `app/services/orchestrator_agent/`：自然语言编排 Agent 运行时。
- `data_acquisition_agent/`：受控的顶层运行时子项目，用于自然语言取数与审核后 SQL 执行。
- `app/country_packs/`：国家相关配置和规则。
- `.agents/skills/`：Codex 仓库本地技能，不参与运行时业务逻辑。
- `.codex/config.toml`：Codex 配置，不放开发长文档。

## 运行时模块规则
- 新 runtime Skill 必须继承 `app/runtime_skills/base.py::BaseSkill`。
- 新 runtime Skill 必须定义 `name`、`stage`、`depends_on`。
- 新 runtime Skill 必须注册到 `app/services/orchestrator.py::_build_registry()`。
- 除非用户明确要求破坏性迁移，否则不要修改 `BaseSkill.analyze(uid, **kwargs)` 签名。
- 所有画像模块必须支持 mock 降级。
- 标准画像模块优先沿用六步管线：
  `contracts.py -> data_access.py -> feature_builder.py -> decision_engine.py -> explainer.py -> assembler.py`。
- Skill 输出必须满足 `AgentOutput` 形状：
  `summary`、`structured_result`、`charts`、`report_markdown`。

## 安全约束
- 未脱敏凭据不得进入 Prompt、生成代码、日志、API 响应、文档或提交记录。
- 注入 LLM 的知识库文件必须先经过现有脱敏路径。
- 可能包含凭据的 LLM 输出必须经过输出扫描。
- `data_acquisition_agent` 生成的 SQL / Python 是待审核 artifact，不是自动执行授权。
- SQL 执行必须走 `approved_sql` + `approved_by` 的受控路径。
- `build_table_script` SQL 必须限定在分析师私有 schema / prefix 内，并保留人工审核。
- 来自用户或 LLM 的 UID 必须经过文档约定的双层 UID 校验。

## Codex 工作流
- 小范围修复：读取相关文件，做最小安全改动，运行定向验证。
- 架构、新模块、跨层行为、Prompt 契约、公共 API 改动：先读 `PLANNING.md` 和 `TASK.md`。
- 非平凡能力：先写或更新 `docs/specs/`，再写或更新 `docs/plans/`，最后实施代码。
- 运行时行为变化优先 TDD：先补失败测试，再写最小实现。
- 不破坏既有 API 路由，除非用户明确要求。
- 优先改后端能力和契约，再改前端展示。
- 优先小步增量重构，避免大范围重写。
- 工作区已有大量修改时，只碰本任务需要的文件，不回滚无关改动。
- 不修改 `.agents/skills/`，除非用户明确要求开发 Codex 本地技能。

## 验证要求
- 新运行时能力应尽量覆盖正常、边界、失败路径。
- 优先跑定向测试；风险较大时再跑更广的回归。
- 不随意刷新 Golden Test fixture，除非任务就是刷新契约。
- Prompt 或 LLM 路由变更要验证结构、降级和回归风险，不只看样本文案。
- 前端可见改动应在目标地址明确时做本地 UI 验证。

## Git 安全
- 未经用户明确要求，不提交、不推送、不 reset、不 rebase、不 stage。
- 禁止在未获明确批准时运行 `git reset --hard` 或 `git checkout --`。
- 用户要求 push 时，先运行 `git remote -v`。
- 只在用户明确要求时推送到本项目当前批准的 GitHub 仓库；当前批准目标为 `lizheng33193/MAPS-LZ`。
- 当本地仅配置 `origin` 且其指向 `lizheng33193/MAPS-LZ` 时，可按用户要求正常 push / 创建 PR；若远端指向其他仓库，先停下并向用户确认。
- 不回滚无关的脏工作区改动。

## 文档更新
- 架构、边界、模块状态、已知约束、参考路径变化时，更新 `PLANNING.md`。
- 任务状态、待办、开发中发现变化时，更新 `TASK.md`。
- 设计决策写入 `docs/specs/`，执行细节写入 `docs/plans/`。
- `AGENTS.md` 保持短小稳定，只放索引和高层规则；长篇解释沉淀到 specs / plans / reviews。
- `CLAUDE.md` 保持薄兼容层，不复制完整规则。

## 命名规则
- 新 Codex 技能名使用英文 kebab-case。
- 运行时模块名应匹配现有业务领域词汇。
- 避免新增含义模糊的文件名，除非包路径已经清楚表达职责。
