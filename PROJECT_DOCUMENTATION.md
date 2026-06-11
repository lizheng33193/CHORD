# 用户画像多智能体系统 - 项目说明与使用文档

## 1. 项目定位
本项目是一个基于 FastAPI 的“用户画像多智能体后端”示例工程，当前目标是：
- 保持接口稳定（`/api/analyze`、`/api/analyze-file`）。
- 用本地样例数据跑通完整多智能体执行链。
- 支持 `mock/real` 模型模式切换（默认 `mock`）。
- 为后续接真实大模型、数仓、前端大屏预留扩展位。

当前主链路（已落地）：
`API -> BatchService -> Orchestrator -> Skills(4个) -> Repository/Scripts/Prompts/ModelClient -> Report/Charts -> FinalResponse`

---

## 2. 快速启动

### 2.1 环境准备
```bash
pip install -r requirments.txt
```
或：
```bash
pip install -r requirements.txt
```

### 2.2 启动服务
```bash
uvicorn app.main:app --reload
```

### 2.3 访问入口
- 首页：`http://127.0.0.1:8000/`
- 健康检查：`http://127.0.0.1:8000/health`
- 分析接口：`POST http://127.0.0.1:8000/api/analyze`
- 文件分析接口：`POST http://127.0.0.1:8000/api/analyze-file`
- 自然语言对话：`http://127.0.0.1:8000/?tab=chat`

---

## 3. 接口使用说明

## 3.1 `POST /api/analyze`
请求体支持单 uid 或多 uid：
```json
{"uid": "user_001"}
```
```json
{"uids": ["user_001", "user_002"]}
```

返回主结构（兼容）：
- `results[]`
- 每个用户包含：
  - `uid`
  - `comprehensive_profile`
  - `app_profile`
  - `behavior_profile`
  - `credit_profile`

每个画像块统一结构：
- `summary`
- `structured_result`
- `charts`
- `report_markdown`

## 3.2 `POST /api/analyze-file`
- 支持上传 `txt/csv`
- 自动：解析 uid、去重、过滤空行
- 错误处理：
  - 空文件
  - 不支持格式
  - 全空 uid

## 3.3 `/api/orchestrator/*` 自然语言对话与记忆
- 用途：NL Chat 编排助手，负责把自然语言请求转成工具调用、数据查询、画像分析或 trace 分析。
- 短期记忆：当前 `OrchestratorSession.messages` 与 rolling summary。
- 长期记忆：SQLite + FTS5，默认数据库为 `outputs/memory/memory.sqlite3`。
- 身份隔离：`user_id/project_id/country`；默认 `local-default-user / agent-user-profile-fork / mx`，接口可通过 `X-User-ID`、`X-Project-ID`、`X-Country` 覆盖。
- 管理接口：
  - `GET /api/orchestrator/memory/status`
  - `POST /api/orchestrator/memory/query`
  - `GET /api/orchestrator/memory/list`
  - `POST /api/orchestrator/memory`
  - `PATCH /api/orchestrator/memory/{memory_id}`
  - `POST /api/orchestrator/memory/{memory_id}/archive`
  - `POST /api/orchestrator/memory/{memory_id}/restore`
  - `DELETE /api/orchestrator/memory/{memory_id}`（软删除）
- 前端入口：NL Chat 内的 Memory Inspector 抽屉，可新增、搜索、编辑、归档、恢复、软删除记忆。
- 评估入口：`python -m tests.golden.memory_eval --dataset tests/fixtures/golden/memory/eval_set.json`。
- 行为契约：`docs/specs/memory-behavior-contract.md`。
- 恢复审计：`docs/reviews/memory-recovery-audit-2026-05-25.md` 记录 Memory 功能清单、本地数据恢复范围、验证命令和 Inspector 人工验收流程。

---

## 4. 执行链路详解（多智能体）

以行为画像 skill 为例：
1. `analyze.py` 收到 uid 请求
2. `batch_service.py` 统一调度
3. `orchestrator.py` 调用 `BehaviorProfileSkill`
4. `behavior_data_loader.py` 从 repository 读 uid 数据
5. `behavior_preprocessor.py` 清洗聚合
6. 读取 `prompts/behavior_profile_prompt.md`
7. 组装 prompt，调用 `model_client.py`
8. 返回结构化结果（schema 校验）
9. `chart_builder.py` 生成图表结构
10. `report_renderer.py` 生成 markdown
11. 汇总到最终响应

---

