# UI 分离设计：live_frontend.py → app/static/

- **状态**：设计待评审
- **日期**：2026-04-30
- **关联任务**：TASK.md → 开发中发现 → `app/ui/live_frontend.py` 2256 行 HTML/JS 嵌入 Python 字符串，待前端分离
- **作用范围**：仅前端文件组织方式与 `app/main.py` `GET /` 路由实现；不改后端 API 形状、不改编排层、不改 Skill 内部、不改 data_acquisition_agent。

---

## 1. 背景与动机

### 1.1 现状

`app/ui/live_frontend.py` 是一个 2256 行的单文件，里面用三引号字符串包了一份完整的 React 18 单页应用：

- React 18 + ReactDOM 通过 unpkg UMD CDN 加载
- JSX 在浏览器内由 `@babel/standalone` 实时编译
- 样式来自 `cdn.tailwindcss.com` Play CDN
- 图标来自 lucide-react UMD
- 大约 20 个 React function components 全部写在一个 `<script type="text/babel">` 块里
- HTML 整体作为字符串常量 `LIVE_FRONTEND_HTML` 通过 `app/main.py` `GET /` 直接返回

### 1.2 痛点

PLANNING.md 把 `app/ui/live_frontend.py` 标注为 ⚠️（待重构）。痛点的本质不是"缺少前端框架"——它已经是 React——而是：

1. **不可分文件维护**：~20 个组件、~10 个工具函数、CSS 类、SVG 图表全部塞在一个 Python 字符串里，git diff 不可读、IDE JSX 高亮失效、单组件迭代必须打开 2256 行文件
2. **Python 字符串里的 JSX 无静态检查**：编辑器无法识别这是 React 代码，括号匹配、JSX 标签闭合、props 名误写都依赖运行时报错
3. **嵌入字符串的转义负担**：JSX 内部任何 `\d` / `\\` / 反引号都要在 Python 字符串层面再转义一次（已可见于 `UID_PATTERN = /^\\d{18}$/`）

### 1.3 目标

把这一份 React SPA 从 Python 字符串中拆出，落地到 `app/static/` 下的多个 .jsx / .html / .js 文件，使每个组件可独立编辑、git diff 可读、IDE 语法高亮生效。**不引入 Node 构建链、不改后端 API、不重写组件逻辑。**

---

## 2. 现有前端分析

### 2.1 功能清单

读取 [app/ui/live_frontend.py](../../app/ui/live_frontend.py) 后归纳的功能：

- **三个 view 状态机**：`home`（输入 UID 或上传文件）→ `loading`（5 段固定文案每 800ms 轮播）→ `dashboard`（4 画像 Tab）
- **四个画像 panel**：AppPanel / BehaviorPanel / CreditPanel（含 RichCreditPanel 扩展版）/ ComprehensivePanel
- **多结果选择器**：批量分析时按 UID 切换查看
- **交互组件**：InteractiveDonutChart（hover + pin）、InstallBucketModal、CategoryAppsModal、MetricHelpTip、TimelineItem
- **图表**：3 处真正复杂的 SVG 手绘——donut（App 类目分布）、credit gauge（半圆仪表）、credit-risk-structure；其余进度条 / bar 是 Tailwind width 实现
- **Markdown 渲染**：`MarkdownBlock` 渲染各 panel 的 `report_markdown` 字段
- **文本归一化工具**：`normalizeAnalysisResult` / `findChart` / `chartSeriesData` / `arrayValue` / `objectValue` / `stringValue` 等约 15 个工具函数
- **业务计算函数**：`buildComprehensiveMarketingSuggestion` / `buildComprehensiveRiskSuggestion` 等基于 segment / risk_level 的本地展示文案合成

### 2.2 依赖

CDN 加载（HTML head 内 `<script>` 标签）：

| 依赖 | 来源 | 用途 |
|---|---|---|
| Tailwind CSS | cdn.tailwindcss.com（Play CDN，运行时 JIT） | 全部样式 |
| React 18.2.0 | unpkg.com/react@18.2.0/umd/react.development.js | UI 框架 |
| ReactDOM 18.2.0 | unpkg.com/react-dom@18.2.0/umd/react-dom.development.js | 渲染 |
| @babel/standalone | unpkg.com/@babel/standalone/babel.min.js | 浏览器内 JSX 编译 |
| lucide-react 0.292.0 | unpkg.com/lucide-react@0.292.0/dist/umd/lucide-react.js | 图标 |

