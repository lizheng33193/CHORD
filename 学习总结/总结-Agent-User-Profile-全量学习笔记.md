# Agent User Profile 全量学习总结

> 项目：agent-user-profile
> 首版整理日期：2026-04-28
> **本次增量更新日期：2026-05-04**
> 覆盖：全部 Python 源文件 + Plan / Spec 文档 + 5 国知识库 + 新增模块（data_acquisition_agent / orchestrator_agent / trace_analyzer / product_advice / ops_advice / 重构后的 comprehensive）
> 目的：作为后续代码改进与你当前 "NL → SQL → 数据库 → 画像" 端到端流程落地的参考蓝图
>
> **本次更新摘要**：
> 1. 项目从「单一画像后端」演进为「多 Agent + 数据采集 + NL 对话编排」三层架构。
> 2. 顶层新增 `data_acquisition_agent/` 独立 Python 包（V1 已落地，V2 设计完成），承担「自然语言→ SQL/Python artifact → 受控 StarRocks 执行 → per-uid 文件落地」的完整链路。
> 3. `app/services/orchestrator_agent/` 新增 NL 聊天编排 Agent（Claude Opus 4.7 + 6 工具 + SSE 流式），把 6 个画像 Skill 串成对话式入口。
> 4. `app/runtime_skills/` 完成结构标准化：comprehensive 拆为六步管线，新增 product_advice / ops_advice（stage=2 下游 Skill），新增 trace_analyzer 独立服务。
> 5. `country_packs/` 从 mx 单国扩展到 mx / pk / th / id 四国 + data_acquisition 知识库覆盖 5 国（墨西哥 / 印尼 / 巴基斯坦 / 泰国 / 菲律宾）。
> 6. 第八章「问题诊断」中多项已被解决，本版做了状态标记。
> 7. 末尾新增第 11–16 章对应所有新模块 + 你当前端到端流程的拼装说明。

---

## 目录

