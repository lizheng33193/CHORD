# Trace 前端 UI 设计文档（P1 Trace UI）

- **状态**：Design Draft（待确认）
- **作者**：v-yimingliu
- **日期**：2026-05-01
- **关联后端 Spec**：[docs/specs/trace-analyzer-design.md](docs/specs/trace-analyzer-design.md)
- **关联 Plan**：[docs/plans/trace-analyzer-plan.md](docs/plans/trace-analyzer-plan.md)
- **关联 API**：`GET /api/trace/{uid}` → `TraceAnalyzeResponse`

---

## 1. 目标与非目标

### 1.1 目标
为 `GET /api/trace/{uid}` 的输出构建前端可视化面板，覆盖 6 个数据块：path_graph / friction_hotspots / time_pattern / churn_story / intervention_suggestions / key_events_tail，并暴露 `churn_root_cause`、`event_window`、`model_trace`、`status` 等元信息。

### 1.2 非目标
- 不修改 `/api/analyze` 链路与现有 Skill tab 的行为
- 不引入新前端依赖（保持 React + Tailwind + lucide-react CDN 栈）
- **不改变 [app.jsx](app/static/js/app.jsx) 的 home / loading / streaming / dashboard view 状态机**，trace 不是新 view
- 不实现"批量 trace"或跨 uid 比较（E2 范围）
- 不把 trace 的 `churn_root_cause` 回灌进 ops_advice（与后端 Spec §10 保持一致）

---

## 2. 关键决策（Q1-Q4 锁定）

| 编号 | 决策 | 理由摘要 |
|---|---|---|
| Q1 | Trace 作为 **Dashboard 现有 Skill tab 后的新增 tab**，懒加载 | 与现有 Skill tab 视觉一致；不打断 dashboard 上下文；不破坏 view 状态机 |
| Q2 | path_graph 用双列表 + 箭头卡片 | 零依赖；top-N 小数据列表信息密度高；与 OpsAdvicePanel 卡片风格统一 |
| Q3 | friction_hotspots 用严重度色标卡片网格 | 复用 `churnLevelBadgeClass` 配色；retry/error/stay 三维数据无损；与下方干预建议按 step 名关联 |
| Q4 | time_pattern 用纯 CSS 24 柱状图 | 零依赖；24 柱是固定结构 CSS 实现的最佳场景；与 `active_window_label` 双信道互补 |

---

## 3. 入口与状态机

### 3.1 Tab 入口
DashboardView 的 tab 列表在**现有 Skill tab 之后**新增一项 `trace`，不依赖现有 tab 的具体数量。
- Tab 标签文案：**`深度行为解析`**（锁定）
- lucide 图标：**`Activity`**（锁定）

具体 DashboardView 文件路径以当前 `app/static/js/` 结构为准，Plan 阶段确认。

### 3.2 懒加载与缓存

trace 数据**不**进入 `/api/analyze` 的 results 数组（与现有 Skill 解耦）。**缓存放在 DashboardView 内部**，不上提到 [app.jsx](app/static/js/app.jsx)：

- `traceCacheByUid: Record<uid, CacheEntry>`，key 为当前选中 result 的 uid
- 切换到 trace tab 且 `traceCacheByUid[uid]` 不存在 → 触发 `fetchTrace(uid)`
- 已存在缓存（无论成功/失败）→ 直接复用，不重复请求；失败缓存通过显式 `onRetry` 才清除并重试
- 切换 selected result（多 uid 时）→ 各 uid 独立缓存
- 离开 trace tab 不清缓存（用户来回切换不重复请求）

### 3.3 双层状态模型

**第一层 `requestStatus`**（前端 fetch 生命周期）：

| 值 | 含义 |
|---|---|
| `idle` | 尚未发起请求（用户未切到 trace tab，或当前 uid 缓存为空且未触发） |
| `loading` | fetch 进行中 |
| `success` | **fetch 已完成并可被 UI 业务分支处理**（HTTP 2xx，或 fetchTrace 映射后的 404 data_missing） |
| `error` | 网络错误 / 5xx / fetch 抛错（与上面"可被 UI 业务分支处理"互斥） |