无任何 npm / package.json / node_modules / pyproject.toml。运行时只需 `uvicorn`。

### 2.3 数据流

```
浏览器                          FastAPI
─────                          ─────
GET /                  ───→    app/main.py 返回 LIVE_FRONTEND_HTML 字符串
                              （全部 React + Babel + Tailwind 由 CDN 拉）

POST /api/analyze       ───→    app/api/analyze.py
{uid, application_time}        → AnalysisOrchestrator
                              → SkillRegistry.run_all
                              → 4 + 2 个 Skill 串/并行执行（~163s）
                       ←───   AnalyzeResponse(results=[UserAnalysisResult, ...])

POST /api/analyze-file  ───→    multipart 上传 → parse_uid_file → orchestrator
                       ←───   AnalyzeResponse
```

通信方式：**一次性 fetch + JSON**，无 SSE / WebSocket / 轮询。前端 loading 期间用 5 段固定文案每 800ms 轮播作为伪进度条（与后端真实进度无关）。

### 2.4 后端契约

[app/schemas/final_response.py](../../app/schemas/final_response.py)：

- `AgentOutput` = `{summary, structured_result, charts, report_markdown}`
- `UserAnalysisResult` = `{uid, app_profile, behavior_profile, credit_profile, comprehensive_profile, product_advice?, ops_advice?, standardized_labels?}`
- `ChartData` = `{chart_type, title, x_axis?, indicators?, series, meta}`
- `AnalyzeResponse` = `{results: [UserAnalysisResult, ...]}`

前端用 `findChart(charts, title)` 按英文 title 字符串查找具体图表，例如 `"Installed Apps Category Share"`。**这意味着 chart_builder 输出的 title 字符串是事实上的 API**——分离过程中不可改动。

---

## 3. 方案选型

### 3.1 决策 1：分离方案选型 → 方案 B（中等分离）

把 ~20 个 React 组件按维度拆到 `app/static/js/components/` 下的多个 `.jsx` 文件，主入口 `app.jsx` 只做组装。仍然用 Babel Standalone CDN 在浏览器内编译，**不引入 Node 构建链**。

**拒绝方案 A**（最小分离，整文件搬到一个 `.jsx`）：单文件仍然 2200+ 行，没有解决核心痛点。

**拒绝方案 C**（Vite + npm + TypeScript）：当前业务无 SSR / 路由 / 复杂状态管理需求，引入 Node 构建链解决的问题在本项目都不存在，典型 YAGNI。

### 3.2 决策 2：前后端通信方式 → 方案 2-A（保持一次性 fetch）+ services 层封装

通信方式不变。把 fetch 调用集中到 `static/js/services/api.js`，组件层不直接见 fetch。这样未来真有 SSE / 轮询需求时只改一个文件。

**拒绝 SSE / 异步轮询**：会拖动 SkillRegistry / orchestrator 改造，超出 UI 分离 scope；且 163s 体验差是已知现象，未列入 P0/P1，无业务事件触发。

### 3.3 决策 3：图表渲染策略 → 方案 3-A（保持后端结构化数据 + 前端 SVG 手绘）

后端 `chart_builder.py` 继续输出 `ChartData` 结构化数据，前端继续手绘 SVG。把 InteractiveDonutChart / CreditGauge / CreditRiskStructure 拆成 `static/js/components/charts/` 下的独立组件文件。

**拒绝 Recharts / 后端预渲染图片**：现有 SVG 不复杂（3 处真正手绘，单组件 < 100 行），且 hover/pin 等交互与业务状态深度绑定，迁到第三方库改造工作量极易超过整个分离任务。

### 3.4 决策 4：静态文件服务 → 方案 4-A（StaticFiles + FileResponse）

- `app.mount("/static", StaticFiles(directory="app/static"))`
- `GET /` 返回 `FileResponse("app/static/index.html")`
- **不使用 Jinja2Templates**：当前 HTML 100% 静态、无任何变量需要注入

**拒绝 Jinja2Templates**：YAGNI。未来需要注入 build hash / preloaded state 时再改造，是局部改动（< 1 小时）。

**拒绝 `StaticFiles(html=True)` 挂载到根**：会屏蔽 `/health` / data_acquisition_agent 等已有路由。

### 3.5 决策 5：分离过程中的 fallback → 方案 5-B（?legacy=1 + 三步提交）

三步提交：

