# Design Doc #04 — 前端"自然语言对话"工作区

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-05-02 |
| 作者 | v-yimingliu |
| 关联 | 依赖 Plan #03 后端 SSE 接口。本 Doc 不引用其他 Design Doc 章节号；依赖关系参见 PLANNING.md |

## 0. 一句话目标（Goal）

在前端 Dashboard 保留左侧 7 个画像模块，并把自然语言对话改成右侧常驻工作区，让分析师既能查看结构化画像，也能持续进行自然语言追问；前端继续消费后端 SSE 流，渲染对话流、工具调用过程、SQL 确认弹窗与降级标识。本 Doc 不改后端 API 契约。

2026-05-27 补充说明：工作区壳层不再做“参考式还原”，而是按 `/Users/zhengli/Desktop/html.html` 的桌面端结构逐项照抄：`body/#root` 必须是 `h-screen + overflow-hidden`，左侧分析区与右侧聊天区必须独立滚动，右侧 NL Chat 必须从 header 下沿一直贴到底部；各画像模块正文与后端契约保持不变。

## 1. 背景与目标

### 1.1 当前痛点

现有 Dashboard 6 个 Tab（App / Behavior / Credit / Comprehensive / Trace / 产品策略 / 运营策略）都是"先输 UID → 看结果"的展示型。分析师要做"自然语言分析"必须切到外部工具（如手写 SQL → 跑画像 → 看 Trace）。

### 1.2 目标

新增右侧常驻 NL Chat 工作区：
- 输入框接受自然语言（如"分析泰国上周流失下单用户"）
- 后端 Orchestrator Agent 自主排工具链
- 前端流式渲染：assistant 推理 → 工具调用 → 工具结果 → 最终总结
- SQL 取数前必须显示固定弹窗让用户 ACK
- LLM 全挂时显示降级 badge
- “记忆与历史”不再内嵌在聊天正文上方，统一进入右侧抽屉承载

### 1.3 不重新发明轮子

- 不引入新 React 状态库（继续 hooks + props，与现有 6 个 Panel 风格一致）
- 不引入新 SSE 库（用浏览器原生 `EventSource` 或自制 `fetch + ReadableStream`）
- 不引入新 markdown 渲染（复用现有 `MarkdownBlock`）

## 2. 信息架构

### 2.1 页面位置

`DashboardView.jsx` 改为左右工作区：
- 左侧保留 7 个画像模块卡片：`comprehensive / app / behavior / credit / product / ops / trace`
- 右侧固定 `ChatPanel.jsx` 作为 NL Chat dock
- 桌面端壳层样式按 `html.html` 逐项复刻：默认白底卡片，激活卡片彩色填充，标题字号、卡片尺寸、分隔条、右侧聊天列高度与参考稿一致，页面左右不再使用居中大容器留白
- 在窄屏或空间不足时，聊天区自动折叠为 launcher，点击后以右侧 sheet 展开
- `?tab=chat` 仍有效，但语义改为“打开/聚焦右侧聊天区”，不再表示左侧第 8 个 tab

### 2.2 记忆入口

`MemoryInspector.jsx` 改为抽屉（drawer）：
- 入口位于聊天头部“历史记忆”按钮
- 抽屉宽度桌面默认 840px，窄屏取 `min(92vw, 840px)`
- 抽屉内继续保留 `短期会话历史` 与 `长期记忆` 两部分

### 2.3 状态机

```
       send()                tool_started/completed
idle ──────────► streaming ────────────────────────► streaming
                  │   │                                  │
                  │   │ ack required                     │
                  │   ▼                                  │
                  │ awaiting_ack ──ack/cancel──► streaming
                  │                                      │
                  │ final/error                          │
                  ▼                                      ▼
                done                                   error
```

转换规则：
- `idle → streaming`：用户点发送
- `streaming → awaiting_ack`：收到 SSE 事件 `tool_started: query_data` + 后续 `awaiting_user_ack` 子事件
- `awaiting_ack → streaming`：用户点"确认"，前端 POST 到后端 ACK 接口
- `awaiting_ack → idle`（修正 P0-5）：用户点“取消”→ 本次工具调用 abort，但 session 仍 active 允许用户继续提问（不强制结束 session）
- `streaming → done`：收到 SSE `final` 事件
- 任何状态 → `error`：收到 SSE `error` 事件

## 3. 组件清单（7 个）

### 3.1 `app/static/js/components/panels/chat/ChatPanel.jsx`

容器组件，持有：
- `state`: 当前状态机状态
- `messages`: 消息列表（user / assistant / tool_call / tool_result / system_warning）
- `currentSession`: session_id
- `budgetUsage`: token 用量百分比

子组件：`ChatInput` + `ChatMessageList` + `SqlAckDialog`（条件渲染） + `BudgetWarningBanner`（条件渲染） + `FallbackBadge`（条件渲染）。

### 3.2 `app/static/js/components/panels/chat/ChatInput.jsx`

