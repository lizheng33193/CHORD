# Plan #04 — NL Chat Workspace Frontend (R5.6 Layout Refresh)

| 项 | 值 |
|---|---|
| 状态 | Reviewed R5.5 (2026-05-04) — 上游 Gate 已达成，可启动 Phase 1 执行 |
| 设计文档 | `docs/specs/04-nl-chat-tab-frontend-design.md` (R4) |
| 上游强依赖 | Plan #01 / #02 / #03 全部 `[complete]`（#01 a949830、#02 874c305、#03 8fb3377）✅ |
| Phase 数 | 4（Phase 0/1/2/3）；Phase 0 默认 0 commit，Phase 1/2/3 各 1 commit |
| Commit 策略 | 每 Phase 1 个 commit；commit 前必须先 `git diff --stat` 给用户确认；Phase 3 commit 带 `[complete] nl-chat-tab` |
| Push 策略 | 仅允许推送到当前批准仓库对应的 remote；当前默认使用 `origin` |
| 测试基线 | `tests/` 与 `data_acquisition_agent/tests/` 以执行当日实际结果为准（Plan 内命令已要求双侧回归） |
| 执行模式 | 单人串行，RED → GREEN → 回归 → diff 审核 → commit |

---

## R5.5 审核结论

R5.4 在执行层已无阻塞；本次 R5.5 在“只审计与文档修订”的边界内，做 3 项轻量收口让 Plan 可直接进入 Phase 1：

1. **上游 Gate 已达成**：Plan #01 / #02 / #03 均已 `[complete]`，Phase 0 Task 0.1 仍保留作为执行当天的再确认（防止误操作时漂移）。
2. **P2-1：TC-1 step 5 前向引用收口**：把“打开 `?session=<uuid>`”改为“需先经 TC-2 / TC-4 生成 session_id 再回放本步”，避免新执行人凭空构造 UUID 跑步骤。
3. **P2-2：Phase 3 commit 文件清单补审计报告**：执行轮次产生的 R5.5 → R5.6 审计行需随 Phase 3 commit 一同落盘，避免遗漏。

R5.5 不修改任何运行时代码、不引入新断言、不调整测试基线，只在 Plan 与 audit 文档内做上述 3 项收口。

---

## R5.4 审核结论（保留）

R5.3 的主体已接近可执行；R5.4 在继续保持“只审计与文档修订”的边界内，补齐 1 个 P0 执行缺口，并保留 R5.3 的 4 个文档层收口：

1. **P0：`?tab=chat` 初始打开缺少 `view` 路由**：真实 `app.jsx` 当前 `view` 初始值是 `home`，R5.3 只从 URL 初始化 `activeTab`，会导致 `/?tab=chat` 仍停在 HomeView。R5.4 在 Phase 3 明确新增 `getInitialViewFromUrl()` 与 `getInitialDashboardTab()`，让 `/?tab=chat` 与 `/?session=<uuid>` 直接进入 Dashboard 的 chat tab。
2. **版本与日期需前移**：头部状态与当前审核轮次不一致。
3. **测试基线数字易过期**：固定写死 `270 / 163` 会与后续仓库演进冲突。
4. **Phase 0 漂移核对脚本有硬编码断言风险**：原脚本断言 `window.AppServices.api = {...}` 的整行字符串，易因格式化改动误报。
5. **本轮范围约束需显式声明**：按本次任务要求，Plan 文本应明确“当前轮次仅审计修订，不触发执行”。

R5.4 已修正以上问题：统一版本标识、改为“执行当日实际基线”、将 API 断言改为符号级检查，补充“本轮仅文档审核修订”声明，并把 URL 初始入口从“只改 activeTab”升级为“同时初始化 view 与 activeTab”。

---

## Scope

### 2026-05-27 布局更新说明

本计划的 SSE、session restore、ACK、memory API 契约保持不变，但页面承载方式已升级为：
- 左侧 7 个画像模块卡片 + 详情区
- 右侧常驻 NL Chat dock
- 窄屏自动折叠为 launcher / sheet
- `MemoryInspector` 从内嵌块改为聊天头部触发的大抽屉
- `?tab=chat` 改为“打开/聚焦右侧聊天区”，不再代表左侧第 8 个 tab
- 工作区外层视觉高保真参照 `/Users/zhengli/Desktop/html.html`：全宽顶部栏、默认白底模块卡片、激活彩色态、右侧整列聊天列、细分隔条与窄拖拽柄
- 2026-05-27 壳层修正追加要求：桌面端不接受“近似实现”，必须直接对齐 `html.html` 的根容器、独立滚动、标题字号、卡片尺寸与聊天列全高贴边效果；浏览器文档本身不得成为主滚动容器

以下旧表述如“第 8 个 tab / 高亮 chat tab”，均应按上述新布局理解。

**本 Plan 做：**
1. 在现有 Dashboard 保留 7 个左侧模块，并实现右侧常驻自然语言多轮对话面板。
2. 前端仅使用当前架构：React 18 + Babel Standalone + `window.AppComponents` / `window.AppServices.api`。
3. 新增 `app/static/js/components/panels/chat/` 下的 7 个 chat 组件和 1 个 reducer 文件。
4. 消费 Plan #03 提供的 SSE session API：`session_started / tool_started / tool_completed / assistant_thinking / awaiting_user_ack / budget_warning / provider_fallback / error / final / done`。
5. 补 URL 路由：`?tab=chat` 初始打开或聚焦右侧聊天区，`?session=<uuid>` 刷新恢复历史。
6. 新增 Python 静态/动态测试和手测文档。

**本 Plan 不做：**
- 不修改 Plan #03 后端契约。
- 不修改 `data_acquisition_agent/`。
- 不修改 `.agents/skills/`。
- 不引入 npm / jest / vitest / Redux / Zustand。
- 不改现有画像卡片业务逻辑。
- 不做 SQL 二次签名或风控，只实现前端 ACK 按钮到后端 ACK endpoint 的调用。
- 当前轮次（R5.5）仍只做文档收口；启动 Phase 1 执行需用户在另一轮明确指令。

---

## Phase 0 — Gate 与真实基线核对

**目标**：执行任何代码修改前，确认上游完成、当前代码结构与本 Plan 匹配、测试基线可复现。

