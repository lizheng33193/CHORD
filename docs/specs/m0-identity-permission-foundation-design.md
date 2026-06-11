# M0 Identity And Permission Foundation Design

## Purpose

为 MAPS-LZ Agent Harness 建立第一层真实身份底座，让每一次请求都具备：

- 可识别的 actor
- 明确的 project scope
- 可校验的 country scope
- 可组合的 role / permission
- 可传播到 Orchestrator / Memory / Trace / Data Agent 的 `UserContext`

本阶段不是做复杂后台，也不是做一次性登录页；目标是建立后续
LangGraph、SQL HITL、Memory、Audit、Tool 权限控制都能复用的统一身份层。

## Scope

### In

- MySQL 持久化用户、角色、权限、项目、会话、审计
- FastAPI 注册 / 登录 / JWT / `/api/auth/me`
- `UserContext` / `RequestContext` 统一结构
- 关键 API 权限依赖与 scope 校验
- Orchestrator / Memory / Trace / Data Acquisition 接入真实身份
- 前端登录 / 注册 / 退出 / 会话保持
- 为 SQL 审核与 LangGraph state 预留 actor / reviewer / executor 元数据

### Out

- 复杂组织架构
- OAuth / 企业 SSO
- 细粒度字段权限
- 可视化 RBAC 管理后台
- 完整 LangGraph 迁移
- DataAgentGraph 重写

## Harness Impact

本次改动同时影响以下 Harness 层：

- 信息边界：匿名请求改为 `UserContext + RequestContext`
- 工具接口：关键 API 变为带认证与权限约束
- 执行编排：Orchestrator run 需要携带 actor / request scope
- 记忆/状态：Memory / Session / Trace 以真实身份隔离
- 评估/观测：Audit / Trace 记录真实 actor
- 约束/恢复：权限不足与 scope 不匹配时显式阻断

## Data Model

本阶段新增以下认证域模型：

- `users`
- `roles`
- `permissions`
- `user_roles`
- `role_permissions`
- `projects`
- `user_project_access`
- `user_sessions`
- `audit_events`

### User

用户保存基础身份信息与默认 scope：

- `username`
- `email`
- `password_hash`
- `display_name`
- `status`
- `is_superuser`
- `default_project_id`
- `default_country`
- `last_login_at`

### Role / Permission

第一版内置角色：

- `admin`
- `data_admin`
- `analyst`
- `viewer`

第一版内置权限：

- `profile:run`
- `profile:view`
- `trace:run`
- `trace:view`
- `data:query:generate`
- `data:query:review`
- `data:query:execute`
- `data:query:view_sql`
- `memory:read`
- `memory:write`
- `memory:manage`
- `audit:view`
- `user:manage`
- `project:manage`

### Project Scope

`projects` + `user_project_access` 共同描述访问边界：

- 用户至少要有一个 project membership
- `country = NULL` 表示当前项目下全部国家可访问
- `country = mx/th/...` 表示仅当前国家可访问
- `access_level` 第一版只做持久化与审计，不做复杂行为分叉

### Session / Audit

`user_sessions` 为 JWT session revocation 与设备审计预留：

- `session_token_hash`
- `expires_at`
- `revoked_at`

`audit_events` 统一记录关键行为：

- 登录 / 退出
- 画像运行
- SQL 生成 / 审核 / 执行
- Memory 写入 / 管理
- Trace 查看

## Runtime Context Model

### UserContext

业务层统一消费 `UserContext`，不直接散用 ORM 对象：

```python
@dataclass(frozen=True)
class ProjectAccessScope:
    project_id: int
    project_code: str
    access_level: str
    country: str | None


@dataclass(frozen=True)
class UserContext:
    user_id: int
    username: str
    email: str | None
    display_name: str | None
    roles: tuple[str, ...]
    permissions: tuple[str, ...]
    project_id: int | None
    project_code: str | None
    country: str | None
    project_scopes: tuple[ProjectAccessScope, ...]
    is_superuser: bool = False
```

### RequestContext

每次请求都生成 `RequestContext`：

```python
@dataclass(frozen=True)
class RequestContext:
    request_id: str
    user: UserContext | None
    session_id: str | None
    trace_id: str | None
```

用途：

- FastAPI route -> service
- Orchestrator run -> session / trace metadata
- Data Agent execute / preview 审计
- 后续 LangGraph state 注入

## Auth Architecture

### Backend

新增 `app/auth/` 模块：