- 多行文本输入框
- 发送按钮（Enter 键发送，Shift+Enter 换行）
- `streaming` / `awaiting_ack` 状态时禁用

### 3.3 `app/static/js/components/panels/chat/ChatMessageList.jsx`

- 渲染消息列表
- 每条消息根据 type 路由到不同渲染器：
  - `user`: 简单气泡
  - `assistant`: `MarkdownBlock` 渲染（支持流式增量）
  - `tool_call`: `ToolCallCard` 组件
  - `tool_result`: `ToolCallCard` 组件（同一个 card 折叠 result）
  - `system_warning`: 黄色背景 banner

### 3.4 `app/static/js/components/panels/chat/ToolCallCard.jsx`

- 显示工具名 + 参数 + 状态 icon（pending / running / done / error）
- 默认收起，点击展开看完整 JSON 参数和 result
- 工具名映射中文：`parse_uid_file → 解析 UID 文件` / `run_profile → 跑画像` / `run_trace → 行为轨迹` / `query_data → 取数` / `memory_write → 记忆写` / `memory_read → 记忆读` / `load_skill → 加载分析规则`

### 3.5 `app/static/js/components/panels/chat/SqlAckDialog.jsx`

模态弹窗。触发条件：状态机进入 `awaiting_ack`。

显示：
- SQL 全文（**只读**，禁止编辑——避免绕过后端安全校验）
- 预估影响行数（来自后端 `count_precheck` 字段）  - 如果 `rows_estimated == -1`（数据源不支持 EXPLAIN/COUNT）→ 显示“未知（数据源不支持估算）” + 黄色警告 icon，提示分析师此 SQL 可能是大查询- "确认执行" 按钮 → POST `/api/orchestrator/sessions/{session_id}/ack`
- "取消" 按钮 → POST `/api/orchestrator/sessions/{session_id}/ack` with `cancel=true`
- Esc 键 = 取消

### 3.6 `app/static/js/components/panels/chat/BudgetWarningBanner.jsx`

顶部 banner，触发条件：收到 SSE `budget_warning` 事件（80% 软提醒）。

显示：
- 黄色背景
- 文案："本次会话已消耗 X% token 配额，建议尽快总结结束"
- 不阻塞输入

### 3.7 `app/static/js/components/panels/chat/FallbackBadge.jsx`

消息气泡角标，触发条件：收到的消息 `confidence < 0.5`（关键词路由兜底模式）。

显示：
- 红色小角标
- 文案："AI 服务降级中"
- 顶部同时显示一个全局 banner

## 4. SSE 事件消费

### 4.1 `app/static/js/services/orchestratorApi.js`

```javascript
// 新建文件，独立于现有 services/api.js
export async function* chatStream(prompt, sessionId) {
  try {
    const response = await fetch('/api/orchestrator/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt, session_id: sessionId }),
    });
    if (!response.ok || !response.body) {
      yield { type: 'error', message: `HTTP ${response.status}` };
      return;
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split('\n\n');
      buffer = events.pop();
      for (const evt of events) {
        const parsed = parseSSEEvent(evt);
        if (parsed) yield parsed;
      }
    }
  } catch (e) {
    // P1-5：网络断 / 422 / reader.read() 抛错不能让状态卡住
    yield { type: 'error', message: '连接中断: ' + (e.message || String(e)) };
  }
}

export async function ackSql(sessionId, confirm) {
  return fetch(`/api/orchestrator/sessions/${sessionId}/ack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ confirm }),
  });
}