**第二层 `response.status`**（后端业务语义，仅在 `requestStatus === 'success'` 时存在）：

| 值 | HTTP | 来源 |
|---|---|---|
| `ok` | 200 | 全链路成功 |
| `model_unavailable` | 200 | LLM 失败/mock，规则产物完整，叙述模板兜底 |
| `insufficient_events` | 200 | 事件数 < 阈值 |
| `data_missing` | **404** | CSV 不存在（fetchTrace 把 404 映射为最小 data_missing 对象，见 §3.5） |
| `error` | 200 | CSV 损坏/列缺失等服务端可恢复错误 |

**CacheEntry 结构**：
```ts
type CacheEntry =
  | { requestStatus: 'loading' }
  | { requestStatus: 'success', response: TraceAnalyzeResponse }   // response.status ∈ 5 枚举
  | { requestStatus: 'error', errorMessage: string };
```

### 3.4 UI 渲染分支
TracePanel 先看 `requestStatus`，success 时再分发 `response.status`：

| requestStatus | response.status | UI |
|---|---|---|
| `idle` | — | 不渲染（tab 未激活，理论上 TracePanel 不会被挂载） |
| `loading` | — | Skeleton + "正在解析行为序列..." |
| `success` | `ok` | 完整面板 |
| `success` | `model_unavailable` | 完整面板 + 顶部琥珀提示 + ChurnStoryCard 角标"模板兜底" |
| `success` | `insufficient_events` | 空态："该用户事件数过少，无法生成深度解析" + `errors` 列表 |
| `success` | `data_missing` | 空态："未找到该 uid 的行为数据" |
| `success` | `error` | 错误态卡片 + `errors` 列表（无重试，区别于 `requestStatus=error`） |
| `error` | — | 错误卡片 + "重试"按钮（点击清当前 uid 缓存并重新 fetch） |

### 3.5 API 服务层

新增 `fetchTrace`，**保持现有 [app/static/js/services/api.js](app/static/js/services/api.js) 的模块导出方式**（沿用既有 `analyzeByUid` / `analyzeByFile` / `analyzeByUidStream` 同款导出）。不新增 `window.AppServices` 注入。

```js
export async function fetchTrace(uid) {
  const res = await fetch(`/api/trace/${encodeURIComponent(uid)}`);
  if (res.status === 404) {
    return { uid, status: 'data_missing' };
  }
  if (!res.ok) {
    throw new Error(`trace_http_${res.status}`);
  }
  return await res.json();
}
```

要点：
- 404 **不**伪造完整 default fields，只返回最小 `{ uid, status: 'data_missing' }`
- TracePanel 的 `data_missing` 分支只读 `uid` 和 `status` 两个字段，不访问 `path_graph` / `friction_hotspots` 等
- 实际导出语法（ES module `export` vs 现有项目模式）以当前 [app/static/js/services/api.js](app/static/js/services/api.js) 为准，Plan 阶段确认并对齐

---

## 4. 面板布局总览

`TracePanel` 整体结构（自上而下）：

```
┌─ Header（图标 + 标题 + status 徽章 + event_window 摘要） ─────┐
├─ ChurnRootCauseBar（横排徽章，no_clear_signal 时不渲染） ───┤
├─ ChurnStoryCard（LLM 故事线 + model_trace 来源标识） ──────┤
├─ Two-Column Row ──────────────────────────────────────────┤
│   左:PathGraphCard（top_pages 列表 + top_transitions 卡片）│
│   右:TimePatternCard（24 柱状图 + active_window_label）   │
├─ FrictionHotspotGrid（severity 色标卡片网格 1/2 列） ─────┤
├─ InterventionList（按 hotspot.step 关联，列表式建议卡） ─┤
└─ KeyEventsTimeline（最后 N 步事件时间轴，默认折叠） ─────┘
```