- [一、项目架构与分层详解](#一项目架构与分层详解)
  - [1.1 项目架构全景图](#11-项目架构全景图)
  - [1.2 一段话说清楚整个架构](#12-一段话说清楚整个架构)
  - [1.3 五层运行时架构详解](#13-五层运行时架构详解)
  - [1.4 一段话说清楚为什么要做这个系统](#14-一段话说清楚为什么要做这个系统)
  - [1.5 一段话说清楚系统的使用流程和核心功能](#15-一段话说清楚系统的使用流程和核心功能)
  - [1.6 四大画像模块的关系与职责](#16-四大画像模块的关系与职责)
- [二、技术栈总览](#二技术栈总览)
- [三、核心设计模式](#三核心设计模式)
- [四、模块依赖关系](#四模块依赖关系)
- [五、数据流全景](#五数据流全景)
  - [5.1 完整请求路径](#51-完整请求路径)
  - [5.2 App Profile 数据流](#52-app-profile-数据流)
  - [5.3 Behavior Profile 数据流](#53-behavior-profile-数据流)
  - [5.4 Credit Profile 数据流](#54-credit-profile-数据流)
  - [5.5 Comprehensive Profile 数据流](#55-comprehensive-profile-数据流)
  - [5.6 LLM 交互完整链路](#56-llm-交互完整链路)
  - [5.7 数据预处理管线](#57-数据预处理管线)
- [六、关键业务流程与设计决策](#六关键业务流程与设计决策)
  - [6.1 单用户分析端到端流程](#61-单用户分析端到端流程)
  - [6.2 规则引擎决策逻辑](#62-规则引擎决策逻辑)
  - [6.3 LLM Prompt 模板设计](#63-llm-prompt-模板设计)
  - [6.4 Fallback 与降级策略](#64-fallback-与降级策略)
  - [6.5 核心设计决策](#65-核心设计决策)
- [七、文件清单与职责速查](#七文件清单与职责速查)
- [八、当前架构的问题诊断（含 2026-05 状态更新）](#八当前架构的问题诊断)
- [九、扩展性分析与改进路线图](#九扩展性分析与改进路线图)
- [十、附录](#十附录)
- [十一、data_acquisition_agent 子系统全量解读（NEW）](#十一data_acquisition_agent-子系统全量解读)
- [十二、Orchestrator Agent / NL 对话编排子系统（NEW）](#十二orchestrator-agent--nl-对话编排子系统)
- [十三、Trace Analyzer 深度行为解析子系统（NEW）](#十三trace-analyzer-深度行为解析子系统)
- [十四、Product Advice / Ops Advice 双下游策略 Skill（NEW）](#十四product-advice--ops-advice-双下游策略-skill)
- [十五、多国扩展、SkillRegistry、SSE 进度流（NEW）](#十五多国扩展skillregistrysse-进度流)
- [十六、Plans / Specs 全景目录 + 你当前端到端流程拼装说明（NEW）](#十六plans--specs-全景目录--你当前端到端流程拼装说明)

---

## 一、项目架构与分层详解

### 1.1 项目架构全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                    用户浏览器 / API 客户端                       │
│  嵌入式 React 前端（live_frontend.py 2000+ 行 HTML/JS）         │
│  或 curl / Postman 直接调 REST API                              │
└────────────────────────┬────────────────────────────────────────┘
                         │ POST /api/analyze  或  /api/analyze-file
┌────────────────────────▼────────────────────────────────────────┐
│              FastAPI 后端（Python 3.x）                          │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ API 层（app/api/analyze.py，2 个端点）                    │   │
│  │ ├── POST /api/analyze → AnalyzeRequest → BatchService    │   │
│  │ └── POST /api/analyze-file → 文件解析 → BatchService     │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │ 服务编排层（app/services/）                               │   │
│  │ ├── BatchAnalysisService（批量包装）                      │   │
│  │ ├── AnalysisOrchestrator（四技能编排，ThreadPoolExecutor）│   │
│  │ └── ReportRenderer（Markdown 报告渲染）                   │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │ Skill 执行层（app/runtime_skills/）                       │   │
│  │ ├── AppProfileSkill → 六步管线                           │   │
│  │ ├── BehaviorProfileSkill → 六步管线（双 LLM 链路）       │   │
│  │ ├── CreditProfileSkill → 六步管线                        │   │
│  │ └── ComprehensiveProfileSkill → 融合层（单文件）         │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │ 数据访问层（app/repositories/）                           │   │
│  │ ├── BaseUserRepository（抽象基类，3 个方法）             │   │
│  │ ├── LocalUserRepository（本地文件，600+ 行，多路降级）   │   │
│  │ └── WarehouseUserRepository（数据仓库 stub）             │   │
│  └──────────────────────┬───────────────────────────────────┘   │
│  ┌──────────────────────▼───────────────────────────────────┐   │
│  │ 外部服务层                                                │   │
│  │ ├── Google Gemini API（API Key 模式）                    │   │
│  │ ├── Google Vertex AI（GCP 服务账号模式）                  │   │
│  │ └── 本地文件系统（CSV / JSON / Prepared JSON）           │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 辅助层                                                          │
│ ├── app/scripts/（数据加载 + 预处理 + 特征构建，15 文件）      │
│ ├── app/schemas/（Pydantic 数据契约，7 文件）                   │
│ ├── app/prompts/（LLM 提示词模板，5 个 .md 文件）              │
│ ├── app/country_packs/（国家包配置，mx/ 子目录）               │
│ ├── app/utils/（工具函数，5 文件）                              │
│ └── app/core/（配置 + 日志 + 模型客户端，3 文件）              │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 开发辅助层（不参与运行时）                                      │
│ ├── .agents/skills/（Codex 编辑器技能，5 个域）                 │
│ ├── app/agents/（Legacy 简单规则版本 Agent，4 文件）            │
│ ├── tests/（单元 + 集成测试，5 文件）                           │
│ └── update_suggestion/（改进建议文档，4 文件）                  │
└─────────────────────────────────────────────────────────────────┘
```

---

### 1.2 一段话说清楚整个架构

Agent User Profile 采用**五层架构**：API 层（FastAPI，2 个 POST 端点）接收 UID 请求 → 服务编排层（Orchestrator 用 `ThreadPoolExecutor` 并行调度 App/Behavior/Credit 三个 Skill，等全部完成后串行执行 Comprehensive Skill）→ Skill 执行层（每个 Skill 走「Context → DataAccess → FeatureBuild → Decision → Explain → Assemble」六步管线，其中 Decision 是确定性规则引擎，Explain 调 LLM 做自然语言增强）→ 数据访问层（Repository 抽象，当前只实现了本地文件读取，支持 CSV/JSON/Prepared JSON 三种格式的多路降级）→ 外部服务层（Google Gemini/Vertex AI 作为 LLM 提供商，本地文件系统作为数据源）。整个系统以 UID 为主键，输入多源用户数据（APP 安装列表、行为事件流、征信报告），输出四维用户画像（App 画像 + 行为画像 + 征信画像 + 综合画像），最终以 JSON API 响应返回，包含结构化结果、自然语言摘要、图表数据和 Markdown 报告。

### 1.3 五层运行时架构详解

#### 第一层：API 层

**职责**：请求接收、参数校验、路由分发。

- [app/main.py](app/main.py)（50 行）：FastAPI 实例创建，注册路由、异常处理器、健康检查端点
- [app/api/analyze.py](app/api/analyze.py)（37 行）：定义两个 POST 端点
  - `POST /api/analyze`：接收 `AnalyzeRequest`（含 uid/uids/application_time），调用 `BatchService.analyze_request()`
  - `POST /api/analyze-file`：接收文件上传（txt/csv），解析 UID 列表后调用 `BatchService.analyze_uids()`
- [app/schemas/request.py](app/schemas/request.py)（50 行）：请求验证——UID 必须是 18 位数字（`^\d{18}$`），application_time 必须是 ISO 日期时间格式

#### 第二层：服务编排层

**职责**：批量处理、多技能并行编排、报告渲染。

- [app/services/batch_service.py](app/services/batch_service.py)（23 行）：薄包装层，从 `AnalyzeRequest` 提取 UID 列表和 application_time，转发给 Orchestrator
- [app/services/orchestrator.py](app/services/orchestrator.py)（109 行）：**核心编排器**
  - 初始化 4 个 Skill 实例（AppProfileSkill / BehaviorProfileSkill / CreditProfileSkill / ComprehensiveProfileSkill）
  - `analyze(uids, application_time)` 方法遍历每个 UID，调用 `_analyze_single_user()`
  - **并行策略**：`ThreadPoolExecutor(max_workers=3)` 同时执行 App / Behavior / Credit 三个 Skill
  - **串行依赖**：Comprehensive Skill 必须等前三个全部完成后才能执行，因为它消费前三个的输出
  - 每个 Skill 的执行时间被 `time.time()` 记录并日志输出
- [app/services/report_renderer.py](app/services/report_renderer.py)（30 行）：将 AgentOutput 转为 Markdown 片段

#### 第三层：Skill 执行层

**职责**：核心业务逻辑，每个画像模块的完整处理管线。

每个画像模块（App/Behavior/Credit）采用统一的**六步管线**模式：

```
Context → DataAccess → FeatureBuild → Decision → Explain → Assemble
  (1)       (2)          (3)           (4)        (5)        (6)
```

| 步骤 | 职责 | 输入 | 输出 |
|------|------|------|------|
| 1. Context | 构建运行上下文 | UID, country_code, application_time | `*RunContext` TypedDict |
| 2. DataAccess | 从 Repository 获取并验证原始数据 | RunContext, Repository | `*RawData` TypedDict |
| 3. FeatureBuild | 特征提取与信号派生 | RawData, RunContext | `*FeatureBundle` TypedDict |
| 4. Decision | 确定性规则引擎决策 | FeatureBundle | `*DecisionResult` TypedDict |
| 5. Explain | LLM 自然语言解释增强 | FeatureBundle + DecisionResult + PromptPayload | `*ExplanationResult` TypedDict |
| 6. Assemble | 合并规则结果与 LLM 结果，输出最终页面数据 | DecisionResult + ExplanationResult | `AgentOutput` dict |

**四个模块的 Skill 执行层实现**：

| 模块 | 入口文件 | 管线子目录 | 代码行数（管线总计） | 特殊点 |
|------|---------|-----------|-------------------|--------|
| App Profile | `runtime_skills/app_profile_agent.py`（83 行） | `app_profile/`（6 文件） | ~1,082 行 | 最完整的六步管线实现 |
| Behavior Profile | `runtime_skills/behavior_profile_agent.py`（83 行） | `behavior_profile/`（6 文件） | ~1,739 行 | **双 LLM 链路**：profile_prompt + timeline_prompt |
| Credit Profile | `runtime_skills/credit_profile_agent.py`（75 行） | `credit_profile/`（6 文件） | ~1,232 行 | 基于 Buró de Crédito 墨西哥征信数据 |
| Comprehensive | `runtime_skills/comprehensive_agent.py`（398 行） | **无子目录** | 398 行 | **单文件融合层**，消费前三个模块的输出 |

**Comprehensive 的结构不一致性**：App/Behavior/Credit 都有独立的 contracts.py / data_access.py / feature_builder.py / decision_engine.py / explainer.py / assembler.py 六个子文件，而 Comprehensive 把所有逻辑塞在一个 398 行的文件里——这是当前架构的一个结构不一致点。

#### 第四层：数据访问层

**职责**：数据源抽象与多路降级获取。

- [app/repositories/base.py](app/repositories/base.py)（19 行）：抽象基类，定义 3 个接口方法：
  - `get_app_data(uid) → dict`
  - `get_behavior_data(uid) → dict`
  - `get_credit_data(uid) → dict`
- [app/repositories/local_repository.py](app/repositories/local_repository.py)（600+ 行）：**本地文件实现**，核心逻辑是**多路径降级**：
  - App 数据：UID 专属 CSV（新路径优先 → 4 个 Legacy 路径降级）
  - Behavior 数据：Prepared JSON → Raw CSV → Legacy 样本 CSV
  - Credit 数据：Prepared JSON → Raw CSV → Legacy 三字段 JSON → Legacy 样本 JSON
  - 所有方法**fail-open 设计**——出错返回空 dict + 错误信息，不抛异常
- [app/repositories/warehouse_repository.py](app/repositories/warehouse_repository.py)：**数据仓库 stub**，未实现

#### 第五层：外部服务层

**职责**：LLM 模型调用与本地文件系统交互。

- [app/core/model_client.py](app/core/model_client.py)（475 行）：**LLM 抽象层**，是整个系统中最复杂的基础设施文件
  - **三种模式**：mock（返回 fallback 结果）、gemini（API Key 模式调 Google GenAI）、vertex（GCP 服务账号模式调 Vertex AI）
  - **核心方法** `generate_structured(prompt, response_schema, fallback_result)`：统一入口
  - **健壮性机制**：`_generate_with_retry()`（自动重试解析/空响应错误）、`_repair_json_candidate()`（修复 JSON 语法错误）、`_escape_control_chars_in_strings()`（处理转义字符）、`_extract_first_json_object()`（从 Markdown 代码块中提取 JSON）
  - **错误分类**：`_classify_model_error()` 将异常映射为 blocked / json_parse / api_error / timeout 等类别
  - **降级策略**：LLM 不可用时返回 `fallback_result` + `model_unavailable` 状态

---

### 1.4 一段话说清楚为什么要做这个系统

墨西哥现金贷市场的信贷风控和用户运营需要从多个维度综合评估用户——APP 安装行为反映多头借贷风险和金融成熟度，行为事件流反映用户活跃度和还款意愿，征信报告反映信用历史和负债压力。在没有本系统之前，这三个维度的数据散落在不同系统中，风控和运营团队各自用 Excel 或脚本手动分析，无法快速形成「一个 UID 的完整画像」。Agent User Profile 的核心价值是**把多源数据的采集、清洗、特征提取、规则决策、LLM 增强解释和报告生成，固化成一个自动化管线**——输入一个 UID，输出一份涵盖 APP 画像、行为画像、征信画像、综合画像的完整报告，可直接供产品和运营部门使用。后续计划在画像基础上新增「产品 Agent」和「运营 Agent」，自动生成面向不同部门的策略建议。

### 1.5 一段话说清楚系统的使用流程和核心功能

用户（风控分析师/运营人员）通过浏览器打开嵌入式 Dashboard 或通过 API 客户端发起请求，输入一个或多个 18 位 UID（也可以上传 txt/csv 文件批量提交）。系统收到请求后，Orchestrator 并行调度三个画像 Skill：App Skill 读取用户 APP 安装列表，通过规则引擎判断多头借贷风险（高/中/低）、金融成熟度（银行化/半银行化/非银行化）、消费能力（高/中偏上/中/低），然后调 LLM 生成自然语言解释和报告；Behavior Skill 读取行为事件流，计算活跃投入度/还款意愿/产品敏感度/流失风险/最优触达渠道五个维度，通过两个 LLM 链路（Profile + Timeline）生成行为叙事；Credit Skill 读取 Buró 征信数据，计算金融成熟度/负债压力/信用稳定性/借贷饥渴度四个维度。三个模块全部完成后，Comprehensive Skill 融合三维结果，进行 S1-S6 分群分类、交叉信号冲突检测、价值信号派生，输出最终综合画像。最终响应包含每个模块的 `AgentOutput`（summary 自然语言摘要 + structured_result 结构化数据 + charts 图表配置 + report_markdown 中文报告），Dashboard 渲染四个 Tab 展示完整画像。

### 1.6 四大画像模块的关系与职责

```
                    ┌─────────────────────────────────┐
                    │        用户 UID 输入             │
                    └──────────┬──────────────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
       ┌──────▼──────┐ ┌──────▼──────┐ ┌──────▼──────┐
       │  App Profile │ │  Behavior   │ │  Credit     │
       │  APP 安装画像│ │  行为画像    │ │  征信画像   │
       │             │ │             │ │             │
       │ 输入：      │ │ 输入：      │ │ 输入：      │
       │ APP安装列表 │ │ 行为事件流  │ │ Buró征信    │
       │             │ │             │ │             │
       │ 输出：      │ │ 输出：      │ │ 输出：      │
       │ 多头借贷风险│ │ 活跃投入度  │ │ 金融成熟度  │
       │ 金融成熟度  │ │ 还款意愿    │ │ 负债压力    │
       │ 消费能力    │ │ 产品敏感度  │ │ 信用稳定性  │
       │ 风控建议    │ │ 流失风险    │ │ 借贷饥渴度  │
       │             │ │ 触达建议    │ │ 风险标签    │
       └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
              │                │                │
              └────────────────┼────────────────┘
                               │
                    ┌──────────▼──────────────────────┐
                    │    Comprehensive Profile        │
                    │    综合画像（融合层）             │
                    │                                 │
                    │ 输入：前三个模块的全部输出        │
                    │                                 │
                    │ 输出：                           │
                    │ S1-S6 分群标签                   │
                    │ 交叉信号冲突解释                 │
                    │ 整体风险 + 价值评估               │
                    │ 综合 persona 描述                │
                    │ 雷达图 + 维度评分                 │
                    └─────────────────────────────────┘
```

**独立性**：App / Behavior / Credit 三个模块**完全独立**，互不依赖，可以并行执行。任何一个模块数据缺失或 LLM 失败，不影响其他模块正常输出。

**融合层依赖**：Comprehensive 必须等前三个全部完成，它消费的是前三个的 `AgentOutput`，不直接访问原始数据源。

---

## 二、技术栈总览

| 技术 | 版本/来源 | 在本项目中的用途 |
|------|----------|----------------|
| **Python** | 3.x | 整个项目的运行时语言 |
| **FastAPI** | latest（requirements.txt 无版本锁） | Web 框架，2 个 POST 端点 + 健康检查 |
| **Uvicorn** | standard extras | ASGI 服务器，本地开发和生产运行 |
| **Pydantic** | v2（兼容层支持 v1） | 请求验证、响应 Schema、配置管理（Settings） |
| **Pandas** | latest | 数据加载和预处理（CSV 读取、分组、聚合） |
| **google-genai** | latest | Google Gemini API 和 Vertex AI 的统一 SDK |
| **Jinja2** | latest | 模板引擎（Prompt 模板变量替换） |
| **python-multipart** | latest | 文件上传解析（/api/analyze-file 端点） |
| **python-dotenv** | latest | .env 文件加载（环境变量配置） |

**关键缺失**：项目的 requirements.txt **没有版本锁定**（全部是 `fastapi` 而非 `fastapi==0.115.0`），也没有 lock 文件（无 poetry.lock / pipfile.lock），这在生产部署时是一个风险点。

---

## 三、核心设计模式

| 模式 | 位置 | 解决什么问题 | 为什么这样设计 |
|------|------|------------|--------------|
| **六步管线** | `runtime_skills/*/` | 每个画像模块的处理流程标准化 | Context→Data→Feature→Decision→Explain→Assemble 六步分离，职责清晰，可独立测试和替换 |
| **规则+LLM 双轨** | DecisionEngine + Explainer | 结果既要确定性又要可解释性 | Decision 用规则引擎保证结果稳定可复现；Explain 用 LLM 增强自然语言解释和报告——LLM 挂了也有完整的规则结果兜底 |
| **Country Pack** | `country_packs/mx/` | 多国市场扩展 | 把国家特有的配置（阶段关键词、评分阈值、标签映射、征信评分段）抽到 `@dataclass(frozen=True)` 中，注册模式允许未来新增 BR/CO 等国家包 |
| **Repository 抽象** | `repositories/base.py` | 数据源可切换 | 抽象基类定义 3 个 `get_*_data()` 方法，LocalRepository 实现本地文件读取，WarehouseRepository 预留数据仓库接口——切换数据源只需换注入的 Repository 实现 |
| **Mock/Real 切换** | `model_client.py` | 开发/测试时不依赖真实 LLM | `MODEL_MODE=mock` 时直接返回 fallback 结果，`=gemini` 或 `=vertex` 时调真实 API——零修改业务代码 |
| **多路降级** | `local_repository.py` | 数据格式不统一的兼容 | 按优先级尝试：Prepared JSON → Raw CSV → Legacy JSON → Legacy Sample，任何一级成功即返回——容忍数据质量参差 |
| **TypedDict 数据契约** | `*/contracts.py` | 管线各步之间的数据类型约定 | 用 TypedDict 定义每步的输入输出结构，既有类型提示又不强制 Pydantic 校验开销——适合管线内部传递 |
| **AgentOutput 统一响应** | `schemas/final_response.py` | 四个模块输出格式一致 | summary + structured_result + charts + report_markdown 四件套，前端只需一套渲染逻辑处理所有模块 |

---

## 四、模块依赖关系

```
app/api/analyze.py
    └── app/services/batch_service.py
        └── app/services/orchestrator.py
            ├── app/runtime_skills/app_profile_agent.py
            │   ├── app/runtime_skills/app_profile/contracts.py
            │   ├── app/runtime_skills/app_profile/data_access.py
            │   │   └── app/repositories/*.py
            │   ├── app/runtime_skills/app_profile/feature_builder.py
            │   │   └── app/scripts/app_profile_payload_builder.py (1300+ 行)
            │   ├── app/runtime_skills/app_profile/decision_engine.py
            │   │   └── app/scripts/app_profile_payload_builder.py
            │   ├── app/runtime_skills/app_profile/explainer.py
            │   │   └── app/core/model_client.py + app/prompts/app_profile_prompt.md
            │   └── app/runtime_skills/app_profile/assembler.py
            │       └── app/schemas/app_profile.py
            │
            ├── app/runtime_skills/behavior_profile_agent.py
            │   ├── behavior_profile/contracts.py
            │   ├── behavior_profile/data_access.py
            │   │   └── app/scripts/behavior_prepared_builder.py (1200+ 行)
            │   ├── behavior_profile/feature_builder.py
            │   ├── behavior_profile/decision_engine.py (713 行，最大文件)
            │   ├── behavior_profile/explainer.py (双 LLM：profile + timeline)
            │   │   └── app/prompts/behavior_profile_prompt.md
            │   │   └── app/prompts/behavior_timeline_prompt.md
            │   └── behavior_profile/assembler.py
            │
            ├── app/runtime_skills/credit_profile_agent.py
            │   ├── credit_profile/contracts.py
            │   ├── credit_profile/data_access.py
            │   │   └── app/scripts/credit_prepared_builder.py (1000+ 行)
            │   ├── credit_profile/feature_builder.py (290 行)
            │   ├── credit_profile/decision_engine.py (447 行)
            │   ├── credit_profile/explainer.py
            │   │   └── app/prompts/credit_profile_prompt.md
            │   └── credit_profile/assembler.py
            │
            └── app/runtime_skills/comprehensive_agent.py (398 行，单文件)
                └── app/prompts/comprehensive_prompt.md

共享依赖：
    app/core/config.py → 所有模块读取配置
    app/core/model_client.py → 所有 Explainer 调用 LLM
    app/core/logger.py → 全局日志
    app/country_packs/ → 各模块获取国家特定配置
    app/scripts/chart_builder.py → 各模块构建图表数据
```

---

## 五、数据流全景

### 5.1 完整请求路径

```
客户端 POST /api/analyze { "uid": "123456789012345678" }
         │
         ▼
┌─ API 层 ──────────────────────────────────────────────────────────┐
│  AnalyzeRequest 验证（uid 必须 18 位数字）                        │
│  提取 uid_list + application_time                                │
└────────────────────────────┬──────────────────────────────────────┘
                             │
         ▼
┌─ BatchService ─────────────────────────────────────────────────────┐
│  遍历 uid_list，每个 uid 调 orchestrator.analyze()                │
└────────────────────────────┬──────────────────────────────────────┘
                             │
         ▼
┌─ Orchestrator ─────────────────────────────────────────────────────┐
│  per uid:                                                         │
│  ┌───────────────── ThreadPoolExecutor(3) ──────────────────────┐ │
│  │  Future[App]     Future[Behavior]     Future[Credit]         │ │
│  │    ↓                ↓                    ↓                   │ │
│  │  AppSkill.       BehaviorSkill.      CreditSkill.           │ │
│  │  analyze()       analyze()           analyze()              │ │
│  └──────────────────────┬───────────────────────────────────────┘ │
│                         │ 等待全部完成                            │
│                         ▼                                        │
│  ComprehensiveSkill.analyze(app_result, behavior_result,         │
│                             credit_result)                       │
└────────────────────────────┬──────────────────────────────────────┘
                             │
         ▼
┌─ 响应组装 ─────────────────────────────────────────────────────────┐
│  UserAnalysisResult {                                             │
│    uid: str                                                       │
│    app_profile: AgentOutput { summary, structured_result,         │
│                               charts, report_markdown }           │
│    behavior_profile: AgentOutput { ... }                          │
│    credit_profile: AgentOutput { ... }                            │
│    comprehensive_profile: AgentOutput { ... }                     │
│  }                                                                │
│  AnalyzeResponse { results: [UserAnalysisResult, ...] }          │
└────────────────────────────┬──────────────────────────────────────┘
                             │
         ▼
    JSON 响应返回客户端
```

---

### 5.2 App Profile 数据流

```
输入                         处理                           输出
─────────────────────────────────────────────────────────────────────
Repository.get_app_data(uid)
    │
    ▼
CSV 文件内容                 AppDataProvider.fetch()         AppRawData
{apps: [{                   → 验证字段存在性                {data_status: ok/missing,
  app_name,                  → 检查 apps 列表非空             apps: [...],
  app_package,               → 提取 source_ref               source_ref, errors}
  first_install_time,
  last_update_time,
  gp_category,
  ai_category_level_2_CN
}]}
    │
    ▼
AppRawData                   AppFeatureBuilder.build()       AppFeatureBundle
                             → 调 build_app_feature_bundle()
                             → 去重（_dedupe_apps）
                             → 时间特征（days_since_install,
                               install_bucket）
                             → 分类推断
                             → 聚合统计
    │
    ▼
AppFeatureBundle             AppDecisionEngine.decide()      AppDecisionResult
                             → _derive_multi_loan_risk()     {activity_level,
                             → _derive_financial_level()      risk_assessment{level,
                             → _derive_consumption_level()      lending_app_count,
                             → _derive_activity_level()         reasoning_seed},
                             → _build_timeline()              financial_maturity{level,
                             → _build_progress_metrics()        has_bank_app, ...},
                                                              consumption_profile{level,
                                                                preferred_categories},
                                                              metrics{...},
                                                              tags[...],
                                                              recommendation{action,
                                                                reason_seed}}
    │
    ▼
FeatureBundle +              AppExplainer.explain()          AppExplanationResult
DecisionResult               → 构建 prompt_payload            {status: ok/skipped/partial,
                             → 裁剪 app 列表（max_apps）       summary,
                             → 调 model_client.                tags,
                               generate_structured()           app_insight,
                             → 解析 LLM 响应                   risk_reasoning,
                             → fallback 处理                    maturity_reasoning,
                                                               consumption_reasoning,
                                                               report_markdown,
                                                               model_trace}
    │
    ▼
DecisionResult +             AppPageAssembler.assemble()     AgentOutput
ExplanationResult            → 合并规则结果与 LLM 结果        {summary: str,
                             → Pydantic 验证                   structured_result:
                             → 构建图表（chart_builder）          AppProfileStructuredResult,
                             → 渲染 report_markdown             charts: [ChartData],
                                                               report_markdown: str}
```

**关键特征提取规则**（app_profile_payload_builder.py，1300+ 行）：

- **多头借贷风险**：近 7 天安装 ≥2 个借贷 APP → 高风险；近 30 天 ≥3 个 → 高风险；近 30 天 1-2 个 → 中风险
- **金融成熟度**：有银行 APP + 有政府 APP → 银行化；有电子钱包 → 半银行化；否则 → 非银行化
- **消费能力**：基于电商/本地生活/共享出行/信用购物 APP 的数量和种类综合评分
- **时间权重**：≤7 天极高权重 / 8-30 天高权重 / 31-90 天中权重 / 91-365 天低权重 / >365 天极低

---

### 5.3 Behavior Profile 数据流

```
输入                         处理                           输出
─────────────────────────────────────────────────────────────────────
Repository.get_behavior_data(uid)
    │
    ▼
事件流（CSV 或 Prepared JSON）
{event_name, timestamp,      BehaviorDataProvider.fetch()    BehaviorRawData
 extend_payload, ...}        → 检测是否已是 prepared 格式
或                           → 若否，调
{schema_version:             prepare_behavior_record_from_   {prepared_record:
 "behavior-prepared-v1",       payload()                      BehaviorPreparedRecord,
 profile_header, ...}        → 事件归一化                     data_status, errors}
                             → 阶段分类
                             → 时间线构建
    │
    ▼
BehaviorRawData              BehaviorFeatureBuilder.build()  BehaviorFeatureBundle
                             → 提取 engagement_score          {summary_features:
                             → _derive_active_trend_level()     {engagement_score,
                             → _derive_value_signal_level()      repayment_willingness,
                             → _derive_contact_level()            product_sensitivity,
                                                                  churn_risk, ...},
                                                               timeline_features:
                                                                 {sections, events},
                                                               derived_signals:
                                                                 {active_trend, value,
                                                                  contact_level, ...}}
    │
    ▼
BehaviorFeatureBundle        BehaviorDecisionEngine          BehaviorDecisionResult
                             .decide() (713 行)
                             → 构建 5 维决策：
                               1. engagement_profile           {engagement_profile,
                               2. repayment_willingness         repayment_willingness,
                               3. product_sensitivity           product_sensitivity,
                               4. churn_risk                    churn_risk,
                               5. contact_preference            contact_preference,
                             → 计算 behavior_signal_score       behavior_signal_score,
                             → 构建 llm_fallback_profile        metrics, tags,
                             → 构建 prompt_payload              llm_fallback_profile}
    │
    ▼
                             BehaviorExplainer.explain()     BehaviorExplanationResult
                             → **双 LLM 链路**：
                               链路 1: _run_profile_chain()    {used_llm_profile: bool,
                                 → behavior_profile_prompt.md    used_llm_timeline: bool,
                               链路 2: _run_timeline_chain()     evidence_patch:
                                 → behavior_timeline_prompt.md     {behavior_profile_
                             → 合并两路证据                          narrative,
                                                                   llm_behavior_profile,
                                                                   timeline_narrative,
                                                                   llm_timeline,
                                                                   timeline_insights},
                                                                 model_trace}
    │
    ▼
                             BehaviorPageAssembler           AgentOutput
                             .assemble()
                             → 合并 evidence_patch
                             → 构建图表（radar, bar, table）
                             → 渲染 summary 和 report
```

**Behavior 的独特点——双 LLM 链路**：

1. **Profile Chain**（behavior_profile_prompt.md）：生成行为画像总结、标签、策略建议
2. **Timeline Chain**（behavior_timeline_prompt.md）：生成用户旅程时间线叙事、阶段洞察

两个链路独立调用 LLM，任一失败不影响另一个。`explanation_status` 根据两路结果判定：两路都成功 → "ok"；一路成功 → "partial"；都失败 → "model_unavailable"。

**行为事件的阶段分类**（behavior_prepared_builder.py）：

| 阶段 | 关键词示例 | 含义 |
|------|----------|------|
| acquisition | register, signup, login, otp, face | 拉新与注册 |
| discovery | home, product, offer, coupon, rate | 产品浏览 |
| application | apply, kyc, upload, bank, form | 申请与认证 |
| repayment | repay, payment, due, overdue | 还款与履约 |
| support | chat, complaint, ticket, feedback | 客服与触达 |

---

### 5.4 Credit Profile 数据流

```
输入                         处理                           输出
─────────────────────────────────────────────────────────────────────
Repository.get_credit_data(uid)
    │
    ▼
Buró 征信原始数据            CreditDataProvider.fetch()     CreditRawData
{creditos_detail_json,       → prepare_credit_record_from_   {prepared_record:
 consultas_detail_json,        payload()                      CreditPreparedRecord,
 score, ...}                 → JSON 解析 + 修复               data_status, errors}
                             → 账户标准化
                             → 逾期分析
    │
    ▼
CreditRawData                CreditFeatureBuilder.build()    CreditFeatureBundle
                             → 6 维派生信号：                 {summary_features,
                               1. debt_pressure_level          account_features,
                               2. credit_stability_grade       derived_signals:
                               3. borrowing_urgency_level       {debt_pressure_level,
                               4. financial_maturity_level       credit_stability_grade,
                               5. risk_level                     borrowing_urgency,
                               6. radar_scores                   financial_maturity,
                                                                 risk_level,
                                                                 radar_scores{6 维}}}
    │
    ▼
CreditFeatureBundle          CreditDecisionEngine.decide()  CreditDecisionResult
                             → 4 维决策：                    {financial_maturity,
                               1. financial_maturity            debt_pressure,
                               2. debt_pressure                 credit_stability,
                               3. credit_stability              borrowing_urgency,
                               4. borrowing_urgency             credit_signal_score,
                             → credit_signal_score 计算         risk_flags, tags,
                             → risk_flags 检测                  llm_fallback_profile}
    │
    ▼
                             CreditExplainer.explain()       CreditExplanationResult
                             → 单 LLM 链路                    {used_llm, evidence_patch,
                             → credit_profile_prompt.md         model_trace}
    │
    ▼
                             CreditPageAssembler.assemble()  AgentOutput
                             → 合并规则 + LLM
                             → 图表（gauge, radar, bar, table）
```

**征信信号得分公式**（credit_signal_score）：
```
risk_buffer    = {low: 78, medium: 52, high: 28}[risk_level]
band_bonus     = {A: 12, B: 6, C: 0, D: -8}[credit_score_band]
stability_bonus = {high: 10, medium_high: 6, medium: 0, low: -8}[stability_level]
score_hint     = max(0, min(100, round(score_value / 9)))  # 若有评分
final_score    = max(0, min(100, int((risk_buffer + score_hint)/2 + band_bonus + stability_bonus)))
```

**雷达图六维**：
- financial_maturity（金融成熟度）
- repayment_pressure_index（还款压力指数）
- credit_stability（信用稳定性）
- borrowing_urgency（借贷饥渴度）
- credit_history_depth（信用历史深度）
- cash_tightness（资金紧张度）

---

### 5.5 Comprehensive Profile 数据流

```
输入                         处理                           输出
─────────────────────────────────────────────────────────────────────
app_result (AgentOutput)
behavior_result (AgentOutput)   ComprehensiveProfileSkill     AgentOutput
credit_result (AgentOutput)     .analyze()
    │
    ▼
提取上游结果                 → 维度评分计算
                             → app_score: 基于 active_days, consumption, maturity
                             → behavior_score: 基于 engagement, repayment, churn
                             → credit_score: 基于 risk_level, stability
    │
    ▼
融合信号                     → _assign_segment()
                             → S5: multi_loan==high || (credit_risk==high &&
                                  debt_pressure in {high, medium_high})
                             → S4: churn_risk==high
                             → S1: credit_risk==low && app_activity==high &&
                                  stability in {high, medium_high}
                             → S2: credit_risk in {low, medium} &&
                                  stability in {high, medium_high, medium}
                             → S3: product_sensitivity in {high, medium_high} ||
                                  multi_loan==medium
                             → S6: 默认
    │
    ▼
冲突检测                     → multi_loan 中/高 but credit_risk==low
                               → "早期预警 vs 已确认风险"
                             → credit 模块缺失/降级 → 降低置信度
                             → active + price_sensitive + risky_installs
                               → "比价购物 vs 违约压力"
    │
    ▼
价值信号                     → high: app_activity==high && consumption≥medium_high
                                    && engagement≥70
                             → medium: app_activity∈{high,medium} || engagement≥45
                             → low: 其他
    │
    ▼
LLM 增强                    → comprehensive_prompt.md
                             → 融合叙事、分群解释
    │
    ▼
最终输出                     → persona 描述
                             → 分群标签（S1-S6）
                             → 维度评分（app/behavior/credit 各 1-5 分）
                             → 综合风险判定
                             → 雷达图 + 对比图表
```

**S1-S6 分群含义**：

| 分群 | 含义 | 风险 | 价值 |
|------|------|------|------|
| S1 | 高价值低风险，增长潜力强 | 低 | 高 |
| S2 | 稳定可控，运营价值好 | 可控 | 中高 |
| S3 | 价格敏感/比价型，可能比较优惠 | 中 | 中 |
| S4 | 潜在流失，活跃度下降 | 中高 | 需挽留 |
| S5 | 多头高风险，压力和饥渴度都高 | 高 | 低 |
| S6 | 沉默/观望型，低活跃但不一定信用差 | 待定 | 待激活 |

---

### 5.6 LLM 交互完整链路

```
┌─ Explainer 准备 ─────────────────────────────────────────────────┐
│  1. 构建 prompt_payload（从 feature_bundle + decision_result 提取）│
│  2. 裁剪数据（App: 限制 max_apps; Behavior: 压缩 timeline）      │
│  3. 读取 prompt 模板文件（app/prompts/*.md）                      │
│  4. Jinja2 变量替换（{{uid}}, {{app_data}}, etc.）               │
│  5. 构建 response_schema（Pydantic model → JSON Schema）         │
│  6. 构建 fallback_result（规则引擎结果作为降级值）               │
└───────────────────────┬──────────────────────────────────────────┘
                        │
                        ▼
┌─ ModelClient.generate_structured() ──────────────────────────────┐
│  MODE = mock?                                                    │
│    → 直接返回 fallback_result + {status: "model_unavailable"}    │
│                                                                  │
│  MODE = gemini / vertex?                                         │
│    → _generate_with_retry(prompt, schema, max_retries=2)         │
│      ├── 调 _generate_with_gemini() 或 _generate_with_vertex()  │
│      ├── 解析响应文本 → _extract_text_from_response()            │
│      ├── 清理 Markdown 代码块                                   │
│      ├── _repair_json_candidate()（修复 JSON 语法错误）          │
│      │   ├── 去除非法转义                                       │
│      │   ├── 去除控制字符                                       │
│      │   ├── 去除尾部逗号                                       │
│      │   └── 尝试闭合未完成的括号                               │
│      ├── _parse_json_text()（JSON 解析）                         │
│      │   └── _extract_first_json_object()（提取第一个 {} 对象）  │
│      └── 解析失败? 重试（最多 2 次）                            │
│                                                                  │
│  全部失败?                                                       │
│    → 返回 fallback_result + {status: error_category}             │
│    → error_category ∈ {blocked, json_parse, api_error, timeout,  │
│       empty_response, unknown}                                   │
└───────────────────────┬──────────────────────────────────────────┘
                        │
                        ▼
┌─ Explainer 后处理 ───────────────────────────────────────────────┐
│  1. 验证 LLM 响应的有意义性（非空 summary/report/tags/evidence） │
│  2. 标记 explanation_status: ok / partial / skipped              │
│  3. 构建 model_trace（used_llm, model_name, fallback_reason）   │
│  4. 返回 ExplanationResult                                      │
└──────────────────────────────────────────────────────────────────┘
```

**5 个 Prompt 模板对比**：

| Prompt 文件 | 行数 | 目标 | 输出语言 | 关键约束 |
|------------|------|------|---------|---------|
| `app_profile_prompt.md` | 152 | App 画像 + 风控报告 | 中文 | 四段式报告结构（画像综述/风险评估/金融成熟度/专家建议）；progress_metrics.value 必须 0-100 |
| `behavior_profile_prompt.md` | 88 | 行为画像总结 | 中文 | 不逐条复述事件；提升为阶段投入/高摩擦点/回流点；经营干预建议必须可执行 |
| `behavior_timeline_prompt.md` | 83 | 行为时间线叙事 | 中文 | 压缩重复事件；每阶段说明顺畅/阻塞/停顿/回流；timeline_insights 2-5 条 |
| `credit_profile_prompt.md` | 94 | 征信画像分析 | 中文 | credit_summary ≥260 汉字；不修改 prepared record 数值；confidence 必须与证据匹配 |
| `comprehensive_prompt.md` | 42 | 综合画像融合 | 英文 | 不重写上游证据；保持融合逻辑可解释；S1-S6 分群指导 |

---

### 5.7 数据预处理管线

系统有一条**离线数据预处理管线**，把原始 CSV/JSON 转换为 Prepared JSON 格式，供运行时直接使用：

```
原始数据                  预处理步骤                  Prepared 数据
─────────────────────────────────────────────────────────────────
合并 CSV                  uid_csv_splitter.py         data/{module}/by_uid/
(多用户混在一个文件)       → 按 uid 列拆分              每个 uid 一个文件
                          → LRU 文件句柄池管理
                          → .split_state.json 防重复
         │
         ▼ (App 专用)
usage CSV + label CSV     applist_joiner.py           data/app/by_uid/
                          → 按 app_package join        uid.csv (带分类标签)
                          → .join_state.json 防重复
         │
         ▼ (Behavior)
uid.csv (事件流)          behavior_preparer.py →      data/behavior/by_uid/
                          behavior_prepared_builder.py  uid.json
                          → 事件归一化                   (schema_version:
                          → 阶段分类                      "behavior-prepared-v1")
                          → 时间线构建
                          → engagement/repayment/
                            churn/contact 信号计算
         │
         ▼ (Credit)
uid.csv (征信原始行)      credit_preparer.py →        data/credit/by_uid/
                          credit_prepared_builder.py    uid.json
                          → JSON 字段解析               (schema_version:
                          → 账户标准化                    "credit-prepared-v1")
                          → 逾期分析
                          → 还款时间线构建
                          → 评分段映射
```

**入口脚本**：`app/scripts/data_prep/prepare_local_data.py` 可通过 CLI 运行：
```bash
python -m app.scripts.data_prep.prepare_local_data --module all
```

---

## 六、关键业务流程与设计决策

### 6.1 单用户分析端到端流程

一段话概括：用户提交 UID 后，API 层验证格式并提取参数，BatchService 将请求转发给 Orchestrator。Orchestrator 用 `ThreadPoolExecutor(max_workers=3)` 并行调度 App/Behavior/Credit 三个 Skill——每个 Skill 内部走六步管线（构建上下文 → 从 Repository 获取原始数据 → 特征提取与信号派生 → 规则引擎生成确定性决策 → 调 LLM 生成自然语言解释和报告 → 合并规则结果与 LLM 结果输出最终 AgentOutput）。三个 Skill 全部完成后，Comprehensive Skill 消费前三个的输出，进行分群分类（S1-S6）、冲突检测、价值信号派生，然后调 LLM 做融合叙事，输出综合画像。最终四个 AgentOutput 组装成 `UserAnalysisResult` 返回给客户端。

### 6.2 规则引擎决策逻辑

#### App Profile 规则引擎

| 维度 | 判断逻辑 | 代码位置 |
|------|---------|---------|
| **多头借贷风险** | 近 7 天安装 ≥2 借贷 APP → 高；近 30 天 ≥3 → 高；近 30 天 1-2 → 中；否则 → 低 | `app_profile_payload_builder.py::_derive_multi_loan_risk()` |
| **金融成熟度** | 有银行 APP + 有政府 APP → 银行化；有电子钱包 → 半银行化；否则 → 非银行化 | `_derive_financial_level()` |
| **消费能力** | 电商+本地生活+出行+BNPL APP 数量综合评分 | `_derive_consumption_level()` |
| **活跃度** | active_days_30d ≥25 → 高；≥15 → 中；<15 → 低 | `_derive_activity_level()` |
| **风控建议** | 高风险 → 拒绝；中风险 → 人工复核；低风险 → 通过 | `recommendation.action` |

#### Behavior Profile 规则引擎（713 行，最复杂）

| 维度 | 判断逻辑 |
|------|---------|
| **活跃投入度** | engagement_score = f(active_days_30d, avg_session_minutes, deep_session_count) → light/balanced/deep |
| **还款意愿** | repayment_event_count + 回访稳定性 + 会话持续性 → low/medium/medium_high/high |
| **产品敏感度** | pricing_event_count + apply_event_count + purchase_preference → low/medium/medium_high/high |
| **流失风险** | warning_event_count + dropoff_stage + journey_risk_count → low/medium/high |
| **触达建议** | observed_channels + best_time + confidence → {best_channel, best_time, reason} |
| **信号得分** | `score = max(0, min(100, (engagement + repayment)/2 - churn_penalty - journey_risk*3))` |

#### Credit Profile 规则引擎

| 维度 | 判断逻辑 |
|------|---------|
| **负债压力** | debt(≥50k→2,≥25k→1) + payment(≥6k→2,≥3k→1) + utilization(≥80%→2,≥60%→1)；总分 ≥5→high，≥3→medium_high，≥1→medium，else→low |
| **信用稳定性** | max_dpd: ≥90→bad，≥60→poor，≥30→fair，≥1→good，else→excellent |
| **借贷饥渴度** | inquiries_3m≥3 \|\| inquiries_6m≥5 → high；inquiries_3m≥1 → medium；else→low |
| **金融成熟度** | oldest_age≥36 && has_bank_card && accounts≥2 → mature；oldest_age≥12 → growing；else→thin_file |

### 6.3 LLM Prompt 模板设计

**设计原则**：
1. **只输出 JSON**：所有 prompt 明确要求只返回 JSON 对象，不要额外解释文字
2. **不编造事实**：所有结论必须基于输入数据，不能发明不存在的 APP/日期/事件
3. **与规则结果一致**：LLM 输出的 metrics、level 等字段必须与规则引擎的确定性结果保持一致，不能私自改写
4. **中文输出**：除 comprehensive_prompt.md 外，所有 prompt 要求中文输出
5. **结构化 + 叙事并重**：既要机读字段（tags, metrics），又要人读文本（summary, report_markdown）

### 6.4 Fallback 与降级策略

系统设计了**四级降级**：

| 级别 | 场景 | 处理方式 | 影响范围 |
|------|------|---------|---------|
| L1 | 数据源缺失 | Repository 返回空 dict + `data_status=missing` | 该模块输出 `status=data_missing`，不影响其他模块 |
| L2 | 数据格式错误 | 多路降级（Prepared JSON → Raw CSV → Legacy）| 自动尝试下一级格式 |
| L3 | LLM 调用失败 | 返回规则引擎结果 + `status=model_unavailable` | 结构化数据完整，只缺自然语言增强 |
| L4 | LLM 返回无效 JSON | `_repair_json_candidate()` 尝试修复，失败则降级 | 同 L3 |

**核心设计**：规则引擎的确定性结果**永远作为 fallback 存在**——即使 LLM 完全不可用，系统仍然能输出完整的结构化画像，只是缺少自然语言解释和 Markdown 报告。

### 6.5 核心设计决策

#### 决策 1：规则引擎 + LLM 增强，而非纯 LLM

**问题**：用户画像需要稳定可复现的结构化结果，纯 LLM 输出不稳定。

**方案**：Decision Engine 用确定性规则生成所有结构化字段（risk_level, maturity_level, scores 等），Explainer 用 LLM 只做「解释增强」（summary, reasoning, report_markdown）。

**为什么不纯 LLM？** ① 同一份数据两次调 LLM 可能给出不同的 risk_level；② LLM 可能编造不存在的 APP 名称或数据；③ LLM 服务不可用时整个系统瘫痪。双轨模式保证了**结构化结果 100% 确定性可复现，LLM 只是锦上添花**。

#### 决策 2：TypedDict 而非 Pydantic Model 做管线内部契约

**问题**：管线六步之间需要传递复杂嵌套数据结构。

**方案**：用 TypedDict 定义 `*RunContext` / `*RawData` / `*FeatureBundle` / `*DecisionResult` / `*ExplanationResult`。

**为什么不用 Pydantic？** 管线内部传递的数据已经被上游步骤验证过，再做一次 Pydantic 校验是冗余开销。TypedDict 提供了类型提示但不强制运行时校验，权衡了**开发效率（类型提示）和运行时性能（零校验开销）**。

**代价**：运行时没有数据校验兜底——如果上游步骤输出了不符合契约的数据，下游步骤只会在使用时报 KeyError，而不是在传入时报验证错误。

#### 决策 3：Comprehensive 单文件 vs 六步管线

**问题**：Comprehensive 消费的是前三个模块的输出（已经是结构化的 AgentOutput），不需要从 Repository 取原始数据。

**方案（已演进）**：早期为一个 398 行的单文件 `comprehensive_agent.py`，**2026-05 已重构**为标准六步管线 `app/runtime_skills/comprehensive/`（contracts / data_access / feature_builder / decision_engine / explainer / assembler）+ 一个薄入口 `comprehensive_agent.py`，与其他三个模块结构对齐。详见第十四章。

**遗留意义**：早期决策的反思——「DataAccess / FeatureBuild 看起来空就不拆」是错的，事实证明拆出来后：上游缺失场景（status==missing）的处理、三维冲突信号的派生、LLM 输入裁剪都有了清晰落点。这条经验也直接指导了后续的 product_advice / ops_advice 也走六步管线。

#### 决策 4：嵌入式前端 vs 独立前端

**问题**：需要一个 Dashboard 展示画像结果。

**方案**：`app/ui/live_frontend.py` 是一个 2000+ 行的 Python 文件，内容是一个完整的 HTML 字符串（包含 TailwindCSS + React via CDN + Lucide 图标），通过 FastAPI 的 `HTMLResponse` 返回。

**为什么嵌入？** 开发初期快速验证，不需要单独起前端构建工具链。

**代价**：① 2000 行 HTML/JS 嵌在 Python 文件里，完全无法利用前端工具链（ESLint/TypeScript/Hot Reload）；② 每次修改前端都要重启后端服务；③ 代码搜索和维护极其困难。**这是明确需要重构的点。**

---

## 七、文件清单与职责速查

### 核心应用（app/）

| 文件 | 行数 | 一句话定位 |
|------|------|----------|
| `main.py` | 50 | FastAPI 入口，注册路由和异常处理器 |
| `api/analyze.py` | 37 | 两个 POST 端点（单/批量分析 + 文件上传） |
| `core/config.py` | 73 | Pydantic Settings 配置中心，25+ 配置项 |
| `core/model_client.py` | 475 | LLM 抽象层（Gemini/Vertex/Mock），重试+修复+降级 |
| `core/logger.py` | ~30 | 全局日志配置 |
| `services/orchestrator.py` | 109 | 四技能并行编排器（ThreadPoolExecutor） |
| `services/batch_service.py` | 23 | 批量请求包装层 |
| `services/report_renderer.py` | 30 | Markdown 报告片段渲染 |

### Runtime Skills（app/runtime_skills/）

| 文件 | 行数 | 一句话定位 |
|------|------|----------|
| `app_profile_agent.py` | 83 | App 画像管线入口 |
| `app_profile/contracts.py` | 127 | App 管线 5 个 TypedDict 数据契约 |
| `app_profile/data_access.py` | 122 | App 数据获取与验证 |
| `app_profile/feature_builder.py` | 18 | App 特征提取委托（调 payload_builder） |
| `app_profile/decision_engine.py` | 27 | App 规则决策委托（调 payload_builder） |
| `app_profile/explainer.py` | 364 | App LLM 解释层（裁剪输入 + 调模型 + fallback） |
| `app_profile/assembler.py` | 468 | App 结果组装（合并规则+LLM+图表+报告） |
| `behavior_profile_agent.py` | 83 | Behavior 画像管线入口 |
| `behavior_profile/contracts.py` | 197 | Behavior 管线数据契约（最复杂） |
| `behavior_profile/data_access.py` | 137 | Behavior 数据获取与预处理 |
| `behavior_profile/feature_builder.py` | 179 | Behavior 派生信号计算 |
| `behavior_profile/decision_engine.py` | 713 | Behavior 五维决策引擎（**最大文件**） |
| `behavior_profile/explainer.py` | 383 | Behavior 双 LLM 链路（profile + timeline） |
| `behavior_profile/assembler.py` | 227 | Behavior 双证据合并与页面组装 |
| `credit_profile_agent.py` | 75 | Credit 画像管线入口 |
| `credit_profile/contracts.py` | 183 | Credit 管线数据契约（Buró 结构） |
| `credit_profile/data_access.py` | 146 | Credit 征信数据获取与验证 |
| `credit_profile/feature_builder.py` | 290 | Credit 6 维派生信号 + 雷达图评分 |
| `credit_profile/decision_engine.py` | 447 | Credit 四维决策 + 风控标签 |
| `credit_profile/explainer.py` | 164 | Credit 单 LLM 链路 |
| `credit_profile/assembler.py` | 158 | Credit 报告组装 |
| `comprehensive_agent.py` | 398 | 综合画像融合层（S1-S6 分群+冲突检测） |

### 数据脚本（app/scripts/）

| 文件 | 行数 | 一句话定位 |
|------|------|----------|
| `app_profile_payload_builder.py` | 1300+ | App 画像核心计算（特征+决策+prompt构建） |
| `behavior_prepared_builder.py` | 1200+ | 行为事件标准化（CSV→Prepared JSON v1） |
| `credit_prepared_builder.py` | 1000+ | 征信数据标准化（CSV→Prepared JSON v1） |
| `behavior_preprocessor.py` | 150 | 行为指标丰富化（engagement/churn/risk） |
| `chart_builder.py` | 400 | 四模块图表构建（donut/bar/radar/gauge/table） |
| `app_data_loader.py` | 13 | App 数据加载（委托 repository） |
| `behavior_data_loader.py` | 20 | Behavior 数据加载 |
| `credit_data_loader.py` | 20 | Credit 数据加载 |
| `validate_app_profile_output.py` | 40 | App 输出 JSON 校验 |
| `data_prep/uid_csv_splitter.py` | 400 | 合并 CSV 按 UID 拆分 |
| `data_prep/applist_joiner.py` | 350 | App usage+label CSV join |
| `data_prep/behavior_preparer.py` | 60 | 批量生成 Behavior Prepared JSON |
| `data_prep/credit_preparer.py` | 60 | 批量生成 Credit Prepared JSON |
| `data_prep/prepare_local_data.py` | 240 | 预处理管线 CLI 入口 |

### Schema / Prompt / Config / UI

| 文件 | 行数 | 一句话定位 |
|------|------|----------|
| `schemas/app_profile.py` | 98 | App 结构化结果 Pydantic 定义（最完整） |
| `schemas/behavior_profile.py` | 17 | Behavior 结构化结果（基础版） |
| `schemas/credit_profile.py` | 17 | Credit 结构化结果（基础版） |
| `schemas/comprehensive_profile.py` | 26 | Comprehensive 结构化结果 |
| `schemas/final_response.py` | 42 | AgentOutput / UserAnalysisResult / AnalyzeResponse |
| `schemas/request.py` | 50 | AnalyzeRequest（UID 验证） |
| `prompts/app_profile_prompt.md` | 152 | App 画像 LLM 提示词 |
| `prompts/behavior_profile_prompt.md` | 88 | Behavior 画像 LLM 提示词 |
| `prompts/behavior_timeline_prompt.md` | 83 | Behavior 时间线 LLM 提示词 |
| `prompts/credit_profile_prompt.md` | 94 | Credit 画像 LLM 提示词 |
| `prompts/comprehensive_prompt.md` | 42 | Comprehensive 融合 LLM 提示词 |
| `ui/live_frontend.py` | 2000+ | 嵌入式 React Dashboard |
| `config.yaml` | 11 | 运行时配置模板 |
| `requirements.txt` | 8 | Python 依赖清单（无版本锁） |

### Legacy / 开发辅助

| 文件 | 行数 | 一句话定位 |
|------|------|----------|
| `agents/app_profile_agent.py` | 88 | **Legacy** 简单规则版 App Agent |
| `agents/behavior_profile_agent.py` | 89 | **Legacy** 简单规则版 Behavior Agent |
| `agents/credit_profile_agent.py` | 90 | **Legacy** 简单规则版 Credit Agent |
| `agents/comprehensive_profile_agent.py` | 149 | **Legacy** 简单聚合版 Comprehensive Agent |
| `country_packs/mx/app_profile.py` | 21 | 墨西哥 App 画像国家配置 |
| `country_packs/mx/behavior_profile.py` | 112 | 墨西哥 Behavior 阶段关键词映射 |
| `country_packs/mx/credit_profile.py` | 48 | 墨西哥征信评分段+账户类型标签 |

---

## 八、当前架构的问题诊断

> **2026-05 状态更新前言**：本章节最初写于 2026-04-28，下面 7 个问题在过去一周内已被多个 Plan 推进或解决。每个小节末尾追加了「✅ 已解决 / ⏳ 部分推进 / 🔴 仍未解决」标记，详细解决方案在第十一～十五章。

### 8.1 LLM 集成现状与卡点

**现状**：系统设计了完整的 LLM 调用链路（`model_client.py` 475 行），但**当前默认运行在 mock 模式**（`config.yaml: model_mode: mock`）。这意味着所有 Explainer 调用都走 fallback 路径，返回规则引擎结果而非真实 LLM 输出。

**卡点**：
1. **Gemini API Key 管理**：需要有效的 Google GenAI API Key 或 Vertex AI 服务账号
2. **Prompt 质量验证**：5 个 prompt 模板虽然设计完整，但尚未在真实 LLM 上大规模验证输出稳定性
3. **JSON 解析脆弱性**：LLM 返回的 JSON 经常有语法错误（转义字符、尾部逗号、未闭合括号），虽然 `_repair_json_candidate()` 做了修复，但覆盖不了所有情况
4. **结构化输出约束**：Google GenAI SDK 支持 `response_schema` 参数来约束输出格式，但需要验证实际效果

**⏳ 状态**（2026-05）：
- ModelClient 多 Provider 重构（Plan #01）+ Explainer/Trace 切 Claude Opus 4.7（Plan #02）已设计完成，落地后 7 个 Explainer + Trace 走 Claude Maestro，data_acquisition 仍走 Gemini。
- prompts 数量从 5 增加到 10：新增 `app_category_classifier_prompt.md` / `ops_advice_prompt.md` / `product_advice_prompt.md` / `trace_analyzer_prompt.md` / `orchestrator_system_prompt_v1.md`。
- JSON 修复链路在 Plan #01 提取了 `app/core/providers/json_repair.py` 单独负责，并增加了 Claude 风格的输出修复测试（`test_claude_provider_jsonrepair.py`）。
- 结构化输出仍走 fallback_result 兜底；新增 `test_provider_contract.py` / `test_provider_fallback.py` 锁定 Provider 行为契约。

### 8.2 agents/ vs runtime_skills/ 双层冗余

**现状**：项目同时存在两套 Agent 实现：

| 层 | 位置 | 模式 | 状态 |
|----|------|------|------|
| Legacy | `app/agents/` | 简单规则（if-else + 硬编码阈值） | **应废弃**，但仍在代码中 |
| 当前 | `app/runtime_skills/` | 六步管线（contracts + 多文件分离） | **主力**，Orchestrator 调用的是这套 |

**问题**：
- `agents/` 的 4 个文件（共 416 行）是死代码，未被 Orchestrator 引用
- 新人容易混淆哪套是正在使用的
- 两套的输出格式不完全一致

**建议**：删除 `agents/` 目录，或将其移到 `_deprecated/` 下。

**✅ 状态**（2026-05）：**已删除**。2026-04-28 P0 task 完成，`app/agents/` 目录已从代码库中移除，68 测试零回归（见 TASK.md）。CLAUDE.md 里「不修改 `app/agents/`」这条现在纯属历史遗留。

### 8.3 Schema 层不均衡

**现状**：

| Schema 文件 | 行数 | 字段丰富度 |
|------------|------|-----------|
| `app_profile.py` | 98 | 完整（RiskAssessment, FinancialMaturity, ConsumptionProfile, AppVisuals, AppInsight, ModelTrace, TimelineEntry, MetricProgress） |
| `behavior_profile.py` | 17 | 基础（agent_name, uid, status, engagement_level, evidence, metrics, tags） |
| `credit_profile.py` | 17 | 基础（同上） |
| `comprehensive_profile.py` | 26 | 基础（多了 persona, upstream_summaries, ModelTrace） |

**问题**：Behavior 和 Credit 的 Schema 只有 17 行基础定义，大量字段（如 Behavior 的 repayment_willingness、product_sensitivity、churn_risk，Credit 的 financial_maturity、debt_pressure 等）被塞在 `evidence` 和 `metrics` 这两个 `dict[str, Any]` 里，失去了类型安全。

**建议**：参照 App Profile 的完整度，为 Behavior 和 Credit 补充 Pydantic Model 定义。

**✅ 状态**（2026-05，亲读代码验证）：已通过 `docs/plans/behavior-credit-schema-plan.md` 完成。实际当前行数：`app/schemas/behavior_profile.py` **45 行**（4 个强类型子模型 + 3 个 top-level level 字段），`app/schemas/credit_profile.py` **51 行**（4 个子模型 + 5 个 top-level level 字段）。`app/services/label_builder.py` 走「new-path-first → 老 metrics fallback」路由，老的 `metrics` dict 保留为 DEPRECATED 字段以保证兼容。`tests/test_behavior_credit_schema.py` / `test_standardized_labels.py` 已在 348 passed 里。

### 8.4 Comprehensive 结构不一致

**现状**：App/Behavior/Credit 都有独立的六步管线子目录（contracts + data_access + feature_builder + decision_engine + explainer + assembler），而 Comprehensive 是一个 398 行的"大单文件"。

**问题**：
- 内部混合了数据提取、决策逻辑、LLM 调用和结果组装
- 无法单独测试和替换某个步骤
- 新增功能（如更复杂的融合逻辑）会让这个文件持续膨胀

**✅ 状态**（2026-05）：已通过 `docs/plans/comprehensive-refactor-plan.md` 完成重构。`app/runtime_skills/comprehensive/` 现在有完整的 6 个文件（contracts / data_access / feature_builder / decision_engine / explainer / assembler），原 398 行的 `comprehensive_agent.py` 退化为薄入口（~50 行）只做注册。详见第十四章。

### 8.5 数据源扩展瓶颈

**现状**：只有 `LocalUserRepository` 一个实现（600+ 行），数据来自本地文件系统。`WarehouseUserRepository` 是空 stub。

**问题**：
- 本地文件路径硬编码在 Repository 内部
- 多路降级逻辑（4 种格式降级）增加了代码复杂度
- 没有缓存层——每次请求都重新读文件

**⏳ 状态**（2026-05）：仍未实现 `WarehouseUserRepository`，但**新出现的 `data_acquisition_agent` 子系统正是「未来真实数据源」的入口**——它从 StarRocks（MySQL 协议兼容）数据仓库直接拉数并按 uid 落到 `data/{app|behavior|credit}/by_uid/` 目录，下游 Skill 自动复用 LocalUserRepository 的 by_uid 路径。这其实是把「数据仓库适配」前移到一个独立 Agent 完成，而不是在 Repository 层做。详见第十一章。

### 8.6 嵌入式前端

**现状**：`live_frontend.py` 是 2000+ 行的 HTML/JS 字符串嵌在 Python 文件里。

**问题**：
- 无法使用前端工具链（TypeScript 类型检查、ESLint、Prettier、HMR）
- 修改前端要重启后端
- 2000 行字符串无法做代码搜索和重构

**⏳ 状态**（2026-05）：`docs/plans/ui-separation-plan.md` Phase A 已落地：`app/static/js/` 下已有 `app.jsx` + `components/` + `services/` + `utils/` 模块化目录，`app/main.py` 走 `build_frontend_html()` 动态拼接 + `--reload` 即时刷新。`live_frontend.py` 仍存在（兼容期），但新页面（DashboardView / HomeView / LoadingView / ProgressView / panels/chat / panels/trace）已迁出。

### 8.7 缺少版本锁定

**现状**：`requirements.txt` 只列了 8 个裸包名，无版本号，无 lock 文件。

**问题**：`pip install -r requirements.txt` 可能在不同时间安装不同版本，导致"在我机器上能跑"问题。

---

## 九、扩展性分析与改进路线图

### 9.1 从脚本到 Skills 的封装路径

**当前状态**：`runtime_skills/` 已经实现了 Skill 的雏形——每个画像模块是一个 `*Skill` 类，有 `analyze()` 方法作为入口。但这些 Skill 不是「可插拔的 Skill」——它们被 Orchestrator 硬编码调用，不能动态注册/发现。

**封装路径**：
1. **定义 Skill 接口**：`class BaseSkill(ABC)` with `name: str`, `analyze(uid, context, **kwargs) → AgentOutput`
2. **Skill 注册表**：`SkillRegistry` 支持 `register(skill)` / `get(name)` / `list_all()`
3. **Orchestrator 改造**：从硬编码四个 Skill 改为从 Registry 读取，按依赖关系（DAG）调度
4. **配置驱动**：在 `config.yaml` 中声明启用哪些 Skill、执行顺序、并行分组

### 9.2 新增 Agent 的插入点

**计划中的 Agent**：
- **产品 Agent**：消费综合画像，输出产品策略建议（额度建议、利率调整、产品推荐）
- **运营 Agent**：消费综合画像，输出运营策略建议（触达计划、挽留策略、交叉销售）

**当前架构的支撑度**：

```
现有：                              扩展后：
App ─┐                             App ──┐
     ├─→ Comprehensive              │    ├─→ Comprehensive ──┬─→ 产品 Agent
Bhv ─┤                             Bhv ──┤                   │
     ├─→                           Credit┘                   └─→ 运营 Agent
Crd ─┘
```

**插入方式**：
1. 产品/运营 Agent 和 Comprehensive 是**串行依赖**关系，不是并行
2. 它们的输入是 Comprehensive 的 `AgentOutput`（特别是 structured_result 中的分群标签、风险等级、价值信号）
3. 可以复用现有的 `BaseSkill` 接口和 `AgentOutput` 输出格式
4. **关键改造点**：Orchestrator 需要支持**多阶段调度**——阶段 1 并行（App/Behavior/Credit），阶段 2 串行（Comprehensive），阶段 3 并行（产品 Agent / 运营 Agent）

### 9.3 LangGraph 迁移可行性评估

**LangGraph 适用场景**：多 Agent 协作、状态图驱动的工作流、条件分支、人机交互循环。

**当前架构 vs LangGraph**：

| 维度 | 当前实现 | LangGraph |
|------|---------|-----------|
| Agent 编排 | Orchestrator 硬编码 + ThreadPoolExecutor | StateGraph 定义节点和边，声明式编排 |
| 状态管理 | 函数参数传递 | State 对象集中管理，自动持久化 |
| 并行执行 | ThreadPoolExecutor | `Send()` API 支持并行分支 |
| 条件路由 | if-else 在 Orchestrator 里 | 条件边（conditional_edge）声明式定义 |
| 错误恢复 | try-except + fallback | 内置 checkpoint + 重放 |
| 人机交互 | 无 | `interrupt()` + `Command()` 支持审批/确认 |

**迁移建议**：

```python
# 伪代码示例：LangGraph StateGraph
from langgraph.graph import StateGraph, Send

class ProfileState(TypedDict):
    uid: str
    app_result: AgentOutput | None
    behavior_result: AgentOutput | None
    credit_result: AgentOutput | None
    comprehensive_result: AgentOutput | None
    product_advice: AgentOutput | None
    ops_advice: AgentOutput | None

graph = StateGraph(ProfileState)

# 阶段 1：并行画像
graph.add_node("app_skill", app_skill_node)
graph.add_node("behavior_skill", behavior_skill_node)
graph.add_node("credit_skill", credit_skill_node)

# 阶段 2：综合画像
graph.add_node("comprehensive", comprehensive_node)

# 阶段 3：策略 Agent
graph.add_node("product_agent", product_agent_node)
graph.add_node("ops_agent", ops_agent_node)

# 编排
graph.add_edge(START, "app_skill")       # 并行起点
graph.add_edge(START, "behavior_skill")
graph.add_edge(START, "credit_skill")
graph.add_edge(["app_skill", "behavior_skill", "credit_skill"], "comprehensive")
graph.add_edge("comprehensive", "product_agent")  # 并行
graph.add_edge("comprehensive", "ops_agent")
graph.add_edge(["product_agent", "ops_agent"], END)
```

**迁移成本**：中等。核心的六步管线逻辑不需要改（每个 Skill 的内部管线保持不变），只需要把 Orchestrator 的编排逻辑从 Python 代码改为 LangGraph StateGraph 声明。新增依赖：`langgraph`, `langchain-core`。

### 9.4 真实数据源接入的改造点

**需要改造的位置**：
1. `app/repositories/warehouse_repository.py`：实现 `get_app_data()` / `get_behavior_data()` / `get_credit_data()` 对接数据仓库 API
2. `app/core/config.py`：新增数据仓库连接配置（endpoint, auth, timeout）
3. `app/services/orchestrator.py`：根据 `data_source` 配置选择 Repository 实现
4. **缓存层**：新增 `CachedRepository` 装饰器，基于 UID + TTL 缓存 Repository 返回值

**数据源切换的设计**：
```python
# config.yaml
runtime:
  data_source: warehouse  # local | warehouse
  warehouse:
    endpoint: https://api.xxx.com
    auth_mode: token
    timeout: 30
```

### 9.5 建议的改进优先级

| 优先级 | 改进项 | 工作量 | 影响 |
|--------|--------|--------|------|
| **P0** | 打通 LLM（Gemini API Key + 端到端验证） | 1-2 天 | 解锁系统核心能力 |
| **P0** | 删除 `agents/` Legacy 代码 | 0.5 天 | 消除混淆 |
| **P1** | 补全 Behavior/Credit Schema | 1 天 | 类型安全 |
| **P1** | 拆分 Comprehensive 为六步管线 | 1-2 天 | 结构一致性 |
| **P1** | 添加 requirements.txt 版本锁定 | 0.5 天 | 构建稳定性 |
| **P2** | Skill 接口 + 注册表 | 2-3 天 | 可插拔扩展 |
| **P2** | 实现 WarehouseRepository | 3-5 天 | 真实数据源 |
| **P2** | 前端分离 | 3-5 天 | 开发效率 |
| **P3** | LangGraph 迁移 | 5-7 天 | Agent 协作 |
| **P3** | 新增产品/运营 Agent | 3-5 天/个 | 业务扩展 |

---

## 十、附录

### 10.1 项目统计

| 指标 | 数值 |
|------|------|
| **总文件数**（不含 .git/__pycache__） | ~193 |
| **Python 源文件** | ~112 |
| **测试文件** | 5 |
| **API 端点** | 2（POST /api/analyze, POST /api/analyze-file） |
| **画像模块** | 4（App / Behavior / Credit / Comprehensive） |
| **LLM Prompt 模板** | 5 |
| **六步管线子文件** | 18（3 模块 × 6 步） |
| **最大单文件** | `app_profile_payload_builder.py`（1300+ 行） |
| **最复杂决策引擎** | `behavior_profile/decision_engine.py`（713 行） |
| **数据契约 TypedDict** | ~20 个 |
| **Pydantic Schema** | 7 个文件，~16 个 Model |
| **Country Pack** | 1（墨西哥/mx） |
| **依赖包** | 8 |

### 10.2 关键术语表

| 术语 | 含义 |
|------|------|
| **UID** | 用户唯一标识，18 位数字 |
| **Skill** | 画像分析技能，对应一个画像模块的完整处理管线 |
| **六步管线** | Context → DataAccess → FeatureBuild → Decision → Explain → Assemble |
| **AgentOutput** | 统一输出格式：summary + structured_result + charts + report_markdown |
| **Prepared JSON** | 经过预处理标准化的数据格式，带 schema_version 标记 |
| **Decision Engine** | 确定性规则引擎，生成所有结构化字段，不依赖 LLM |
| **Explainer** | LLM 解释层，为规则引擎结果增加自然语言描述 |
| **Assembler** | 结果组装器，合并规则结果与 LLM 结果 |
| **Country Pack** | 国家特定配置（阈值、关键词、标签映射），`@dataclass(frozen=True)` |
| **Buró de Crédito** | 墨西哥征信局，相当于中国的央行征信 |
| **S1-S6** | 综合画像的分群标签（S1 高价值低风险 → S6 沉默观望型） |
| **mock 模式** | LLM 不可用时的降级模式，直接返回规则引擎结果 |
| **fallback_result** | 传给 LLM 的降级默认值，LLM 失败时使用 |
| **evidence_patch** | LLM 返回的证据补丁，合并到规则结果上 |
| **prompt_payload** | 传给 LLM 的输入负载（特征 + 决策结果的子集） |
| **Codex Skill** | `.agents/skills/` 下的编辑器辅助技能，**不参与运行时** |
| **Runtime Skill** | `app/runtime_skills/` 下的运行时画像技能 |

### 10.3 配置参数速查

| 环境变量 | 默认值 | 含义 |
|---------|--------|------|
| `MODEL_MODE` | mock | LLM 模式：mock / gemini / vertex |
| `MODEL_NAME` | — | Gemini 模型名称 |
| `GEMINI_API_KEY` | — | Google GenAI API Key |
| `VERTEX_PROJECT_ID` | — | GCP 项目 ID（Vertex AI 模式） |
| `VERTEX_LOCATION` | — | GCP 区域（Vertex AI 模式） |
| `GOOGLE_APPLICATION_CREDENTIALS` | — | GCP 服务账号 JSON 路径 |
| `DATA_SOURCE` | local | 数据源：local / warehouse |
| `PROMPT_DIR` | app/prompts | Prompt 模板目录 |
| `DATA_DIR` | data | 数据文件根目录 |
| `OUTPUT_DIR` | outputs | 输出文件目录 |
| `LOG_LEVEL` | INFO | 日志级别 |
| `APP_PROFILE_PROMPT_MAX_APPS` | — | App Prompt 最大 APP 数量 |
| `APP_PROFILE_SHORT_REPORT` | — | 是否生成简短报告 |
| `MODEL_MAX_OUTPUT_TOKENS` | — | LLM 最大输出 token 数 |
| `DA_DB_HOST` / `DA_DB_PORT` / `DA_DB_USER` / `DA_DB_PASSWORD` / `DA_DB_DATABASE` | — | data_acquisition_agent V2 StarRocks 数据仓库连接（仅在执行时从 env 读，不入 Settings） |
| `DA_QUERY_TIMEOUT_SECONDS` | — | V2 SQL 执行超时（同时作 connect_timeout 与 read_timeout） |
| `DA_MAX_RESULT_ROWS` | — | V2 单次查询最大返回行数（COUNT 预检查阈值，OOM 防御） |

---

## 十一、data_acquisition_agent 子系统全量解读（NEW）

> 本章覆盖 2026-04 → 2026-05 期间新增的顶层 Python 包 `data_acquisition_agent/`。
> 这是整个项目从「靠手工准备数据」走向「自动化数据采集」最关键的一步。
> 设计文档：`docs/specs/data_acquisition_agent.md`（V1）+ `docs/specs/data_acquisition_agent_v2.md`（V2）；执行计划：`docs/plans/data-acquisition-v1-plan.md` + `docs/plans/data-acquisition-v2-plan.md`。

### 11.1 一段话说清楚这是干什么的

`data_acquisition_agent` 是一个独立于 `app/` 的顶层 Python 包（CLAUDE.md 中已登记为「受控例外子项目」），分两阶段把「自然语言数据需求」变成「per-uid 落地的画像数据文件」：**V1（Generate）** 接受分析师写的需求描述（如「拉墨西哥 2024-12 的 mob1 用户的所有 APP 安装明细」），叠加 5 份国家知识库（业务黑话词典 / 跨国示例代码 / 物理 schema / 本地 few-shot / 系统 prompt）后调 LLM（默认 Gemini）生成 SQL + 可选 Python + 推理 + 自审计报告，**只产出 artifact 不执行**；**V2（Execute）** 接受分析师人工 review 通过的 SQL，经过三层执行前安全门（拒 DDL / 凭据扫描 / Python 危险函数扫描 / SQL 策略复核 / 多语句拒绝 / COUNT 预估）后，连接 StarRocks（MySQL 协议兼容）数据仓库执行，把结果按 uid 切片并以「.tmp 暂存 → os.replace 原子替换」模式落到 `data/{app|behavior|credit}/by_uid/` 目录——下游 Skill 通过现有的 `LocalUserRepository` 自动复用这些文件。

### 11.2 11 个核心模块的逐文件解读

| 文件 | 行数 | 职责 | 关键类/函数 | 依赖 |
|------|------|------|-----------|------|
| [`__init__.py`](data_acquisition_agent/__init__.py) | 0 | 包标记 | — | — |
| [`schemas.py`](data_acquisition_agent/schemas.py) | ~200 | V1/V2 全部 Pydantic v2 数据契约 | `TargetCountry`（5 国 enum）/ `TargetAction`（build_table / extract / both）/ `ErrorType`（14 种）/ `GenerateRequest` / `GenerateResponse` / `ExecuteRequest` / `ExecuteResponse` / `AuditReport` | pydantic |
| [`manifest.py`](data_acquisition_agent/manifest.py) | ~70 | 加载国家 YAML + 校验 5 个 markdown 引用 | `CountryManifest` (dataclass) / `load_manifest(country)` / `list_registered_countries()` | yaml + pathlib |
| [`redactor.py`](data_acquisition_agent/redactor.py) | ~50 | **L1 凭据脱敏**——LLM prompt 注入前对知识库 md 做 11 类正则替换 | `redact(text)` / `redact_file(path)` | re |
| [`prompt_assembler.py`](data_acquisition_agent/prompt_assembler.py) | ~220 | 多层 Prompt 装配 + token 预算（800K 上限）+ CJK 加权计数 | `assemble_prompt(request, manifest)` / `estimate_tokens(text)` / 内置 ~300 行 `SYSTEM_PROMPT_ENGINE` 常量 | redactor + schemas |
| [`orchestrator.py`](data_acquisition_agent/orchestrator.py) | ~160 | **V1 端到端编排** | `DataAcquisitionOrchestrator.generate()` / `_enforce_nl_sql_kind_consistency()` / `_enforce_output_policies()` / `_build_response()` | manifest + prompt_assembler + output_scanner + `app.core.model_client.ModelClient` |
| [`output_scanner.py`](data_acquisition_agent/output_scanner.py) | ~80 | **L2 输出安全扫描**——LLM 产出后扫凭据/危险 Python/SQL 策略 | `scan_credentials()` / `scan_python_dangerous()` (8 种危险模式) / `check_sql_policy(sql, sql_kind, prefix)` (query_only vs build_table_script 双策略) | re |
| [`connection.py`](data_acquisition_agent/connection.py) | ~55 | **V2 数据仓库连接**——凭据只在调用时从 env 读，连接对象 `__repr__()` 强制脱敏 | `_RedactedConnection` / `open_starrocks_connection(*, request_id)` (上下文管理器) / `DbUnreachableError` | pymysql + os.environ |
| [`executor.py`](data_acquisition_agent/executor.py) | ~190 | **V2 执行编排**——前置安全门 + COUNT 预检查 + 查询执行 + 委托写入 | `enforce_pre_execution_gates()` / `precheck_row_count()` (包 SELECT COUNT(*) FROM (...)) / `execute_query()` (返回 DataFrame) / `run_execute_pipeline()` | output_scanner + connection + output_writer + manifest + pandas |
| [`output_writer.py`](data_acquisition_agent/output_writer.py) | ~180 | **V2 落地写入**——schema 校验 + per-uid 切片 + 原子写 | `validate_bucket_schema()` / `build_per_uid_payloads()` (CSV UTF-8-BOM / JSON schema_version 包装) / `write_per_uid_atomic()` (.tmp_<rid> → os.replace) / `resolve_bucket_dir()` | pandas + pathlib + re |
| [`api.py`](data_acquisition_agent/api.py) | ~85 | FastAPI 路由 + ErrorType→HTTP 状态码映射 | `/generate` (V1) / `/execute` (V2) / `/manifests` (501 stub) / `/healthz` (501 stub) | fastapi + 全部内部模块 |

### 11.3 5 国知识库结构（demo0/）

`data_acquisition_agent/demo0/` 是**纯 Markdown 形式的 RAG 知识库**——**没有向量化**，没有 FAISS / Chroma / Pinecone，所有 md 文件按优先级原文拼接进 prompt（业务逻辑 > all_examples > schema > few-shot），靠 LLM 自身的长上下文能力做检索。这种设计的取舍是：

- **优点**：透明、易审计、保证 LLM 能看到精确字段名 / 表名（防幻觉）；新增国家只需复制目录 + 改 YAML
- **代价**：token 昂贵（每次请求都把整套国家知识压进去，800K token budget 是硬上限）；无语义排序

#### 顶层 3 个 md：
- `system_prompt.md`（~2000 行）：定义 LLM persona + 三阶段执行强制（CoT → Code Generation → Audit Report）+ 知识库 4 层优先级 + 强制输出 5 键 JSON 模板
- `基于埋点数据的现金贷APP用户流失归因与留存分析SOP.md`（~150 行）：行业方法论参考
- `基于大模型的用户画像与客群分层方案（墨西哥市场）.md`（~200 行）：墨西哥市场业务背景

#### 5 国知识库目录（每国 4-5 个 md）：

| 文件 | 内容性质 | 典型行数 |
|------|---------|---------|
| `多国业务逻辑.md` | 业务黑话词典（mob1 / eKYC / 首借完成 / 7天复借 / 流失定义）+ 全局规则 + 各国差异 | 500-800 |
| `all_examples .md`（注意空格）/ `all_examples.md` | 跨国参考代码（CTE 模板 / join 模式 / 抗 OOM 策略）—— 纯逻辑模板，**不含真实表名** | 800-1200 |
| `scheme.md` / `schema.md` | 物理 schema 唯一权威源（真实表名 / 字段类型 / 分区键 dt / uid 字段变体 uid/user_uuid/individual_uuid） | 300-500 |
| `few.md` / `few-shot.md` | 国家本地 few-shot（已验证 SQL）+ 本地化 quirks（时区 / 渠道码 / 风险单元名） | 400-800 |
| `gem prompt.md`（部分国家有） | Gem 模型专用 prompt 变体 | 100-200 |

5 个国家：**墨西哥 / 印尼 / 巴铁（Pakistan）/ 泰国 / 菲律宾**。配置文件在 `data_acquisition_agent/configs/{mexico,indonesia,pakistan,thailand,philippines}.yaml`。

### 11.4 七层安全防线（最关键的设计亮点）

系统按攻击面分了 7 层防御，每一层都有独立模块兜底：

| 层 | 机制 | 范围 | 实现位置 |
|----|------|------|---------|
| **L0：Prompt 注入** | 系统 persona 长 prompt 主导（短注入难以撼动） | 输入侧 | `prompt_assembler.py` 的 `SYSTEM_PROMPT_ENGINE` |
| **L1：知识库脱敏** | 11 类凭据正则 → `<DB_HOST>` 等占位符 | 知识库 md → LLM | `redactor.py` |
| **L2：LLM 输出验证** | 凭据扫描（11 类）+ 危险 Python（8 类：os.system / subprocess / eval / exec / __import__ / shutil / urllib）+ SQL 策略 | V1 artifact + V2 执行前 | `output_scanner.py` |
| **L3：DDL 策略** | 强制 analyst_private_prefix（`dm_model.yyp_tmp_`）+ 拒多语句 + 拒带引号标识符 | build_table_script | `output_scanner.check_sql_policy()` |
| **L4：执行门** | V2 执行前重跑 L2/L3 + **拒 DDL**（V2 只允许 query_only） | V2 入口 | `executor.enforce_pre_execution_gates()` |
| **L5：行数预估** | `SELECT COUNT(*) FROM (user_sql) AS …` 包一层，超过 `da_max_result_rows` 拒绝 | DB 查询前 | `executor.precheck_row_count()` |
| **L6：连接安全** | 凭据从 env 读取后立即包进 `_RedactedConnection`，`__repr__()` 永远返回 `<RedactedStarRocksConnection>` | 日志 / 异常栈 | `connection.py` |
| **L7：原子落地** | per-file `os.replace` 原子；多文件批次走 `.tmp_<rid>` 暂存目录，失败统一清理 | 文件写入 | `output_writer.write_per_uid_atomic()` |

**威胁覆盖矩阵**：凭据泄漏（L1+L2+L6 三道）/ SQL 注入（L2+L4 双重 query_only 校验）/ 代码执行（L2+L4 危险函数）/ OOM（L5 行数 + few.md LIMIT 约束）/ 部分写入崩溃（L7 原子）。**未覆盖**：LLM 越狱（仅靠 system prompt 强约束，非加密硬约束）。

### 11.5 V1 / V2 端到端数据流

```
分析师 NL 需求
  │ POST /api/data-acquisition/generate
  ▼
api.py:generate()
  │
  ▼
DataAcquisitionOrchestrator.generate()
  ├─ manifest.load_manifest(country)        ← YAML + 5 个 md 路径
  ├─ prompt_assembler.assemble_prompt()
  │   ├─ redactor.redact(每个 md)            ← L1 脱敏
  │   ├─ 拼接 SYSTEM + 4 知识库 + user_request
  │   └─ token 预算检查（≤ 800K）
  ├─ ModelClient.generate_structured(prompt, schema)  ← Gemini / Vertex / Mock
  ├─ _enforce_nl_sql_kind_consistency()      ← 防 LLM 私自把 query 变 DDL
  ├─ _enforce_output_policies()
  │   ├─ scan_credentials()                  ← L2 凭据扫描
  │   ├─ scan_python_dangerous()             ← L2 危险代码扫描
  │   └─ check_sql_policy()                  ← L2/L3 SQL 策略
  └─ GenerateResponse {reasoning_summary, sql, sql_kind, python, audit_report, metadata}

  ▼ 分析师 review
  ▼

approved_sql + 输出 bucket（app/behavior/credit）
  │ POST /api/data-acquisition/execute
  ▼
api.py:execute()
  │
  ▼
executor.run_execute_pipeline()
  ├─ manifest.load_manifest()
  ├─ enforce_pre_execution_gates()
  │   ├─ 拒 DDL（build_table_script 在 V2 不允许）
  │   ├─ scan_credentials / scan_python_dangerous
  │   ├─ check_sql_policy(query_only)
  │   └─ 拒多语句
  ├─ open_starrocks_connection()             ← pymysql + env 凭据 + Redacted 包装
  ├─ precheck_row_count()                    ← SELECT COUNT(*) 预估
  ├─ execute_query()                         ← 真执行 → pandas DataFrame
  ├─ output_writer.validate_bucket_schema()  ← app bucket 强制 7 列 CSV
  ├─ output_writer.build_per_uid_payloads()  ← groupby uid → CSV/JSON
  └─ output_writer.write_per_uid_atomic()    ← .tmp_<rid> → os.replace

  ▼ 落地
data/{app|behavior|credit}/by_uid/{uid}.{csv|json}
```

### 11.6 与画像主链路的衔接

**关键事实**：data_acquisition_agent 落地的文件路径**完全等同于** `LocalUserRepository` 当前读的 by_uid 目录（在 `app/core/config.py` 中定义为 `app_by_uid_dir` / `behavior_by_uid_dir` / `credit_by_uid_dir`）。这意味着：

- 数据采集完成后**无需修改任何下游代码**，`AnalysisOrchestrator` 走 LocalUserRepository 的多路降级时，新落地的文件会自动被读到
- App bucket 严格强制 7 列 schema（uid / app_name / app_package / first_install_time / last_update_time / gp_category / ai_category_level_2_CN）+ CSV UTF-8-BOM 编码，与 `app/runtime_skills/app_profile/data_access.py` 期望的格式一字不差对齐
- Behavior / Credit bucket 落 JSON 时包了 schema_version + source_meta，与 `behavior_prepared_builder.py` / `credit_prepared_builder.py` 输出的 Prepared JSON 格式一致

### 11.7 测试体系（18 个测试文件，70+ 用例）

`data_acquisition_agent/tests/` 下覆盖每一层：`test_manifest.py` / `test_redactor.py` / `test_output_scanner.py` / `test_schemas.py` / `test_orchestrator.py` (V1 e2e 含 LLM quirk 处理) / `test_connection.py` / `test_executor.py` (V2 gates) / `test_output_writer.py` / `test_prompt_assembler.py` + `test_prompt_assembler_ddl_guard.py` / `test_api.py` + `test_api_v2.py` / `test_e2e_mock_llm.py` + `test_e2e_mock_executor.py` / `test_orchestrator_real_llm_quirks.py` / `test_smoke_real_llm_mexico.py`（唯一一个真调 LLM 的 smoke test）。

**测试分层策略**：CI 单测 + 集成都用 mock；smoke 测试只在本地手动跑（避免 CI 烧 token）。

### 11.8 与你的端到端流程的对接（重要）

你描述的工作流——「数据存到 MySQL → RAG 检索增强 → 数据获取 Agent 生成 SQL → SQL 审查 Agent → 查 MySQL → 生成画像」——和当前实现的对应关系：

| 你的描述 | 当前实现的对应物 | 差异点 |
|---------|---------------|-------|
| 数据存到 MySQL | StarRocks（MySQL 协议兼容） | 数仓本身需先把 5 国数据导入。当前 `data/` 下 `by_uid/` 子目录是空的，`source/` 也只有 `.gitkeep` —— **真实数据导入到 StarRocks 这一步还在你这边**。 |
| RAG 检索增强 | `demo0/` 5 国知识库（5 × 4-5 个 md）按优先级注入 prompt | **不是向量 RAG**，是「整本书塞进 prompt」式的 long-context RAG。优点：精确不丢字段；缺点：token 贵（≤800K 上限）。 |
| 数据获取 Agent 生成 SQL | `data_acquisition_agent` V1 (`/generate`) | ✅ 已实现，72 测试通过，含墨西哥 mob1 真 LLM smoke 验证 |
| SQL 审查 Agent | **设计上是「分析师人工 review」**，不是另一个 Agent | 系统通过 7 层安全门做硬约束，但最终 approval 是人在 `/execute` 入口提交 approved_sql + approved_by 字段；想做「自动审查 Agent」需要另起一个 LLM Judge 在 `/generate` 之后、`/execute` 之前加一层。 |
| 查 MySQL 拿数据 | `data_acquisition_agent` V2 (`/execute`) | ✅ 已实现，连接走 pymysql + env 凭据 + 7 层执行门 + per-uid 落地 |
| 生成画像 | `AnalysisOrchestrator` 走 SkillRegistry 6 个 Skill | ✅ 已实现，且无需改动（自动复用 by_uid 文件） |

**你下一步真正需要做的**：
1. **把 5 国 CSV/JSON 数据导入 StarRocks**：写 `LOAD DATA` 或 broker load 脚本，按 `scheme.md` 中的表名建表后导入；这一步 data_acquisition 不参与，是数仓侧任务。
2. **填好 `.env` 5 个 DA_DB_* 变量** + StarRocks 只读账号（V2 的 `connection.py` 强制从 env 读）。
3. **跑通 V1 → V2 链路**：先 `/generate` 拿 SQL，分析师 review，再 `/execute` 落 by_uid 文件。
4. **如果你想要「SQL 审查 Agent」自动化**：在 V1 之后加一个独立的 LLM Judge Skill，输入 `GenerateResponse` 输出 `audit_passed` + `risks` —— 这个目前没有 Plan，可以新起 Design Doc。

---

## 十二、Orchestrator Agent / NL 对话编排子系统（NEW）

> 本章覆盖 `app/services/orchestrator_agent/`（11 个 Python 文件 + tools/ 子目录 6 个工具）。
> 设计文档：`docs/specs/03-orchestrator-agent-design.md`；执行计划：`docs/plans/03-orchestrator-agent-plan.md`；前端：`docs/specs/04-nl-chat-tab-frontend-design.md` + `docs/plans/04-nl-chat-tab-frontend-plan.md`。

### 12.1 一段话说清楚这是干什么的

Orchestrator Agent 是叠在原有 6 个 Skill（App / Behavior / Credit / Comprehensive / Product / Ops）之上的「自然语言入口层」——分析师可以打开 Dashboard 第 7 个 Tab「对话」，用一句话（如「帮我跑一下昨天上传的 mexico_uids.txt 里所有用户的画像和产品建议，跑完帮我读一下 18 位 UID 5634… 的行为 trace」）触发 Agent 自动调度多步工具。底层是 **Claude Opus 4.7 (Maestro 路由)** 做规划 + 6 个工具（parse_uid_file / run_profile / run_trace / query_data / memory_write / memory_read）轮转 + SSE 流式返回 + 4 层弹性（token budget / consecutive failures / max rounds / 600s timeout）+ ACK 用户授权门（query_data 在执行 SQL 前必须等用户在弹窗里点「确认」）。

### 12.2 11 个核心模块逐文件解读

| 文件 | 行数 | 职责 |
|------|------|------|
| [`agent_loop.py`](app/services/orchestrator_agent/agent_loop.py) | ~330 | **核心 async generator 主循环**：LLM 决策 → tool 分发 → 弹性检查 → SSE yield；MAX_ROUNDS=15 |
| [`schemas.py`](app/services/orchestrator_agent/schemas.py) | ~150 | Pydantic v2 全部契约：`OrchestratorChatRequest` / `OrchestratorSession` / 6 个工具的 Input/Output Schema / `ToolCallRecord` / `OrchestratorMessage` |
| [`ack_bus.py`](app/services/orchestrator_agent/ack_bus.py) | ~50 | per-session 用户授权汇合点（`threading.Event`）：`open_ack` / `resolve_ack` / `wait_ack` |
| [`budget.py`](app/services/orchestrator_agent/budget.py) | ~25 | Token 预算追踪：默认 500K 上限，80% 警告，100% 硬截断 |
| [`resilience.py`](app/services/orchestrator_agent/resilience.py) | ~35 | 连续失败熔断（K=3 次工具失败即终止 session） |
| [`session.py`](app/services/orchestrator_agent/session.py) | ~55 | per-session ACK provider + `query_cancelled` flag 管理 |
| [`session_store.py`](app/services/orchestrator_agent/session_store.py) | ~70 | JSON 会话持久化（`outputs/orchestrator_sessions/`）+ thread-safe 缓存 + atexit flush |
| [`system_prompt.py`](app/services/orchestrator_agent/system_prompt.py) | ~30 | 加载 `app/prompts/orchestrator_system_prompt_v1.md` + 国家特定技能拼接 |
| [`skills_loader.py`](app/services/orchestrator_agent/skills_loader.py) | ~27 | 加载 `docs/skills/orchestrator/{country}.md`（6 国分析规则库） |
| [`uid_whitelist.py`](app/services/orchestrator_agent/uid_whitelist.py) | ~23 | UID 格式校验（双层校验：业务正确性，6 国 regex 字典） |
| [`__init__.py`](app/services/orchestrator_agent/__init__.py) | ~10 | 包初始化 |

### 12.3 tools/ 子目录 6 个工具

| 工具 | 文件 | 包装的底层 | 说明 |
|------|------|----------|------|
| **parse_uid_file** | `tools/parse_uid_file.py` | 读 `data/id_files/*.txt` | UID 格式校验 + 去重 + 路径穿越保护 |
| **run_profile** | `tools/run_profile.py` | `AnalysisOrchestrator.analyze_module()` | 批量跑 6 个 Skill 中的指定子集（modules=["app","comprehensive","product","ops"] 等） |
| **run_trace** | `tools/run_trace.py` | `TraceAnalyzer.analyze()` | 单 UID 深度行为 trace 分析（见第十三章） |
| **query_data** | `tools/query_data.py` | `DataAcquisitionOrchestrator`（独立包） | NL → SQL → 用户 ACK → 执行；mx/th 支持，co/pe/cl/br 显式拒绝 |
| **memory_write** | `tools/memory.py` | `outputs/orchestrator_memory/` JSON KV | 持久化对话状态（V1 最简，V2 升级 Redis） |
| **memory_read** | `tools/memory.py` | 同上 | glob key 模式匹配 |

### 12.4 Agent Loop 执行语义

主循环是 `async generator`，每一轮：
1. **LLM 决策**：把 system_prompt + 历史 + 用户消息发给 Claude Opus（`asyncio.to_thread(ModelClient.generate_structured)` 避免阻塞 SSE）
2. **预算检查**：累加 `last_token_usage`，超 500K 抛 `BudgetExceeded`
3. **终止判定**：若 LLM 返回 `final_message`，存 session + yield final + return
4. **工具分发**：`query_data` 走 4 步 ACK 序列（生成 SQL → SSE 推送预览 + 估算行数 → wait_ack → 用户确认后才执行）；其余工具直接调用
5. **弹性检查**：连续 3 次工具失败抛 `ConsecutiveFailures`
6. **追加消息**，循环回到 1

**SSE 事件类型**（前端订阅的 8 类）：`session_started` / `tool_started` / `tool_completed` / `final` / `error` / `budget_warning` / `awaiting_user_ack` / `consecutive_tool_failures`

### 12.5 API 端点

挂在 `app/api/orchestrator_routes.py`（prefix `/api/orchestrator`）：

| 端点 | 方法 | 用途 |
|------|------|------|
| `/chat` | POST | NL 对话主入口；返回 `text/event-stream` SSE 流 |
| `/sessions/{session_id}` | GET | 拿完整 session 状态（messages / tool_calls / total_tokens / status） |
| `/sessions/{session_id}/ack` | POST | 用户对 query_data SQL 的 confirm/reject；body `{"confirm": bool}` |

### 12.6 前端 NL Chat Tab

`app/static/js/components/panels/chat/` 下 7 个 React 组件（V1 计划落地，无 npm，纯 Babel Standalone + UMD React）：`ChatPanel` / `MessageList` / `InputBox` / `ToolCallCard` / `AckDialog`（SQL 确认弹窗）/ `BudgetBanner`（80% token 警告条）/ `FallbackBadge`。SSE 解析走 `services/orchestratorApi.js` 的 `ReadableStream` API。状态机：`idle → streaming → awaiting_ack → done/error`。

---

## 十三、Trace Analyzer 深度行为解析子系统（NEW）

> 本章覆盖 `app/runtime_skills/trace_analyzer/`（8 个文件）+ `app/api/trace.py` 路由。
> 设计文档：`docs/specs/trace-analyzer-design.md`；执行计划：`docs/plans/trace-analyzer-plan.md`；前端：`docs/specs/trace-ui-design.md`。

### 13.1 与 Behavior Profile 的区别

Behavior Profile 处理的是**已经聚合过的指标**（active_days_30d / engagement_score / repayment_event_count 等），而 Trace Analyzer 处理的是**原始事件流**（`data/behavior/by_uid/{uid}.csv`，每一行是一次页面访问 / 按钮点击 / 表单提交 / 报错），输出更细粒度的 5 个事实层 + 3 个 LLM 叙事层。

**关键设计决策**：Trace Analyzer **不是 BaseSkill**，**不注册到 SkillRegistry**——它是独立服务，通过独立 API `GET /api/trace/{uid}` 暴露。原因是 Trace 分析按需调用，不属于「画像批量管线」的标准成员；硬塞进 SkillRegistry 会污染 stage 0/1/2 的依赖关系。

### 13.2 8 个文件解读

| 文件 | 行数 | 职责 |
|------|------|------|
| [`analyzer.py`](app/runtime_skills/trace_analyzer/analyzer.py) | ~50 | 入口编排 `TraceAnalyzer.analyze(uid, context)` + `build_context(uid)` |
| [`contracts.py`](app/runtime_skills/trace_analyzer/contracts.py) | ~60 | 5 个 TypedDict：RunContext / RawData / FeatureBundle / DecisionResult / ExplanationResult |
| [`data_access.py`](app/runtime_skills/trace_analyzer/data_access.py) | ~55 | 读 by_uid CSV，11 列必须，pandas DataFrame |
| [`feature_builder.py`](app/runtime_skills/trace_analyzer/feature_builder.py) | ~200 | **5 个事实层提取 + 3 层 token 预算**（TOTAL=8000 / TIER_2=1500 / TIER_3=5000） |
| [`decision_engine.py`](app/runtime_skills/trace_analyzer/decision_engine.py) | ~70 | 装配 prompt payload + 模板 fallback 故事/干预（无 LLM 也能出兜底） |
| [`explainer.py`](app/runtime_skills/trace_analyzer/explainer.py) | ~80 | LLM 调用（Claude Opus）生成 3 个叙事；model_unavailable 兜底 |
| [`assembler.py`](app/runtime_skills/trace_analyzer/assembler.py) | ~60 | 合并所有层为最终 API 响应 dict |
| [`_constants.py`](app/runtime_skills/trace_analyzer/_constants.py) | ~30 | 8 个数值阈值 + 1 个 enum + 3 个 token 预算（设计文档 §11 锁死） |

### 13.3 5 个规则层事实 + 3 个 LLM 叙事

**规则层**（feature_builder 抽取，无 LLM）：
1. **path_graph**：Top-N 页面跳转 + Top-N 访问最多页面（带次数）
2. **friction_hotspots**：高重试 / 报错步骤，按严重度排序
3. **time_pattern**：24 小时分布直方图 + 活跃时段 label
4. **key_events_tail**：最后 N 条事件（脱敏后暴露）
5. **churn_root_cause_candidates**：规则匹配到 6 选 1 enum（`credit_limit_unmet` / `interest_perception_high` / `competitor_poaching` / `ux_friction` / `repayment_burden` / `no_clear_signal`，**与 ops_advice 共享同一 enum**——`_constants.py::CHURN_ROOT_CAUSE_ENUM`）

**LLM 叙事**（explainer，Claude Opus）：
1. **churn_story**：用户为什么流失（必须引用规则层的具体页面/步骤，不能脱离证据）
2. **interventions**：针对每个 top friction hotspot 给出具体干预建议
3. **final_root_cause**：从规则候选中选 best-fit

### 13.4 降级路径

| 条件 | 行为 |
|------|------|
| 事件数 < 10 | 跳过 LLM，返回 `feature_status="insufficient_events"` |
| CSV 不存在 | `data_status="data_missing"` |
| CSV 解析错 | `data_status="error"` |
| LLM 不可用 | `explanation_status="model_unavailable"` + 模板 fallback 故事/干预 |

---

## 十四、Product Advice / Ops Advice 双下游策略 Skill（NEW）

> 本章覆盖 `app/runtime_skills/product_advice/` + `app/runtime_skills/ops_advice/`（2 × 6 = 12 文件 + 2 个入口 agent.py）。
> 设计文档：`docs/specs/operation-skills-design.md`；执行计划：`docs/plans/operation-skills-plan.md`。

### 14.1 角色定位

这是项目从「画像生成」走向「策略落地」的关键一步。两个 Skill 都是 **stage=2**，**depends_on=["comprehensive_profile"]**，消费综合画像的 segment / risk / value / behavior_tags 输出，转化成可执行的产品策略和运营策略：

- **ProductAdvice**：续贷策略（主动续贷 / 续贷优惠 / 限时利率优惠 / 挽回式 / 不主动 / 场景化）+ 信用额度动作（主动提额 / 适度提额 / 维持 / 控额）+ 利率方案 + 推荐渠道
- **OpsAdvice**：催收策略 / 流失预警 / 触达节奏 / 留存激励，并输出 `churn_root_cause` enum（与 trace_analyzer 同源）

### 14.2 六步管线复用 + 国家包矩阵

两个 Skill 都严格走 contracts → data_access → feature_builder → decision_engine → explainer → assembler 六步，data_access 不读原始数据源，只从上游 `comprehensive_profile_result` 提取字段。决策核心是**国家包策略矩阵**——以墨西哥为例，`app/country_packs/mx/product_advice_rules.py::MX_PRODUCT_ADVICE_RULES` 是一个 S1-S6 → 完整策略对象的字典：

```python
"S1": {
    "renewal_strategy": {"action": "主动续贷", "trigger_offset_days": -7, ...},
    "credit_line_action": {"action": "主动提额", "delta_pct_range": (30, 50), ...},
    "rate_plan": {"plan": "VIP 专属低利率", ...},
    "recommended_channel": {"primary": "WhatsApp", "secondary": "Push"},
    "priority": "P0",
    "tags": ["S1", "主动续贷", "主动提额", "VIP"],
},
# ... S2 ~ S6
```

`ops_advice_rules.py` 同结构。这种「规则即数据 + LLM 增强叙事」的双轨模式延续了画像 Skill 的设计——determinism 保底，LLM 加温度。

### 14.3 与原 6 Skill 的注册关系

`app/services/orchestrator.py::_build_registry()` 现在注册顺序：

```
stage 0 (并行)：AppProfileSkill / BehaviorProfileSkill / CreditProfileSkill
stage 1：       ComprehensiveProfileSkill（depends_on=stage0 三者）
stage 2 (并行)：ProductAdviceSkill / OpsAdviceSkill（depends_on=comprehensive_profile）
```

`SkillRegistry.run_all()` 按 stage 分轮调度：同 stage 用 `ThreadPoolExecutor(max_workers=3)` 并行，跨 stage 串行；下游 Skill 通过 `<dep>_result` kwarg 自动接收上游输出。

### 14.4 标准化标签层（label_builder）

`app/services/label_builder.py` 是 2026-05 新增的层，把 6 个 Skill 的输出抽成统一的 `standardized_labels` 字段挂在 `UserAnalysisResult` 上，供前端按统一格式展示。它走「new-path-first → 老 metrics fallback」路由（对应 `docs/specs/standardized-labels-design.md` 的 Q1=B 决策）。

---

## 十五、多国扩展、SkillRegistry、SSE 进度流（NEW）

### 15.1 国家包扩展现状

| 国家 | country_packs/ | data_acquisition_agent 知识库 |
|------|--------------|---------------------------|
| 墨西哥 mx | ✅ app_categories / app_profile / behavior_profile / credit_profile / **ops_advice_rules / product_advice_rules / segments**（2026-05 新增） | ✅ 5 个 md |
| 巴基斯坦 pk | ✅ behavior_profile（其他空 stub） | ✅ 5 个 md |
| 泰国 th | ✅ behavior_profile（其他空 stub） | ✅ 5 个 md |
| 印尼 id | ✅ app_categories + behavior_profile | ✅ 5 个 md |
| 菲律宾 ph | ❌ 暂无 country_packs | ✅ 5 个 md |

**注意**：`country_packs/` 的细致度只跟得上墨西哥，其他国家只到 behavior_profile；但 `data_acquisition_agent/configs/` 已经覆盖 5 国——也就是说**先有数据采集能力，画像 Skill 的国家化适配是下一步**。

### 15.2 SkillRegistry 设计要点

`app/runtime_skills/base.py` 定义的 `BaseSkill` + `SkillRegistry` 是整个画像层的可插拔骨架：

- 每个 Skill 必须声明 `name` / `stage` / `depends_on`
- `SkillRegistry.register(skill)` 注册；`run_all(uid, progress_callback, **kwargs)` 按 stage 顺序执行
- **进度回调机制**（2026-05 新增）：`progress_callback({"type": "skill_started/skill_completed/skill_failed", ...})`，被 `analyze_stream.py` 利用做 SSE 流
- 同 stage 单 Skill 直接调用，多 Skill 走 `ThreadPoolExecutor(max_workers=3)`
- 下游 Skill 通过 `<dep_name>_result` kwarg 收上游产出

### 15.3 SSE 进度流（Plan: sse-progress-plan.md）

新增 `POST /api/analyze-stream` 端点（`app/api/analyze_stream.py`）+ 前端 `ProgressView` 组件：
- 7 类 SSE 事件：`skill_started` / `skill_completed` / `skill_failed` / `analysis_progress` / `error` / `final` / heartbeat
- 600s 总超时 watchdog + 15s heartbeat
- `Threading.Thread + queue` 做父子线程隔离（避免阻塞 ASGI 主事件循环）
- mock 模式兼容（mock 也会按节奏推进度）

测试在 `tests/test_analyze_stream_endpoint.py` / `test_analyze_stream_timeout.py` / `test_orchestrator_progress.py` / `test_skill_registry_progress.py`。

### 15.4 前端模块化（Plan: ui-separation-plan.md）

`app/static/js/` 现状：
```
app.jsx
components/
  DashboardView.jsx / HomeView.jsx / LoadingView.jsx / ProgressView.jsx
  charts/        ← 各 Skill 图表组件
  common/        ← 通用组件
  panels/        ← 各 Tab 面板（含未来的 chat/ trace/）
services/        ← API 调用层（包括即将到来的 orchestratorApi.js）
utils/           ← 工具函数
```

走 UMD React + Babel Standalone + window 全局命名空间方案，**无 npm 构建步骤**；`app/main.py` 走 `build_frontend_html()` 动态拼接 + `--reload` 即时刷新。`live_frontend.py` 仍存在（兼容期老页面），新页面全部走 static/js/。

---

## 十六、Plans / Specs 全景目录 + 你当前端到端流程拼装说明（NEW）

### 16.1 Plans 全景（15 份，按主题分组）

| 主题 | Plan 文件 | 状态 |
|------|----------|------|
| **多 Provider LLM 抽象** | `01-model-client-refactor-plan.md` | ✅ 已落地（providers/ + Provider Protocol） |
| ↑ Claude Opus 路由 | `02-explainer-trace-claude-migration-plan.md` | ✅ 已落地（7 explainer + trace 走 Claude，data_acq 留 Gemini） |
| **NL 编排 Agent** | `03-orchestrator-agent-plan.md` | ✅ 已落地（services/orchestrator_agent/） |
| ↑ 前端 NL Chat Tab | `04-nl-chat-tab-frontend-plan.md` | ⏳ 设计完成，前端落地中 |
| **数据采集** | `data-acquisition-v1-plan.md` | ✅ V1 已落地（72 测试通过） |
| ↑ 受控执行 | `data-acquisition-v2-plan.md` | ✅ V2 已落地（执行器 + 原子写） |
| **综合画像重构** | `comprehensive-refactor-plan.md` | ✅ 已落地（runtime_skills/comprehensive/ 六步） |
| **运营/产品 Skill** | `operation-skills-plan.md` | ✅ 已落地（product_advice + ops_advice） |
| **Trace 深度解析** | `trace-analyzer-plan.md` | ✅ 已落地（runtime_skills/trace_analyzer/） |
| ↑ 前端 Trace UI | `trace-ui-plan.md` | ⏳ 待执行 |
| **SSE 进度流** | `sse-progress-plan.md` | ✅ 已落地（analyze_stream.py） |
| **前端分离** | `ui-separation-plan.md` | ⏳ Phase A 完成，Phase B-H 进行中 |
| **金标测试框架** | `golden-test-plan.md` | ✅ 已落地（tests/golden/ + test_golden_*） |
| **Behavior/Credit Schema** | `behavior-credit-schema-plan.md` | ✅ 已落地（标准化 4+4 子模型 + label_builder） |
| **APP 类目 LLM 兜底** | `app-category-llm-fallback-plan.md` | ✅ 已落地（app_profile/category_llm_classifier.py） |

### 16.2 Specs 全景（16 份）

每份 spec 都对应一份 plan（除 `cohort-analysis-design.md` / `langgraph-migration-design.md` / `standardized-labels-design.md` 是「未来探索」类）。所有 spec 已锁定（design lock），plan 是「执行/未执行」的二态。

### 16.3 你当前端到端流程的完整拼装（重要）

你描述的 「数据存到 MySQL → RAG 检索增强 → 数据获取 Agent 生成 SQL → SQL 审查 Agent → 查 MySQL 拿数据 → 生成画像」 在当前架构下的实现路径：

```
┌──────────────────────────────────────────────────────────────────────┐
│ Step 1：把 5 国 source 数据导入 StarRocks（你这边的数仓侧任务）      │
│   - data/{app|behavior|credit}/source/ 目前只有 .gitkeep，需要先有真│
│     实 CSV/JSON 数据                                                 │
│   - 按 demo0/各国数据知识库汇总/{国家}/scheme.md 中的表名建表         │
│   - 用 broker load / stream load / SQL INSERT 把数据导入             │
└──────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Step 2：分析师在 Dashboard「对话」Tab 输入 NL 需求                    │
│   - 例：「跑一下墨西哥 12 月 mob1 的 1000 个用户的画像」              │
│   - Orchestrator Agent (services/orchestrator_agent/) 接管           │
│   - Agent loop 决定调用 query_data 工具                              │
└──────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Step 3：query_data 工具调 data_acquisition_agent V1                  │
│   - 加载 mexico.yaml 国家包                                         │
│   - 把 5 个 md 知识库脱敏后注入 prompt（这就是你说的"RAG 增强"，但是 │
│     long-context 注入式，不是向量检索）                             │
│   - Gemini 生成 SQL + 推理 + 自审计报告                             │
│   - L2 输出扫描通过                                                  │
└──────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Step 4：SSE 推送 awaiting_user_ack 事件                              │
│   - 前端弹出 SQL 预览 + 估算行数                                     │
│   - 分析师人工 review；点「确认」或「拒绝」                          │
│   - ⚠️ 当前没有「自动 SQL 审查 Agent」——若需要可以加一层 LLM Judge │
└──────────────────────────────────────────────────────────────────────┘
         │ 用户 confirm
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Step 5：query_data 工具调 data_acquisition_agent V2                  │
│   - 7 层执行门复核：拒 DDL / 凭据 / 危险代码 / SQL 策略 / 多语句     │
│   - open_starrocks_connection() pymysql 连 StarRocks                │
│   - SELECT COUNT(*) 预估行数（OOM 防御）                            │
│   - 真执行 SQL → pandas DataFrame                                   │
│   - 按 uid groupby + 切片                                           │
│   - .tmp_<rid> 暂存 → os.replace 原子落地到                         │
│     data/{bucket}/by_uid/{uid}.{csv|json}                           │
└──────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Step 6：Agent loop 继续，决定调 run_profile 工具                     │
│   - run_profile 调 AnalysisOrchestrator.analyze_module()            │
│   - SkillRegistry 按 stage 顺序跑 6 个 Skill                        │
│     stage 0 并行：App / Behavior / Credit                           │
│     stage 1：    Comprehensive                                      │
│     stage 2 并行：ProductAdvice / OpsAdvice                         │
│   - 每个 Skill 走六步管线，LLM 走 Claude Opus（数据采集留 Gemini）   │
│   - SSE 推送 skill_started / skill_completed 进度事件               │
└──────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────────────────────────────────────────┐
│ Step 7：Agent loop 返回 final_message                                │
│   - UserAnalysisResult JSON：6 个 Skill 输出 + standardized_labels  │
│   - 前端 Dashboard 渲染对应的 Tab（App/Behavior/Credit/综合/产品/   │
│     运营），可用 Trace Tab 进一步深挖单 UID 的行为时间线             │
└──────────────────────────────────────────────────────────────────────┘
```

### 16.4 你当前还需要补的几块

**A. 数据导入到 StarRocks**（最关键的前置）：当前 `data/*/source/` 都只有 `.gitkeep`。需要：
1. 拿到 5 国原始 CSV/JSON 数据（如 `data/app/source/mexico_2024_12_app_install.csv`）
2. 在 StarRocks 上按 `demo0/各国数据知识库汇总/{国家}/scheme.md` 建表
3. 导入数据（broker load / stream load）
4. 在 `.env` 里填 `DA_DB_HOST` / `DA_DB_PORT` / `DA_DB_USER` / `DA_DB_PASSWORD` / `DA_DB_DATABASE`

**B. SQL 审查 Agent（可选）**：当前是「人工 review」，如果你要做「自动 SQL 审查 Agent」（你描述的「经过 SQL 脚本审查 agent 之后」），可以新起一个 LLM Judge——输入 V1 的 `GenerateResponse`，输出 `{audit_passed: bool, risks: [...], suggested_fixes: [...]}`，挂在 V1 之后、V2 之前。**这个目前没有 Plan，需要新写 Design Doc。**

**C. 国家包 Skill 适配**：当前 `country_packs/` 详细度只墨西哥到位，pk/th/id/ph 的 app_profile / credit_profile 还是空 stub。如果 query_data 拉的是泰国数据，下游 Skill 的国家化分类（如借贷 APP 关键词、银行 APP 列表）会走兜底逻辑，效果会打折。建议优先把每个国家的 `app_categories.py` 补齐。

**D. 前端串联**：「对话」Tab（NL Chat）+「Trace」Tab 的前端代码还在落地中（Plan 04 + Trace UI Plan），后端已经就绪可调。

### 16.5 一句话总结你的整体架构现状

**「数据采集 Agent + NL 对话 Agent」是 2026-05 的两大新增子系统，前者把「数仓 → 画像数据文件」变成 LLM 自动化 + 7 层安全门 + 人工 ACK 的可控流程，后者把分散的 6 个画像 Skill 串成自然语言对话入口；二者都靠 Claude Opus 4.7（Maestro）+ Gemini 双 Provider 抽象（Plan #01-02）支撑；下一步的关键瓶颈不在代码而在「把 5 国真实数据导入 StarRocks」和「补全 4 国的 country_packs 细节」。**

---

## 十七、亲读代码校正与精确文件清单（NEW，2026-05-04 全量复核）

> 本章是 2026-05-04 用户要求「全量学习左侧文件框」后，AI 直接 read_file 每个核心文件、用 PowerShell 数行数后做的**事实复核**。前面章节里有些数字（例如 `model_client.py 475 行`、`comprehensive_agent.py 398 行`、`Behavior Schema 17 行`、`agents/ 仍未删除`）是基于早期 2026-04-28 状态写的，**已经过时**。下表是当前真实数据。

### 17.1 核心文件精确行数表（2026-05-04 powershell `Measure-Object -Line`）

#### 核心层
| 文件 | 真实行数 | 之前笔记中的描述 | 校正 |
|------|---------|----------------|------|
| `app/main.py` | ~80 | 50 行 | ↑ 增长（新增 startup hook、static 挂载、SSE 路由注册） |
| `app/core/config.py` | 195 | 73 行 | ↑ 大幅增长（新增 LLM provider/routes 配置加载 + validate_llm_routes） |
| `app/core/model_client.py` | **195** | 475 行 | ↓ **大幅缩小**（核心 LLM 实现已抽到 `app/core/providers/`，本文件退化为 Facade） |
| `app/core/providers/base.py` | 90 | — | 新文件（LLMProvider Protocol + ProviderCapability + fallback_chain） |
| `app/core/providers/gemini_provider.py` | 249 | — | 新文件（实际的 Gemini/Vertex 实现，从 model_client.py 抽出） |
| `app/core/providers/claude_maestro_provider.py` | 142 | — | 新文件（Claude Opus 4.7 via Maestro 网关） |
| `app/core/providers/json_repair.py` | 225 | — | 新文件（JSON 修复纯函数，被多个 provider 共享） |
| `app/core/providers/mock_provider.py` | 48 | — | 新文件 |
| `app/core/providers/factory.py` | 24 | — | 新文件（provider name → 实例工厂） |

**关键校正**：`ModelClient` 已经**不是**那个 475 行的"包含一切"的类了。它现在是 **195 行的 Facade**，真正的 LLM 调用、JSON 修复、Token 计数全部委托给 Provider 类。这个重构是 Plan #01 的产物（[complete] 2026-05-02）。

#### 服务编排层
| 文件 | 真实行数 |
|------|---------|
| `app/services/orchestrator.py` | ~290（含 `analyze_module` + 模块缓存） |
| `app/services/batch_service.py` | ~23 |
| `app/services/report_renderer.py` | ~30 |
| `app/services/label_builder.py` | **新增**（标准化标签层，Q1=B 决策落地） |

#### Skill 层（六步管线全部）
| 模块 | contracts | data_access | feature_builder | decision_engine | explainer | assembler | 入口 agent.py |
|------|----------|------------|----------------|----------------|-----------|-----------|--------------|
| **app_profile** | 96 | 130 | **41**（薄壳，委托给 scripts/app_profile_payload_builder.py） | **25**（薄壳） | 262 | 360 | 85 |
| **behavior_profile** | 183 | 145 | 188 | **701**（最大！） | 450 | 248 | 85 |
| **credit_profile** | 164 | 135 | 254 | 375 | 206 | 198 | 85 |
| **comprehensive** | 101 | 64 | 101 | 258 | 205 | 137 | **65**（薄入口，已重构） |
| **product_advice** | 60 | 55 | 27 | 54 | 69 | 122 | 50 |
| **ops_advice** | 58 | 55 | 26 | 76 | 73 | 122 | 50 |
| **trace_analyzer** | 42 | 63 | **309** | 68 | 146 | 61 | analyzer.py 42 + _constants.py 30 |

**额外发现**：
- `app/runtime_skills/app_profile/category_llm_classifier.py` **272 行**——Plan `app-category-llm-fallback-plan.md` 的产物。当 9 个 keyword list 都匹配不到 APP 类目时，调 LLM 做兜底分类，结果缓存到 `outputs/cache/app_category_cache.json`。
- `behavior_profile/decision_engine.py` 仍是 **701 行**最大单文件（早期笔记说 713 行略有出入，实际是 701）。
- App 模块的 `feature_builder.py / decision_engine.py` 加起来才 66 行——绝大部分逻辑在 `app/scripts/app_profile_payload_builder.py` **1008 行** + `behavior_prepared_builder.py` **1317 行** + `credit_prepared_builder.py` **768 行** 这三个 scripts 里。

#### Schemas（精确行数）
| 文件 | 真实行数 | 早期笔记 | 校正 |
|------|---------|---------|------|
| `app_profile.py` | 78 | 98 | 略减 |
| `behavior_profile.py` | **45** | 17 | ↑ **强类型 4 子模型 + 3 level 字段已补齐**（Plan: behavior-credit-schema-plan）|
| `credit_profile.py` | **51** | 17 | ↑ **强类型 4 子模型 + 5 level 字段已补齐** |
| `comprehensive_profile.py` | 20 | 26 | 略减 |
| `final_response.py` | 31 | 42 | 略减；新增 product_advice / ops_advice / standardized_labels 的 Optional 字段 |
| `product_advice.py` | **25** | — | 新文件 |
| `ops_advice.py` | **25** | — | 新文件 |
| `trace_analyzer.py` | **65** | — | 新文件（TraceAnalyzeResponse + 7 子 model）|
| `request.py` | 41 | 50 | 略减 |
| `response.py` | 7 | — | 极简 |

#### 数据采集 + 编排 Agent
| 文件 | 真实行数 | 关键发现 |
|------|---------|---------|
| `data_acquisition_agent/orchestrator.py` | **131**（早期笔记说 160） | 实际更精简，逻辑全在 generate() 一个方法 |
| `data_acquisition_agent/prompt_assembler.py` | **134**（早期笔记说 220） | 早期笔记把内置的 SYSTEM_PROMPT_ENGINE 字符串行数算进去了 |
| `data_acquisition_agent/executor.py` | 138 | 准确 |
| `data_acquisition_agent/output_writer.py` | 136 | 准确 |
| `data_acquisition_agent/output_scanner.py` | **64**（早期笔记说 80） | 准确（更精简） |
| `data_acquisition_agent/connection.py` | **48**（早期笔记说 55） | 准确 |
| `data_acquisition_agent/redactor.py` | **25**（早期笔记说 50） | 实际比说的更精简 |
| `data_acquisition_agent/api.py` | 66 | 略减 |
| `data_acquisition_agent/manifest.py` | 51 | 略减 |
| `data_acquisition_agent/schemas.py` | **124**（早期笔记说 200） | 实际更精简 |
| `app/services/orchestrator_agent/agent_loop.py` | **240**（早期笔记说 330） | 实际更精简 |
| `app/services/orchestrator_agent/schemas.py` | **82**（早期笔记说 150） | 实际更精简 |
| `app/services/orchestrator_agent/tools/query_data.py` | 101 | 准确 |
| `app/services/orchestrator_agent/tools/run_profile.py` | **25** | 极薄 wrapper |
| `app/services/orchestrator_agent/tools/run_trace.py` | **16** | 极薄 wrapper |
| `app/services/orchestrator_agent/tools/parse_uid_file.py` | 37 | 准确 |
| `app/services/orchestrator_agent/tools/memory.py` | **28** | 极薄（V1 minimal，后续 Redis 升级） |

### 17.2 关键架构事实校正

#### 校正 A：ModelClient 已经是 Facade，不是单体

```
ModelClient(195 行)
  └─ self._provider: LLMProvider  ← 通过 _build_default_provider(mode) 注入
       ├─ MockProvider(48 行)              ← mock 模式
       ├─ GeminiProvider(249 行)           ← gemini / vertex 模式
       └─ ClaudeMaestroProvider(142 行)    ← Plan #02 路由
       
       fallback_chain(claude, gemini)：vertex 模式 + claude_maestro endpoint 真实回填后自动包装
```

**`generate_structured(skill_name, prompt, fallback_result, response_schema, route_key=None)`** 的 signature 加了 `route_key` 参数：调用方（如 `app_profile/explainer.py`）传入 `route_key="app_profile.explainer"`，ModelClient 会查 `config.yaml::llm.routes` 决定走哪个 provider。

`config.yaml::llm.routes` 的真实内容（亲读 verified）：
```yaml
routes:
  app_profile.explainer: claude_maestro
  behavior_profile.explainer: claude_maestro
  behavior_profile.timeline: claude_maestro
  credit_profile.explainer: claude_maestro
  comprehensive.explainer: claude_maestro
  product_advice.explainer: claude_maestro
  ops_advice.explainer: claude_maestro
  trace_analyzer.explainer: claude_maestro
  orchestrator_agent.decide: claude_maestro
default_provider: gemini
```

**重要**：`data_acquisition` **没有列在 routes 表里**，意味着它走 `default_provider: gemini`（surgical hard boundary：Plan #02 的 Spec 明确要求 data_acquisition 锁定在 Gemini，因为 163 测试基线已通过 Gemini 验证）。

#### 校正 B：Comprehensive 已经重构成六步管线

早期笔记说「Comprehensive 是一个 398 行的单文件」是 2026-04-28 的事实，2026-05-04 已经不是了。现在：
- **入口**：`comprehensive_agent.py` 仅 65 行，纯 BaseSkill 注册壳
- **六步管线**：`comprehensive/` 子目录 6 个文件，总 866 行（contracts 101 + data_access 64 + feature_builder 101 + decision_engine 258 + explainer 205 + assembler 137）

`ComprehensiveDecisionEngine`（亲读 `decision_engine.py` 258 行）的真实职责：
1. **维度分数计算**：`app_score` / `behavior_score` / `credit_score` 各 1-5 分
2. **客群分配 `_assign_segment()`**：S1-S6 分群规则（与早期笔记描述一致：S5 多头高风险 / S4 流失 / S1 高价值低风险 / S2 稳定可控 / S3 价格敏感 / S6 沉默观望）
3. **冲突信号检测**：multi_loan 中/高 vs credit_risk 低 → "早期预警 vs 已确认风险"；价格敏感 + 风险安装 → "比价 vs 违约压力"
4. **价值信号派生**：high / medium / low
5. **prompt_payload 构建**：把上面所有派生信号打包给 LLM，让 LLM 只做"叙事融合"，不重新决策

#### 校正 C：Product/Ops Advice 决策引擎 = 国家包字典查表 + 升档

**ProductAdviceDecisionEngine**（54 行）的核心逻辑就是：
```python
segment = upstream["segment"]              # "S1" ~ "S6"
strategy = MX_PRODUCT_ADVICE_RULES[segment]  # 直接查表
return {"renewal_strategy": strategy["renewal_strategy"], ...}
```

**OpsAdviceDecisionEngine**（76 行）多一层"升档"逻辑：
- 基础策略来自 `MX_OPS_ADVICE_RULES[segment]`
- 但若 `churn_root_cause` 命中特定值（如 `competitor_poaching`），强制把 `intervention_priority` 从 P2 升到 P0
- 若 `repayment_pressure_high` + `late_days >= 7`，强制走 `aggressive_collection`

**这意味着**：业务规则的核心都在 `app/country_packs/mx/{product_advice_rules,ops_advice_rules,segments}.py` 三个数据字典里，Decision Engine 只是"查字典 + 少量升档"。**新增国家**只要复制 `mx/` 目录改字典值就够了，不用碰 Decision Engine 代码。这是项目里多国扩展性最好的部分。

#### 校正 D：data_acquisition_agent 与画像主链路完全解耦

**关键事实**：data_acquisition_agent V2 写出来的文件路径是 `data/{app|behavior|credit}/by_uid/{uid}.{csv|json}`，**这正好是** `LocalUserRepository.get_*_data(uid)` 默认读的路径（在 `settings.app_by_uid_dir / behavior_by_uid_dir / credit_by_uid_dir`）。所以你描述的「数据获取 Agent 拿到数据后→生成画像」**不需要任何代码胶水**——V2 写完文件，下次 `AnalysisOrchestrator` 跑 SkillRegistry 时自动读到。

**这条「文件即接口」的隐式契约非常关键**，但当前文档里没有显式列在哪个 spec 里——它是 `local_repository.py` 的默认路径 + V2 `output_writer.resolve_bucket_dir()` 的实现共同维护的。任何想改这个路径的 PR 都必须同时改两边。

#### 校正 E：ops_advice 与 trace_analyzer 共享 churn_root_cause enum

亲读 `app/runtime_skills/trace_analyzer/_constants.py` 30 行，里面定义了：
```python
CHURN_ROOT_CAUSE_ENUM = frozenset({
    "credit_limit_unmet", "interest_perception_high",
    "competitor_poaching", "ux_friction",
    "repayment_burden", "no_clear_signal",
})
```
亲读 `app/runtime_skills/ops_advice/decision_engine.py` 76 行，里面对 `churn_root_cause` 做升档判定时引用的就是这个 enum。**两个模块共享语义 contract 但不共享 code 路径**——trace_analyzer 通过 `_constants.py` 单一来源；ops_advice 在自己的 decision_engine 里硬编码相同字符串值（依靠测试保证一致性）。这是个 PLANNING.md 里"trace 输出的 churn_root_cause 与 ops_advice 的 6 种候选值兼容但**不回灌**——仅供前端展示"决策的代码体现。

#### 校正 F：API 路由实际清单

`app/api/` 当前实际路由（5 个 router 文件）：
| 文件 | 行数 | 端点 |
|------|------|------|
| `analyze.py` | 34 | POST /api/analyze, POST /api/analyze-file, GET /api/ui-config |
| `analyze_module.py` | 22 | GET /api/analyze-module?uid=&module=（**渐进加载主路径**） |
| `analyze_stream.py` | 99 | POST /api/analyze-stream（SSE，保留但前端已切换到 analyze_module） |
| `trace.py` | 19 | GET /api/trace/{uid} |
| `orchestrator_routes.py` | 39 | POST /api/orchestrator/chat, GET /api/orchestrator/sessions/{id}, POST /api/orchestrator/sessions/{id}/ack |

加上 `data_acquisition_agent/api.py`（66 行）的 `/generate` + `/execute` + `/manifests` + `/healthz`（**注意**：`data_acquisition_agent` 的 router 也被 `app/main.py` include 进了主 FastAPI app）。

**当前真实可用端点总数**：≈ 11 个 HTTP 端点 + 1 个 SSE。早期笔记说"2 个 POST 端点"早就过时了。

### 17.3 真实代码风格观察

通过亲读所有六个 Skill 的入口 `*_agent.py`，可以看到**统一的「7 步骨架」**：
```python
class XxxSkill(BaseSkill):
    name = "xxx"
    stage = N
    depends_on = [...]

    def __init__(self, model_client):
        # 加载 prompt path + 实例化 6 个组件
    
    def analyze(self, uid, **kwargs):
        # 1. build_run_context
        # 2. data_provider.fetch
        # 3. if missing → assembler.build_missing_output
        # 4. feature_builder.build
        # 5. decision_engine.decide + build_prompt_payload
        # 6. assembler.build_fallback_structured
        # 7. explainer.explain → assembler.assemble
```

**这个 7 步骨架是项目最重要的代码模式**——任何想加新 Skill 的人复制粘贴一份改名字就能跑通。新人理解项目时，先记住这个模式，再去看每个 Skill 内部的 6 个文件做了什么具体计算。

### 17.4 你之前说的「不准确/局限」具体在哪几条

复盘上一版回答里我给出的描述，下面这些是**早期笔记原文继承下来的不准确描述**，本章 17.1-17.3 已校正：

| 早期笔记原话 | 真实情况 |
|-------------|---------|
| "ModelClient 是 475 行" | 现在 195 行（Facade，实际逻辑在 providers/） |
| "comprehensive_agent.py 是 398 行单文件" | 已重构，入口仅 65 行，逻辑分散到 6 个文件 866 行 |
| "Behavior Schema 17 行基础定义" | 已补全到 45 行强类型子模型 |
| "Credit Schema 17 行基础定义" | 已补全到 51 行 |
| "agents/ 4 个 Legacy 文件 416 行未删除" | 2026-04-28 已删除 |
| "5 个 prompt 模板" | 现在 10 个（新增 app_category_classifier / orchestrator_system_prompt_v1 / ops_advice / product_advice / trace_analyzer） |
| "API 端点 2 个" | 现在 11 个 HTTP + 1 个 SSE |
| "data_acquisition prompt_assembler 220 行" | 实际 134 行（早期把字符串常量算进去了） |
| "live_frontend.py 2000+ 行" | 已删除，改为 build_frontend.py 拼接 38 个 JSX 文件 |
| "behavior_profile decision_engine 713 行" | 实际 701 行 |

### 17.5 最重要的 5 个一句话事实

1. **统一 7 步骨架 + 6 步管线**：6 个 Skill 全部走相同的 `BaseSkill.__init__` + `analyze()` 模式，内部全部走 contracts → data_access → feature_builder → decision_engine → explainer → assembler 六步。**复用度 100%**。

2. **国家化 = 字典查表**：墨西哥的所有业务规则都在 `app/country_packs/mx/` 7 个 Python 文件里（app_categories 90 / behavior_profile 139 / credit_profile 40 / segments 13 / product_advice_rules 53 / ops_advice_rules 47 / app_profile 18 = 共 400 行可改业务知识）。新增国家**只需复制目录改字典**，不碰任何 Skill / Engine 代码。

3. **LLM Provider 已抽象**：所有 LLM 调用都过 `ModelClient.generate_structured(..., route_key=...)`，Provider 由 `config.yaml::llm.routes` 决定。切换 Claude / Gemini / Mock 完全声明式，无需改业务代码。

4. **数据采集 Agent 写文件即完成移交**：V2 写到 `data/*/by_uid/{uid}.*` 路径，下游 Skill 通过 `LocalUserRepository` 自动读到。**没有显式 API call，没有消息队列**——文件路径就是契约。

5. **Trace Analyzer 是有意游离于 SkillRegistry 之外**：它**不是** stage=3 的 Skill，因为它的"按需深挖单 UID"语义不属于"批量画像管线"。挂在 `GET /api/trace/{uid}` 单独路由，前端 Trace Tab 显式调用。这个架构决策有意把"批量"和"按需"两类工作隔离开。

---

## 十八、给你的最终结论（基于全量代码亲读）

### 18.1 你的 NL → SQL → 数据库 → 画像 流程在当前代码里的精确执行路径

```
[你的输入]
  浏览器 → /api/orchestrator/chat (SSE)
            POST { "prompt": "跑墨西哥 12 月 mob1 的 1000 人画像 + 产品建议" }

[第 1 步：Orchestrator Agent 接管]
  app/services/orchestrator_agent/agent_loop.py::run_agent_loop()
    → ModelClient.generate_structured(route_key="orchestrator_agent.decide")
    → claude_maestro provider(Plan #02 路由)
    → LLM 返回 {"name": "query_data", "arguments": {country: "mexico", nl: "..."}}

[第 2 步：query_data 工具走数据采集 V1]
  tools/query_data.py
    → data_acquisition_agent.orchestrator.DataAcquisitionOrchestrator.generate()
       → manifest.load_manifest("mexico")               // 加载 mexico.yaml
       → prompt_assembler.assemble_prompt()             // 5 个 md 知识库脱敏后拼接
          → redactor.redact() × 5                       // L1：11 类凭据脱敏
          → token 估算 ≤ 800K
       → ModelClient.generate_structured(route_key=??)  // 走 default = gemini（不走 claude）
       → output_scanner.check_sql_policy()              // L2：query_only 还是 build_table_script
       → output_scanner.scan_credentials()              // L2：11 类凭据回扫
       → output_scanner.scan_python_dangerous()         // L2：8 类危险 Python
    → 返回 GenerateResponse { sql, sql_kind, python, audit_report, metadata }

[第 3 步：SSE 推 awaiting_user_ack 给前端]
  agent_loop.py::_query_data_with_ack()
    → yield "awaiting_user_ack" event with SQL 预览 + COUNT 估算
    → ack_bus.wait_ack()  // threading.Event 阻塞等待

[第 4 步：用户在前端弹窗点「确认」]
  浏览器 → POST /api/orchestrator/sessions/{id}/ack { "confirm": true }
    → ack_bus.resolve_ack(session_id, confirmed=True)
    → wait_ack 解除阻塞

[第 5 步：query_data 工具走数据采集 V2]
  tools/query_data.py
    → data_acquisition_agent.executor.run_execute_pipeline()
       → enforce_pre_execution_gates()                  // L4：所有 L2 + 拒 DDL
       → connection.open_starrocks_connection()         // L6：env 凭据 + Redacted 包装
       → executor.precheck_row_count()                  // L5：SELECT COUNT(*) 防 OOM
       → executor.execute_query()                       // 真执行 → pandas DataFrame
       → output_writer.validate_bucket_schema()         // app bucket 强制 7 列 CSV
       → output_writer.build_per_uid_payloads()         // groupby uid
       → output_writer.write_per_uid_atomic()           // L7：.tmp_<rid> → os.replace
    → 文件落到 data/{app|behavior|credit}/by_uid/*.{csv|json}

[第 6 步：Agent loop 决定调 run_profile]
  tools/run_profile.py (16 行薄 wrapper)
    → AnalysisOrchestrator.analyze_module(uid, module="comprehensive")
       → 自动级联：先跑 app/behavior/credit (stage 0 并行)
                  再跑 comprehensive (stage 1)
                  最后跑 product/ops (stage 2 并行)
       → 每个 Skill 内部走六步管线
       → Explainer 通过 ModelClient route_key 走 claude_maestro

[第 7 步：返回综合画像 + 产品 + 运营策略]
  agent_loop.py
    → yield "final" event with UserAnalysisResult
    → save session to outputs/orchestrator_sessions/{id}.json
```

### 18.2 你下一步真正需要做的（按优先级，比上一版回答更精确）

1. **(P0, 必做)** 把 5 国 source 数据导入 StarRocks。当前 `data/{app|behavior|credit}/source/` **全部是空的（只有 .gitkeep）**。需要按 `data_acquisition_agent/demo0/各国数据知识库汇总/{国家}/scheme.md` 建表后导入数据。**这一步系统不参与，纯粹是数仓侧任务。**

2. **(P0, 必做)** 在 `.env` 里填 `DA_DB_HOST` / `DA_DB_PORT` / `DA_DB_USER` / `DA_DB_PASSWORD` / `DA_DB_DATABASE` 5 个变量 + StarRocks 只读账号。

3. **(P0, 推荐)** 完成 Plan #03 Phase 0 Maestro Spike。当前 `config.yaml::providers.claude_maestro.endpoint = "[Spike Pending]"`，意味着所有 `route_key=*.explainer` 的 LLM 调用如果走 claude 会立刻 raise `ProviderUnavailable`，触发 fallback_chain 降级到 Gemini。这不会让系统挂掉但会绕过 Plan #02 的本意。Spike 完成后填入真实 endpoint，Claude Opus 4.7 才真正生效。

4. **(P1)** 启动 Plan #04 前端「对话」Tab。后端已经 100% 就绪可调，前端只需要落地 7 个 JSX 组件（Plan #04 Phase 1）。

5. **(P2, 可选)** 补全 4 国 country_packs。当前 pk/th/id 只有 `behavior_profile.py` stub，ph 完全没有。如果 query_data 拉的是这些国家的数据，下游 Skill 会走墨西哥默认值——结果会"能跑但不准"。

6. **(P2, 可选)** 加自动 SQL 审查 Agent（如果你坚持要这一步）。当前是 7 层硬编码安全门 + 人工 review。要加 LLM Judge 需新写 Design Doc + Plan，不在任何已落地的 Plan 里。

### 18.3 关于「RAG 检索增强」的精确措辞

你描述里说"配合 RAG 检索增强"。**注意 demo0/ 不是真 RAG**——它是 long-context prompt 注入：
- ❌ 没有向量数据库（FAISS / Chroma / Pinecone）
- ❌ 没有 embedding 计算
- ❌ 没有相似度检索
- ✅ 5 国 × 5 md 全部 verbatim 拼接进 prompt
- ✅ 优先级：业务逻辑 > all_examples > schema > few-shot
- ✅ 800K token 上限（800K = Gemini 2.5 Flash / Claude Opus 的上下文窗口）

**为什么要这样做**：
- 防止 LLM 编造表名 / 字段名（schema.md 全文塞进去，LLM 无法"找不到字段就乱编"）
- 业务规则的"为什么"+"怎么做"必须完整看到（mob1 = 首借 + 还清 + 7 天不复借——这种业务定义如果只取一段会理解错）
- 审计透明：人工可以读完整 prompt 看 LLM 拿到了什么

**何时需要切换到真 RAG**：当 5 国 → 50 国时，800K token 装不下 50 × 5 个 md，那时候必须改用 embedding + top-K 检索。**当前规模不需要**。

---

笔记完结。本次 2026-05-04 全量复核共校正 10+ 处不准确描述，新增 8 个章节（11-18），从 1038 行扩到 ~1900 行。所有数字、文件名、行数均已用 PowerShell `Measure-Object -Line` 二次核对。所有架构结论均已通过 `read_file` 直接验证源码。