## 5. 目录与文件逐项说明

下文按“文件路径 -> 用途 -> 当前作用 -> 扩展性”说明。

## 5.1 根目录文件

### `AGENTS.md`
- 用途：Codex-first 项目级开发规范主入口。
- 当前作用：定义开发代理的工作方式、Harness Engineering 原则、项目边界、运行时/工具层分离规则和验证要求。
- 扩展性：仅保留高层规则和索引；较长的架构说明应沉淀到 `PLANNING.md`、`docs/specs/`、`docs/plans/`。

### `docs/specs/harness-engineering-governance.md`
- 用途：Harness Engineering 项目治理细则。
- 当前作用：解释每次改动如何做 Harness layer impact 判断，以及不同改动级别应该如何更新文档、代码和测试。
- 扩展性：当项目开发方法论变化时更新；不要把全文复制进 `AGENTS.md`。

### `CLAUDE.md`
- 用途：Claude Code 历史兼容入口。
- 当前作用：薄转发到 `AGENTS.md`，避免旧 Claude Code 工作流与 Codex 主规则漂移。
- 扩展性：不再承载独立规则；新增项目规范应优先写入 `AGENTS.md`。

### `README.md`
- 用途：项目对外简介。
- 当前作用：基础说明（可逐步同步到本文件）。
- 扩展性：建议补充 API 示例、架构图、常见问题。

### `config.yaml`
- 用途：统一配置载体（当前为工程占位+可读配置）。
- 当前作用：记录 app/runtime 默认参数。
- 扩展性：后续可接入 YAML 配置加载器，实现环境分层配置。

### `.env`（根目录）
- 用途：环境变量配置。
- 当前作用：`app/core/config.py` 已支持读取。
- 扩展性：可加入模型密钥、超时、重试、限流等配置。

### `requirments.txt`
- 用途：历史兼容依赖文件（拼写保留）。
- 当前作用：与旧启动方式兼容。
- 扩展性：建议长期保留但标注 deprecated。

### `requirements.txt`
- 用途：规范依赖文件。
- 当前作用：与 `requirments.txt` 同步。
- 扩展性：可拆分为 `requirements-dev.txt`、`requirements-prod.txt`。

### `PROJECT_DOCUMENTATION.md`
- 用途：本项目完整说明文档。
- 当前作用：你现在阅读的这份文件。
- 扩展性：可继续补充“开发规范、测试规范、部署规范”。

## 5.2 `app/` 应用主目录

### `app/__init__.py`
- 用途：包初始化文件。
- 当前作用：标记 `app` 为 Python 包。
- 扩展性：可放版本常量或应用元信息。

### `app/main.py`
- 用途：FastAPI 入口。
- 当前作用：
  - 创建应用实例
  - 注册 `/health`
  - 注册首页 `/`
  - 挂载 `/api` 路由
- 扩展性：可加入中间件、异常处理器、CORS、生命周期钩子。

## 5.3 `app/api/`

### `app/api/__init__.py`
- 用途：API 包初始化。
- 当前作用：结构占位。
- 扩展性：可统一导出路由对象。

### `app/api/analyze.py`
- 用途：分析接口层。
- 当前作用：
  - `POST /api/analyze`：处理单/多 uid 请求
  - `POST /api/analyze-file`：处理 txt/csv 上传
  - 调用 `BatchAnalysisService`
  - 使用 `utils/file_parser.py` 做文件解析
- 扩展性：
  - 增加鉴权
  - 增加请求追踪 ID
  - 增加异步任务队列模式

## 5.4 `app/core/`

### `app/core/__init__.py`
- 用途：核心模块包初始化。
- 当前作用：结构占位。
- 扩展性：可统一导出核心对象。

### `app/core/config.py`
- 用途：全局配置中心。
- 当前作用：
  - 定义 `Settings`
  - 读取环境变量
  - 支持相对路径解析
- 扩展性：
  - 增加配置校验
  - 支持 `yaml + env` 混合加载
  - 支持多环境（dev/test/prod）配置切换

### `app/core/logger.py`
- 用途：统一日志入口。
- 当前作用：提供 `get_logger(name)`。
- 扩展性：
  - 接入 JSON 日志
  - 接入 ELK/Datadog
  - 增加 trace_id/span_id

### `app/core/model_client.py`
- 用途：模型调用封装层。
- 当前作用：
  - 支持 `mock` 模式（可离线运行）
  - 预留 `real` 模式入口
  - 模型失败自动降级并输出 `model_unavailable`
