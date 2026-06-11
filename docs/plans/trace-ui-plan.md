# Trace 前端 UI 实现 Plan

- **关联 Design Doc**：[docs/specs/trace-ui-design.md](../specs/trace-ui-design.md)
- **关联后端 Spec**：[docs/specs/trace-analyzer-design.md](../specs/trace-analyzer-design.md)
- **关联后端 Plan**：[docs/plans/trace-analyzer-plan.md](trace-analyzer-plan.md)
- **目标**：为 `GET /api/trace/{uid}` 增加 Dashboard 内懒加载 Trace tab，覆盖 path_graph / friction_hotspots / time_pattern / churn_story / intervention_suggestions / key_events_tail 六个数据块
- **状态**：Plan Draft（待审核）
- **作者**：v-yimingliu
- **日期**：2026-05-01

---

## 0. 不变量（每个 Task 执行前后必须满足）

| # | 不变量 | 验证方式 |
|---|---|---|
| 0.1 | 不修改 `/api/analyze` 链路 | `git diff app/api/ app/services/orchestrator.py` 为空 |
| 0.2 | 不修改 [app/static/js/app.jsx](../../app/static/js/app.jsx) view 状态机；如发现必须改 app.jsx，**停下重新确认设计** | `git diff app/static/js/app.jsx` 为空 |
| 0.3 | 不修改 [app/static/js/components/panels/OpsAdvicePanel.jsx](../../app/static/js/components/panels/OpsAdvicePanel.jsx) | `git diff app/static/js/components/panels/OpsAdvicePanel.jsx` 为空 |
| 0.4 | 不新增 npm/package.json 依赖；不引入新 CDN | `git diff app/static/index.html` 仅可能新增 `<script type="text/babel" src="/static/js/components/panels/trace/*.jsx">` 标签（与现有 panel 一致），不新增 `https://...` CDN |
| 0.5 | 不修改任何 `tests/fixtures/golden/**`；如执行前 status 已有 fixture modified，保持未暂存、未提交；如当前无 fixture modified，不要求制造或保持 modified 状态 | `git diff -- tests/fixtures/golden/` 不应出现本任务新增改动；commit 前不要 `git add` 任何 fixture |
| 0.6 | 不修改禁止目录：`.agents/skills/`、`app/agents/`、`data_acquisition_agent/`（与本任务无关） | `git diff` 验证 |
| 0.7 | 不修改 `tests/`（Plan 阶段不写前端测试）；如需 contract 测试，列入 Out-of-Scope 或后续 Plan | `git diff tests/` 为空 |
| 0.8 | 所有新增 `app/static/js/components/panels/trace/*.jsx` 文件 ≤500 行 | `wc -l` 验证 |
| 0.9 | `git add` 必须显式路径，禁止 `git add .` / `git add -A` | 每个 Task 的 commit 步骤显式列出文件 |
| 0.10 | 不 push（直到用户显式要求） | 不出现 `git push` |
| 0.11 | 不修改 CLAUDE.md / PLANNING.md / TASK.md | `git diff` 验证 |

---

## 1. 事实勘察结果（基于只读勘察，2026-05-01）