1. **新版上线但默认 off**：新增 `app/static/`，`GET /` 默认仍走 `LIVE_FRONTEND_HTML`，`?next=1` 走新版
2. **切换默认为新版**：默认走新版，`?legacy=1` 走 `LIVE_FRONTEND_HTML`
3. **删除旧版**：删 `live_frontend.py`，移除 `?legacy=1` 分支

**拒绝硬切换**：单 PR 跨度过大、回归风险无缓冲。

**拒绝按组件渐进迁移**：旧 HTML 字符串 + 新组件文件混合桥接代码丑且短命。

### 3.6 决策 6：live_frontend.py 最终处理 → 方案 6-A（彻底删除）

第三步执行：删除 `app/ui/live_frontend.py`，移除 `app/main.py` 中相关 import 和 `?legacy=1` 分支。`app/ui/mock_frontend.py` 不动（未被 import，处理需另行评估）。

**拒绝归档到 `_legacy/` / `docs/archive/`**：git 历史本身就是归档，文件系统再留一份是冗余且引发"这份代码还要不要更新"的歧义。

**拒绝 deprecation stub**：无外部 import 它，纯防御性占位违反 YAGNI。

### 3.7 决策 7：样式方案 → 方案 7-A（Tailwind CDN + className 原样搬运）

HTML head 继续 `<script src="https://cdn.tailwindcss.com"></script>`。拆组件时 className 字符串**一字符不改地**搬运到对应 `.jsx` 文件。

**拒绝 PostCSS 本地构建**：直接违背决策 1 选 B 的"零构建链"承诺。

**拒绝重写为自定义 CSS**：~几千个 className 重写工作量爆炸，视觉回归风险 100%。

---

## 4. 目标架构

### 4.1 高层结构

```
app/
├── main.py                       ← GET / 改为 FileResponse；?legacy=1 期间双路径
├── ui/
│   └── mock_frontend.py          ← 不动（未被 import）
│   └── live_frontend.py          ← 第三步删除
└── static/                       ← 新增（本轮唯一新增目录）
    ├── index.html                ← 从 LIVE_FRONTEND_HTML 字符串拆出
    └── js/
        ├── app.jsx               ← 顶层 App + 三个 view 状态机
        ├── components/
        │   ├── HomeView.jsx
        │   ├── LoadingView.jsx
        │   ├── DashboardView.jsx
        │   ├── panels/
        │   │   ├── AppPanel.jsx
        │   │   ├── BehaviorPanel.jsx
        │   │   ├── CreditPanel.jsx
        │   │   ├── RichCreditPanel.jsx
        │   │   └── ComprehensivePanel.jsx
        │   ├── charts/
        │   │   ├── DonutChart.jsx           ← InteractiveDonutChart
        │   │   ├── CreditGauge.jsx
        │   │   └── CreditRiskStructure.jsx
        │   └── common/
        │       ├── InfoRow.jsx
        │       ├── ProgressRow.jsx
        │       ├── CreditProgressRow.jsx
        │       ├── LegendDot.jsx
        │       ├── MetricHelpTip.jsx
        │       ├── InstallBucketModal.jsx
        │       ├── CategoryAppsModal.jsx
        │       ├── TimelineItem.jsx
        │       └── MarkdownBlock.jsx
        ├── services/
        │   └── api.js            ← analyzeByUid / analyzeByFile（唯一接触 fetch 的文件）
        └── utils/
            ├── chartLookup.js    ← findChart / chartSeriesData / chartMetaLevels
            ├── normalize.js      ← normalizeAnalysisResult / arrayValue / objectValue / stringValue
            ├── displayMappers.js ← toRiskDisplay / toConfidenceDisplay / toValueSignalDisplay
            └── advice.js         ← buildComprehensiveMarketingSuggestion / buildComprehensiveRiskSuggestion
```

具体每个组件的 props 拆分、common/ 子组件最终归属、utils 文件粒度，留给 Step 4 Plan 阶段决定。本 Design Doc 只规定**目录边界和职责分层**。

### 4.2 加载方式（决策 4 子选项 i/ii 留给 Plan）

`index.html` 中 React / Babel / Tailwind / lucide-react 仍从 CDN 加载。本地组件文件的引用方式有两个候选：

- **i**：多个 `<script type="text/babel" src="/static/js/...">` 标签逐个声明，组件用全局变量（`window.AppPanel = ...`）互相引用
- **ii**：`<script type="module">` + Babel Standalone 7.x ES module 支持 + esm.sh 替代 unpkg 拉 React（参考 mock_frontend.py 现有写法）