底部加 `model_trace` 信息行（`mode / used_llm / model_name / fallback_reason`），灰色小字。

---

## 5. 各组件详细设计

### 5.1 Header
- 标题：`深度行为解析`（lucide `Activity` 图标 + violet 主色，与 OpsAdvicePanel 一致）
- 副标题：`{event_window.start} ~ {event_window.end} · 共 {total_events} 事件，分析 {analyzed_events} 条`
- status 徽章配色：
  - `ok` → 绿色
  - `model_unavailable` → 琥珀
  - `insufficient_events` / `data_missing` / `error` → 灰/红

### 5.2 ChurnRootCauseBar
- 数据：`response.churn_root_cause: list[str]`
- TracePanel 内**复制** [OpsAdvicePanel.jsx:67-74](app/static/js/components/panels/OpsAdvicePanel.jsx#L67-L74) 的 `churnRootCauseLabels` 字典，并加注释 cross-link 标注"与 OpsAdvicePanel 同义字典，未来如需统一抽到 utils"
- **本轮不改 [OpsAdvicePanel.jsx](app/static/js/components/panels/OpsAdvicePanel.jsx)**
- **`no_clear_signal` 时整个 ChurnRootCauseBar 不渲染**（锁定）

### 5.3 ChurnStoryCard
- 数据：`response.churn_story`，用 `MarkdownBlock` 渲染
- `model_trace.used_llm === false` 时，卡片右上角加灰色标签 `模板兜底（model_unavailable）`
- 视觉风格仿 OpsAdvicePanel 的 `retention_pitch` 渐变区（violet→purple）

### 5.4 PathGraphCard
**左列 top_pages**（按 `visit_count` 降序）：

| 页面 | 访问 | 平均停留 |
|---|---|---|
| 验证码页 | 12 | 45.3s |
| 身份证上传 | 8 | 78.1s |

**右列 top_transitions**：
```
[登录页] ──→ [验证码页]   ×12
[验证码页] ──→ [身份证页]  ×8
```
箭头用 lucide `ArrowRight`，count 用蓝色 badge。

桌面端 `md:grid-cols-2` 并排，移动端堆叠。

### 5.5 TimePatternCard

- 顶部 `active_window_label`（紫色徽章）
- 24 柱状图：
  - 容器 `flex items-end gap-px h-32`
  - 单柱 `flex-1`，高度按 `(count / max) * 100%`
  - **颜色采用固定分段**（锁定，便于跨 uid 视觉一致；不用四分位以避免低活跃 uid 仍出现深紫误导）：
    - `count == 0` → `bg-slate-100`
    - `0 < ratio ≤ 0.25` → `bg-violet-300`
    - `0.25 < ratio ≤ 0.5` → `bg-violet-400`
    - `0.5 < ratio ≤ 0.75` → `bg-violet-500`
    - `ratio > 0.75` → `bg-violet-600`
    - 其中 `ratio = count / max(hour_histogram)`，`max == 0` 时整体走 `bg-slate-100`（防 NaN）
  - 单柱 hover tooltip 通过 `title` 属性显示该小时事件数（实现示例伪代码，避免模板字符串嵌套问题）：
    ```jsx
    const tip = hour + ':00 → ' + count + ' 事件';
    return <div title={tip} style={{ height: pct + '%' }} className={...} />;
    ```
- 底部刻度：`0 · 6 · 12 · 18 · 23` 5 个对齐刻度

### 5.6 FrictionHotspotGrid

- 网格 `grid-cols-1 md:grid-cols-2 gap-4`
- 单卡片：
  - 左侧 4px 色条（severity → high=`bg-red-500` / medium=`bg-amber-500` / low=`bg-slate-400`）
  - 顶行：`step` 大字 + severity 徽章（复用 `churnLevelBadgeClass` 风格）
  - 三列数字：`重试 {retry_count} · 错误 {error_count} · 停留 {avg_stay_seconds}s`
- 排序：severity desc，同级按 `retry_count + error_count` desc

### 5.7 InterventionList
- 数据：`response.intervention_suggestions: [{ hotspot, advice, channel_hint }]`
- 每条卡片：
  - 顶部 chip：`hotspot`（蓝色 pill，与 FrictionHotspotGrid 同名 step 视觉关联）
  - 主体：`advice` 用 MarkdownBlock 渲染
  - 右下灰色小字：`channel_hint`（如有）

### 5.8 KeyEventsTimeline
- 数据：`response.key_events_tail`
- **默认折叠**（锁定），标题 `最后 N 步事件 ▼`，点击展开
- 展开后：左侧竖线 + 节点圆点；每行 `[+{ts_offset}s] {page} · {event}{field?: " · " + field}`，等宽字体；按 `ts_offset` 升序

---

## 6. 文件结构

```
app/static/js/
├── components/
│   └── panels/
│       ├── trace/
│       │   ├── TracePanel.jsx              # 入口，状态机 + 子卡片编排
│       │   ├── PathGraphCard.jsx
│       │   ├── TimePatternCard.jsx
│       │   ├── FrictionHotspotGrid.jsx
│       │   ├── InterventionList.jsx
│       │   ├── KeyEventsTimeline.jsx
│       │   └── ChurnStoryCard.jsx
│       └── OpsAdvicePanel.jsx              # 已存在，本轮不改
├── services/
│   └── api.js                              # 已存在，新增 fetchTrace（沿用现有导出方式）
└── (DashboardView 文件)                    # 实际路径以 app/static/js 当前结构为准，Plan 阶段确认
```

DashboardView 改动（不改 app.jsx）：
- 在现有 Skill tab 之后新增 `trace` tab 选项
- 新增 `traceCacheByUid` 状态与首次 fetch 触发逻辑
- tab content switch 中加 `case 'trace': return <TracePanel ... />`

每个 jsx 文件 ≤500 行。

---

## 7. 数据流

```
用户切到 trace tab（DashboardView 内部）
   ↓
查 traceCacheByUid[uid]
   ↓ 缓存缺失
setTraceCacheByUid(uid, { requestStatus: 'loading' })
   ↓
fetchTrace(uid)  ← services/api.js（404 → 最小 data_missing 对象）
   ↓
   ├─ resolve  → setTraceCacheByUid(uid, { requestStatus: 'success', response })
   └─ reject   → setTraceCacheByUid(uid, { requestStatus: 'error', errorMessage })
   ↓
<TracePanel cacheEntry={...} onRetry={() => clearAndRefetch(uid)} />
   ↓ 按 §3.4 表格分支渲染
```

---

## 8. 与现有系统的集成

### 8.1 与 OpsAdvicePanel 的关系
- `churnRootCauseLabels` 在 TracePanel 内复制，加 cross-link 注释；本轮不抽公共 utils，**不改 OpsAdvicePanel**
- trace 不联动 ops_advice

### 8.2 与 SSE 进度流的关系
- Trace 走独立同步 fetch，不走 SSE，与窗口 2（D2）解耦

### 8.3 与 normalizeAnalysisResult 的关系
- TraceAnalyzeResponse 不进入 `normalizeAnalysisResult`
- TracePanel 直接消费后端响应，依赖后端 schema 稳定（[app/schemas/trace_analyzer.py](app/schemas/trace_analyzer.py)）

### 8.4 与 [app.jsx](app/static/js/app.jsx) 的关系
- **不修改 app.jsx 的 view 状态机**（home / loading / streaming / dashboard 保持原样）
- trace 缓存与 fetch 触发完全在 DashboardView 内部

---

## 9. 可访问性 / 响应式

- tab、重试按钮、KeyEventsTimeline 折叠头：`cursor-pointer` + `focus-visible:ring`
- 24 柱状图单柱加 `title` 属性
- 卡片网格全部支持移动端堆叠
- 颜色不作为唯一信息载体（severity 同时用色条 + 文字徽章）

---

## 10. 验收标准

1. **默认进入 Dashboard 不发起 `/api/trace/{uid}` 请求**（Network 面板验证）
2. **只有首次切到 trace tab 才发起请求**
3. **同 uid 切走再切回不重复请求**（缓存命中，Network 面板无新请求）
4. 多 uid result 切换时，各 uid 独立缓存
5. `requestStatus=loading` 时显示 skeleton
6. `response.status=ok` 渲染 6 个数据块全部可见
7. `response.status=model_unavailable` 渲染规则产物 + 顶部琥珀提示 + ChurnStoryCard 角标"模板兜底"
8. `response.status=insufficient_events` / `data_missing` 渲染对应空态文案
9. `response.status=error`（200 但业务出错）渲染错误态卡片，**无**重试按钮
10. `requestStatus=error`（网络/5xx）显示重试按钮，点击后清当前 uid 缓存并重新 fetch
11. `churn_root_cause === ['no_clear_signal']` 时 ChurnRootCauseBar 整条不渲染
12. KeyEventsTimeline 默认折叠
13. **默认不修改 [app.jsx](app/static/js/app.jsx)**；如 Plan 阶段发现必须修改，先停下重新确认设计（git diff 验证）
14. 不修改 [OpsAdvicePanel.jsx](app/static/js/components/panels/OpsAdvicePanel.jsx) 任何行（git diff 验证）
15. 不引入任何新前端 npm/CDN 依赖（`index.html` script 标签 diff 验证）
16. 所有 `trace/*.jsx` 文件 ≤500 行

---

## 11. Plan 阶段已锁定的决策

| 项 | 决策 |
|---|---|
| KeyEventsTimeline 默认折叠 | **是** |
| `no_clear_signal` 时 ChurnRootCauseBar | **不渲染** |
| `churnRootCauseLabels` 共享方式 | **TracePanel 内复制 + cross-link 注释；不改 OpsAdvicePanel** |
| Tab 文案 | **`深度行为解析`** |
| lucide 图标 | **`Activity`** |
| TimePatternCard 颜色 | **固定分段（5 档：0 / ≤0.25 / ≤0.5 / ≤0.75 / >0.75）** |

## 12. Plan 阶段仍待确认

- DashboardView 文件实际路径与导出风格
- [app/static/js/services/api.js](app/static/js/services/api.js) 的实际导出语法（ES module `export` vs 其他），`fetchTrace` 与之对齐
- 顶部琥珀提示、空态、错误态的最终文案

---

## 13. 风险与缓解

| 风险 | 缓解 |
|---|---|
| Trace fetch 慢（LLM 秒级） | 切 tab 立即显示 skeleton；已加载结果缓存 |
| 多 uid 批量场景下用户对每个 uid 都点 trace 触发大量 LLM | E1 不做并发控制，由后端 LLM 限流兜底 |
| 后端 schema 字段微调破坏前端 | 严格依赖 [app/schemas/trace_analyzer.py](app/schemas/trace_analyzer.py)；Plan 阶段加最小契约测试 |
| `churnRootCauseLabels` 双份漂移 | TracePanel 内 cross-link 注释指向 OpsAdvicePanel 行号 |
| 24 柱状图低事件量 NaN | `max == 0` 全部 `bg-slate-100`，跳过比例计算 |
| api.js 导出风格猜错 | Plan 阶段先读 api.js 再写 fetchTrace，与现有函数同款导出 |

---

## 14. Out-of-Scope

- 批量 trace 比较视图
- trace 面板的编辑/标注/导出
- 前端 localStorage 持久化（仅内存缓存）
- 真正的桑基图 / 流程图（保持零依赖）
- 修改 `/api/analyze` 链路或现有 Skill tab