- 扩展性：
  - 接入 OpenAI/自建模型 SDK
  - 增加重试、超时、并发控制
  - 增加结构化 JSON 严格校验与修复策略

## 5.5 `app/repositories/`

### `app/repositories/__init__.py`
- 用途：仓储层统一导出。
- 当前作用：导出 `LocalUserRepository`、`WarehouseUserRepository`。
- 扩展性：未来可增加工厂模式按配置选择数据源。

### `app/repositories/base.py`
- 用途：仓储抽象基类。
- 当前作用：定义 `get_app_data/get_behavior_data/get_credit_data` 接口契约。
- 扩展性：新增缓存接口、批量查询接口、连接健康检查接口。

### `app/repositories/local_repository.py`
- 用途：本地样例数据读取实现。
- 当前作用：
  - 从 `data/*.csv/json` 加载数据
  - 按 uid 读取 app/behavior/credit 数据
  - 缺失返回空结构，不抛未处理异常
- 扩展性：
  - 支持更复杂字段类型映射
  - 增加本地缓存失效机制
  - 增加多文件分片读取

### `app/repositories/warehouse_repository.py`
- 用途：数仓仓储占位实现。
- 当前作用：抛 `NotImplementedError`，明确未接入。
- 扩展性：
  - 接 Spark/ClickHouse/BigQuery/Snowflake
  - 增加 SQL 模板与参数校验

## 5.6 `app/scripts/`（数据处理脚本层）

### `app/scripts/__init__.py`
- 用途：脚本包初始化。
- 当前作用：结构占位。
- 扩展性：可统一导出常用处理函数。

### `app/scripts/app_data_loader.py`
- 用途：App 数据读取函数。
- 当前作用：封装从 repository 获取 app 数据。
- 扩展性：可加入字段标准化、缺失补齐策略。

### `app/scripts/behavior_data_loader.py`
- 用途：行为数据读取函数。
- 当前作用：封装从 repository 获取 behavior 数据。
- 扩展性：可接入埋点分表数据拼接逻辑。

### `app/scripts/credit_data_loader.py`
- 用途：征信数据读取函数。
- 当前作用：封装从 repository 获取 credit 数据。
- 扩展性：可加入多源征信结果归一化。

### `app/scripts/behavior_preprocessor.py`
- 用途：行为数据预处理。
- 当前作用：
  - 类型归一化
  - 计算 `engagement_score`
  - 生成 `engagement_level`
  - 输出 `processed_at_utc`
- 扩展性：
  - 时间窗口聚合（7d/30d/90d）
  - 序列截断与异常值处理
  - 时区转换与事件归并

### `app/scripts/chart_builder.py`
- 用途：从结构化结果生成图表数据。
- 当前作用：返回前端可直接渲染的 chart JSON，不生成图片文件。
- 扩展性：
  - 增加图表主题与多语言 label
  - 输出 ECharts/Vega-Lite 双格式

## 5.7 `app/prompts/`

### `app/prompts/__init__.py`
- 用途：提示词包初始化。
- 当前作用：结构占位。
- 扩展性：可统一 prompt 加载工具。

### `app/prompts/app_profile_prompt.md`
- 用途：App 画像提示词模板。
- 当前作用：定义输出约束与输入变量占位。
- 扩展性：加入 few-shot、规则库、字段解释。

### `app/prompts/behavior_profile_prompt.md`
- 用途：行为画像提示词模板。
- 当前作用：强调 engagement 与偏好信息。
- 扩展性：加入序列行为 pattern 提示与异常检测提示。

### `app/prompts/credit_profile_prompt.md`
- 用途：征信画像提示词模板。
- 当前作用：强调风险与还款状态解释。
- 扩展性：加入风险标签标准词典。

### `app/prompts/comprehensive_prompt.md`
- 用途：综合画像提示词模板。
- 当前作用：只消费前三个 skill 结果，不直接读原始数据。
- 扩展性：可加入客群分层规则、策略建议模板。

## 5.8 `app/skills/`（新多智能体实现）

### `app/skills/__init__.py`
- 用途：skills 包初始化。
- 当前作用：结构占位。
- 扩展性：可统一导出 skill registry。

### `app/skills/app_profile_agent.py`
- 用途：App 画像 skill。
- 当前作用：`取数 -> prompt -> model -> schema -> chart -> report`。
- 扩展性：接入真实模型后可增强“应用偏好标签”和“生命周期预测”。

