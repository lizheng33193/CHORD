# M0 Identity And Permission Foundation Plan

## Goal

在不重写现有 Orchestrator / Data Agent / 前端架构的前提下，建立一套可运行、可验证、可扩展的认证与权限基础层，使真实用户身份可以贯穿 API、Session、Memory、Trace 与 SQL 执行入口。

## Architecture

实现分三层推进：

1. `app/auth/*` 负责身份、角色、权限、JWT、审计
2. `app/core/*context.py` 负责统一 `UserContext` / `RequestContext`
3. 现有业务入口通过 FastAPI dependencies 接入，而不是大范围重写核心 runtime

本轮保持现有 runtime session JSON 与 SQLite memory 不迁移，只把 identity contract 打通。

## Tech Stack

- FastAPI
- SQLAlchemy 2.x
- PyMySQL
- Passlib bcrypt
- python-jose
- React 18 + inline Babel + Tailwind CDN

## File Map

### New backend files

- `app/auth/__init__.py`
- `app/auth/database.py`
- `app/auth/models.py`
- `app/auth/schemas.py`
- `app/auth/password.py`
- `app/auth/jwt.py`
- `app/auth/permissions.py`
- `app/auth/service.py`
- `app/auth/dependencies.py`
- `app/auth/router.py`
- `app/auth/seed.py`
- `app/core/user_context.py`
- `app/core/request_context.py`
- `app/core/audit.py`
- `scripts/init_auth_db.py`

### Modified backend files

- `app/core/config.py`
- `app/main.py`
- `app/api/analyze.py`
- `app/api/analyze_module.py`
- `app/api/analyze_stream.py`
- `app/api/trace.py`
- `app/api/orchestrator_routes.py`
- `app/services/batch_service.py`
- `app/services/orchestrator.py`
- `app/services/orchestrator_agent/schemas.py`
- `app/services/orchestrator_agent/session_store.py`
- `app/services/orchestrator_agent/loop_context.py`
- `app/services/orchestrator_agent/agent_loop.py`
- `app/services/orchestrator_agent/memory_context.py`
- `data_acquisition_agent/api.py`
- `requirements.txt`
- `PLANNING.md`
- `TASK.md`

### New frontend files

- `app/static/js/services/httpClient.js`
- `app/static/js/services/authApi.js`
- `app/static/js/state/authStore.js`
- `app/static/js/components/AuthGate.jsx`
- `app/static/js/components/LoginPage.jsx`
- `app/static/js/components/RegisterPage.jsx`

### Modified frontend files

- `app/ui/build_frontend.py`
- `app/static/js/app.jsx`
- `app/static/js/services/api.js`
- `app/static/js/components/HomeView.jsx`
- `app/static/js/components/DashboardView.jsx`
- `app/static/js/components/panels/chat/MemoryInspector.jsx`

### New tests

- `tests/auth/test_auth_service.py`
- `tests/auth/test_auth_api.py`
- `tests/auth/test_permissions.py`
- `tests/auth/test_seed.py`
- `tests/orchestrator_agent/test_identity_context.py`
- `tests/frontend/test_auth_gate_ui.py`

### Modified tests

- `tests/orchestrator_agent/test_memory_api_sqlite.py`
- `tests/test_trace_analyzer_api.py`

## Execution Order

### Phase 1: Spec And Config Boundary

- 新增 auth 设计文档与实施计划
- 扩展 `settings` 支持 auth env
- 增加 requirements

### Phase 2: RED Tests For Auth Core

- 为 `UserContext`、JWT、register/login、permission guard 写失败测试
- 为 auth-disabled fallback 写失败测试

### Phase 3: Auth Module Implementation

- 建数据库层、ORM、password、JWT、service、router
- 建 seed / init 脚本

### Phase 4: API Guard Integration

- `/api/auth/*`
- `/api/analyze*`
- `/api/trace/*`
- `/api/orchestrator/*`
- `/api/data-acquisition/*`

### Phase 5: Runtime Identity Propagation

- `run_agent_loop` 接 `request_context`
- session / trace metadata 带 actor
- memory facade 使用真实身份

### Phase 6: Frontend Auth Layer

- `AuthGate`
- 登录 / 注册页
- token 持久化
- 统一 `httpClient`
- 基于 permissions 的局部显隐

### Phase 7: Verification And Delivery

- 定向 pytest
- 前端静态 contract tests
- 本地 UI smoke
- `git status --short`
- `git diff --stat`
- `git add` 相关文件
- `git commit`
- `git remote -v` 校验
- `git push`

## Verification Matrix

### Backend

- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- permission denied / 403 matrix
- auth-disabled fallback
- session identity persistence
- trace metadata actor persistence

### Frontend

- 无 token -> 登录页
- 注册成功 -> 登录页
- 登录成功 -> Dashboard
- refresh -> 会话保持
- 401 -> 自动退出
- 403 -> 权限提示

### Integration

- `viewer` 无法 execute SQL
- `analyst` 可跑 analyze / orchestrator
- memory 查询按 user/project/country 隔离

## Commit Strategy

建议按以下逻辑形成一次提交：

- `feat: add m0 identity and permission foundation`

如果中间出现明显独立修复，可拆小 commit，但最终保持单一主题。
