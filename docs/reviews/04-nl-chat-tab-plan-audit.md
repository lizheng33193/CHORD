# Plan #04 审计报告 — R5.5 全量审核与修订记录

| 项 | 值 |
|---|---|
| 审计对象 | `docs/plans/04-nl-chat-tab-frontend-plan.md` |
| 审计版本 | R5.5 Reviewed |
| 审计依据 | Vibe Coding 五点检查法 + Karpathy 四原则 + Superpowers TDD 节律 + 项目 CLAUDE.md / PLANNING.md / TASK.md + 真实代码基线 |
| 审计时间 | 2026-05-04 |
| 审计结论 | **绿灯，可直接作为执行稿**。Plan #01 / #02 / #03 全部 `[complete]`，#04 上游 Gate 已达成；R5.5 在文档层完成 P2-1（TC-1 前向引用）与 P2-2（commit 清单补审计报告）两项收口 |

---

## 一句话结论

R5.4 已通过 Vibe Coding 五点检查与 Karpathy 四原则；R5.5 在“只改 Plan 与审计文档”的边界内进一步收口：把 Plan #03 已完成的事实写进 Plan 头部、把 TC-1 前向引用补成 “需先经 TC-2 / TC-4 拿到真实 session_id”、把 R5.x 审计报告纳入 Phase 3 commit 清单。文档现已满足“执行人无需任何外部澄清即可单人推进 Phase 1 → Phase 3”的执行稿标准。

---

## 本轮新增审计项（R5.5）

### P2-1：TC-1 步骤 5 存在前向引用

**问题**：R5.4 的 TC-1 step 5 让执行人“打开 `http://localhost:8000/?session=<uuid>`”，但 session_id 要等 TC-2 创建对话或 TC-4 完成首轮后才能产生；新执行人若严格按顺序读 TC-1，会无法构造合法 UUID。

**影响**：手测脚本可执行性下降，执行人会被迫离开文档去翻 Plan #03 / 后端日志找 UUID。

**修复**：R5.5 改写 TC-1 step 5 为 “**本步需先完成 TC-2 / TC-4 拿到真实 `<uuid>`**：用 TC-2 创建的 session_id 拼出 `http://localhost:8000/?session=<uuid>`，期望直接进入 DashboardView，第 8 个 tab 高亮，并触发 session restore（无真实 session_id 时跳过本步）”。删除原 step 6（与新 step 5 冗余）。

### P2-2：Phase 3 commit 文件清单未包含审计报告

**问题**：R5.4 Phase 3 Task 3.5 的 `git add` 列表只含 Plan 文件，不含 `docs/reviews/04-nl-chat-tab-plan-audit.md`；执行轮次产生的 R5.5 → R5.6 审计行将被遗漏。

**影响**：违反 “文件驱动而非对话记忆” 原则，下次新对话读不到执行轮次的审计变更。

**修复**：R5.5 在 Phase 3 Task 3.5 的 `git add` 命令末尾追加 `docs/reviews/04-nl-chat-tab-plan-audit.md`。

---

## 仍保留观察的 P2 项（不阻塞执行，留 V1.1 polish）

- **P2-3：离开 chat tab 时 URL 不擦 `?session=`**。当前 URL 同步只写不擦；若需要切换到其他 tab 时清掉 session 上下文，可在执行轮次的"切到非 chat tab 的 useEffect" 里加 `params.delete('session')`。建议留 V1.1。
- **P2-4：ChatPanel 卸载时 `setStreaming(false)` 可能在 unmount 后执行**。React 18 StrictMode 下会出现 warning，可用 `mountedRef` 包裹。建议留 V1.1。

---

## 继承 R5.4 的修订项

### P0-1：`?tab=chat` 初始打开不成立（R5.4 已解决）

**问题**：R5.3 只要求把 `activeTab` 初始化为 URL 中的 tab，但真实 `app/static/js/app.jsx` 当前还有 `const [view, setView] = useState('home');`。因此打开 `http://localhost:8000/?tab=chat` 时，React 仍会先渲染 HomeView，用户看不到 DashboardView，也看不到第 8 个 chat tab。

**影响**：Scope、TC-1 手测、完成标志里的“`/?tab=chat` 可直接打开 chat tab”都会失真；执行人照 R5.3 做完后仍无法通过核心入口验收。

**修复**：R5.4 将 Phase 3 Task 3.2 升级为“初始入口与 tab URL 双向同步”：新增 `getInitialViewFromUrl()` 和 `getInitialDashboardTab()`；普通 `/` 保持 HomeView，`/?tab=chat` 与 `/?session=<uuid>` 直接进入 DashboardView 的 chat tab。Phase 3 Task 3.1 的静态测试同步增加 `useState(getInitialViewFromUrl)`、`useState(getInitialDashboardTab)`、`params.get('session')` 等断言。

---

## 继承 R5.3 的修订项

### P1-1：Plan 头部版本与日期滞后

**问题**：Plan 仍标记 R5.2 / 2026-05-03。

**影响**：后续对话仅靠文件驱动时会误判当前审计轮次。