### `app/skills/behavior_profile_agent.py`
- 用途：行为画像 skill。
- 当前作用：强制经过 `behavior_preprocessor` 后再推理。
- 扩展性：增加行为序列建模、异常行为检测、兴趣迁移分析。

### `app/skills/credit_profile_agent.py`
- 用途：征信画像 skill。
- 当前作用：围绕 credit band / repayment / risk 输出结构化结果。
- 扩展性：可接多机构评分并融合为统一风险指数。

### `app/skills/comprehensive_agent.py`
- 用途：综合画像 skill。
- 当前作用：整合前三个 skill 结果，给出 persona、维度分与总结。
- 扩展性：可加入“客群分层、策略建议、干预动作”。

## 5.9 `app/agents/`（兼容旧实现）

### `app/agents/__init__.py`
- 用途：旧 agents 包初始化。
- 当前作用：兼容保留。
- 扩展性：建议后续仅保留薄代理或逐步下线。

### `app/agents/app_profile_agent.py`
### `app/agents/behavior_profile_agent.py`
### `app/agents/credit_profile_agent.py`
### `app/agents/comprehensive_profile_agent.py`
- 用途：旧规则式 agent 实现。
- 当前作用：兼容历史结构，不是新主链路。
- 扩展性：建议后续迁移到 `skills/` 后统一维护，避免双实现分叉。

## 5.10 `app/services/`

### `app/services/__init__.py`
- 用途：服务层包初始化。
- 当前作用：结构占位。
- 扩展性：可统一导出 service factory。

### `app/services/orchestrator.py`
- 用途：多智能体总编排器。
- 当前作用：
  - 按顺序调用 4 个 skill
  - 聚合结果为最终响应对象
  - 根据配置选择 repository（local/warehouse）
- 扩展性：
  - 可并行化前三个 skill
  - 可增加熔断、重试、链路追踪

### `app/services/batch_service.py`
- 用途：批量调度服务。
- 当前作用：让 `/analyze` 和 `/analyze-file` 共用处理逻辑。
- 扩展性：可加入批处理分片、并发控制、任务队列。

### `app/services/report_renderer.py`
- 用途：结构化结果 -> Markdown 报告。
- 当前作用：输出标准 markdown 报告片段。
- 扩展性：可新增 HTML/PDF 渲染、模板多语言。

## 5.11 `app/schemas/`

### `app/schemas/__init__.py`
- 用途：schema 包导出。
- 当前作用：导出关键 request/response。
- 扩展性：可加入统一 schema 版本声明。

### `app/schemas/request.py`
- 用途：请求 schema。
- 当前作用：支持 `uid/uids`，并做基础校验与标准化。
- 扩展性：可加 `trace_id`、`context`、`options` 字段。

### `app/schemas/response.py`
- 用途：兼容响应入口。
- 当前作用：re-export 到 `final_response.py`，保证对外不破坏。
- 扩展性：可做版本兼容层（v1/v2）。

### `app/schemas/final_response.py`
- 用途：最终响应主结构定义。
- 当前作用：统一 `AgentOutput`、`ChartData`、`AnalyzeResponse`。
- 扩展性：可增加 `errors/warnings/latency` 观测字段。

### `app/schemas/app_profile.py`
### `app/schemas/behavior_profile.py`
### `app/schemas/credit_profile.py`
### `app/schemas/comprehensive_profile.py`
- 用途：各 skill 的结构化结果 schema。
- 当前作用：做结果校验和字段约束。
- 扩展性：可以细化 metrics 类型，减少 `dict[str, Any]`。

## 5.12 `app/utils/`

### `app/utils/__init__.py`
- 用途：工具包初始化。
- 当前作用：结构占位。
- 扩展性：可统一导出通用工具函数。

### `app/utils/file_parser.py`
- 用途：uid 文件解析工具。
- 当前作用：支持 txt/csv 解析、去重、空值过滤、错误抛出。
- 扩展性：可支持 xlsx/json 文件输入。

### `app/utils/time_utils.py`
- 用途：时间工具。
- 当前作用：提供 UTC ISO 时间函数。
- 扩展性：可加入时区转换、窗口切分等函数。

## 5.13 `app/ui/`

### `app/ui/__init__.py`
- 用途：前端模板包初始化。
- 当前作用：结构占位。
- 扩展性：后续可拆分成独立前端工程。