- `database.py`：SQLAlchemy engine / session / base
- `models.py`：认证域 ORM 模型
- `schemas.py`：register / login / me / project response
- `password.py`：bcrypt hash / verify
- `jwt.py`：access token encode / decode
- `service.py`：注册、登录、权限装配、上下文构建
- `permissions.py`：permission / scope 判断函数
- `dependencies.py`：FastAPI auth dependencies
- `router.py`：`/api/auth/*`
- `seed.py`：默认角色、权限、项目、管理员种子

### Token Strategy

第一版使用 JWT access token + DB-backed `user_sessions`：

- JWT 只存轻量身份字段：`sub`、`sid`、`project_id`、`country`、`exp`
- 权限不塞进 JWT
- 每次请求根据 `sid` 查 `user_sessions`，若 revoked 或 expired 则拒绝
- 当前 scope 可由 header 覆盖：
  - `X-Project-ID`
  - `X-Country`
- 覆盖前必须经过 `user_project_access` 校验

### Auth Feature Flag

引入 `AUTH_ENABLED`：

- `true`：强制 JWT + DB 身份
- `false`：返回 demo `UserContext`，保留开发联调能力

## API Integration

### New Auth APIs

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `GET /api/auth/my-permissions`
- `GET /api/auth/my-projects`

### Permission Guards

关键 API 的第一版授权矩阵：

- `/api/analyze*` -> `profile:run`
- `/api/trace/{uid}` -> `trace:run`
- `/api/orchestrator/chat` / `/api/orchestrator/sessions*` -> `profile:run`
- `/api/orchestrator/memory/query|list` -> `memory:read`
- `/api/orchestrator/memory` create -> `memory:write`
- `/api/orchestrator/memory/*` update/archive/restore/delete -> `memory:manage`
- `/api/data-acquisition/generate` -> `data:query:generate`
- `/api/data-acquisition/execute` -> `data:query:execute`

### Scope Guards

带国家入参的 API 需要校验：

- 路由参数 / query / body 中的 `country`
- 或 header `X-Country`

规则：

- superuser 直接通过
- project membership 中存在 `country=NULL` 则允许
- 或存在与目标国家完全匹配的 membership
- 否则 `403`

### HTTP Semantics

认证失败与越权失败在第一版已明确拆开：

- `401`：token 无效、session 不存在、session 已撤销、session 过期、user 不存在或已停用
- `403`：permission 不足、project scope 不匹配、country scope 不匹配

前端只对 `401` 自动退出；`403` 只提示“无权限或 scope 不匹配”，不清登录态。

### Country Alias Normalization

country scope 判断统一走别名归一化，第一版至少支持：

- `mx` / `mexico` -> `mx`
- `th` / `thailand` -> `th`

`UserContext.country`、`project_scopes.country`、`X-Country` override、Data Acquisition target country 都以归一化后的 country code 比较。

## Orchestrator / Memory / Trace Integration

### Session Identity

`OrchestratorSession` 继续保留：

- `user_id`
- `project_id`
- `country`

同时在 `active_entities` 内附加 request metadata：

- `request_context`
- `user_context_snapshot`

已创建 session 的可见性与续跑边界固定为 `(user_id, project_id, country)` 三元组：

- 同 user 但不同 project/country 不能读取旧 session
- `_apply_request_identity(...)` 只刷新 request snapshot，不再重写 session 绑定 identity
- 旧 session 不允许被新的 scope override“重新挂接”

### Agent Loop

`run_agent_loop(...)` 升级为兼容接收：

- `user_context`
- `request_context`

并在入口统一：

- apply identity to session
- attach request metadata to trace/session
- bind memory facade with real `user_id/project_id/country`

### Trace

第一版不破坏现有 SSE contract，新增 actor 信息落到：

- `ExecutionTraceRecord.request_id`
- `ExecutionTraceRecord.internal_metadata.actor`

内部 trace metadata 至少包含：

- `user_id`
- `username`
- `project_id`
- `project_code`
- `country`
- `request_id`

### Memory

现有 SQLite Memory store 继续保留，但 identity 改为来自登录用户：

- `user_id = ctx.user_id`
- `project_id = ctx.project_id`
- `country = ctx.country`

这保证长期记忆即使暂时不迁 MySQL，也具备真实 actor 隔离。

SQLite v1 memory 的读取语义固定为：

- `session`：同 `user + project + country + session`
- `user`：同 `user + project + country`
- `project`：同 `project + country`，跨用户共享
- `global`：同 `project`，跨国家共享

去重规则同步固定为：

- `session/user`：继续带 `user_id`
- `project`：按 `project + country` 去重
- `global`：按 `project` 去重

共享 scope 的记录仍保留 `user_id` 作为创建者，但可见性不再由创建者限制。

### Data Acquisition

Data Agent API 层显式接权限：

- generate 需要 `data:query:generate`
- execute 需要 `data:query:execute`