export async function fetchSession(sessionId) {
  return fetch(`/api/orchestrator/sessions/${sessionId}`).then(r => r.json());
}
```

### 4.2 事件 → 状态映射

| SSE 事件 | 状态机动作 | 消息列表动作 |
|---|---|---|
| `assistant_thinking` | `streaming` 保持 | append 或更新最后一条 assistant 消息（流式） |
| `tool_started` | `streaming` 保持 | append 一条 tool_call 消息 |
| `tool_completed` | `streaming` 保持（如果是 query_data 且 awaiting_ack 则切到 awaiting_ack） | 更新对应 tool_call 消息为 done |
| `budget_warning` | 保持 | 显示 BudgetWarningBanner |
| `provider_fallback` | 保持 | 显示 FallbackBadge |
| `error` | → `error` | append system_warning 消息 |
| `final` | → `done` | append assistant 最终消息 |
| **user clicks cancel in ACK dialog**（P0-5） | → `idle` | append system_warning 消息 “用户取消了 SQL 执行”；session 仍 active |

## 5. 交互细节

### 5.1 流式打字机

`assistant_thinking` 事件每次推一段 partial content，前端 append 到最后一条 assistant 消息的 markdown buffer，触发 re-render。最终 `final` 事件覆盖 buffer 为完整内容。

### 5.2 工具调用展开/收起

默认收起（只显示工具名 + 状态）。点击 card 展开看 JSON 参数 / 结果。同一 chat 内多次工具调用形成时间线。

### 5.3 SQL ACK 弹窗

- SQL 显示用 `<pre readOnly>` + `style={{userSelect: 'text', whiteSpace: 'pre-wrap'}}`（修正 P0-4：原措辞“<pre> + disabled”是 HTML 语法错，<pre> 没有 disabled 属性）
- 允许文本选中 / 复制，但禁止编辑 —— 避免绕过后端安全校验是经典 prompt injection 漏洞
- React 实装参考：`<pre readOnly style={{whiteSpace:'pre-wrap'}}>{sqlText}</pre>`；整个弹窗内禁止键盘事件冒泡修改 SQL
- 取消 = 用户主动放弃这条工具调用（状态机回到 idle，参§ 2.2 P0-5），session 仍保留供 resume / 继续提问

### 5.4 降级模式

- 关键词路由兜底返回的消息 `confidence=0.1`
- 前端检测 `confidence < 0.5` → 显示 FallbackBadge + 顶部全局 banner
- banner 文案："AI 推理服务降级中，当前回答基于关键词匹配，准确性可能下降"

## 6. 路由与持久化

### 6.1 URL 设计

- 主路由：`/?tab=chat`
- 带 session：`/?tab=chat&session={session_id}`
- 用户分享 URL → 别人打开 → 自动恢复对话历史

### 6.2 Session 恢复

- 进入 Tab 时检查 `URL.searchParams.get('session')`
- 有 session_id → 调 `fetchSession(sessionId)` 加载历史 messages，渲染到 ChatMessageList
- 无 session_id → idle 状态

## 7. 构建集成

### 7.1 `app/ui/build_frontend.py` 的 `LOAD_ORDER`

在现有 LOAD_ORDER 末尾追加 7 个新组件文件，并在源码里加依赖顺序注释（P2-6）：

```python
# === Chat panel components (subcomponents must precede ChatPanel) ===
"app/static/js/services/orchestratorApi.js",
"app/static/js/components/panels/chat/ToolCallCard.jsx",       # leaf
"app/static/js/components/panels/chat/SqlAckDialog.jsx",       # leaf
"app/static/js/components/panels/chat/BudgetWarningBanner.jsx",  # leaf
"app/static/js/components/panels/chat/FallbackBadge.jsx",      # leaf
"app/static/js/components/panels/chat/ChatInput.jsx",          # leaf
"app/static/js/components/panels/chat/ChatMessageList.jsx",    # depends on ToolCallCard, FallbackBadge
"app/static/js/components/panels/chat/ChatPanel.jsx",          # depends on all above
```

注意：`ChatPanel` 必须放最后（因为它依赖前面所有子组件）。

### 7.2 `DashboardView.jsx` Tab 入口

在现有 7 Tab 列表末尾追加：

```jsx
{ key: 'chat', label: '对话', component: window.ChatPanel },
```

## 8. 测试策略

### 8.1 jest/RTL 单测

新建 `tests/frontend/test_chat_panel.test.js`（如项目尚未配置 jest/RTL，本 Plan Phase 1 引入）：
- ChatPanel 状态机转换：idle → streaming → done
- SqlAckDialog 弹窗显示/隐藏
- FallbackBadge 渲染条件

### 8.2 Mock SSE 事件流

提供 mock fixture：`tests/frontend/fixtures/sse_events_happy_path.json`，包含一组合规的 SSE 事件序列（`assistant_thinking` × 3 + `tool_started: query_data` + `awaiting_ack` + `tool_completed` + `tool_started: run_profile` + `tool_completed` + `final`）。

### 8.3 端到端

mock 模式下手动跑：
1. 启 backend mock 模式
2. 浏览器打开 `/?tab=chat`
3. 输入"看下 UID U001 的行为轨迹"
4. 验证：tool_call 显示 run_trace + 最终消息渲染

## 9. 可达性 / 国际化

### 9.1 中文文案

所有界面文案中文。键盘快捷键：
- Enter：发送
- Shift+Enter：换行
- Esc：取消 ACK 弹窗

### 9.2 ARIA

- `ChatMessageList`：`role="log"` + `aria-live="polite"`，方便屏幕阅读器读出新消息。
- `SqlAckDialog`（P2-5）：`role="dialog"` + `aria-modal="true"` + `aria-labelledby` 指向弹窗标题 id（如 `<h3 id="ack-dialog-title">`）。
- `BudgetWarningBanner`（P2-5）：`role="alert"`。
- `FallbackBadge`（P2-5）：`aria-label="AI 服务降级中"`。

## 10. 不在本期范围（Out of Scope）

- 不改后端 API 契约（SSE 事件格式由后端 Doc 决定，前端只消费）
- 不引入新 React 状态库（Redux / Zustand 等）
- 不引入新 SSE 库（用浏览器原生 ReadableStream）
- 不重构现有 7 个 Tab 的展示逻辑
- 不在本 Doc 落地后端 Orchestrator Agent / 路由配置
- 不实现多人协作 / 实时 push（chat 是单用户单 session 模型）