### 1.1 services/api.js 现有导出方式
**不是 ES module**。文件末尾 [api.js:96-97](../../app/static/js/services/api.js#L96-L97)：
```js
window.AppServices = window.AppServices || {};
window.AppServices.api = { analyzeByUid, analyzeByFile, analyzeByUidStream };
```
**Plan 影响**：`fetchTrace` 必须用同款 `window.AppServices.api.fetchTrace = fetchTrace` 注入方式，**不**用 `export async function`。这与 Design Doc §3.5 的伪代码示例不一致——Design Doc 已标注"实际导出语法以当前 api.js 为准，Plan 阶段确认并对齐"，本 Plan 据此对齐。

### 1.2 DashboardView 实际路径与结构
- 路径：[app/static/js/components/DashboardView.jsx](../../app/static/js/components/DashboardView.jsx)
- tabs 数组定义：L87-94，6 项（comprehensive / app / behavior / credit / product / ops）
- content switch：L166-171（一连串 `{activeTab === '...' && <Panel .../>}`）
- 组件挂载：`window.AppComponents.DashboardView = DashboardView`（L179）
- `activeTab` state **不在 DashboardView 内部**，而是由 [app.jsx:41](../../app/static/js/app.jsx#L41) `useState('comprehensive')` 管理，通过 props 下传

### 1.3 app.jsx 不修改的可行性确认
- `activeTab` 字符串值新增 `'trace'` **不需要修改 app.jsx 源码**（state 是字符串，无枚举校验）
- DashboardView 接收 `activeTab` / `setActiveTab` props，可在 DashboardView 内部独立新增 `traceCacheByUid` state，无需上提到 app.jsx
- **结论**：Phase D 不需改 app.jsx；如果实施时发现必须改，按不变量 0.2 停下重新确认

### 1.4 MarkdownBlock 实际签名
- 路径：[app/static/js/components/common/MarkdownBlock.jsx](../../app/static/js/components/common/MarkdownBlock.jsx)
- 实际签名：[MarkdownBlock.jsx:17](../../app/static/js/components/common/MarkdownBlock.jsx#L17) `function MarkdownBlock({ text })`
- **Trace UI 必须使用 `<MarkdownBlock text={...} />`**，这不是偏离实现，而是基于实际组件签名的兼容要求
- 如 [OpsAdvicePanel.jsx](../../app/static/js/components/panels/OpsAdvicePanel.jsx) 中存在 `content={...}` 用法，**本 Plan 不修复、不触碰 OpsAdvicePanel**（不变量 0.3）
- **挂载**：`window.AppComponents.MarkdownBlock`

### 1.5 OpsAdvicePanel 复用资产位置
- `churnLevelBadgeClass(level)`：[OpsAdvicePanel.jsx:12-24](../../app/static/js/components/panels/OpsAdvicePanel.jsx#L12-L24)，函数定义在文件顶层但**未导出**到 `window`
- `churnRootCauseLabels`：[OpsAdvicePanel.jsx:67-74](../../app/static/js/components/panels/OpsAdvicePanel.jsx#L67-L74)，**定义在 `OpsAdvicePanel` 函数体内部**，组件外不可访问
- **Plan 影响**：trace 子组件必须**复制**这两段（复制后加 cross-link 注释指向 OpsAdvicePanel 的对应行号），与 Design Doc §5.2 / §11 锁定一致

### 1.6 现有 tab / 图标占用
- DashboardView 已存在 6 个 tab：comprehensive / app / behavior / credit / product / ops（命名简短，未带 `_profile` 后缀）
- lucide `Activity` 图标已被 **behavior tab** 占用（[DashboardView.jsx:90](../../app/static/js/components/DashboardView.jsx#L90)）
- **Design Doc §3.1 已锁定 trace 也使用 `Activity`**，本 Plan 遵循 Design Doc 决策
- **说明**：`Activity` 已被 behavior tab 使用，但 Design Doc 已锁定 trace 也使用 `Activity`；本次不因图标重复偏离设计。如后续需要区分图标，单独修 Design Doc

### 1.7 index.html 加载机制
- 路径：[app/static/index.html](../../app/static/index.html)
- 加载方式：`<script type="text/babel" src="...">`（babel-standalone 运行时编译）
- **现状疑点**：index.html 的 script 列表（L23-47）**未包含** `panels/OpsAdvicePanel.jsx`、`panels/ProductAdvicePanel.jsx`，但这两个 panel 在生产中确实工作。可能机制：
  - 假设 A：index.html 是过时副本（后端实际服务的是别处生成的 HTML）
  - 假设 B：babel-standalone / 浏览器有兜底加载
  - 假设 C：列表只是不完整但能运行（不严格依赖顺序）
- **Plan 影响**：Phase E.1 必须**实测**——trace 子组件文件落盘后，先**不**改 index.html 启动服务，看是否能加载；如不能，再按现有 panel 同款风格新增 `<script type="text/babel" src="/static/js/components/panels/trace/*.jsx">` 标签。新增 script 标签**不算引入新依赖**（不变量 0.4 允许）

### 1.8 现有 product / ops tab 已存在
- product / ops 的 tab 项已在 [DashboardView.jsx:92-93](../../app/static/js/components/DashboardView.jsx#L92-L93) 注册，content switch 在 [L170-171](../../app/static/js/components/DashboardView.jsx#L170-L171)
- 验证 Design Doc 假设："Trace 作为 Dashboard 现有 Skill tab 后的新增 tab"——成立

---

## 2. 实现阶段拆分

### Phase A：前置只读确认（无文件改动，2-3 分钟）

#### Task A.1：再次确认事实表
- **目标**：执行 Plan 前重新核对 §1 勘察结果是否仍成立（防止其他窗口并行改动）
- **操作**：
  ```bash
  git status --short
  git log --oneline -5
  ```
  + 只读 `app/static/js/services/api.js` 末尾、`DashboardView.jsx` L87-94 与 L166-171
- **新增/修改文件**：无
- **验证**：勘察结果与 §1 一致，未发现并行改动
- **commit**：无（只读）

#### Task A.2：（已收敛，无需用户确认偏离）
- **目标**：trace tab lucide 图标遵循 Design Doc §3.1 锁定值 `Activity`，不偏离 Design Doc
- **操作**：无需用户额外确认；如未来需区分 trace / behavior 图标，单独修 Design Doc
- **新增/修改文件**：无
- **验证**：实施 Task D.1 时核对图标值 = `Activity`
- **commit**：无

#### Task A.3：（已收敛，仅记录策略）
- **目标**：记录 index.html 默认不修改策略；实测延后到 Phase E.1
- **策略**：**默认不修改 index.html**；先用当前加载机制实测；只有出现 `TracePanel is not defined` / 组件未加载 / Network 缺少 trace 脚本时，才**停下汇报，让 user 确认**后再进入 Task D.2
- **新增/修改文件**：无
- **验证**：策略写入本 Plan 即可，无需额外用户确认
- **commit**：无

---

### Phase B：API service 层（1 个 Task，3 分钟）

#### Task B.1：在 api.js 新增 fetchTrace
- **目标**：扩展 `window.AppServices.api`，新增 `fetchTrace(uid)`，404 → `{ uid, status: 'data_missing' }`
- **新增/修改文件**：[app/static/js/services/api.js](../../app/static/js/services/api.js)（修改）
- **操作概要**（不在本 Plan 写完整代码，下面是要点）：
  1. 在 `analyzeByUidStream` 函数后新增 `async function fetchTrace(uid)`
  2. 函数体：
     - `const res = await fetch(\`/api/trace/${encodeURIComponent(uid)}\`);`
     - `if (res.status === 404) return { uid, status: 'data_missing' };`
     - `if (!res.ok) throw new Error(\`trace_http_${res.status}\`);`
     - `return await res.json();`
  3. 末尾注入对象增补：`window.AppServices.api = { analyzeByUid, analyzeByFile, analyzeByUidStream, fetchTrace };`
- **验证命令**：
  ```bash
  grep -n "fetchTrace" app/static/js/services/api.js
  wc -l app/static/js/services/api.js
  git diff app/static/js/services/api.js | head -50
  ```
- **commit**：`feat(trace-ui): add fetchTrace to api.js with 404 → data_missing mapping`
- **commit 命令**：`git add app/static/js/services/api.js && git commit -m "..."`

---

### Phase C：trace 子组件（7 个 Task，每 3-5 分钟）

约定：所有 trace 子组件放置于 `app/static/js/components/panels/trace/`，每个文件末尾用 `window.AppComponents.XxxCard = XxxCard;` 注入（与现有 panel 一致）。每个文件 ≤500 行。

#### Task C.1：ChurnStoryCard.jsx
- **目标**：渲染 `response.churn_story`（MarkdownBlock）+ `model_unavailable` 角标
- **新增文件**：`app/static/js/components/panels/trace/ChurnStoryCard.jsx`
- **操作概要**：
  - props: `{ story, modelTrace }`
  - 用 `window.AppComponents.MarkdownBlock` 渲染（**实际签名 `{ text }`**，§1.4，调用形式 `<MarkdownBlock text={story} />`）
  - `modelTrace?.used_llm === false` 时右上角加灰色徽章 `模板兜底（model_unavailable）`
  - 视觉：violet→purple 渐变背景，仿 OpsAdvicePanel retention_pitch 区
- **验证命令**：`wc -l app/static/js/components/panels/trace/ChurnStoryCard.jsx`（≤500）
- **commit**：`feat(trace-ui): add ChurnStoryCard for churn_story narrative`

#### Task C.2：PathGraphCard.jsx
- **目标**：双列表（top_pages 表 + top_transitions 卡片列表）
- **新增文件**：`app/static/js/components/panels/trace/PathGraphCard.jsx`
- **操作概要**：
  - props: `{ pathGraph }` 即 `{ top_pages, top_transitions }`
  - 桌面端 `md:grid-cols-2`，移动端单列
  - 左列：表格 `页面 | 访问 | 平均停留`，按 visit_count desc
  - 右列：每条 transition 行 `[from] →(ArrowRight) [to] ×count`，count 用蓝色 badge
  - lucide：`ArrowRight`（来自 `window.LucideReact`）
- **验证**：`wc -l ...` ≤500
- **commit**：`feat(trace-ui): add PathGraphCard with top_pages table + transitions list`

#### Task C.3：TimePatternCard.jsx
- **目标**：纯 CSS 24 柱状图 + active_window_label
- **新增文件**：`app/static/js/components/panels/trace/TimePatternCard.jsx`
- **操作概要**：
  - props: `{ timePattern }` 即 `{ hour_histogram, active_window_label }`
  - 顶部紫色徽章渲染 `active_window_label`
  - 24 柱：`flex items-end gap-px h-32`；单柱 `flex-1`
  - `max = Math.max(...hour_histogram, 0)`；`max === 0` 时全部 `bg-slate-100`，跳过比例
  - 比例分段（Design Doc §5.5 锁定）：
    - `count == 0` → `bg-slate-100`
    - `0 < r ≤ 0.25` → `bg-violet-300`
    - `0.25 < r ≤ 0.5` → `bg-violet-400`
    - `0.5 < r ≤ 0.75` → `bg-violet-500`
    - `r > 0.75` → `bg-violet-600`
  - 单柱 `title={hour + ':00 → ' + count + ' 事件'}`（字符串拼接，避免模板嵌套）
  - 底部刻度：0 / 6 / 12 / 18 / 23
- **验证**：`wc -l ...` ≤500
- **commit**：`feat(trace-ui): add TimePatternCard with 24-bar CSS histogram`

#### Task C.4：FrictionHotspotGrid.jsx
- **目标**：severity 色标卡片网格
- **新增文件**：`app/static/js/components/panels/trace/FrictionHotspotGrid.jsx`
- **操作概要**：
  - props: `{ hotspots }` 即 `list[FrictionHotspot]`
  - 在文件顶层**复制** `churnLevelBadgeClass`（来自 OpsAdvicePanel.jsx:12-24），加 cross-link 注释
  - 排序：severity desc，同级按 `retry_count + error_count` desc
  - 网格 `grid-cols-1 md:grid-cols-2 gap-4`
  - 单卡：左侧 4px 色条（high=red-500 / medium=amber-500 / low=slate-400）；顶行 step + severity 徽章；三列 `重试 X · 错误 Y · 停留 Zs`
- **验证**：`wc -l ...` ≤500
- **commit**：`feat(trace-ui): add FrictionHotspotGrid with severity colored cards`

#### Task C.5：InterventionList.jsx
- **目标**：干预建议列表卡
- **新增文件**：`app/static/js/components/panels/trace/InterventionList.jsx`
- **操作概要**：
  - props: `{ suggestions }`
  - 每条卡：顶部蓝色 pill 显示 hotspot；MarkdownBlock 渲染 advice（**调用 `<MarkdownBlock text={advice} />`**，§1.4）；右下灰色小字 channel_hint
- **验证**：`wc -l ...` ≤500
- **commit**：`feat(trace-ui): add InterventionList for intervention suggestions`

#### Task C.6：KeyEventsTimeline.jsx
- **目标**：默认折叠的事件时间轴
- **新增文件**：`app/static/js/components/panels/trace/KeyEventsTimeline.jsx`
- **操作概要**：
  - props: `{ events }`
  - `useState(false)` 控制展开/折叠（默认折叠，§11 锁定）
  - 标题行：`最后 N 步事件` + chevron 图标
  - 展开后：左侧竖线 + 圆点；每行 `[+{ts_offset}s] {page} · {event}{field?: " · " + field}`，等宽字体；按 ts_offset 升序
- **验证**：`wc -l ...` ≤500
- **commit**：`feat(trace-ui): add KeyEventsTimeline collapsible event log`

#### Task C.7：TracePanel.jsx（入口）
- **目标**：状态机分发 + 子卡片编排 + ChurnRootCauseBar + Header
- **新增文件**：`app/static/js/components/panels/trace/TracePanel.jsx`
- **操作概要**：
  - props: `{ uid, cacheEntry, onRetry }`
  - 顶部**复制** `churnRootCauseLabels`（来自 OpsAdvicePanel.jsx:67-74），加 cross-link 注释
  - 渲染分支按 Design Doc §3.4 表格：idle / loading / success+(ok|model_unavailable|insufficient_events|data_missing|error) / error
  - 编排顺序：Header → ChurnRootCauseBar（`no_clear_signal` 时不渲染）→ ChurnStoryCard → PathGraphCard + TimePatternCard 双列 → FrictionHotspotGrid → InterventionList → KeyEventsTimeline → model_trace 灰色脚注
  - lucide 图标：**`Activity`**（与 Design Doc §3.1 锁定一致；§1.6 已说明与 behavior tab 共用 `Activity`，本次不偏离设计）
  - 末尾 `window.AppComponents.TracePanel = TracePanel;`
- **验证**：`wc -l ...` ≤500；`grep -n "window.AppComponents.TracePanel" ...` 命中
- **commit**：`feat(trace-ui): add TracePanel orchestrator with two-layer status branching`

---

### Phase D：DashboardView 集成（2 个 Task）

#### Task D.1：在 DashboardView 增加 trace tab + 缓存 + fetch 触发
- **目标**：tabs 数组追加 `trace` 项；新增 `traceCacheByUid` state；首次切到 trace tab 触发 `fetchTrace`；retry 清当前 uid 缓存
- **修改文件**：[app/static/js/components/DashboardView.jsx](../../app/static/js/components/DashboardView.jsx)
- **操作概要**：
  1. 在 [DashboardView.jsx:6](../../app/static/js/components/DashboardView.jsx#L6) lucide 解构追加项**：`Activity` 已存在（被 behavior 使用），无需新增解构；trace tab 直接复用同一 `Activity` 引用（与 Design Doc §3.1 锁定一致）
  2. 在 [L15](../../app/static/js/components/DashboardView.jsx#L15) `window.AppComponents` 解构追加 `TracePanel`
  3. 在 [L87-94](../../app/static/js/components/DashboardView.jsx#L87-L94) tabs 数组末尾追加：
     ```js
     { id: 'trace', title: '深度行为解析', sub: 'Trace Analysis', icon: Activity, bg: 'from-purple-400 to-violet-600', shadow: 'shadow-violet-500/30' }
     ```
  4. 在 DashboardView 函数顶部新增 `const [traceCacheByUid, setTraceCacheByUid] = React.useState({});`
  5. 新增 `useEffect`：当 `activeTab === 'trace'` 且 `!traceCacheByUid[uid]` 时，先 setState `{ requestStatus: 'loading' }`，再调 `window.AppServices.api.fetchTrace(uid)`，resolve → `{ requestStatus: 'success', response }`，reject → `{ requestStatus: 'error', errorMessage }`
  6. 新增 `handleRetry(uid)`：从 `traceCacheByUid` 删除该 uid 条目，触发 useEffect 重新 fetch
  7. 在 [L166-171](../../app/static/js/components/DashboardView.jsx#L166-L171) content switch 末尾追加：`{activeTab === 'trace' && <TracePanel uid={uid} cacheEntry={traceCacheByUid[uid]} onRetry={() => handleRetry(uid)} />}`
- **验证命令**：
  ```bash
  git diff app/static/js/components/DashboardView.jsx
  git diff app/static/js/app.jsx   # 必须为空（不变量 0.2）
  wc -l app/static/js/components/DashboardView.jsx   # ≤500
  ```
- **commit**：`feat(trace-ui): wire trace tab with lazy fetch + per-uid cache in DashboardView`

#### Task D.2：（条件性，需 user 确认后才执行）index.html 注册 trace script 标签

**默认不执行**。仅在 Phase E.1 实测出现以下任一信号时触发，并且**必须先停下汇报、让 user 显式确认**后才允许执行：
- DevTools Console 报 `TracePanel is not defined` 或 `XxxCard is not defined`
- trace tab 点击后页面崩溃 / 空白且 React 无对应组件挂载
- DevTools Network 明确缺少 trace 相关脚本请求

- **目标**：在 [app/static/index.html](../../app/static/index.html) 新增 trace 子组件 `<script type="text/babel">` 标签，使 babel-standalone 能加载它们
- **修改文件**：[app/static/index.html](../../app/static/index.html)（条件性修改）
- **严格约束**（D.2 内任何步骤违反则停下回报）：
  - 只允许新增 `<script type="text/babel" src="/static/js/components/panels/trace/*.jsx">` 行
  - **不允许新增** `https://...` CDN 标签
  - **不允许修改** 现有 CDN 版本号（react / react-dom / tailwind / lucide-react / babel-standalone 全部冻结）
  - **不允许引入** 新依赖（npm / package.json / 其他 CDN 服务）
  - 加载顺序：先加载 6 个子组件，最后加载 TracePanel.jsx（依赖关系）
- **操作概要**（仅条件触发且 user 确认后）：
  - 在 panels script 区块（与现有 `BehaviorPanel.jsx` 等同位置）新增 7 行：
    ```html
    <script type="text/babel" src="/static/js/components/panels/trace/ChurnStoryCard.jsx"></script>
    <script type="text/babel" src="/static/js/components/panels/trace/PathGraphCard.jsx"></script>
    <script type="text/babel" src="/static/js/components/panels/trace/TimePatternCard.jsx"></script>
    <script type="text/babel" src="/static/js/components/panels/trace/FrictionHotspotGrid.jsx"></script>
    <script type="text/babel" src="/static/js/components/panels/trace/InterventionList.jsx"></script>
    <script type="text/babel" src="/static/js/components/panels/trace/KeyEventsTimeline.jsx"></script>
    <script type="text/babel" src="/static/js/components/panels/trace/TracePanel.jsx"></script>
    ```
- **验证命令**：
  ```bash
  git diff app/static/index.html
  # 仅看到新增 <script type="text/babel"> 标签；无 https:// 行新增；无版本号变化
  grep -c "https://" app/static/index.html   # 与 Phase A 基线比对，数字不变
  ```
- **commit**：`chore(trace-ui): register trace panel scripts in index.html`
- **注**：如 Phase E.1 实测无需该 Task，跳过；Plan 完成报告写"D.2 跳过，原因：实测无需"

---

### Phase E：验证（多 Task，10-15 分钟）

#### Task E.1：静态加载验证
- **目标**：服务启动后浏览器无 JS 错误，trace tab 可点击
- **操作**：
  ```bash
  python -m uvicorn app.main:app --reload --port 8000   # 后台启动
  curl -s http://localhost:8000/static/js/components/panels/trace/TracePanel.jsx | head -5
  ```
  + 浏览器打开 `http://localhost:8000`，DevTools Console 无报错
  + 如有 `TracePanel is not defined` / `XxxCard is not defined` / trace tab 崩溃 / Network 缺 trace 脚本：**停下汇报，让 user 确认是否触发 Task D.2**，未确认前不修改 index.html
- **验证**：DevTools Console 干净；trace tab 可见；点击不崩溃
- **commit**：无（验证步骤）

#### Task E.2：懒加载 Network 验证
- **目标**：进入 dashboard 不请求 trace；首次切才请求；切回不重复请求
- **操作**：浏览器 DevTools Network → 跑一个 uid → dashboard 出现后 Filter 只看 `trace`：
  - 默认 0 个请求 ✓
  - 切到 trace tab：1 个 `GET /api/trace/{uid}` ✓
  - 切到其他 tab 再切回 trace：仍 1 个（无新请求）✓
- **验证**：手动 Network 截图记录
- **commit**：无

#### Task E.3：5 种 status 分支手动验证
- **目标**：5 种 response.status + requestStatus=error 全部覆盖
- **策略**：
  - `ok` / `model_unavailable`：用现有 uid（mock 模式自然是 model_unavailable）
  - `insufficient_events`：用事件极少的 uid（如新建 mock CSV 仅 5 行）
  - `data_missing`：用不存在的 uid `999999999999999999`（应 404）
  - `error`：临时把后端返回 `status: "error"`（用环境变量或临时改 trace 后端，**完成后回滚**）
  - `requestStatus=error`：DevTools 离线模式或后端返回 500
- **验证**：每种状态 UI 渲染符合 Design Doc §3.4 表格
- **commit**：无

#### Task E.4：约束扫描
- **操作**：
  ```bash
  git diff app/static/js/app.jsx                        # 必须为空
  git diff app/static/js/components/panels/OpsAdvicePanel.jsx   # 必须为空
  grep -c "https://" app/static/index.html              # 不增加（与 Phase A 基线对比）
  find app/static/js/components/panels/trace -name "*.jsx" -exec wc -l {} \;   # 全部 ≤500
  git diff -- tests/fixtures/golden/                    # 不应出现本任务新增改动；commit 前不要 add 任何 fixture
  ```
- **验证**：全部命令输出符合预期
- **commit**：无

#### Task E.5：churn_root_cause 边界
- **目标**：`['no_clear_signal']` 时 ChurnRootCauseBar 不渲染（验收 11）
- **操作**：找一个 ops_advice 输出 churn_root_cause = `['no_clear_signal']` 的 uid，切到 trace tab 看是否隐藏整条
- **commit**：无

#### Task E.6：KeyEventsTimeline 默认折叠
- **操作**：浏览器中验证 trace tab 加载完成后该卡片默认是折叠态（验收 12）
- **commit**：无

---

## 3. 验收标准（执行 checklist，源自 Design Doc §10）

| # | 标准 | 验证方式 | 对应 Task |
|---|---|---|---|
| 1 | 默认进入 Dashboard 不发起 `/api/trace/{uid}` 请求 | DevTools Network 验证 | E.2 |
| 2 | 只有首次切到 trace tab 才发起请求 | DevTools Network 验证 | E.2 |
| 3 | 同 uid 切走再切回不重复请求（缓存命中） | DevTools Network 验证 | E.2 |
| 4 | 多 uid result 切换时各自缓存独立 | DevTools Network + 切换 uid 按钮 | E.2 |
| 5 | `requestStatus=loading` 时显示 skeleton | 慢速网络 throttle | E.3 |
| 6 | `response.status=ok` 渲染 6 个数据块全部可见 | 浏览器视觉 | E.3 |
| 7 | `response.status=model_unavailable` 渲染规则产物 + 顶部琥珀提示 + ChurnStoryCard 角标 | 浏览器视觉 | E.3 |
| 8 | `insufficient_events` / `data_missing` 渲染对应空态 | 浏览器视觉 | E.3 |
| 9 | `response.status=error`（200 业务错）渲染错误态卡片，**无**重试按钮 | 浏览器视觉 | E.3 |
| 10 | `requestStatus=error`（网络/5xx）显示重试按钮，点击清缓存重新 fetch | 离线模式 + 重试 | E.3 |
| 11 | `churn_root_cause === ['no_clear_signal']` 时 ChurnRootCauseBar 不渲染 | 浏览器视觉 | E.5 |
| 12 | KeyEventsTimeline 默认折叠 | 浏览器视觉 | E.6 |
| 13 | 默认不修改 app.jsx；如必须改，停下重新确认 | `git diff app/static/js/app.jsx` 为空 | E.4 |
| 14 | 不修改 OpsAdvicePanel.jsx 任何行 | `git diff` 为空 | E.4 |
| 15 | 不引入新前端 npm/CDN 依赖 | `git diff index.html` 仅可能新增 `text/babel` 标签 | E.4 |
| 16 | 所有 `trace/*.jsx` ≤500 行 | `wc -l` | E.4 |
| 17 | 不修改任何 `tests/fixtures/golden/**`；如执行前已有 fixture modified，保持未暂存；无则不要求制造 | `git diff -- tests/fixtures/golden/` 无本任务新增改动 | E.4 |

---

## 4. 风险与回滚

### 4.1 风险

| 风险 | 触发条件 | 缓解 |
|---|---|---|
| Trace fetch 慢（LLM 秒级） | 后端实际调 LLM 时 | TracePanel `loading` 态有 skeleton 与 "正在解析..." 文案；用户可切回其他 tab 不阻塞 |
| 后端 schema 字段变动 | trace_analyzer 后端迭代 | 严格依赖 [app/schemas/trace_analyzer.py](../../app/schemas/trace_analyzer.py)；前端用可选链 `?.` 防御；后续 Plan 可加最小契约测试（本 Plan Out-of-Scope） |
| 404 映射误用（把真正的 404 当业务正常） | fetchTrace 把所有 404 视为 data_missing | 接受该简化（与 Design Doc §3.5 一致）；后续如后端有其他 404 语义，再细化 |
| 缓存导致 stale | 用户希望强制刷新但只能切 tab | 提供"重试"按钮（仅 `requestStatus=error` 出现）；`ok` / `model_unavailable` 状态下手动强刷需刷新整页（接受） |
| **不变量 0.2 违反**：实施时发现必须改 app.jsx | 例如 `activeTab` 初始值要默认 `trace` | **停下，回 Step 2 修订 Design Doc**；不绕过 |
| 零依赖图表可读性 | 24 柱状图 / 桑基替代列表对非技术用户不直观 | active_window_label 文字 + hover tooltip 双信道；后续可升级为桑基（Design Doc §14 已标注） |
| trace 与 behavior tab 共用 `Activity` 图标导致视觉混淆 | 两个 tab 同图标 | 接受（Design Doc §3.1 已锁定 `Activity`，本次不偏离）；如后续需区分，单独修 Design Doc |
| Phase E.1 index.html 兜底失败 | trace 子组件未自动加载 | **停下汇报，让 user 确认**后才触发 Task D.2；D.2 严格只允许新增 trace 相关 `text/babel` script 标签，不允许引入新依赖、不允许改 CDN 版本 |
| MarkdownBlock prop 名兼容 | 实际签名 `{ text }`，trace 严格用 `text={...}` | 严格使用 `<MarkdownBlock text={...} />`；不修复 OpsAdvicePanel（不变量 0.3） |

### 4.2 回滚

每个 Phase 都是独立 commit，按反向顺序 `git revert`：

```bash
# 全量回滚（不触碰 tests/fixtures/golden/，无论是否有 modified）
git revert <D.1 commit>
git revert <C.7 ... C.1 commits>
git revert <B.1 commit>
# Task D.2（条件性）如有，也 revert
```

回滚后：
- `/api/analyze` 链路不受影响（trace 是独立端点）
- 6 个旧 tab 全部正常（DashboardView 改动反向应用）
- app.jsx 从未改动（不变量 0.2）
- OpsAdvicePanel.jsx 从未改动（不变量 0.3）
- 删除 `app/static/js/components/panels/trace/` 目录（如 revert 不能删空目录则手动）

---

## 5. Out of Scope（与 Design Doc §14 一致 + 本 Plan 补充）

- 批量 trace 比较视图（E2 范围）
- trace 面板的编辑/标注/导出
- 前端 localStorage 持久化（仅内存缓存）
- 真正的桑基图 / 流程图（保持零依赖）
- 修改 `/api/analyze` 链路或现有 6 个 Skill tab
- **修复 OpsAdvicePanel.jsx:162 的 `content` vs `text` prop 名错误**（独立任务，不在本 Plan 处理）
- **抽取 `churnRootCauseLabels` / `churnLevelBadgeClass` 到 utils**（独立 refactor 任务）
- 前端单元测试 / Playwright e2e（项目当前无前端测试框架；本 Plan 不引入）
- 后端 trace_analyzer 实现（由后端 Plan [trace-analyzer-plan.md](trace-analyzer-plan.md) 负责）

---

## 附录：Plan 阶段需用户确认的偏离项

| # | 偏离 | 原 Design Doc 条款 | 建议处理 | 状态 |
|---|---|---|---|---|
| App.1 | Tab `id` 用 `trace`（与现有 `comprehensive` / `app` / `behavior` 等短名一致），不用 `trace_analysis` 等长名 | §3.1 仅说"新增一项 trace" | 默认采用 `trace` | 默认通过 |
| App.2 | Phase D.2 (index.html 修改) 是条件性 Task，触发前必须停下汇报由 user 确认；只允许新增 trace 相关 `text/babel` script 标签，禁止新增 CDN / 改 CDN 版本 / 引入新依赖 | Design Doc §1.2 锁定不引入新依赖；新增 `<script type="text/babel">` 标签不算依赖 | 默认不修改 index.html，实测后凭 user 确认才进入 D.2 | 已锁定策略 |

**已收敛的原偏离项**（不再需要用户确认）：
- ~~icon `Activity` → `Footprints`~~：Design Doc 已锁定 `Activity`，Plan 回到 `Activity`，不偏离设计
- ~~MarkdownBlock 用 `content` vs `text` 偏离~~：基于实际签名 `{ text }` 的兼容要求，Plan 直接采用 `text={...}`，不构成偏离

如以上 App.2 触发 user 拒绝，停下重新确认；其他情况按本 Plan 执行。