chat 中的 `query_data` 在 preview 前同时要求：

- `data:query:view_sql`
- `data:query:execute`

此外：

- `/api/data-acquisition/generate` 与 `/api/data-acquisition/execute` 都先做 `require_country_access(...)`
- `approved_by` 从 `UserContext.username` 贯穿 preview / execute / trace / audit

执行审计与 reviewer/executor 预留字段：

- `approved_by` 由当前登录用户名兜底
- `source_request_id`
- `draft_sql_hash`
- `approved_sql_hash`
- `reviewer_user_id`
- `executor_user_id`
- `review_decision`

第一版不重构 Data Agent 内部状态机，只在 API / 审计边界预留字段。

## Frontend Architecture

新增轻量认证层：

- `app/static/js/services/httpClient.js`
- `app/static/js/services/authApi.js`
- `app/static/js/state/authStore.js`
- `app/static/js/components/AuthGate.jsx`
- `app/static/js/components/LoginPage.jsx`
- `app/static/js/components/RegisterPage.jsx`

### Session Flow

启动流程：

1. 读取 `localStorage.access_token`
2. 读取 `/api/auth/my-projects` 作为授权 scope 真源
3. 按 `supported_countries ∩ authorizedScopes` 解析有效 project/country
4. 调 `/api/auth/me`
5. 成功 -> hydrate `authStore` -> 渲染主应用
6. `403` -> 回退到合法 scope 后重试
7. `401` -> 清理 token -> 渲染登录页

### Visual Direction

登录页采用 `ui-ux-pro-max` 推荐的“可信企业 + 数据产品”方向，但避免通用 dashboard 复制感：

- 主色：深蓝 + 冷白 + 琥珀强调
- 字体：`Lexend` + `Source Sans 3`
- 布局：左侧品牌叙事，右侧浮层表单
- 背景：浅色网格 + 柔和辐射光斑 + 数据纹理
- 动效：轻量进入动画，并尊重 `prefers-reduced-motion`

### Frontend Permissions

第一版仅做入口显隐与禁用：

- 无 `data:query:generate`：隐藏 SQL 生成入口
- 无 `data:query:execute`：执行按钮 disabled
- 无 `memory:manage`：隐藏 Memory 管理按钮
- 无 `audit:view`：隐藏 Trace/Audit 管理入口

scope selector 也必须走真实授权边界：

- 不再硬编码国家列表
- 国家选项来自 `supported_countries ∩ authorizedScopes`
- 项目只有一个时不额外展示项目切换

## Persistence Strategy

### Auth Data

用户 / 角色 / 权限 / 审计持久化到 MySQL。

### Existing Local Runtime Data

以下存储本阶段暂不迁移：

- `outputs/orchestrator_sessions/*.json`
- `outputs/memory/memory.sqlite3`

原因：

- 本次目标是先统一 actor 身份，不是一次性替换所有 runtime backend
- 先把 identity contract 打通，再决定后续是否把 session / memory 全量迁入 MySQL

## Backward Compatibility

- `AUTH_ENABLED=false` 时保留 demo identity
- 旧的 `X-User-ID / X-Project-ID / X-Country` header 逻辑只作为 auth-disabled fallback
- `run_agent_loop(user_id=..., project_id=..., country=...)` 兼容保留
- 现有前端 country 切换继续可用，但通过 `X-Country` 和 scope 校验生效

## Risks And Mitigations

### Risk: MySQL 不可用导致本地无法启动

缓解：

- `AUTH_ENABLED=false` fallback
- `scripts/init_auth_db.py` 独立初始化
- 测试使用 SQLite URL 覆盖 auth DB

### Risk: 现有前端大量 fetch 调用改造成本高

缓解：

- 统一收口到 `httpClient`
- 尽量保持原 API payload 不变

### Risk: Orchestrator tests 依赖旧 identity behavior

缓解：

- 保留旧函数签名兼容层
- 先补 route/dependency tests，再补 orchestrator identity propagation tests

## Verification

本阶段最小验收覆盖：

- 注册 / 登录 / 登出 / 刷新保持会话
- `/api/auth/me` 返回 roles / permissions / default scope
- `viewer` 调 `/api/data-acquisition/execute` -> 403
- `analyst` 调 `/api/analyze` -> 允许
- Orchestrator session / trace 持久化真实 `user_id/project_id/country`
- Memory query / write 使用真实身份隔离
- Audit 至少记录 register / login / logout / analyze / trace / data generate / data execute

## Future Follow-up

M0 完成后，后续阶段可直接复用：

- RootGraphState.user_context
- SQL review / approval actor chain
- project-scoped memory
- audit explorer
- MySQL-backed session / trace migration