### Task 0.1 — 上游完成 Gate（强制 BLOCK）

**说明**：截至 R5.5 审核日（2026-05-04），Plan #03 已达成 `[complete] orchestrator-agent`（commit `8fb3377`）。本 Task 在执行当天仍需重跑一次，避免分支切换后状态漂移。

**验证命令**：

```powershell
cd C:\Users\v-yimingliu\agent-userprofile\CHORD
git log --oneline | Select-String "\[complete\] orchestrator-agent"
```

**期望输出**：至少一行包含 `[complete] orchestrator-agent`。若为空，立即 **BLOCK**，先完成 Plan #03。

### Task 0.2 — 必读文件与漂移核对

**必须打开并核对：**
1. `app/static/js/components/DashboardView.jsx`
2. `app/static/js/app.jsx`
3. `app/ui/build_frontend.py`
4. `app/static/js/services/api.js`
5. `docs/specs/04-nl-chat-tab-frontend-design.md`
6. `docs/plans/03-orchestrator-agent-plan.md`

**验证命令**：

```powershell
python -c "from pathlib import Path; root=Path.cwd(); dv=(root/'app/static/js/components/DashboardView.jsx').read_text(encoding='utf-8'); app=(root/'app/static/js/app.jsx').read_text(encoding='utf-8'); bf=(root/'app/ui/build_frontend.py').read_text(encoding='utf-8'); api=(root/'app/static/js/services/api.js').read_text(encoding='utf-8'); assert 'const { ChevronRight, Bot, Network, Smartphone, Activity, CreditCard, Package, Headphones } = window.LucideReact || {};' in dv; assert 'function DashboardView({' in dv and 'activeTab,' in dv and 'setActiveTab,' in dv; assert \"const [activeTab, setActiveTab] = useState('comprehensive');\" in app; assert 'path = STATIC_DIR / rel' in bf and '\"js/app.jsx\"' in bf; assert 'window.AppServices = window.AppServices || {};' in api; assert 'analyzeByUidStream' in api and 'analyzeModule' in api and 'fetchTrace' in api; print('R5.5 baseline matches current code')"
```

**期望输出**：`R5.5 baseline matches current code`。

### Task 0.3 — 测试基线

**验证命令**：

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 3
python -m pytest data_acquisition_agent/tests/ -q 2>&1 | Select-Object -Last 3
git status
```

**期望输出**：`tests/` 当前基线通过；`data_acquisition_agent/tests/` 当前基线通过；`git status` 干净或只有本 Plan / audit 文档改动。

---

## Phase 1 — RED→GREEN Chat 骨架 + LOAD_ORDER + Tab 入口

**目标**：新增 chat 组件骨架，接入 bundler 和 Dashboard 第 8 个 tab。此阶段不连接 SSE。

### Task 1.1 — RED：骨架静态测试

**新增文件**：`tests/frontend/__init__.py`（空文件）和 `tests/frontend/test_chat_skeleton.py`。

```python
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHAT_DIR = REPO / "app" / "static" / "js" / "components" / "panels" / "chat"

EXPECTED_COMPONENTS = [
    "ChatPanel",
    "ChatMessageList",
    "ChatInputBox",
    "ChatToolCallStream",
    "ChatAckCard",
    "ChatBudgetBanner",
    "ChatProviderFallbackBanner",
]


def test_chat_component_files_exist_and_register() -> None:
    assert CHAT_DIR.is_dir(), f"missing dir: {CHAT_DIR}"
    for name in EXPECTED_COMPONENTS:
        path = CHAT_DIR / f"{name}.jsx"
        assert path.is_file(), f"missing component: {path}"
        body = path.read_text(encoding="utf-8")
        assert f"window.AppComponents.{name} = {name};" in body


def test_load_order_contains_chat_files_before_dashboard() -> None:
    bf = (REPO / "app" / "ui" / "build_frontend.py").read_text(encoding="utf-8")
    dash = bf.index('"js/components/DashboardView.jsx"')
    for name in EXPECTED_COMPONENTS:
        needle = f'"js/components/panels/chat/{name}.jsx"'
        assert needle in bf, f"LOAD_ORDER missing {needle}"
        assert bf.index(needle) < dash, f"{needle} must load before DashboardView"


def test_dashboard_has_chat_tab_and_branch() -> None:
    src = (REPO / "app" / "static" / "js" / "components" / "DashboardView.jsx").read_text(encoding="utf-8")
    assert "ChatPanel," in src
    assert re.search(r"id:\s*'chat'", src)
    assert "activeTab === 'chat'" in src
    assert "<ChatPanel />" in src
```

**验证命令**：

```powershell
python -m pytest tests/frontend/test_chat_skeleton.py -q
```

**期望输出**：测试 FAIL，原因是 chat 组件目录和 Dashboard chat 分支尚不存在。这是 Phase 1 RED。

### Task 1.2 — GREEN：创建 7 个组件骨架

**新建目录**：`app/static/js/components/panels/chat/`。

**新建 `ChatPanel.jsx`：**

```jsx
const {
  ChatMessageList,
  ChatInputBox,
  ChatToolCallStream,
  ChatAckCard,
  ChatBudgetBanner,
  ChatProviderFallbackBanner,
} = window.AppComponents;