### `app/ui/live_frontend.py`
- 用途：首页 + loading + dashboard 的内嵌页面模板（真实接口模式）。
- 当前作用：调用 `/api/analyze` 与 `/api/analyze-file` 并渲染四个 tab。
- 扩展性：建议后续迁移至 `frontend/` 独立项目。

### `app/ui/mock_frontend.py`
- 用途：演示或调试用 mock 页面模板。
- 当前作用：辅助快速 UI 验证。
- 扩展性：可保留为 Storybook 风格原型页面。

## 5.14 `data/`

### `data/sample_app_data.csv`
- 用途：App 数据样例。
- 当前作用：本地 repository 的 app 数据源。
- 扩展性：可扩充更多字段（安装时间、使用频次、品类向量）。

### `data/sample_behavior_data.csv`
- 用途：行为数据样例。
- 当前作用：本地 repository 的 behavior 数据源。
- 扩展性：可扩充事件明细、时序行为。

### `data/sample_credit_data.json`
- 用途：征信数据样例。
- 当前作用：本地 repository 的 credit 数据源。
- 扩展性：可扩充机构维度、授信额度、逾期历史。

### `data/sample_ids.txt`
- 用途：批量 uid 样例。
- 当前作用：测试文件上传分析接口。
- 扩展性：可加入更多测试用户与边界样例。

## 5.15 `outputs/`
- 用途：运行输出目录。
- 当前作用：预留 `reports/` 与 `cache/`，并存放 Orchestrator session、SQLite 长期记忆和 eval 报告。
- 常见子目录：
  - `outputs/orchestrator_sessions/`：本地对话 session JSON。
  - `outputs/memory/memory.sqlite3`：SQLite 长期记忆数据库。
  - `outputs/evals/memory/`：离线记忆评估报告。
- 扩展性：可存报告文件、缓存推理结果、调试日志快照；`outputs/` 默认不入 git。

---

## 6. 配置项说明（核心）

主要来自 `.env`（由 `app/core/config.py` 读取）：
- `APP_NAME`：服务名称
- `APP_VERSION`：服务版本
- `DATA_SOURCE`：`local` 或 `warehouse`
- `MODEL_MODE`：`mock` 或 `real`
- `MODEL_NAME`：模型名称标记
- `MODEL_TIMEOUT_SECONDS`：模型超时
- `PROMPT_DIR`：提示词目录
- `DATA_DIR`：数据目录
- `OUTPUT_DIR`：输出目录
- `LOG_LEVEL`：日志级别

---

## 7. 扩展路线建议（建议按优先级）

### P1（短期）
- 接入真实模型 SDK（完善 `model_client.py` 的 `real` 路径）。
- 给每个 prompt 增加 JSON schema 强约束。
- 增加统一异常码和 `status_reason` 字段。

### P2（中期）
- 引入异步并发（前三个 skill 并行，综合 skill 汇总）。
- 接入数仓实现 `warehouse_repository.py`。
- 增加结果缓存（uid + 数据版本）减少重复推理成本。

### P3（中长期）
- 引入客群分层策略引擎（规则 + 模型融合）。
- 增加实验框架（A/B prompt、策略评估）。
- 前后端分离，建设独立 `frontend/` 工程。

---

## 8. 当前已知注意事项
- 项目中 `requirments.txt` 为历史兼容文件，`requirements.txt` 为规范文件，建议二者保持同步。
- `app/agents` 与 `app/skills` 当前并存，主链路已切到 `skills`；后续建议逐步收敛，避免双份逻辑漂移。
- 本地环境若出现 `__pycache__` 权限问题，不影响主功能逻辑，可清理后重试编译检查。

---

## 9. 最小联调示例

### 单用户
```bash
curl -X POST "http://127.0.0.1:8000/api/analyze" ^
  -H "Content-Type: application/json" ^
  -d "{\"uid\":\"user_001\"}"
```

### 多用户
```bash
curl -X POST "http://127.0.0.1:8000/api/analyze" ^
  -H "Content-Type: application/json" ^
  -d "{\"uids\":[\"user_001\",\"user_002\"]}"
```

### 文件上传（Windows PowerShell）
```bash
curl -X POST "http://127.0.0.1:8000/api/analyze-file" ^
  -F "file=@data/sample_ids.txt"
```

---

如果你愿意，下一步我可以在这份文档基础上继续补一版：
- “真实模型接入实操手册”
- “数仓接入规范模板”
- “前端字段契约文档（dashboard 专用）”