两种都可行，trade-off 不影响目录结构。Plan 阶段确认后写进具体 Task。

### 4.3 服务端改造

[app/main.py](../../app/main.py) 改动范围（**仅此一处后端改动**）：

```
新增 import：from fastapi.staticfiles import StaticFiles
            from fastapi.responses import FileResponse
新增挂载：app.mount("/static", StaticFiles(directory="app/static"))
GET / 路由实现：按当前所处步骤（1/2/3）切换
```

第一步：默认返回 `LIVE_FRONTEND_HTML`，`?next=1` 返回 `FileResponse("app/static/index.html")`。
第二步：默认返回 `FileResponse(...)`，`?legacy=1` 返回 `LIVE_FRONTEND_HTML`。
第三步：删除 `LIVE_FRONTEND_HTML` import 和 `?legacy=1` 分支，只剩 `FileResponse(...)`。

[app/api/analyze.py](../../app/api/analyze.py) **不动**。后端 API 输出形状不动。

---

## 5. 不变量

下列约束在本轮分离过程中**必须维持**：

1. **API 输出形状不变**：`UserAnalysisResult` 字段集合、`AgentOutput` 形状、`ChartData` 形状全部不动
2. **图表 title 字符串不变**：`chart_builder.py` 输出的 `title` 字段（"Installed Apps Category Share" / "Credit Risk Level" 等）是前端 `findChart` 的事实查找键，不可改
3. **API 端点不变**：`POST /api/analyze` / `POST /api/analyze-file` 路径、请求体形状、响应体形状全部不动
4. **后端编排层不动**：SkillRegistry、orchestrator、所有 Skill 内部、ModelClient 全部不动
5. **CDN 资产源与版本不变**：React 18.2.0 / ReactDOM 18.2.0 / lucide-react 0.292.0 / @babel/standalone / cdn.tailwindcss.com 在 index.html 中保持当前版本（如需切 esm.sh 仅作为决策 4 子选项 ii 的实现细节）
6. **className 字符串不变**：分离时不重写、不优化、不语义化任何 Tailwind className
7. **三步可逆**：每一步独立提交，每一步可单独 revert
8. **现有功能视觉一致**：4 个画像 panel 的所有交互（hover / pin / Modal / timeline / Markdown 渲染 / 多结果切换）在新版必须可用
9. **不新增运行时依赖**：requirements.txt 不动；package.json / pyproject.toml 不创建
10. **不修改 mock_frontend.py / data_acquisition_agent / app/agents/ / .agents/skills/**

---

## 6. 迁移策略

### 6.1 三步提交

| 步骤 | 内容 | 默认行为 | fallback | 退出条件 |
|---|---|---|---|---|
| 1 | 新增 `app/static/` 全部文件；`app/main.py` 加 `?next=1` 分支 | 仍是旧版 | 无需 | `/?next=1` 视觉与 `/` 一致 |
| 2 | 反转 `app/main.py` 默认行为 | 新版 | `?legacy=1` 走旧版 | 默认访问稳定，无回归 |
| 3 | 删除 `app/ui/live_frontend.py`、`?legacy=1` 分支 | 新版 | 无 | （由用户判断）新版稳定后执行 |

每一步对应一个独立 commit / PR。Plan 阶段拆出每步内的 Task。

### 6.2 第二步退役 `?legacy=1` 的判定（写明在 Design Doc 的目的：避免技术债残留）

进入第三步的条件：

- 第二步合入后，至少完整跑过一次端到端真实 LLM（vertex 模式）分析流程
- 对比 4 个画像 panel 视觉无回归（特别确认：donut hover/pin、credit gauge 指针位置、Modal 打开 / 关闭、Markdown 渲染、多结果切换）
- 没有新发现需要回退到 `?legacy=1` 的场景
- 由用户判断"新版稳定"——不设固定天数

### 6.3 验证手段

- **第一步验证**：开两个浏览器 tab，`/`（旧版）vs `/?next=1`（新版），逐个 panel 视觉比对
- **第二步验证**：默认访问拿到新版且功能正常；`?legacy=1` 仍可达
- **第三步验证**：默认访问拿到新版；`?legacy=1` 返回 404 或 ignored；`grep -r "live_frontend" app/` 无任何引用
- **后端回归**：`python -m pytest tests/ -v` 全过（理论上不应有任何变化，因为 API 形状不动）

### 6.4 commit 风格

- 第一步：`feat(ui): split live_frontend.py into app/static/ behind ?next=1`
- 第二步：`refactor(ui): switch GET / default to new app/static/ frontend`
- 第三步：`refactor(ui): remove legacy live_frontend.py after split (see docs/specs/ui-separation-design.md)`

---

## 7. 风险与缓解

| 风险 | 严重度 | 缓解 |
|---|---|---|
| className 搬运过程中误改空格、引号嵌套，触发视觉细节回归（spacing / shadow / border 偏移） | 中 | 决策 7-A 明确"原样搬运"；决策 5-B 提供 `?legacy=1` 对比窗口；第二步退役前必须人工逐 panel 比对 |
| InteractiveDonutChart 的 hover / pin 状态与 `setHoveredCategoryIndex` / `setPinnedCategoryIndex` 在父组件，拆分后 props 漏传导致交互失效 | 中 | Plan 阶段为每个交互组件明确列出 props 接口；第一步合入后立刻人工验证 hover/pin |
| Babel Standalone 在多 .jsx 文件下的加载顺序 / 模块解析行为不确定（决策 4 子选项 i vs ii） | 中 | Plan 阶段先做最小 PoC（2 个组件互引用），跑通后再批量拆 |
| `findChart` 的 title 字符串在搬运过程中被无意改写 | 高（API 契约破坏） | 不变量 #2 写明；Plan 阶段加 grep 自检 |
| 第二步切换默认行为后发现新版深层 bug，但 `?legacy=1` 没保留全 | 中 | 第二步合入前必须验证 `?legacy=1` 路径可达；不变量 #7 保证可 revert |
| Tailwind Play CDN 服务异常导致样式全失效 | 低（现状已存在的风险，不是分离引入） | 与现状一致，不在本轮 scope |
| 部署环境对 `StaticFiles` 路径解析与开发环境不一致（如 cwd 不是项目根） | 低 | Plan 阶段确认用绝对路径或 `pathlib.Path(__file__).parent / "static"` 而非相对路径 |
| `app/main.py` 在第一步引入 `?next=1` 临时分支后忘记在第二步反转 | 低 | 三步 commit 各自的 message 已写明默认行为；第二步合入时必须验证 `/` 拿到的是新版 |

---

## 8. Out of Scope

下列内容**不在本轮分离范围**：

- **后端 API 改造**：SSE / WebSocket / 异步任务 / 进度推送（决策 2 已拒绝）
- **图表库引入**：Recharts / ECharts / Chart.js / D3（决策 3 已拒绝）
- **Node 构建链**：Vite / Webpack / npm / pnpm / TypeScript / package.json（决策 1 + 7 已拒绝）
- **样式重写**：Tailwind 本地 PostCSS / 自定义 CSS / CSS modules / styled-components（决策 7 已拒绝）
- **Jinja2 模板渲染**：HTML 变量注入 / preloaded state / build hash / CSP nonce（决策 4 已拒绝）
- **mock_frontend.py 的处理**：未被 import，独立评估
- **CDN 切换**：unpkg → jsdelivr / esm.sh（除非作为决策 4 子选项 ii 的实现细节出现）
- **现有 163s 端到端延迟的优化**：与 UI 分离无关
- **PLANNING.md / TASK.md / CLAUDE.md 更新**：Step 3 流程的事
- **视觉回归自动化测试**：Playwright / Storybook / 截图对比，单独立项
- **暗色主题 / i18n / 移动端适配**：当前未实现，本轮不引入
- **lucide-react 图标集裁剪 / 自托管图标**：CDN 加载方式不变
- **app/ui/ 目录本身的去留**：第三步删除 live_frontend.py 后该目录还有 mock_frontend.py，目录保留

---

## 9. 后续步骤

本 Design Doc 确认后：

- **Step 3**：架构 Stub（创建空目录 + 占位 index.html / app.jsx，验证 StaticFiles 挂载与 FileResponse 路径解析）+ 更新 PLANNING.md（`app/static/` 目录登记）+ 更新 TASK.md（移除"待前端分离"开发中发现条目）
- **Step 4**：Plan（每个组件的 props 接口、决策 4 子选项 i/ii 选定、TDD 顺序、三步内的具体 Task 拆分）
- **Step 5**：TDD 实现（第一步 → 第二步 → 第三步，每一步独立 commit）
- **Step 7**：交付（合入 main + 推送到当前批准仓库对应的 remote）
- **Step 8**：白盒审计（确认 className / chart title / API 契约无意外改动）