function ChatPanel() {
  return (
    <section className="flex flex-col gap-4 min-h-[520px]">
      <div>
        <h2 className="text-xl font-bold text-slate-800">自然语言对话</h2>
        <p className="text-sm text-slate-500">NL Chat</p>
      </div>
      <ChatBudgetBanner used={null} limit={null} />
      <ChatProviderFallbackBanner from={null} to={null} reason={null} />
      <div className="flex-1 rounded-xl border border-slate-200 bg-slate-50 p-4 overflow-y-auto">
        <ChatMessageList messages={[]} />
        <ChatToolCallStream toolCalls={[]} />
      </div>
      <ChatAckCard pending={null} onApprove={() => {}} onReject={() => {}} />
      <ChatInputBox value="" onChange={() => {}} onSend={() => {}} disabled={false} />
    </section>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatPanel = ChatPanel;
```

**新建 `ChatMessageList.jsx`：**

```jsx
function ChatMessageList({ messages }) {
  if (!messages || messages.length === 0) {
    return <div className="text-sm text-slate-400 italic">开始你的第一条消息...</div>;
  }
  return (
    <div className="flex flex-col gap-3">
      {messages.map((m, index) => (
        <div key={index} className={`max-w-[82%] rounded-xl px-4 py-3 text-sm ${m.role === 'user' ? 'self-end bg-blue-600 text-white' : 'self-start bg-white text-slate-700 border border-slate-200'}`}>
          <div className="text-xs opacity-70 mb-1">{m.role}</div>
          <div className="whitespace-pre-wrap">{m.content}</div>
        </div>
      ))}
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatMessageList = ChatMessageList;
```

**新建 `ChatInputBox.jsx`：**

```jsx
function ChatInputBox({ value, onChange, onSend, disabled }) {
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !disabled) {
      e.preventDefault();
      onSend();
    }
  };
  return (
    <div className="flex gap-3">
      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        rows={2}
        className="flex-1 rounded-xl border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-slate-100"
        placeholder="输入问题，Enter 发送，Shift+Enter 换行"
      />
      <button
        onClick={onSend}
        disabled={disabled || !value.trim()}
        className="rounded-xl bg-blue-600 px-5 py-2 text-sm font-semibold text-white disabled:bg-slate-300"
      >
        发送
      </button>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatInputBox = ChatInputBox;
```

**新建 `ChatToolCallStream.jsx`：**

```jsx
function ChatToolCallStream({ toolCalls }) {
  if (!toolCalls || toolCalls.length === 0) return null;
  return (
    <div className="mt-4 border-t border-dashed border-slate-200 pt-3">
      <div className="mb-2 text-xs font-semibold text-slate-500">工具调用</div>
      <div className="space-y-1">
        {toolCalls.map((t) => (
          <div key={t.tool_call_id} className="font-mono text-xs text-slate-700">
            {t.status === 'ok' ? 'DONE' : t.status === 'error' ? 'ERROR' : 'RUN'} {t.tool_name || t.tool_call_id}
          </div>
        ))}
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatToolCallStream = ChatToolCallStream;
```

**新建 `ChatAckCard.jsx`：**

```jsx
function ChatAckCard({ pending, onApprove, onReject }) {
  if (!pending) return null;
  return (
    <div className="rounded-xl border border-amber-300 bg-amber-50 p-4">
      <div className="font-semibold text-amber-900">即将执行 SQL，预计 {pending.rows_estimated ?? '?'} 行</div>
      <pre className="mt-2 max-h-32 overflow-auto rounded-lg bg-white p-3 text-xs text-slate-700">{pending.sql_text || ''}</pre>
      <div className="mt-3 flex gap-2">
        <button onClick={onApprove} className="rounded-lg bg-emerald-600 px-3 py-1 text-sm font-semibold text-white">同意 Enter</button>
        <button onClick={onReject} className="rounded-lg bg-rose-600 px-3 py-1 text-sm font-semibold text-white">拒绝 Esc</button>
      </div>
    </div>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatAckCard = ChatAckCard;
```

**新建 `ChatBudgetBanner.jsx`：**

```jsx
function ChatBudgetBanner({ used, limit }) {
  if (used == null || limit == null) return null;
  const pct = limit > 0 ? Math.round((used / limit) * 100) : 0;
  if (pct < 80) return null;
  return <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">Token 预算使用 {used} / {limit} ({pct}%)</div>;
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatBudgetBanner = ChatBudgetBanner;
```

**新建 `ChatProviderFallbackBanner.jsx`：**

```jsx
function ChatProviderFallbackBanner({ from, to, reason }) {
  if (!from || !to) return null;
  return <div className="rounded-lg bg-blue-50 px-3 py-2 text-sm text-blue-800">模型已从 {from} 切换到 {to}{reason ? `：${reason}` : ''}</div>;
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatProviderFallbackBanner = ChatProviderFallbackBanner;
```

### Task 1.3 — GREEN：更新 LOAD_ORDER

**编辑文件**：`app/ui/build_frontend.py`。

在 trace panel 区段之后、`js/components/HomeView.jsx` 之前加入：

```python
    "js/components/panels/chat/ChatMessageList.jsx",
    "js/components/panels/chat/ChatInputBox.jsx",
    "js/components/panels/chat/ChatToolCallStream.jsx",
    "js/components/panels/chat/ChatAckCard.jsx",
    "js/components/panels/chat/ChatBudgetBanner.jsx",
    "js/components/panels/chat/ChatProviderFallbackBanner.jsx",
    "js/components/panels/chat/ChatPanel.jsx",
```

### Task 1.4 — GREEN：更新 DashboardView

**编辑文件**：`app/static/js/components/DashboardView.jsx`。

**改动 1：lucide 解构加入 `MessageCircle`。**

```jsx
const { ChevronRight, Bot, Network, Smartphone, Activity, CreditCard, Package, Headphones, MessageCircle } = window.LucideReact || {};
```

**改动 2：AppComponents 解构加入 `ChatPanel`。**

```jsx
const {
  AppPanel,
  BehaviorPanel,
  RichCreditPanel,
  ComprehensivePanel,
  ProductAdvicePanel,
  OpsAdvicePanel,
  LabelsOverviewCard,
  TracePanel,
  ModuleStatusPanel,
  ChatPanel,
} = window.AppComponents;
```

**改动 3：activeModuleState 对 chat 放行。**

```jsx
  const activeModuleState = (activeTab === 'trace' || activeTab === 'chat')
    ? { status: 'success', error: '' }
    : (moduleStates && moduleStates[activeTab]) || { status: 'success', error: '' };
```

**改动 4：tabs 数组追加 chat。**

```jsx
  const tabs = [
    { id: 'comprehensive', title: '综合画像', sub: 'Comprehensive', icon: Network, bg: 'from-amber-400 to-fuchsia-600', shadow: 'shadow-fuchsia-500/30' },
    { id: 'app', title: 'App画像', sub: 'App Usage', icon: Smartphone, bg: 'from-cyan-400 to-blue-600', shadow: 'shadow-blue-500/30' },
    { id: 'behavior', title: '行为画像', sub: 'Behavioral', icon: Activity, bg: 'from-orange-400 to-red-500', shadow: 'shadow-red-500/30' },
    { id: 'credit', title: '征信画像', sub: 'Credit Report', icon: CreditCard, bg: 'from-slate-500 to-slate-700', shadow: 'shadow-slate-500/30' },
    { id: 'product', title: '产品策略', sub: 'Product Advice', icon: Package, bg: 'from-emerald-400 to-teal-500', shadow: 'shadow-emerald-500/30' },
    { id: 'ops', title: '运营策略', sub: 'Operations', icon: Headphones, bg: 'from-violet-400 to-purple-500', shadow: 'shadow-violet-500/30' },
    { id: 'trace', title: '深度行为解析', sub: 'Trace Analysis', icon: Activity, bg: 'from-purple-400 to-violet-600', shadow: 'shadow-violet-500/30' },
    { id: 'chat', title: '自然语言对话', sub: 'NL Chat', icon: MessageCircle, bg: 'from-sky-400 to-blue-600', shadow: 'shadow-blue-500/30' }
  ];
```

**改动 5：tab 状态中 chat 始终 success。**

```jsx
            const tabModuleState = tab.id === 'trace'
              ? (traceCacheByUid[uid] ? { status: (traceCacheByUid[uid].requestStatus === 'success' ? 'success' : traceCacheByUid[uid].requestStatus === 'error' ? 'error' : 'loading') } : { status: 'idle' })
              : tab.id === 'chat'
                ? { status: 'success' }
                : (moduleStates && moduleStates[tab.id]);
```

**改动 6：渲染分支完整替换为：**

```jsx
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 min-h-[560px]">
          {activeTab === 'trace' ? (
            <TracePanel uid={uid} cacheEntry={traceCacheByUid[uid]} onRetry={() => handleTraceRetry(uid)} />
          ) : activeTab === 'chat' ? (
            <ChatPanel />
          ) : (
            <ModuleStatusPanel state={activeModuleState} onRetry={() => onRetryModule && onRetryModule(activeTab)}>
              {activeTab === 'comprehensive' && <ComprehensivePanel profile={selectedResult.comprehensive_profile} />}
              {activeTab === 'app' && <AppPanel profile={selectedResult.app_profile} />}
              {activeTab === 'behavior' && <BehaviorPanel profile={selectedResult.behavior_profile} />}
              {activeTab === 'credit' && <RichCreditPanel profile={selectedResult.credit_profile} />}
              {activeTab === 'product' && <ProductAdvicePanel profile={selectedResult.product_advice} />}
              {activeTab === 'ops' && <OpsAdvicePanel profile={selectedResult.ops_advice} />}
            </ModuleStatusPanel>
          )}
        </div>
```

**验证命令**：

```powershell
python -m pytest tests/frontend/test_chat_skeleton.py -q
python -c "from app.ui.build_frontend import build_frontend_html; html=build_frontend_html(); assert 'ChatPanel' in html and '自然语言对话' in html; print('OK')"
```

**期望输出**：测试 PASS；`OK`。

### Task 1.5 — Phase 1 回归与 commit

**验证命令**：

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 3
python -m pytest data_acquisition_agent/tests/ -q 2>&1 | Select-Object -Last 3
git diff --stat
```

用户确认后执行：

```powershell
git add app/static/js/components/panels/chat/ app/ui/build_frontend.py app/static/js/components/DashboardView.jsx tests/frontend/
git commit -m "feat(plan-04): Phase 1 chat skeleton"
```

---

## Phase 2 — RED→GREEN SSE reducer + API + Stateful ChatPanel

**目标**：实现 reducer、API service、ChatPanel 状态机和 ACK 交互。

### Task 2.1 — RED：Reducer 测试

**新建文件**：`tests/frontend/test_chat_reducer.py`。

```python
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REDUCER = REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "chatReducer.js"

REQUIRED = [
    "user_input", "session_started", "tool_started", "tool_completed",
    "assistant_thinking", "awaiting_user_ack", "budget_warning",
    "provider_fallback", "error", "final", "done",
]


def test_reducer_file_contains_required_cases() -> None:
    assert REDUCER.is_file(), f"missing {REDUCER}"
    body = REDUCER.read_text(encoding="utf-8")
    for action in REQUIRED:
        assert f"case '{action}'" in body or f'case "{action}"' in body
    assert "window.AppComponents.chatReducer" in body
    assert "window.AppComponents.chatInitialState" in body


def test_reducer_walks_full_session() -> None:
    if not shutil.which("node"):
        pytest.fail("Node.js is required for reducer dynamic test; do not skip this test.")
    events = [
        {"type": "user_input", "content": "hello"},
        {"type": "session_started", "session_id": "s-1"},
        {"type": "tool_started", "tool_call_id": "tc-1", "tool_name": "run_trace", "input": {}},
        {"type": "assistant_thinking", "content_delta": "正在"},
        {"type": "assistant_thinking", "content_delta": "分析"},
        {"type": "tool_completed", "tool_call_id": "tc-1", "status": "ok", "output": {"ok": True}},
        {"type": "awaiting_user_ack", "tool_call_id": "tc-2", "sql_text": "SELECT 1", "rows_estimated": 10},
        {"type": "tool_completed", "tool_call_id": "tc-2", "status": "ok", "output": {}},
        {"type": "budget_warning", "used": 9000, "limit": 10000, "percentage": 90},
        {"type": "provider_fallback", "from": "claude", "to": "openai", "reason": "rate_limit"},
        {"type": "final", "final_message": "完成", "total_rounds": 1, "total_tokens": 100, "confidence": 0.8},
        {"type": "done"},
    ]
    js = f"""
const fs = require('fs');
const window = {{}};
eval(fs.readFileSync({json.dumps(str(REDUCER))}, 'utf8'));
let state = window.AppComponents.chatInitialState;
for (const evt of {json.dumps(events)}) state = window.AppComponents.chatReducer(state, evt);
process.stdout.write(JSON.stringify(state));
"""
    out = subprocess.check_output(["node", "-e", js], cwd=REPO)
    state = json.loads(out)
    assert state["sessionId"] == "s-1"
    assert len(state["messages"]) >= 2
    assert state["toolCalls"][0]["status"] == "ok"
    assert state["pendingAck"] is None
    assert state["budget"]["percentage"] == 90
    assert state["providerFallback"]["from"] == "claude"
    assert state["final"]["final_message"] == "完成"
    assert state["streamEnded"] is True
```

**验证命令**：

```powershell
python -m pytest tests/frontend/test_chat_reducer.py -q
```

**期望输出**：测试 FAIL，原因是 `chatReducer.js` 尚不存在。

### Task 2.2 — GREEN：新增 chatReducer.js 并更新 LOAD_ORDER

**新建文件**：`app/static/js/components/panels/chat/chatReducer.js`。

```js
const chatInitialState = {
  sessionId: null,
  messages: [],
  toolCalls: [],
  pendingAck: null,
  budget: null,
  providerFallback: null,
  final: null,
  error: null,
  streamEnded: false,
};

function _appendAssistant(messages, delta) {
  const last = messages[messages.length - 1];
  if (last && last.role === 'assistant' && !last.finalized) {
    return messages.slice(0, -1).concat([{ ...last, content: (last.content || '') + delta }]);
  }
  return messages.concat([{ role: 'assistant', content: delta, finalized: false }]);
}

function _finalizeAssistant(messages, finalMessage) {
  const last = messages[messages.length - 1];
  if (last && last.role === 'assistant' && !last.finalized) {
    return messages.slice(0, -1).concat([{ ...last, content: finalMessage, finalized: true }]);
  }
  return messages.concat([{ role: 'assistant', content: finalMessage, finalized: true }]);
}

function chatReducer(state, evt) {
  switch (evt.type) {
    case 'user_input':
      return { ...state, error: null, messages: state.messages.concat([{ role: 'user', content: evt.content }]) };
    case 'session_started':
      return { ...state, sessionId: evt.session_id };
    case 'tool_started':
      return { ...state, toolCalls: state.toolCalls.concat([{ tool_call_id: evt.tool_call_id, tool_name: evt.tool_name, status: 'pending', input: evt.input, output: null }]) };
    case 'tool_completed': {
      const updated = state.toolCalls.map((t) => t.tool_call_id === evt.tool_call_id ? { ...t, status: evt.status === 'ok' ? 'ok' : 'error', output: evt.output } : t);
      const pendingAck = state.pendingAck && state.pendingAck.tool_call_id === evt.tool_call_id ? null : state.pendingAck;
      return { ...state, toolCalls: updated, pendingAck };
    }
    case 'assistant_thinking':
      return { ...state, messages: _appendAssistant(state.messages, evt.content_delta || '') };
    case 'awaiting_user_ack':
      return { ...state, pendingAck: { tool_call_id: evt.tool_call_id, sql_text: evt.sql_text || '', rows_estimated: evt.rows_estimated ?? null } };
    case 'budget_warning':
      return { ...state, budget: { used: evt.used, limit: evt.limit, percentage: evt.percentage } };
    case 'provider_fallback':
      return { ...state, providerFallback: { from: evt.from, to: evt.to, reason: evt.reason } };
    case 'error':
      return { ...state, error: { error_type: evt.error_type || 'error', message: evt.message || 'unknown error' } };
    case 'final':
      return { ...state, final: { final_message: evt.final_message, total_rounds: evt.total_rounds, total_tokens: evt.total_tokens, confidence: evt.confidence }, messages: _finalizeAssistant(state.messages, evt.final_message || '') };
    case 'done':
      return { ...state, streamEnded: true };
    default:
      return state;
  }
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.chatReducer = chatReducer;
window.AppComponents.chatInitialState = chatInitialState;
```

**编辑文件**：`app/ui/build_frontend.py`，在 `ChatPanel.jsx` 之前加入：

```python
    "js/components/panels/chat/chatReducer.js",
```

**验证命令**：

```powershell
python -m pytest tests/frontend/test_chat_reducer.py -q
```

**期望输出**：测试 PASS。若 Node.js 不在 PATH，按失败处理，不改成 skip。

### Task 2.3 — GREEN：扩展 API service

**编辑文件**：`app/static/js/services/api.js`，在 `analyzeModule` 后追加：

```js
async function createOrchestratorSession(initialMessage) {
  const res = await fetch('/api/orchestrator/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ initial_message: initialMessage })
  });
  if (!res.ok) throw new Error(`createOrchestratorSession ${res.status}`);
  return res.json();
}

async function sendOrchestratorMessage(sessionId, content) {
  const res = await fetch(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content })
  });
  if (!res.ok) throw new Error(`sendOrchestratorMessage ${res.status}`);
  return res.json();
}

function openOrchestratorStream(sessionId, handlers) {
  const es = new EventSource(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/stream`);
  es.onmessage = (event) => {
    try {
      const evt = JSON.parse(event.data);
      handlers.onEvent && handlers.onEvent(evt);
      if (evt.type === 'done') {
        es.close();
        handlers.onClose && handlers.onClose();
      }
    } catch (err) {
      handlers.onError && handlers.onError(err);
    }
  };
  es.onerror = (err) => {
    handlers.onError && handlers.onError(err);
    es.close();
  };
  return es;
}

async function ackOrchestratorTool(sessionId, toolCallId, decision) {
  const res = await fetch(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}/ack`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tool_call_id: toolCallId, decision })
  });
  if (!res.ok) throw new Error(`ackOrchestratorTool ${res.status}`);
  return res.json();
}

async function fetchOrchestratorSession(sessionId) {
  const res = await fetch(`/api/orchestrator/sessions/${encodeURIComponent(sessionId)}`);
  if (!res.ok) throw new Error(`fetchOrchestratorSession ${res.status}`);
  return res.json();
}
```

并把末尾注册替换成：

```js
window.AppServices = window.AppServices || {};
window.AppServices.api = {
  analyzeByUid, analyzeByFile, analyzeByUidStream, fetchTrace, fetchUiConfig, analyzeModule,
  createOrchestratorSession, sendOrchestratorMessage, openOrchestratorStream,
  ackOrchestratorTool, fetchOrchestratorSession
};
```

**验证命令**：

```powershell
python -c "s=open('app/static/js/services/api.js',encoding='utf-8').read(); assert 'createOrchestratorSession' in s and 'fetchOrchestratorSession' in s and 'ackOrchestratorTool' in s; print('OK')"
```

### Task 2.4 — GREEN：替换 ChatPanel 为 stateful 版本

**替换文件**：`app/static/js/components/panels/chat/ChatPanel.jsx`。

```jsx
const {
  ChatMessageList,
  ChatInputBox,
  ChatToolCallStream,
  ChatAckCard,
  ChatBudgetBanner,
  ChatProviderFallbackBanner,
  chatReducer,
  chatInitialState,
} = window.AppComponents;
const { createOrchestratorSession, sendOrchestratorMessage, openOrchestratorStream, ackOrchestratorTool } = window.AppServices.api;
const { useReducer, useState, useRef, useEffect, useCallback } = React;

function ChatPanel() {
  const [state, dispatch] = useReducer(chatReducer, chatInitialState);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const esRef = useRef(null);

  const startStream = useCallback((sessionId) => {
    if (esRef.current) esRef.current.close();
    const es = openOrchestratorStream(sessionId, {
      onEvent: (evt) => dispatch(evt),
      onError: (err) => {
        dispatch({ type: 'error', error_type: 'sse', message: String((err && err.message) || err) });
        setStreaming(false);
      },
      onClose: () => setStreaming(false),
    });
    esRef.current = es;
  }, []);

  const onSend = useCallback(async () => {
    const content = input.trim();
    if (!content) return;
    setInput('');
    dispatch({ type: 'user_input', content });
    setStreaming(true);
    try {
      if (!state.sessionId) {
        const payload = await createOrchestratorSession(content);
        dispatch({ type: 'session_started', session_id: payload.session_id });
        startStream(payload.session_id);
      } else {
        await sendOrchestratorMessage(state.sessionId, content);
        if (!esRef.current || esRef.current.readyState === 2) startStream(state.sessionId);
      }
    } catch (err) {
      dispatch({ type: 'error', error_type: 'send', message: String((err && err.message) || err) });
      setStreaming(false);
    }
  }, [input, state.sessionId, startStream]);

  const onApprove = useCallback(async () => {
    if (!state.pendingAck || !state.sessionId) return;
    try {
      await ackOrchestratorTool(state.sessionId, state.pendingAck.tool_call_id, 'approve');
    } catch (err) {
      dispatch({ type: 'error', error_type: 'ack', message: String((err && err.message) || err) });
    }
  }, [state.pendingAck, state.sessionId]);

  const onReject = useCallback(async () => {
    if (!state.pendingAck || !state.sessionId) return;
    try {
      await ackOrchestratorTool(state.sessionId, state.pendingAck.tool_call_id, 'reject');
    } catch (err) {
      dispatch({ type: 'error', error_type: 'ack', message: String((err && err.message) || err) });
    }
  }, [state.pendingAck, state.sessionId]);

  useEffect(() => {
    if (!state.pendingAck) return undefined;
    const handler = (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        onApprove();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        onReject();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [state.pendingAck, onApprove, onReject]);

  useEffect(() => () => {
    if (esRef.current) esRef.current.close();
  }, []);

  return (
    <section className="flex flex-col gap-4 min-h-[520px]">
      <div>
        <h2 className="text-xl font-bold text-slate-800">自然语言对话</h2>
        <p className="text-sm text-slate-500">NL Chat</p>
      </div>
      <ChatBudgetBanner used={state.budget && state.budget.used} limit={state.budget && state.budget.limit} />
      <ChatProviderFallbackBanner from={state.providerFallback && state.providerFallback.from} to={state.providerFallback && state.providerFallback.to} reason={state.providerFallback && state.providerFallback.reason} />
      {state.error ? <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{state.error.error_type}: {state.error.message}</div> : null}
      <div className="flex-1 rounded-xl border border-slate-200 bg-slate-50 p-4 overflow-y-auto">
        <ChatMessageList messages={state.messages} />
        <ChatToolCallStream toolCalls={state.toolCalls} />
      </div>
      <ChatAckCard pending={state.pendingAck} onApprove={onApprove} onReject={onReject} />
      <ChatInputBox value={input} onChange={setInput} onSend={onSend} disabled={streaming || !!state.pendingAck} />
    </section>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatPanel = ChatPanel;
```

### Task 2.5 — Phase 2 回归与 commit

**验证命令**：

```powershell
python -m pytest tests/frontend/test_chat_reducer.py -q
python -m pytest tests/ -q 2>&1 | Select-Object -Last 3
python -m pytest data_acquisition_agent/tests/ -q 2>&1 | Select-Object -Last 3
git diff --stat
```

用户确认后执行：

```powershell
git add app/static/js/components/panels/chat/ app/static/js/services/api.js app/ui/build_frontend.py tests/frontend/
git commit -m "feat(plan-04): Phase 2 chat SSE reducer and API"
```

---

## Phase 3 — URL 路由 + Session 恢复 + 手测文档 + complete

**目标**：把 `?tab=chat` 放到真实 state owner `app.jsx`，把 `?session=<uuid>` 恢复逻辑放到 ChatPanel。

### Task 3.1 — RED：URL 与 session 恢复静态测试

**新建文件**：`tests/frontend/test_chat_phase3_capabilities.py`。

```python
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "app" / "static" / "js" / "app.jsx"
CHAT_PANEL = REPO / "app" / "static" / "js" / "components" / "panels" / "chat" / "ChatPanel.jsx"


def test_app_owns_tab_url_routing() -> None:
    src = APP.read_text(encoding="utf-8")
    assert "VALID_DASHBOARD_TABS" in src
    assert "function getInitialDashboardTab()" in src
    assert "function getInitialViewFromUrl()" in src
    assert re.search(r"new\s+URLSearchParams\s*\(\s*window\.location\.search\s*\)", src)
    assert re.search(r"\.get\(\s*['\"]tab['\"]\s*\)", src)
    assert re.search(r"\.get\(\s*['\"]session['\"]\s*\)", src)
    assert re.search(r"useState\s*\(\s*getInitialViewFromUrl\s*\)", src)
    assert re.search(r"useState\s*\(\s*getInitialDashboardTab\s*\)", src)
    assert re.search(r"tab\s*===\s*['\"]chat['\"]\s*\|\|\s*params\.get\(\s*['\"]session['\"]\s*\)", src)
    assert "window.history.replaceState" in src


def test_chat_panel_restores_and_writes_session_url() -> None:
    src = CHAT_PANEL.read_text(encoding="utf-8")
    assert re.search(r"\.get\(\s*['\"]session['\"]\s*\)", src)
    assert "fetchOrchestratorSession" in src
    assert re.search(r"\.set\(\s*['\"]session['\"]", src)
    assert re.search(r"\.set\(\s*['\"]tab['\"]\s*,\s*['\"]chat['\"]", src)
    assert "window.history.replaceState" in src
```

**验证命令**：

```powershell
python -m pytest tests/frontend/test_chat_phase3_capabilities.py -q
```

**期望输出**：测试 FAIL，原因是 URL / session 恢复尚未实现。

### Task 3.2 — GREEN：在 app.jsx 实现初始入口与 tab URL 双向同步

**编辑文件**：`app/static/js/app.jsx`。

在 `MODULE_RESULT_MAP` 后新增：

```jsx
const VALID_DASHBOARD_TABS = ['comprehensive', 'app', 'behavior', 'credit', 'product', 'ops', 'trace', 'chat'];

function getInitialDashboardTab() {
  const params = new URLSearchParams(window.location.search);
  const tab = params.get('tab');
  if (VALID_DASHBOARD_TABS.includes(tab)) return tab;
  if (params.get('session')) return 'chat';
  return 'comprehensive';
}

function getInitialViewFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const tab = params.get('tab');
  if (tab === 'chat' || params.get('session')) return 'dashboard';
  return 'home';
}
```

把：

```jsx
  const [view, setView] = useState('home');
```

替换为：

```jsx
  const [view, setView] = useState(getInitialViewFromUrl);
```

把：

```jsx
  const [activeTab, setActiveTab] = useState('comprehensive');
```

替换为：

```jsx
  const [activeTab, setActiveTab] = useState(getInitialDashboardTab);
```

**行为约束**：普通 `/` 仍进入 HomeView；`/?tab=chat` 直接进入 DashboardView 并高亮 chat tab；`/?session=<uuid>` 也直接进入 DashboardView 的 chat tab，并交给 ChatPanel 执行 session restore。

在 fetch config 的 `useEffect` 后新增：

```jsx
  useEffect(() => {
    if (view !== 'dashboard') return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('tab') !== activeTab) {
      params.set('tab', activeTab);
      const nextUrl = `${window.location.pathname}?${params.toString()}${window.location.hash}`;
      window.history.replaceState({}, '', nextUrl);
    }
  }, [view, activeTab]);
```

**验证命令**：

```powershell
python -m pytest tests/frontend/test_chat_phase3_capabilities.py::test_app_owns_tab_url_routing -q
```

**期望输出**：该测试 PASS，且静态断言同时覆盖 `view` 初始路由、`activeTab` 初始路由、`?session=<uuid>` 默认进入 chat。

### Task 3.3 — GREEN：替换 ChatPanel 为 session 恢复终态

**替换文件**：`app/static/js/components/panels/chat/ChatPanel.jsx`。

```jsx
const {
  ChatMessageList,
  ChatInputBox,
  ChatToolCallStream,
  ChatAckCard,
  ChatBudgetBanner,
  ChatProviderFallbackBanner,
  chatReducer,
  chatInitialState,
} = window.AppComponents;
const { createOrchestratorSession, sendOrchestratorMessage, openOrchestratorStream, ackOrchestratorTool, fetchOrchestratorSession } = window.AppServices.api;
const { useReducer, useState, useRef, useEffect, useCallback } = React;

function ChatPanel() {
  const [state, dispatch] = useReducer(chatReducer, chatInitialState);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const esRef = useRef(null);

  const startStream = useCallback((sessionId) => {
    if (esRef.current) esRef.current.close();
    const es = openOrchestratorStream(sessionId, {
      onEvent: (evt) => dispatch(evt),
      onError: (err) => {
        dispatch({ type: 'error', error_type: 'sse', message: String((err && err.message) || err) });
        setStreaming(false);
      },
      onClose: () => setStreaming(false),
    });
    esRef.current = es;
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const sessionId = params.get('session');
    if (!sessionId) return undefined;
    let cancelled = false;
    fetchOrchestratorSession(sessionId).then((history) => {
      if (cancelled) return;
      dispatch({ type: 'session_started', session_id: sessionId });
      (history.messages || []).forEach((message) => {
        if (message.role === 'user') dispatch({ type: 'user_input', content: message.content || '' });
        if (message.role === 'assistant') dispatch({ type: 'final', final_message: message.content || '', total_rounds: 0, total_tokens: 0, confidence: 1 });
      });
    }).catch((err) => {
      if (!cancelled) dispatch({ type: 'error', error_type: 'restore', message: String((err && err.message) || err) });
    });
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!state.sessionId) return;
    const params = new URLSearchParams(window.location.search);
    if (params.get('session') !== state.sessionId || params.get('tab') !== 'chat') {
      params.set('session', state.sessionId);
      params.set('tab', 'chat');
      window.history.replaceState({}, '', `${window.location.pathname}?${params.toString()}${window.location.hash}`);
    }
  }, [state.sessionId]);

  const onSend = useCallback(async () => {
    const content = input.trim();
    if (!content) return;
    setInput('');
    dispatch({ type: 'user_input', content });
    setStreaming(true);
    try {
      if (!state.sessionId) {
        const payload = await createOrchestratorSession(content);
        dispatch({ type: 'session_started', session_id: payload.session_id });
        startStream(payload.session_id);
      } else {
        await sendOrchestratorMessage(state.sessionId, content);
        if (!esRef.current || esRef.current.readyState === 2) startStream(state.sessionId);
      }
    } catch (err) {
      dispatch({ type: 'error', error_type: 'send', message: String((err && err.message) || err) });
      setStreaming(false);
    }
  }, [input, state.sessionId, startStream]);

  const onApprove = useCallback(async () => {
    if (!state.pendingAck || !state.sessionId) return;
    try {
      await ackOrchestratorTool(state.sessionId, state.pendingAck.tool_call_id, 'approve');
    } catch (err) {
      dispatch({ type: 'error', error_type: 'ack', message: String((err && err.message) || err) });
    }
  }, [state.pendingAck, state.sessionId]);

  const onReject = useCallback(async () => {
    if (!state.pendingAck || !state.sessionId) return;
    try {
      await ackOrchestratorTool(state.sessionId, state.pendingAck.tool_call_id, 'reject');
    } catch (err) {
      dispatch({ type: 'error', error_type: 'ack', message: String((err && err.message) || err) });
    }
  }, [state.pendingAck, state.sessionId]);

  useEffect(() => {
    if (!state.pendingAck) return undefined;
    const handler = (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        onApprove();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        onReject();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [state.pendingAck, onApprove, onReject]);

  useEffect(() => () => {
    if (esRef.current) esRef.current.close();
  }, []);

  return (
    <section className="flex flex-col gap-4 min-h-[520px]">
      <div>
        <h2 className="text-xl font-bold text-slate-800">自然语言对话</h2>
        <p className="text-sm text-slate-500">NL Chat</p>
      </div>
      <ChatBudgetBanner used={state.budget && state.budget.used} limit={state.budget && state.budget.limit} />
      <ChatProviderFallbackBanner from={state.providerFallback && state.providerFallback.from} to={state.providerFallback && state.providerFallback.to} reason={state.providerFallback && state.providerFallback.reason} />
      {state.error ? <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{state.error.error_type}: {state.error.message}</div> : null}
      <div className="flex-1 rounded-xl border border-slate-200 bg-slate-50 p-4 overflow-y-auto">
        <ChatMessageList messages={state.messages} />
        <ChatToolCallStream toolCalls={state.toolCalls} />
      </div>
      <ChatAckCard pending={state.pendingAck} onApprove={onApprove} onReject={onReject} />
      <ChatInputBox value={input} onChange={setInput} onSend={onSend} disabled={streaming || !!state.pendingAck} />
    </section>
  );
}

window.AppComponents = window.AppComponents || {};
window.AppComponents.ChatPanel = ChatPanel;
```

**验证命令**：

```powershell
python -m pytest tests/frontend/test_chat_phase3_capabilities.py -q
```

**期望输出**：测试 PASS。

### Task 3.4 — 手测文档

**新建文件**：`docs/reviews/nl-chat-manual-test.md`。

```markdown
# NL Chat Tab 手动测试用例

前置：Plan #03 已完成，运行 `USE_MOCK_LLM=1 uvicorn app.main:app --reload --port 8000`。

## TC-1 首次打开
1. 打开 `http://localhost:8000/`。
2. 期望仍停留在 HomeView，不自动进入 dashboard。
3. 打开 `http://localhost:8000/?tab=chat`。
4. 期望直接进入 DashboardView，第 8 个 tab `自然语言对话 / NL Chat` 高亮，页面无 console error。
5. **本步需先完成 TC-2 / TC-4 拿到真实 `<uuid>`**：用 TC-2 创建的 session_id 拼出 `http://localhost:8000/?session=<uuid>`，期望直接进入 DashboardView，第 8 个 tab 高亮，并触发 session restore（无真实 session_id 时跳过本步）。

## TC-2 首轮对话
1. 输入 `分析 G3 在墨西哥的 churn 风险`，按 Enter。
2. 期望出现 user 气泡、assistant 增量气泡、工具调用状态、最终 final 气泡。

## TC-3 ACK
1. mock 流触发 `awaiting_user_ack`。
2. 期望黄色 ACK 卡片出现。
3. Enter 发送 approve；Esc 发送 reject。

## TC-4 刷新恢复
1. 完成对话后确认 URL 包含 `?tab=chat&session=<uuid>`。
2. F5 刷新，期望历史消息恢复。

## TC-5 错误兜底
1. 停止后端，再发送消息。
2. 期望红色错误条出现，页面不崩溃。

执行结果：
- [ ] TC-1 PASS
- [ ] TC-2 PASS
- [ ] TC-3 PASS
- [ ] TC-4 PASS
- [ ] TC-5 PASS
```

### Task 3.5 — 全量回归 + complete commit + push

**验证命令**：

```powershell
python -m pytest tests/ -q 2>&1 | Select-Object -Last 3
python -m pytest data_acquisition_agent/tests/ -q 2>&1 | Select-Object -Last 3
Test-Path docs/reviews/nl-chat-manual-test.md
git diff --stat
```

用户确认后执行：

```powershell
git add app/static/js/app.jsx app/static/js/components/ app/static/js/services/api.js app/ui/build_frontend.py tests/frontend/ docs/reviews/nl-chat-manual-test.md docs/plans/04-nl-chat-tab-frontend-plan.md docs/reviews/04-nl-chat-tab-plan-audit.md
git commit -m "feat(plan-04): Phase 3 URL restore + [complete] nl-chat-tab"
git remote -v
git push origin main
git log origin/main..HEAD
```

**期望输出**：push 只发生在 `github` remote；`origin/main..HEAD` 仍显示本地领先，证明未 push origin。

---

## 完成标志

1. Phase 1 commit：`feat(plan-04): Phase 1 chat skeleton`
2. Phase 2 commit：`feat(plan-04): Phase 2 chat SSE reducer and API`
3. Phase 3 commit：`feat(plan-04): Phase 3 URL restore + [complete] nl-chat-tab`
4. `tests/` 全量通过；`data_acquisition_agent/tests/` 全量通过。
5. 浏览器 `/` 仍打开 HomeView；`/?tab=chat` 与 `/?session=<uuid>` 可直接进入 DashboardView 的 chat tab。
6. 完成对话后 URL 包含 `tab=chat&session=<uuid>`，刷新可恢复历史。
7. `git push origin main` 成功，并确认其指向当前批准仓库。

---

## 五点检查法自审

| 项 | 结论 |
|---|---|
| 精确文件路径 | 通过：每个新增/修改文件均给出明确路径 |
| 无占位符 | 通过：Dashboard / ChatPanel 关键替换块无 `...保持...` 占位 |
| 完整代码块 | 通过：新增组件、reducer、API、URL routing、session restore 均给完整代码 |
| 验证命令 | 通过：每个 Phase 有 RED/GREEN/回归命令和期望输出 |
| 单一执行人 | 通过：Phase 串行执行，commit 前均要求 diff 审核 |