**修复**：更新为 `R5.4 Reviewed` 与 `2026-05-04`。

### P1-2：固定测试基线数字易腐化

**问题**：Plan 头部写死 `tests/ 270` 与 `data_acquisition_agent/tests/ 163`。

**影响**：仓库演进后即变成伪约束，可能引发错误阻塞或误报。

**修复**：改为“以执行当日实际结果为准”，同时保留双侧回归命令。

### P1-3：漂移核对脚本对 api.js 断言过于脆弱

**问题**：原脚本要求 `window.AppServices.api = {...}` 整行文本完全匹配。

**影响**：仅代码格式或换行变化也会失败，违背“验证 > 信任”里的有效验证原则。

**修复**：改为符号级断言：`window.AppServices` 初始化存在，且 `analyzeByUidStream / analyzeModule / fetchTrace` 关键导出存在。

### P1-4：本轮工作边界未在 Plan 显式标注

**问题**：任务要求本轮只做文档审核修订，但 Plan 文本未显式声明。

**影响**：后续执行者可能误将本轮当成实现启动轮次。

**修复**：在 Scope 的“本 Plan 不做”补充“当前轮次（R5.4）不启动 Phase 1/2/3 执行”。

---

## 五点检查法复审（R5.5）

| 检查点 | R5.5 结果 | 说明 |
|---|---|---|
| 精确文件路径 | 通过 | 每个 Task 明确写出 `app/static/js/...`、`app/ui/build_frontend.py`、`tests/frontend/...`，且 URL state owner 落在 `app.jsx` |
| 无占位符 | 通过 | 执行代码块无 `...保持...` / `同上省略` / TODO/TBD 占位；TC-1 step 5 已用真实 session_id 前置说明替代 `<uuid>` 凭空构造 |
| 完整代码块 | 通过 | 组件、reducer、API service、DashboardView、app.jsx 初始入口与 URL 同步、ChatPanel 终态均为可复制完整块 |
| 验证命令 | 通过 | RED/GREEN/回归命令完整；Node 动态 reducer 测试明确"缺 Node 失败不跳过" |
| 单一执行人 | 通过 | Phase 顺序、diff 审核点、commit 关卡清晰；上游 Gate（#01/#02/#03 `[complete]`）已达成；Phase 3 commit 文件清单已含审计报告 |

---

## Karpathy 四原则复审

| 原则 | R5.5 结果 |
|---|---|
| Think Before Coding | 通过 — Phase 0 baseline 漂移核对仍保留为执行当天再确认 |
| Simplicity First | 通过 — 7 组件 + 1 reducer + 5 API 函数 + 2 helper，无 Redux/Zustand/jest/npm |
| Surgical Changes | 通过 — 显式不动 `data_acquisition_agent/` / `.agents/skills/` / 7 个既有 panels；改动列表明确 |
| Goal-Driven Execution | 通过 — 完成标志 7 项 + TC-1～TC-5 + 双侧回归命令；TC-1 step 5 不再凭空构造 UUID |

---

## TDD 节律复审

| Phase | RED 失败原因 | GREEN 通过条件 | 节律 |
|---|---|---|---|
| Phase 1 | chat 目录 / 7 文件 / Dashboard 分支不存在 | 创建 7 组件 + LOAD_ORDER + Dashboard 改 6 处 | 通过 |
| Phase 2 | `chatReducer.js` 不存在 + 11 个 case 缺失 + Node 动态 walk 失败 | 创建 reducer + Stateful ChatPanel + 5 API 函数 | 通过 |
| Phase 3 | `getInitialViewFromUrl/getInitialDashboardTab` 缺、`useState(...)` 函数形式缺、`params.get('session')` 缺 | 注入两 helper + 替换两 useState + URL 同步 useEffect | 通过 |

Node 缺失策略 `pytest.fail("...do not skip this test.")` 满足 Superpowers “RED must FAIL not SKIP”。

---

## 剩余执行 Gate

1. ✅ Plan #01 / #02 / #03 全部 `[complete]`（a949830 / 874c305 / 8fb3377）— **R5.5 已达成**
2. 本机若无 Node.js，`tests/frontend/test_chat_reducer.py::test_reducer_walks_full_session` 会失败；按规则不降级为 skip。
3. Plan #03 的 SSE / ACK / GET session shape 若与 R5.5 假设不一致，优先在 Plan #03 修后端契约，不在 Plan #04 私改后端。
4. 每个 Phase commit 前必须先展示 `git diff --stat` 并等用户确认。
5. 执行轮次仍需遵守硬边界：不修改 `data_acquisition_agent/`、不修改 `.agents/skills/`、不触碰既有 7 个 Tab 业务组件逻辑。

---

## 审计结论

R5.5 通过，可作为执行稿。Plan #01/#02/#03 已 `[complete]`，#04 上游 Gate 已达成；R5.5 完成 P2-1（TC-1 前向引用）与 P2-2（commit 清单）两项文档收口。下一步在用户明确启动指令后即可进入 Phase 1 → Phase 2 → Phase 3 执行，并在每个 Phase 绿灯后做 diff 审核与 commit。
