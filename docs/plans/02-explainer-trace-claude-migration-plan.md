# Plan #02 — Profile explainer + Trace 切 Claude Opus 4.7

| 项 | 值 |
|---|---|
| 状态 | Pending（等待执行；硬前置：Plan #01 [complete]） |
| Design Doc | docs/specs/02-explainer-trace-claude-migration-design.md |
| 依赖 | Plan #01（[complete] model-client-refactor） |
| 后继 | 无（独立 Plan，与 Plan #03 并行） |
| Phase 数 | 5（Phase 0 baseline + Phase 0.5 codebase 校对 + Phase 1-3） |
| Commit 策略 | 4 commits 上限：baseline + Phase 1 + Phase 2 + Phase 3 [complete]（Phase 0.5 不产生 commit） |

---

## Scope

**本 Plan 做**：
- `config.yaml` 新增 `llm.providers` + `llm.routes`（含 `behavior_profile.timeline` 第 8 条路由）
- `app/core/config.py` 新增 `get_llm_config` / `llm_provider_for` / `validate_llm_routes`
- `ModelClient.generate_structured` 增加 `route_key` 可选参数
- 创建 `app/core/providers/factory.py` + `claude_maestro_provider.py`
- **8 个调用点**接入 `route_key`（7 个 explainer + BehaviorExplainer 的 timeline 第二路）
- Phase 2 Maestro 协议适配 + 复用 Plan #01 Phase 2 抽出的 `json_repair.py`
- Phase 3 fallback chain 验证（在 `ModelClient` 层直接验证，不绕 explainer）

**本 Plan 不做（Out-of-Scope）**：
- 不动 `data_acquisition_agent/**`（Surgical Hard Boundary）
- 不动任何 explainer 的 `__init__` / `explain` 签名（只在 `generate_structured` 调用末尾追加 `route_key=` 参数）
- 不动 7 个 explainer 的 prompt 文本（Design Doc § 4.2 决策：靠 Provider 层 JSON repair 适配差异）
- 不引入 SSE / async 接口（Plan #03 之后再说）
- 不做 feature flag / 灰度 / canary（V1 简化为一次性切换 + `git revert` 回滚）
- 不做 provider 实例 LRU cache（P2-1，延迟监控触发再加）

## 期望最终行为（Worked Example）

执行完 Phase 3 后,下面调用必须能跑（vertex 模式 + Maestro endpoint 真实回填）：

```python
from app.core.model_client import ModelClient

client = ModelClient()  # 默认 vertex 模式 → fallback_chain(claude → gemini)
out = client.generate_structured(
    skill_name="app_profile",
    prompt="...",
    fallback_result={"degraded": True},
    route_key="app_profile.explainer",
)
# 走 Claude → 成功：out["status"] == "ok", structured_result 来自 Claude
# Claude 不可达：自动 fallback Gemini → out["status"] == "ok"，logger 记 provider_fallback warning
```

且 `grep -rn 'route_key=' app/runtime_skills/` 应该精确找到 **8 行**：
- `app_profile.explainer`（L55 调用点）
- `behavior_profile.explainer`（L129 profile chain 调用点）
- `behavior_profile.timeline`（L142 timeline chain 调用点）← R7 P0-2 新增
- `credit_profile.explainer`（L42 调用点）
- `comprehensive.explainer`（L46 调用点）
- `product_advice.explainer`（L42 调用点）
- `ops_advice.explainer`（L42 调用点）
- `trace_analyzer.explainer`（L51 调用点）

## 已知风险与开放问题

1. **Plan #01 [complete] 是硬前置**：本 Plan 全部 Task 依赖 `ModelClient.__init__(provider=...)` / `self._provider` / `last_token_usage` / `_record_usage` / `_classify_model_error` / `fallback_chain` 已落地。Plan #01 R5.1 Phase 2-3 才创建这些。当前 git log 只有 `[baseline] model-client-refactor`，必须先跑完 Plan #01。
2. **Maestro 协议假设**：Task 2.1 实装基于对 Maestro response shape 的纸面假设（`content[].type=='tool_use'.input` / `content[].type=='text'.text`）。Plan #03 Phase 0 Task 0.2 Spike 完成后，必须按真实协议**重新审视** Task 2.1 全部代码——见 Task 2.1 顶部协议警示。
3. **Phase 1 stub 阶段无"看得见的进步"**：`ClaudeMaestroProvider` Phase 1 是 stub，调用必抛 `ProviderUnavailable`，所有 7 explainer 在 vertex 模式下永远 fallback 到 Gemini；Phase 2 Task 2.1 实装真实 `_post` 后才能看到 Claude 切换效果。
4. **`validate_llm_routes` 启动调用**：依赖 `app/main.py` 加 `@app.on_event("startup")` 钩子。Plan #02 不动 main.py 业务逻辑，Task 1.2 给最小 diff 示例。
5. **explainer 真实接口与 Plan 假设不一致风险**：所有 7 explainer 的真实 `__init__` / `explain` 签名 / `_build_*_payload` / `_build_*_response_schema` 各异，**不能假设统一形状**。R7 修订后所有 diff 改为"在 `generate_structured(...)` 调用最后一个参数后追加 `route_key=` 一行"的机械操作模式，不依赖类名/方法名。

## 修订记录

- **R9 (2026-05-02)** — Plan #02 [complete] (4f1b4a5) 后的实施期微调同步修订（6 处，全部追溯锚点已写入 Phase 1/2/3 commit message：3ee2c8f / 16b48fc / 874c305）：
  - **微调 1: Task 1.2 R7 P0-4 placeholder 检测 bug**——原 `ep = (p_cfg.get("endpoint") or "").strip()` 把"未声明 endpoint"和"声明了但是 placeholder"等同处理，导致 gemini/mock 被误报警告（它们走 SDK / 不走网络，本来就不需要 endpoint）。修复：先判 `ep is None` 跳过，再判 strip 后的值是否在 PLACEHOLDER_ENDPOINTS。只有 claude_maestro 这种"声明了 endpoint='[Spike Pending]'"的情况会 warning。
  - **微调 2: Task 1.6 mock 模式回归命令**——原 `$env:MODEL_MODE = "mock"` + 全量 pytest 会让 facade 测试 `test_model_client_accepts_injected_provider` 失败（mock 短路返回 fallback_result `{"fallback": True}`，而测试期望注入 `_FakeProvider` 的返回 `{"echo": ...}`）。这是 facade 测试的设计前提冲突——它需要 vertex 模式才能走 try 块用注入 provider。修复：主验证用 vertex 模式跑全量（与 Phase 0 baseline 同环境对比，期望 282 passed），补充 mock 模式 deselect facade test 跑 sanity（期望 281 passed, 1 deselected）证明"mock 路径绕过 routes 零回归"核心断言。
  - **微调 3: Task 1.3 provider 解析块必须在 try 内**——Plan 原骨架将 provider 解析块放在 try 之外，vertex 模式下 `build_provider_by_name("claude_maestro")` 实例化 `ClaudeMaestroProvider` 因 `endpoint='[Spike Pending]'` 抛 `ProviderUnavailable` 会绕过 ModelClient 既有 except 路径直接冒泡到 explainer/skill，破坏 SkillRegistry → UserAnalysisResult schema 校验。修复：把 provider 解析块挪进 try 块（mock 短路之后），让 ProviderUnavailable 走标准 fallback degraded path（status=model_unavailable + degraded 字典）。Phase 1 commit 时 vertex 282 passed 没暴露此 bug 是因为 Phase 1 末 ClaudeMaestroProvider 还是 stub（直接 raise ProviderUnavailable from `generate_json`，不是 from `__init__`），Phase 2 stub→实装后 `__init__` 才开始抛错暴露问题。
  - **微调 4: Task 2.3 endpoint_unreachable 测试 patch 位置**——原 Plan 用 `monkeypatch.setattr("...ClaudeMaestroProvider._post", _explode)` 替换整个 `_post` 方法，绕过了 `_post` 内部的 `try/except (httpx.ConnectError → ProviderUnavailable)` 转换逻辑（测试压根没覆盖到这个关键转换）。修复：改为 patch `httpx.Client`（`_post` 调用的下一层），让真正的 `_post` try/except 接住 ConnectError 并转换。语义不变，更准确测试 transport error 处理逻辑。
  - **微调 5: Task 2.3 provider fixture 双层 patch**——原 Plan 只 `monkeypatch.setattr("app.core.config.get_llm_config", ...)`，但 `claude_maestro_provider.py` 顶部 `from app.core.config import get_llm_config` 已绑函数到本地命名空间。单跑 5 测试时全 PASS（cache 未填）但全量跑时 setUp 错误（cache 已被前面测试填充为真实 [Spike Pending] config）。修复：fixture 同时 patch `app.core.providers.claude_maestro_provider.get_llm_config`（本地引用）+ `app.core.config.get_llm_config`（源），双层都覆盖 from-import 绑定的本地命名空间问题。
  - **微调 6: Task 3.3 fixture 双层 patch（与微调 5 同根因）**——同样的 from-import 本地命名空间问题。修复：同微调 5，在 Task 3.3 fallback e2e 测试的两个测试函数里都做双层 patch。
- **R8 (2026-05-02)** — Plan #01 [complete] (a949830) 后、本 Plan 执行前的 audit修齐4 项跨 Plan + 实施级问题：
  - **P0-A: Task 1.3 不能覆盖 Plan #01 落地版**——Plan 原给的“完整改造后函数体”会覆盖 Plan #01 R5.1 Task 3.3 落地的 baseline（缺 `self._log_payload_ready(skill_name, structured_result)` 调用 + 多一条无契约价值的 `logger.info("ModelClient ok ...")`）。Plan #01 Task 3.3 已选方案 C：保留 `_log_payload_ready` + 仅追加 `_record_usage` 调用、不加新 `logger.info`。下游 grafana log query / caplog 断言依赖 `"LLM payload ready"` 字串，覆盖即回归。修复：Task 1.3 改为“在 Plan #01 落地版本上做最小修改”模式，明令 baseline 三块代码不动。
  - **P1-A: baseline 测试数字陈旧**——Plan #01 [complete] 后 `tests/` 实际 282 passed（+12: 8 contract 展开 + 2 facade + 2 fallback）、`data_acquisition_agent/tests/` 实际 163 passed (1 skipped)。原 Plan 写 270 / 153 是起草期数字。修复：Task 0.2 / 1.6 / 3.4 期望数字全部锁定为 282 / 163 起步，后续按新增测试递增。
  - **P1-B: Task 0.5.2 grep `fallback_chain` 在 model_client.py 是间接命中**——Plan #01 落地后 `fallback_chain` 定义在 `app/core/providers/base.py`，`model_client.py` 仅通过 `_build_default_provider` 函体内部 `from app.core.providers.base import fallback_chain` 间接引用。原期望“必须看到 fallback_chain 出现”在 model_client.py 表面上可能看不到，会误报 abort。修复：Task 0.5.2 末尾加补充说明 + 额外 grep base.py。
  - **P1-C: commit 用 `git add -A` 是踩雷点**——Plan #01 已踩过（ed66bcc 事故）：外部 untracked 文件（`docs/plans/.r5-stash.patch` / `*.r5-draft.md` / `*.bak` 等）被误带入 commit。修复：Task 0.2 / 1.7 / 2.4 / 3.5 / TASK.md 收尾 commit 全部改为显式 add 清单，禁用 `git add -A`。
- **R7 (2026-05-02)** — 按 R6 audit（docs/reviews/02-...-review.md）修齐 5 P0 + 4 P1：
  - P0-1: Task 1.5 七段 diff 全部凭空编造 → 改为"机械追加规则 + 8 行映射表 + 单一示例 diff"模式（不依赖真实类名/方法名）
  - P0-2: BehaviorExplainer 双调用点漏挂 → `config.yaml` 新增 `behavior_profile.timeline` 路由 + Task 1.5 表格列出 8 个调用点
  - P0-3: Task 3.3 fallback 测试根本跑不起来 → 重写为直接测 `ModelClient` 层（不绕 explainer 复杂签名）
  - P0-4: `validate_llm_routes` 不识别 `[Spike Pending]` → Task 1.2 末尾加 placeholder endpoint warning + Task 1.2 给 `app/main.py` startup 钩子最小 diff
  - P0-5: Plan #01 未 [complete] 是空中楼阁 → 表头 Phase 数改 5、Task 0.1 期望保留 abort 行为、本节列硬前置
  - P1-1: 缺 5 段标准章节 → 本次 R7 一次性补齐 Scope / Out-of-Scope / Worked Example / 已知风险 / 修订记录
  - P1-2: 缺 Phase 0.5 grep 校对栏 → 新增 Phase 0.5（不产生 commit）+ 把真实代码贴入下面 `## Codebase Baseline` 段
  - P1-3: Phase 3 灰度顺序段自相矛盾 → Task 3.1 重写为"V1 简化为一次性切换"
  - P1-4: Task 2.1 Maestro 协议假设无警示 → Task 2.1 顶部加协议假设警示框
- R4 (2026-04-30) — 4-commit 收口、json_repair 解耦、provider cache 备注、factory mode 跟 settings 走
- R2 (2026-04-28) — 7 段 diff 展开（被 R7 替换为机械追加规则）
- R0 (2026-04-26) — 初始版本

---

## Codebase Baseline（grep 验证 2026-05-02，所有 diff 的事实底座）

> **本节内容必须在执行 Phase 1 之前由 Phase 0.5 重新跑一次 grep 刷新**，避免代码已变。下表来自 R7 审核日 grep。

### 7 个 explainer 真实接口

| 文件 | 类名 | `__init__` 签名 | `generate_structured` 调用点 | fallback_result 来源 | response_schema 来源 |
|---|---|---|---|---|---|
| `app/runtime_skills/app_profile/explainer.py` | `AppExplainer` | `(model_client: ModelClient, prompt_path: Path)` | **L55** `skill_name="app_profile"` | `self._build_fallback_payload()` | `self._build_llm_response_schema()` |
| `app/runtime_skills/behavior_profile/explainer.py` | `BehaviorExplainer` | `(model_client, profile_prompt_path, timeline_prompt_path)` | **L129** `skill_name="behavior_profile_summary"` | `self._build_profile_fallback_payload()` | `self._build_profile_response_schema()` |
| 同上（第二路） | 同上 | 同上 | **L142** `skill_name="behavior_timeline_summary"` | `self._build_timeline_fallback_payload()` | `self._build_timeline_response_schema()` |
| `app/runtime_skills/credit_profile/explainer.py` | `CreditExplainer` | `(model_client: ModelClient, prompt_path: Path)` | **L42** `skill_name="credit_profile"` | `self._build_fallback_payload()` | `self._build_llm_response_schema()` |
| `app/runtime_skills/comprehensive/explainer.py` | `ComprehensiveExplainer` | `(model_client: ModelClient, prompt_path: Path)` | **L46** `skill_name="comprehensive_profile"` | `self._build_fallback_payload(decision_result)` | （内联或方法，见真实代码） |
| `app/runtime_skills/product_advice/explainer.py` | `ProductAdviceExplainer` | `(model_client: ModelClient, prompt_path: Path)` | **L42** `skill_name="product_advice"` | 局部变量 `fallback` | 内联 dict |
| `app/runtime_skills/ops_advice/explainer.py` | `OpsAdviceExplainer` | `(model_client: ModelClient, prompt_path: Path)` | **L42** `skill_name="ops_advice"` | 局部变量 `fallback` | 内联 dict |
| `app/runtime_skills/trace_analyzer/explainer.py` | `TraceExplainer` | `(model_client: ModelClient)` ← 单参，**无 prompt_path** | **L51** `skill_name="trace_analyzer"` | 内联 dict（含 `churn_story` / `intervention_suggestions` / `churn_root_cause`） | `self._response_schema()` |

**关键统一规律**：
- 所有 7 个文件都用 `self.model_client`（**无下划线**），不是 `self._model_client`
- 所有 7 个文件 8 个调用点都用 `kwarg=value` 形式调 `generate_structured`，最后一个参数后追加 `route_key="<x>",` 一行即可
- 类名不统一：`AppExplainer` / `BehaviorExplainer` / `CreditExplainer` / `TraceExplainer`（4 个无 `Profile`/`Analyzer` 后缀）vs `ComprehensiveExplainer` / `ProductAdviceExplainer` / `OpsAdviceExplainer`（3 个有完整后缀）

### `ModelClient` 真实接口（grep 2026-05-02）

```
L37: def __init__(self) -> None:               ← Plan #01 Phase 2 改为 def __init__(self, provider: LLMProvider | None = None) -> None
L47: def generate_structured(...)              ← Plan #01 Phase 2 重写为接受 self._provider
L85: degraded["model_error"] = self._classify_model_error(exc)
L93: def _classify_model_error(self, exc: Exception) -> str:
```

**当前缺失**（Plan #01 Phase 2-3 才落地，Plan #02 全部 Task 依赖）：
- `self._provider` 字段
- `self.last_token_usage` 字段
- `_record_usage` 方法
- `_build_default_provider` 模块级函数
- `fallback_chain` helper（在 `app/core/providers/base.py`）

→ **执行 Plan #02 前必须确认 Plan #01 跑到 `[complete] model-client-refactor`**，否则 Task 1.3 改 `ModelClient` 时会发现没有 `self._provider` 字段，diff 失败。

---

## Phase 0 — Baseline

### Task 0.1 — 验证 Plan #01 已 `[complete]`

```powershell
cd C:\Users\v-yimingliu\agent-userprofile\MAPS-LZ
git log --oneline | Select-String "complete.*model-client-refactor"
```

**期望**：找到一行 `[complete] model-client-refactor`。如果找不到，**停止**，先完成 Plan #01。

### Task 0.2 — 跑基线 + commit baseline

```powershell
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v
git status
# R8 P1-C: 禁用 `git add -A`——baseline commit 不需要 add 任何文件，直接 --allow-empty；
# 避免误带外部 untracked 文件（docs/plans/.r5-* / *.bak / docs/reviews/04-*-audit.md 等）。
git commit -m "[baseline] explainer-trace-claude" --allow-empty
```

**期望（R8 P1-A 锁定运行期数字，覆盖原写 270/153）**：
- `tests/` → **282 passed**（Plan #01 [complete] 后的实际基线：270 baseline + 12 新增，含 8 contract 展开 + 2 facade + 2 fallback）
- `data_acquisition_agent/tests/` → **163 passed, 1 skipped**（起草期写 153，期间 da-agent 增加了 10 个测试）
- baseline commit 创建后 `git log -1 --oneline` 期望看到 `[baseline] explainer-trace-claude`

任一数字偏离 → 立刻停下。`tests/` < 282 说明 Plan #01 未真正 [complete] 或有回归；`data_acquisition_agent/tests/` 偏离 163 说明 Surgical Hard Boundary 被破坏。

---

## Phase 0.5 — Codebase Baseline 校对（只读，不产生 commit）

> 用户偏好硬规则："执行前加 Phase 0 核对：先只读检查 baseline skeleton 的实际类名/字段名是否与 Plan 一致"。本 Phase 跑完后用真实输出**刷新顶部 `## Codebase Baseline` 段**，作为 Phase 1-3 所有 diff 的事实底座。

### Task 0.5.1 — grep 7 个 explainer 文件（含 8 个调用点）真实接口

```powershell
Get-ChildItem app/runtime_skills -Filter "explainer.py" -Recurse | ForEach-Object {
    Write-Output "=== $($_.FullName.Replace($PWD.Path + '\','')) ==="
    Select-String -Path $_.FullName -Pattern '^class |def __init__|def explain|generate_structured\(|skill_name=|response_schema=|fallback_result=' |
        ForEach-Object { "  L$($_.LineNumber): $($_.Line.Trim())" }
}
```

**期望**：输出 8 处 `generate_structured(` 调用点（含 BehaviorExplainer 的 L129/L142 两处），与顶部 `## Codebase Baseline` 表格完全一致。如不一致——**先修 Plan 后执行**，不允许凭印象写 diff。

### Task 0.5.2 — grep ModelClient 真实接口（确认 Plan #01 已 [complete]）

```powershell
Select-String -Path "app/core/model_client.py" -Pattern "def __init__|def generate_structured|self\._provider|self\.last_token_usage|fallback_chain|_record_usage|_log_payload_ready" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }
```

**期望**：必须看到 `self._provider` / `self.last_token_usage` / `_record_usage` / `_log_payload_ready` 全部出现。如缺失——**Plan #01 未真正完成**，停止执行 Plan #02，回去补 Plan #01 Phase 2-3。

> **R8 P1-B 补充说明**：`fallback_chain` 在 model_client.py 里是**间接命中**——Plan #01 R5.1 落地后，`fallback_chain` 定义在 `app/core/providers/base.py`，`model_client.py` 仅在 `_build_default_provider` 函体内部 `from app.core.providers.base import fallback_chain` 间接引用。上面 grep 如果命中 这一行算 PASS。如要额外确认 `fallback_chain` 真实定义存在，补跑：
>
> ```powershell
> Select-String -Path "app/core/providers/base.py" -Pattern "def fallback_chain" |
>     ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }
> ```
>
> 期望看到 `def fallback_chain(...)` 定义行。如 base.py 里也没有 → Plan #01 R5.1 未落地，abort。

### Task 0.5.3 — grep providers 目录结构

```powershell
Get-ChildItem app/core/providers/ | Format-Table Name, Length
Test-Path "app/core/providers/json_repair.py"
```

**期望**：`__init__.py` / `base.py` / `mock_provider.py` / `gemini_provider.py` / `json_repair.py` 全部存在（`json_repair.py` 由 Plan #01 Phase 2 抽出）。`claude_maestro_provider.py` / `factory.py` 不应存在（本 Plan Phase 1 创建）。

### Task 0.5.4 — 不一致时的处理

- 任一 grep 结果与顶部 `## Codebase Baseline` 不一致 → **先修 Plan 文档刷新表格，然后才能进 Phase 1**
- Plan #01 缺 `self._provider` / `last_token_usage` / `_record_usage` → **abort，回去补 Plan #01**
- 全部一致 → 进 Phase 1

> 本 Phase 不写代码、不 commit、不改任何文件，只跑 grep 命令验证事实底座。

---

## Phase 1 — `config.yaml` `llm.providers` + `llm.routes` + 8 调用点接入

### Task 1.1 — 修改 `config.yaml` 增加 `llm` 段

**修改文件**：`config.yaml`

**完整新增内容**（追加到现有 `runtime:` 段末尾）：

```yaml
llm:
  providers:
    gemini:
      mode: vertex
      model: gemini-2.5-flash
      project: amberstar-gemini
      location: global
    claude_maestro:
      endpoint: "[Spike Pending]"   # Plan #03 Phase 0 Task 0.2 回填
      model: claude-opus-4.7
      tier: 10x
    mock:
      enabled_in: ["test", "local"]
  routes:
    app_profile.explainer: claude_maestro
    behavior_profile.explainer: claude_maestro
    behavior_profile.timeline: claude_maestro   # R7 P0-2: BehaviorExplainer 第二路（timeline chain）
    credit_profile.explainer: claude_maestro
    comprehensive.explainer: claude_maestro
    product_advice.explainer: claude_maestro
    ops_advice.explainer: claude_maestro
    trace_analyzer.explainer: claude_maestro
    # 未列出的 (data_acquisition.* 等) 走默认 gemini
  default_provider: gemini
```

### Task 1.2 — 修改 `app/core/config.py` 加载 routes

**修改文件**：`app/core/config.py`

**新增字段**（在 `Settings` class 末尾补模块级缓存函数）：

```python
# app/core/config.py 文件顶部补 import
import yaml
from typing import Any

from app.core.logger import get_logger

logger = get_logger(__name__)

# app/core/config.py 模块级缓存
_LLM_CONFIG_CACHE: dict[str, Any] | None = None


def get_llm_config() -> dict[str, Any]:
    global _LLM_CONFIG_CACHE
    if _LLM_CONFIG_CACHE is None:
        path = settings.project_root / "config.yaml"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            _LLM_CONFIG_CACHE = data.get("llm", {})
        else:
            _LLM_CONFIG_CACHE = {}
    return _LLM_CONFIG_CACHE


def llm_provider_for(route_key: str) -> str:
    cfg = get_llm_config()
    routes = cfg.get("routes", {})
    return routes.get(route_key, cfg.get("default_provider", "gemini"))


def validate_llm_routes() -> None:
    """启动期检查：路由表中所有 provider 都在 providers 表里；skill 前缀可识别；
    placeholder endpoint（如 [Spike Pending]）显式 warning。

    在 app/main.py 启动事件中调用；validation 错误报 ValueError 决不允许启动；
    placeholder endpoint 只 warning 不阻断启动（让 stub 阶段能运行 + fallback Gemini）。
    """
    cfg = get_llm_config()
    providers = set(cfg.get("providers", {}).keys())
    known_skill_prefixes = {
        "app_profile", "behavior_profile", "credit_profile",
        "comprehensive", "product_advice", "ops_advice",
        "trace_analyzer", "data_acquisition", "orchestrator",
    }
    for route_key, provider_name in cfg.get("routes", {}).items():
        if "." not in route_key:
            raise ValueError(f"Invalid route_key shape: {route_key}")
        prefix = route_key.split(".", 1)[0]
        if prefix not in known_skill_prefixes:
            logger.warning(f"Unknown skill prefix: {prefix}")
        if provider_name not in providers:
            raise ValueError(
                f"route {route_key} -> {provider_name} not in providers"
            )

    # R7 P0-4 + R9 微调 1：显式识别 placeholder endpoint，区分“未声明 endpoint” vs “声明了但是 placeholder”
    # 未声明 → 该 provider 不依赖 endpoint（如 gemini 走 SDK / mock 不走网络）→ 跳过
    # 声明了但是 placeholder → 真的还没准备好 → warning
    PLACEHOLDER_ENDPOINTS = {"", "[Spike Pending]", "TBD", "TODO"}
    for name, p_cfg in cfg.get("providers", {}).items():
        ep = p_cfg.get("endpoint")
        if ep is None:
            continue  # 该 provider 不依赖 endpoint，跳过
        if ep.strip() in PLACEHOLDER_ENDPOINTS:
            logger.warning(
                "provider %s has placeholder endpoint=%r; will raise ProviderUnavailable on first call "
                "(Plan #03 Maestro Spike pending)", name, ep
            )
```

**新增 `app/main.py` startup 钩子**（最小 diff，不动业务逻辑）：

```python
# app/main.py — 在已有的 FastAPI app = FastAPI(...) 之后
@app.on_event("startup")
async def _validate_llm_routes_on_startup() -> None:
    """R7 P0-4: 启动期校验 llm routes + 显式 warning placeholder endpoint。"""
    from app.core.config import validate_llm_routes
    validate_llm_routes()
```

> ⏸ 实施前 grep 确认 `app/main.py` 现有 `app = FastAPI(...)` 行的精确位置和已有的 `@app.on_event("startup")` 钩子（如已有则在同一函数内追加 `validate_llm_routes()` 调用，避免重复注册多个 startup 事件）。

**验证命令**：

```powershell
python -c "from app.core.config import validate_llm_routes; validate_llm_routes(); print('routes ok')"
```

**期望输出**：`routes ok` + 一行 `WARNING ... provider claude_maestro has placeholder endpoint='[Spike Pending]'`。如果报 `ValueError`，表示 `config.yaml` 中 `routes` 出现未在 `providers` 中注册的 provider 名，需修复后才能进 Task 1.3。

### Task 1.3 — `ModelClient` 支持 route_key

**修改文件**：`app/core/model_client.py`

> **R8 P0-A 硬约束**：下面给的代码是**骨架**，不能整段覆盖 `generate_structured` 方法体。Plan #01 R5.1 Task 3.3 已落地了方案 C：**保留** `self._log_payload_ready(skill_name, structured_result)` 调用 + **仅追加** `self._record_usage(...)` + **不加** 新 `logger.info("ModelClient ok ...")`。下游 grafana log query / caplog 断言依赖 `"LLM payload ready"` 字串，覆盖即回归。
>
> **实施顺序**（必须严格遵守）：
>
> 1. 先 grep `app/core/model_client.py` 当前 `generate_structured` 完整方法体贴出来对照
> 2. 识别 4 个必须保留的 baseline 块：mock 短路、`self._log_payload_ready(...)` 调用行、`self._record_usage(...)` 调用行、except 路径（含 `_classify_model_error` + `degraded` 字典构造）
> 3. 只做 4 处最小修改：
>    - 签名末尾追加 `*, route_key: str | None = None`
>    - 函数体最开始（`if self.mode == "mock":` 之前）插入 R7 P2-1 注释里的 provider 解析块（下面骨架 line ~21-26）
>    - mock 分支 `logger.info` 加 `route=` 字段（仅加 1 个 kwarg，mock 返回字典 4 个 key 顺序不变）
>    - try 块内 `self._provider.generate_json(...)` 改为局部变量 `provider.generate_json(...)` 使用 route 解析后的 provider（同时保留后续 `_log_payload_ready` + `_record_usage` 两行）
> 4. **不动** `_log_payload_ready` 调用位、**不加** 新 `logger.info("ModelClient ok ...")`、**不动** except 路径任何一行
> 5. 落盘前贴 grep + 改后代码对照给用户看，用户 OK 才写盘
>
> 以下代码仅供参考骨架思路，**不是覆盖标准**。真实调整以上面 5 步为准。

**参考骨架**（含“R8 保留 baseline 错位”备注）：

```python
def generate_structured(
    self,
    skill_name: str,
    prompt: str,
    fallback_result: dict[str, Any],
    response_schema: dict[str, Any] | None = None,
    *,
    route_key: str | None = None,  # R8 新增参数
) -> dict[str, Any]:
    """If route_key provided, resolve provider from config.yaml.

    P2-1（性能）：Phase 1 不做 provider cache（实例化成本低，避免引入并发安全问题）；
    如延迟监控显示 P95 影响 > 5ms，Phase 3 加 LRU(maxsize=8) 缓存。
    """
    # baseline 快照 —— mock 短路（R8 仅仅加一个 route= kwarg，返回字典 4 key 不动）
    if self.mode == "mock":
        logger.info("ModelClient mock mode for skill=%s route=%s", skill_name, route_key)  # R8: + route=%s
        return {
            "status": "ok",
            "structured_result": fallback_result,
            "model_name": self.model_name,
            "prompt_preview": prompt[:200],
        }

    # baseline try 快照 —— R8 仅代码 generate_json 调用从 self._provider 改为局部 provider；_log_payload_ready / _record_usage 两行不动
    # R9 微调 3（实施期发现）：provider 解析块必须在 try 内。如果放在 try 之外，
    # vertex 模式下 build_provider_by_name("claude_maestro") 实例化 ClaudeMaestroProvider 因 endpoint=[Spike Pending]
    # 招 ProviderUnavailable 会绕过 ModelClient 既有 except 路径直接冒泡到 explainer/skill，
    # 破坏 SkillRegistry → UserAnalysisResult schema 校验。修复后 ProviderUnavailable 走标准 fallback degraded path。
    try:
        structured_result = provider.generate_json(  # R8: self._provider → provider
            prompt,
            response_schema=response_schema,
        )
        self._log_payload_ready(skill_name, structured_result)  # baseline 保留——grafana / caplog 依赖 "LLM payload ready" 字串
        # R5 (Plan #01 Phase 3 Task 3.3): record token usage on success path only
        # (mock / except paths do not call to avoid polluting per-session budget).
        # Plan #03 Phase 2 budget module reads self.last_token_usage["total"].
        self._record_usage(prompt, json.dumps(structured_result, ensure_ascii=False))  # baseline 保留
        return {
            "status": "ok",
            "structured_result": structured_result,
            "model_name": self.model_name,
            "prompt_preview": prompt[:200],
        }
    except Exception as exc:  # baseline except 路径全部不动
        # 完全保留 baseline：logger.warning + degraded 字典构造 + _classify_model_error
        # R8 不加 route= 字段到 except 日志，避免 caplog 断言回归
        ...  # 原面的 except 代码原样不动
```

> 上面 except 块的 `...` 意思是“baseline 原代码原样保留”，不是占位符。实施时从 grep 拿到 baseline except 完整代码后原样保留。

**验证命令**（Task 1.3 落盘后、进 Task 1.4 之前）：

```powershell
# 1. mock 短路零回归
python -m pytest tests/test_model_client_facade.py tests/test_model_client_repair.py tests/test_model_client_unescaped_newlines.py -v
# 期望：12 passed（2 facade + 6 repair + 4 unescaped——与 Plan #01 Phase 2 末态一致）

# 2. 确认 _log_payload_ready 调用还在
Select-String -Path "app/core/model_client.py" -Pattern "_log_payload_ready\(" -Context 0,1
# 期望：generate_structured 函数体内还能 grep 到 self._log_payload_ready(skill_name, structured_result) 调用行
```

任一项偏离→ 立刻停下贴输出 + grep 问用户。

**新建文件**：`app/core/providers/factory.py`

> R4 P2-1（实施顺序提示）：本 Task 1.3 创建的 `factory.py` 内 import 了 `ClaudeMaestroProvider`——该文件在 **Task 1.4** 才创建。请先跳到 Task 1.4 创建 stub provider，再回到 Task 1.3 创建 factory.py，避免 ImportError。Phase 1 commit 时两个文件都齐全，单测能跑通。

> P2-2（_record_usage 调用点）：上面改造后的 `generate_structured` 必须在 try block 成功路径末尾调用 `self._record_usage(prompt, json.dumps(structured_result, ensure_ascii=False))`（已在上面代码块 line ~38 体现）。mock 模式 / except 路径**不调**——避免污染 `last_token_usage`；Plan #03 Phase 2 budget 模块依赖该字段准确性。

```python
"""Build providers by name from config.yaml."""

from __future__ import annotations

from app.core.providers.base import LLMProvider
from app.core.providers.mock_provider import MockProvider
from app.core.providers.gemini_provider import GeminiProvider


def build_provider_by_name(name: str) -> LLMProvider:
    if name == "mock":
        return MockProvider()
    if name == "gemini":
        from app.core.config import settings
        # R4 P2-2：不硬编码 mode，跟 settings.model_mode 走（vertex/gemini/vertexai 任选）
        m = settings.model_mode
        if m not in {"gemini", "vertex", "vertexai", "gemini-vertex"}:
            m = "vertex"
        return GeminiProvider(mode=m)
    if name == "claude_maestro":
        # Phase 1 stub — Provider 待 Plan #03 Spike 后实装
        from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
        return ClaudeMaestroProvider()
    raise ValueError(f"Unknown provider name: {name}")
```

### Task 1.4 — `ClaudeMaestroProvider` 骨架（Spike Pending 状态）

**新建文件**：`app/core/providers/claude_maestro_provider.py`

```python
"""Claude Opus 4.7 via Agent Maestro — Phase 1 stub awaits Plan #03 Spike."""

from __future__ import annotations

from typing import Any, Iterator

from app.core.providers.base import LLMProvider, ProviderCapability, ProviderUnavailable


class ClaudeMaestroProvider(LLMProvider):
    """Stub: real impl wired after Maestro Spike (Plan #03 Phase 0 Task 0.2)."""

    @property
    def provider_name(self) -> str:
        return "claude_maestro"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=True,
            supports_json_mode=True,
            max_context_tokens=1_000_000,  # 10x tier default
            supports_tools=True,
        )

    def generate_json(self, prompt, response_schema=None, max_output_tokens=None):
        raise ProviderUnavailable(
            "ClaudeMaestroProvider awaits Maestro Spike completion [Spike Pending]"
        )

    def generate_text(self, prompt, max_output_tokens=None):
        raise ProviderUnavailable("ClaudeMaestroProvider awaits Maestro Spike [Spike Pending]")

    def stream(self, prompt: str) -> Iterator[str]:
        raise ProviderUnavailable("ClaudeMaestroProvider awaits Maestro Spike [Spike Pending]")

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
```

### Task 1.5 — 8 个 explainer 调用点接入 route_key（**机械追加规则，不写 7 段精确 diff**）

**关键约束**：本 Phase 仅引入 `route_key` 参数；所有调用点都传 `route_key="<x>"`，但**不实际切到 Claude**——`ClaudeMaestroProvider` Phase 1 还是 stub，会抛 `ProviderUnavailable`，自动 fallback 到 Gemini（依赖 Plan #01 Task 3.1 的 `fallback_chain`）。

**改造规则**（适用于全部 8 个调用点，**不依赖类名 / 方法名 / schema 来源**）：

1. 在该文件中找到目标 `self.model_client.generate_structured(` 调用点（用 `skill_name=` 字符串精确定位）
2. 在该调用的**最后一个参数（一般是 `response_schema=...`）的逗号后追加一行**：
   ```python
       route_key="<对应路由 key>",
   ```
3. **不动该函数的任何其他代码**——不动 `__init__`、不动 `explain` 签名、不动 `_build_*_payload()` / `_build_*_response_schema()` 方法名

**8 个调用点 → route_key 映射表**（来自顶部 Codebase Baseline 表，Phase 0.5 已校对）：

| # | 文件 | Line | skill_name | 追加的 route_key |
|---|---|---|---|---|
| 1 | `app/runtime_skills/app_profile/explainer.py` | L55 | `"app_profile"` | `"app_profile.explainer"` |
| 2 | `app/runtime_skills/behavior_profile/explainer.py` | L129 | `"behavior_profile_summary"` | `"behavior_profile.explainer"` |
| 3 | `app/runtime_skills/behavior_profile/explainer.py` | **L142** | `"behavior_timeline_summary"` | **`"behavior_profile.timeline"`** ← R7 P0-2 新增 |
| 4 | `app/runtime_skills/credit_profile/explainer.py` | L42 | `"credit_profile"` | `"credit_profile.explainer"` |
| 5 | `app/runtime_skills/comprehensive/explainer.py` | L46 | `"comprehensive_profile"` | `"comprehensive.explainer"` |
| 6 | `app/runtime_skills/product_advice/explainer.py` | L42 | `"product_advice"` | `"product_advice.explainer"` |
| 7 | `app/runtime_skills/ops_advice/explainer.py` | L42 | `"ops_advice"` | `"ops_advice.explainer"` |
| 8 | `app/runtime_skills/trace_analyzer/explainer.py` | L51 | `"trace_analyzer"` | `"trace_analyzer.explainer"` |

> Line 号来自 Phase 0.5 grep 输出，仅作定位提示——**实际定位用 `skill_name=` 字符串匹配**，因为代码可能已变。

**示例 diff（以 #1 `app_profile/explainer.py` 为例，其他 7 处机械同构）**：

```diff
         model_result = self.model_client.generate_structured(
             skill_name="app_profile",
             prompt=prompt,
             fallback_result=self._build_fallback_payload(),
             response_schema=self._build_llm_response_schema(),
+            route_key="app_profile.explainer",
         )
```

**示例 diff（以 #3 `behavior_profile/explainer.py` L142 timeline 为例，证明双路都要改）**：

```diff
         return self.model_client.generate_structured(
             skill_name="behavior_timeline_summary",
             prompt=prompt,
             fallback_result=self._build_timeline_fallback_payload(),
             response_schema=self._build_timeline_response_schema(),
+            route_key="behavior_profile.timeline",
         )
```

**8 处全部按此机械追加。** 不需要写 8 段精确 oldString—— Plan #02 R6 audit 已证明：精确 oldString 反而 0 命中，因为 7 个文件的 `_build_*` 方法名 / 字段名 / explain 签名各异，凭印象写一定错。

**实施顺序建议**：先改 #1 app_profile（最简单），跑 mock 模式回归（`pytest tests/test_app_profile_*.py -v`）确认零回归，再批量改余下 7 处。

**Task 1.5 验证**：

```powershell
# 应该精确找到 8 行
Get-ChildItem app/runtime_skills -Filter "explainer.py" -Recurse |
    Select-String -Pattern 'route_key=' |
    ForEach-Object { "$($_.Filename):L$($_.LineNumber): $($_.Line.Trim())" }
```

**期望**：8 行输出，对应表格 8 个调用点。**不能多 / 不能少**——多了说明动了不该动的调用，少了说明漏改。

### Task 1.6 — mock 模式回归测试

**验证命令（R9 微调 2：原写 \$env:MODEL_MODE = "mock" + 全量 pytest有设计冲突，改为 vertex 全量 + mock deselect facade test sanity）**：

```powershell
# 主验证：vertex 模式全量回归（与 Phase 0 baseline 同环境对比）
Remove-Item Env:MODEL_MODE -ErrorAction SilentlyContinue
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v

# 补充：mock 模式 sanity（deselect facade test——该测试在 mock 短路下无法验证注入 provider）
$env:MODEL_MODE = "mock"
python -m pytest tests/ -q --deselect tests/test_model_client_facade.py::test_model_client_accepts_injected_provider 2>&1 | tail -5
Remove-Item Env:MODEL_MODE
```

**期望（R8 P1-A 锁定）**：
- 主验证（vertex）：`tests/` **282 passed** + `data_acquisition_agent/tests/` **163 passed (1 skipped)**
- 补充（mock）：`tests/` **281 passed, 1 deselected** ——证明 "mock 路径绕过 routes 零回归" 核心断言
mock 模式直接走 `MockProvider`，绕过 routes，零回归。本 Phase 1 不新增测试文件。

### Task 1.7 — Phase 1 commit

```powershell
# R8 P1-C: 禁用 `git add -A`——显式 add 清单，避免误带外部 untracked。
# 下面 8 个 explainer.py 路径以 Phase 0.5 Task 0.5.1 grep 实际命中为准；
# 如 grep 发现文件布局与下面不一致，按 grep 调整 add 清单后再 commit。
git add config.yaml `
        app/core/config.py `
        app/core/model_client.py `
        app/core/providers/factory.py `
        app/core/providers/claude_maestro_provider.py `
        app/main.py `
        app/runtime_skills/app_profile/explainer.py `
        app/runtime_skills/behavior_profile/explainer.py `
        app/runtime_skills/credit_profile/explainer.py `
        app/runtime_skills/comprehensive/explainer.py `
        app/runtime_skills/product_advice/explainer.py `
        app/runtime_skills/ops_advice/explainer.py `
        app/runtime_skills/trace_analyzer/explainer.py
git diff --cached --stat
git status
# diff stat 应该准确递 13-14 个文件（8 explainer + config.yaml/config.py/model_client.py/factory.py/claude_maestro_provider.py/main.py）
# `git status` 里 Changes not staged for commit 应为空；Untracked 列表不应被带入。
# 确认后才 commit。
git commit -m "feat(llm): config.yaml llm.providers/routes (8 routes incl behavior.timeline) + ModelClient route_key + 8 explainer wiring + claude_maestro stub awaits Spike"
git push origin main
git log -1 --oneline
```

---

## Phase 2 — Claude/Gemini 输出风格适配 + JSON repair 兼容

### Task 2.1 — 在 `ClaudeMaestroProvider` 实装 JSON repair 兼容层

> ⚠ **R7 P1-4 协议假设警示**：本 Task 给出的 `_post` / `generate_json` 实装基于对 Maestro response shape 的**纸面假设**（`content[].type=='tool_use'.input` / `content[].type=='text'.text`）。
>
> Plan #03 Phase 0 Task 0.2 Maestro Spike 完成后，**必须按真实 response shape 重新审视本 Task 全部代码**：
> - 字段名差异（如 `content` 改 `messages` / `data`）→ 改 `_post` 解析 + `generate_json` 循环
> - 结构差异（如返回数组改返回单 object）→ 改 `generate_json` 循环
> - 错误码差异（如 401/403 不归 transport 错误）→ 改 `_post` status 检查
> - 鉴权 header 差异（如 `X-API-Key` vs `Authorization: Bearer`）→ 改 `_post` headers
>
> Spike 完成前，本 Task 代码可作为骨架先创建文件、跑契约测试（mock `_post`），**不接入真实 Maestro**。**不要在 Spike 完成前以为本 Task 给的代码就是最终形态。**

**前置条件**：本 Task 假设 Plan #03 Phase 0 Task 0.2 的 Maestro Spike **已通过**，端点 URL / 认证 / 协议字段已回填到 `config.yaml`。

如果 Spike 失败（C-1 失败路径），按 PLANNING.md 已知约束：本 Task 改为"explainer 保持 Gemini，Provider 抽象层落地但路由表暂不切 Claude"——即跳过 Task 2.1-2.3，直接进 Phase 3 的回归验证。

**修改文件**：`app/core/providers/claude_maestro_provider.py`

**完整实装**（替换 Phase 1 stub 的三个方法 + 补全初始化）：

```python
"""Claude Opus 4.7 via Agent Maestro — production impl."""

from __future__ import annotations

import os
from typing import Any, Iterator

import httpx

from app.core.config import get_llm_config
from app.core.logger import get_logger
from app.core.providers.base import LLMProvider, ProviderCapability, ProviderUnavailable
from app.core.providers.json_repair import parse_json_text, RETRYABLE_PARSE_HINTS

logger = get_logger(__name__)

_REQUEST_TIMEOUT_SECONDS = 30


class ClaudeMaestroProvider(LLMProvider):
    """Real impl: HTTP POST -> Maestro endpoint, parse tool_use payload."""

    def __init__(self) -> None:
        cfg = get_llm_config().get("providers", {}).get("claude_maestro", {})
        self.endpoint = cfg.get("endpoint", "")
        self.model = cfg.get("model", "claude-opus-4.7")
        self.tier = cfg.get("tier", "10x")
        self.token = os.environ.get("MAESTRO_TOKEN", "")
        if not self.endpoint or self.endpoint == "[Spike Pending]":
            raise ProviderUnavailable(
                "ClaudeMaestroProvider: endpoint missing or [Spike Pending]; complete Plan #03 Phase 0 Spike first"
            )
        if not self.token:
            raise ProviderUnavailable(
                "ClaudeMaestroProvider: MAESTRO_TOKEN env var missing"
            )

    @property
    def provider_name(self) -> str:
        return "claude_maestro"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=True,
            supports_json_mode=True,
            max_context_tokens=1_000_000,
            supports_tools=True,
        )

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            with httpx.Client(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                resp = client.post(
                    self.endpoint,
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            raise ProviderUnavailable(f"maestro transport: {exc}") from exc
        if resp.status_code >= 500 or resp.status_code == 408:
            raise ProviderUnavailable(f"maestro {resp.status_code}: {resp.text[:200]}")
        if resp.status_code >= 400:
            raise ValueError(f"maestro client error {resp.status_code}: {resp.text[:200]}")
        return resp.json()

    def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "tier": self.tier,
            "messages": [{"role": "user", "content": prompt}],
            "tool_choice": {"type": "json_object"},
        }
        if max_output_tokens:
            payload["max_tokens"] = max_output_tokens
        if response_schema:
            payload["response_schema"] = response_schema

        body = self._post(payload)
        # Maestro 会返 content[].type == 'tool_use' 的项，input 字段即结构化输出
        for item in body.get("content", []):
            if item.get("type") == "tool_use" and isinstance(item.get("input"), dict):
                logger.info("maestro tool_use ok model=%s", self.model)
                return item["input"]
        # 退回：文本字段走 parse_json_text repair
        text = ""
        for item in body.get("content", []):
            if item.get("type") == "text" and item.get("text"):
                text += str(item["text"])
        if not text:
            raise ValueError("Model response candidates were empty")
        try:
            return parse_json_text(text)
        except Exception as exc:
            if any(h in str(exc) for h in RETRYABLE_PARSE_HINTS):
                # 一次 retry，追加 strict JSON 提示
                payload["messages"][0]["content"] = (
                    prompt + "\n\nRespond with ONLY a valid JSON object. No prose."
                )
                body2 = self._post(payload)
                text2 = "".join(
                    str(i.get("text", "")) for i in body2.get("content", []) if i.get("type") == "text"
                )
                return parse_json_text(text2)
            raise

    def generate_text(
        self,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str:
        payload = {
            "model": self.model,
            "tier": self.tier,
            "messages": [{"role": "user", "content": prompt}],
        }
        if max_output_tokens:
            payload["max_tokens"] = max_output_tokens
        body = self._post(payload)
        return "".join(
            str(i.get("text", "")) for i in body.get("content", []) if i.get("type") == "text"
        )

    def stream(self, prompt: str) -> Iterator[str]:
        # V1 简化：不使用原生 SSE，一次调用后 yield 整个文本。Plan #03 SSE 上层自己拆分。
        yield self.generate_text(prompt)

    def count_tokens(self, text: str) -> int:
        # Maestro 暂未提供 count_tokens API；naive 估算，后续可接入 anthropic tokenizer。
        return max(1, len(text) // 4)
```

> `httpx` 在 `requirements.txt` 中已存在（FastAPI 间接依赖）。`MAESTRO_TOKEN` 从环境变量读，不进 `config.yaml` 以免凭据泄露；baseline 按 CLAUDE.md SQL/凭据安全约束。

### Task 2.2 — 确认 `json_repair.py` 已存在（Plan #01 Phase 2 已创建）

**R4 P0-A 修复**：本 Task 不再“新建” `app/core/providers/json_repair.py`——该文件在 Plan #01 Task 2.2 迁 `GeminiProvider` 时已同步抽出并创建。本 Task 仅做“存在性检查 + 兼容兑现”。

**前置检查**：

```powershell
Test-Path "app/core/providers/json_repair.py"
```

- 存在（Plan #01 [complete] 后必然存在）→ **跳过本 Task**，直接进 Task 2.3。
- 不存在（异常情况，可能 Plan #01 实施期遗漏）→ 按下面代码块补齐，内容与 Plan #01 Task 2.2 同步。

**兑现代码**（与 Plan #01 同步的兑现参考）：

```python
"""Provider-agnostic JSON repair utilities."""

from __future__ import annotations

import json
import re
from typing import Any

RETRYABLE_PARSE_HINTS = (
    "Model response candidates were empty",
    "Model response did not include text content",
    "Unterminated string",
    "Invalid \\u",
    "Invalid control character",
    "Expecting value",
    "Expecting ',' delimiter",
    "Expecting ':' delimiter",
    "Expecting property name enclosed in double quotes",
    "Extra data",
    "JSONDecodeError",
    "json_parse",
    "json_repair_failed",
)


def parse_json_text(text: str) -> dict[str, Any]:
    """Try to parse JSON; pre-escape bare newlines on first failure."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        cleaned = re.sub(r"(?<!\\)\n", "\\\\n", text)
        return json.loads(cleaned)


def is_retryable(error_message: str) -> bool:
    return any(hint in error_message for hint in RETRYABLE_PARSE_HINTS)
```

### Task 2.3 — 测试 Claude Provider JSON repair

**新建文件**：`tests/test_claude_provider_jsonrepair.py`

**完整代码**：

```python
"""Claude Maestro Provider 契约测试。"""

from __future__ import annotations

import pytest

from app.core.providers.base import ProviderUnavailable


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("MAESTRO_TOKEN", "test-token-stub")
    # R9 微调 5（实施期发现）：双层 patch——同时 patch “本地引用”和“源”。
    # claude_maestro_provider.py 顶部用 from app.core.config import get_llm_config 已绑函数到本地
    # 命名空间，只 patch 源不 patch 本地引用会在全量跑时 cache 被填充后取不到 fake config。
    fake_cfg = {
        "providers": {
            "claude_maestro": {
                "endpoint": "https://maestro.test/v1/chat",
                "model": "claude-opus-4.7",
                "tier": "10x",
            }
        }
    }
    monkeypatch.setattr("app.core.config.get_llm_config", lambda: fake_cfg)
    monkeypatch.setattr(
        "app.core.providers.claude_maestro_provider.get_llm_config",
        lambda: fake_cfg,
    )
    from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
    return ClaudeMaestroProvider()


class _FakeResponse:
    def __init__(self, status_code: int, body: dict | str):
        self.status_code = status_code
        self._body = body
        self.text = body if isinstance(body, str) else ""

    def json(self):
        return self._body


def test_claude_provider_happy_path(provider, monkeypatch):
    captured = {}

    def _fake_post(self, payload):
        captured["payload"] = payload
        return {"content": [{"type": "tool_use", "input": {"score": 0.8, "label": "low_risk"}}]}

    monkeypatch.setattr(provider, "_post", _fake_post.__get__(provider))
    out = provider.generate_json("hello prompt")
    assert out == {"score": 0.8, "label": "low_risk"}
    assert captured["payload"]["model"] == "claude-opus-4.7"


def test_claude_provider_repair_unescaped_newline(provider, monkeypatch):
    raw = '{"text":"line1\nline2"}'  # bare newline inside string

    def _fake_post(self, payload):
        return {"content": [{"type": "text", "text": raw}]}

    monkeypatch.setattr(provider, "_post", _fake_post.__get__(provider))
    out = provider.generate_json("p")
    assert out == {"text": "line1\nline2"}


def test_claude_provider_truncated_triggers_retry(provider, monkeypatch):
    calls = {"n": 0}

    def _fake_post(self, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"content": [{"type": "text", "text": '{"a": "unter'}]}  # truncated
        return {"content": [{"type": "text", "text": '{"a": "ok"}'}]}

    monkeypatch.setattr(provider, "_post", _fake_post.__get__(provider))
    out = provider.generate_json("p")
    assert out == {"a": "ok"}
    assert calls["n"] == 2


def test_claude_provider_endpoint_unreachable_raises_unavailable(provider, monkeypatch):
    # R9 微调 4（实施期发现）：原 Plan 改 patch _post 本身会绕过 _post 内部 try/except
    # (httpx.ConnectError → ProviderUnavailable) 转换逻辑。改为 patch httpx.Client（_post
    # 调用的下一层），让真正的 _post try/except 接住 ConnectError 并转换。语义不变，
    # 更准确测试 transport error 处理逻辑。
    import httpx

    class _BoomClient:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def post(self, *a, **kw):
            raise httpx.ConnectError("dns failure")

    monkeypatch.setattr(
        "app.core.providers.claude_maestro_provider.httpx.Client",
        _BoomClient,
    )
    with pytest.raises(ProviderUnavailable):
        provider.generate_json("p")


def test_claude_provider_count_tokens_returns_positive(provider):
    assert provider.count_tokens("hello world") >= 1
```

**验证命令**：

```powershell
python -m pytest tests/test_claude_provider_jsonrepair.py -v
```

**期望**：5 tests passed。

### Task 2.4 — Phase 2 commit

```powershell
# R8 P1-C: 禁用 `git add -A`——显式 add 清单。
# Plan #01 落地后 json_repair.py 已存在，Task 2.2 跳过创建。
# 本 Phase 2 只动 2 个文件：claude_maestro_provider.py（stub → 真实实装） + 新建测试。
git add app/core/providers/claude_maestro_provider.py `
        tests/test_claude_provider_jsonrepair.py
git diff --cached --stat
git status
# diff stat 应为准确 2 个文件。
# `git status` 里 Changes not staged for commit 应为空。
git commit -m "feat(claude): JSON repair tooling shared with Gemini + Claude tool_use parsing"
git push origin main
git log -1 --oneline
```

---

## Phase 3 — 灰度 + 回归矩阵 + fallback 验证

### Task 3.1 — V1 简化：一次性切换（不做逐 Skill 灰度）

**Design Doc § 8.2 描述了灰度顺序**（app_profile → behavior_profile → ... → trace_analyzer），**但本 Plan V1 简化为一次性切换 + `git revert` 整体回滚**。

**理由**：
1. 真灰度需要 feature flag 或逐 route 改 `config.yaml` + 多次部署，本 V1 不引入这层基础设施
2. 用户偏好硬规则：每 Plan 最多 4 commits（baseline + Phase 1 + Phase 2 + Phase 3 [complete]）
3. 7 个 `git commit --allow-empty` 没有真实代码差异，`git revert` 撤销的是空气，不能实现真灰度
4. 回滚路径单一清晰：发现回归 → `git revert <Phase 3 commit>` 整体回退到 Phase 2 状态（Phase 1 已经是 routes 全配 + stub 阶段，回到 Phase 2 即"Provider 实装完但仍走 stub 失败 → fallback Gemini"）

**真灰度延后到 V2**：当 Claude 调用稳定 P95 ≤ 8s 后，V2 引入 LaunchDarkly 或 `config.yaml` 热加载做真灰度。

**Phase 3 操作清单**：
- Phase 2 Task 2.1 已经把 `ClaudeMaestroProvider` 从 stub 替换为真实实装
- Phase 1 已经把 8 个 routes（含 behavior.timeline）全配到 `claude_maestro`（但在 Phase 1 stub 阶段走 fallback Gemini）
- 进入 Phase 3 = Provider + 路由都已就绪，自动开始走 Claude
- Task 3.3 跑 fallback 验证 + Task 3.4 跑全量回归 + Task 3.5 一次性 `[complete]` commit
- **不产生 `--allow-empty` commit**

### Task 3.2 — 全部 8 个调用点已切换 + 各自单测全绿

**说明**：本 Task 名为"切换"，实际不再有"切换"动作——Phase 1 Task 1.5 已经把 8 个调用点全部接入 `route_key`；Phase 2 Task 2.1 已经把 `ClaudeMaestroProvider` 从 stub 替换为真实实装。**Phase 3 进入时，切换已经发生**，本 Task 只验证全量测试零回归。

**4 commit 上限的合理性**（保留 R4 修复理由）：
- 用户偏好硬规则：每 Plan 最多 4 commits，不要每 Task 一个
- 7 个 `git commit --allow-empty` 没有真实代码差异，`git revert` 撤销的是空气，不能实现真灰度
- 真灰度需要 feature flag 或逐 route 改 config.yaml，本 V1 不做这层
- 如果切换后发现回归→ `git revert` Phase 3 的单 commit 整体回退

**验证命令**：

```powershell
# 实施前 grep 确认 8 处 route_key 都在
Get-ChildItem app/runtime_skills -Filter "explainer.py" -Recurse |
    Select-String -Pattern 'route_key=' |
    ForEach-Object { "$($_.Filename):L$($_.LineNumber)" }
# 期望 8 行

# 然后跑全量
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v
```

**期望（R8 P1-A 锁定）**：
- `tests/` → **287 passed**（282 baseline + 5 新增 Claude provider contract 测试）
- `data_acquisition_agent/tests/` → **163 passed, 1 skipped**
- 8 处 `route_key=` grep 输出精确为位（Phase 1 Task 1.5 已接入，Phase 2/3 不增不减）

> **R7 P0-3 修订理由**：原 Task 3.3 试图通过 `AppProfileExplainer()` 零参构造 + `explainer.explain(features={}, decision={...})` dict 入参做 e2e fallback 验证，但**两条假设全错**：
> - 真实类名 `AppExplainer`（无 `Profile` 后缀）
> - 真实 `__init__(self, model_client: ModelClient, prompt_path: Path)` —— **必传 2 个参数，无零参构造**
> - 真实 `explain(self, uid, feature_bundle, decision_result, prompt_payload, context)` —— 5 个 kwarg，不是 `features=...`
>
> 验证目标是"fallback chain 工作正常"——下沉一层在 `ModelClient` 层直测，不依赖 explainer 复杂签名，等价且更可靠。

**新建文件**：`tests/test_explainer_fallback_e2e.py`

**完整代码**：

```python
"""R7 Task 3.3 — Claude 不可达时 ModelClient 自动 fallback 到 Gemini 验证。

验证策略：在 ModelClient 层直接验证（不绕 explainer 复杂构造签名）。
等价性：所有 explainer 内部都是调 ModelClient.generate_structured(...)，
       ModelClient 层 fallback 工作 = explainer 层 fallback 工作。
"""

from __future__ import annotations

import logging

import pytest


def test_model_client_falls_back_to_gemini_when_claude_unavailable(monkeypatch, caplog):
    """vertex 模式 + Claude endpoint 已就绪 + Claude 调用失败 → 自动走 Gemini。"""
    from app.core.config import settings
    from app.core.model_client import ModelClient
    from app.core.providers.base import ProviderUnavailable
    from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
    from app.core.providers.gemini_provider import GeminiProvider

    # 1) 强制进 vertex 路径（让 _build_default_provider 走 fallback_chain(claude → gemini)）
    monkeypatch.setattr(settings, "model_mode", "vertex", raising=False)

    # 2) 让 Claude endpoint 看起来已就绪（绕开 ClaudeMaestroProvider.__init__ 的 endpoint 检查）
    # R9 微调 6（实施期发现，与微调 5 同根因）：双层 patch 避免 from-import 本地命名空间问题
    fake_cfg = {
        "providers": {
            "claude_maestro": {
                "endpoint": "https://maestro.test/v1/chat",  # 非 [Spike Pending]
                "model": "claude-opus-4.7",
                "tier": "10x",
            }
        },
        "routes": {"app_profile.explainer": "claude_maestro"},
        "default_provider": "gemini",
    }
    monkeypatch.setattr("app.core.config.get_llm_config", lambda: fake_cfg)
    monkeypatch.setattr(
        "app.core.providers.claude_maestro_provider.get_llm_config",
        lambda: fake_cfg,
    )
    monkeypatch.setenv("MAESTRO_TOKEN", "test-token-stub")

    # 3) Claude 所有调用都抛 ProviderUnavailable
    def _raise_unavailable(*args, **kwargs):
        raise ProviderUnavailable("simulated maestro down")

    monkeypatch.setattr(ClaudeMaestroProvider, "generate_json", _raise_unavailable)

    # 4) Gemini 返回可用结构化结果
    monkeypatch.setattr(
        GeminiProvider,
        "generate_json",
        lambda self, p, response_schema=None, max_output_tokens=None: {
            "summary": "fallback ok",
            "score": 0.5,
        },
    )

    # 5) 调用 ModelClient（默认 vertex 模式 → fallback_chain(claude, gemini)）
    caplog.set_level(logging.WARNING)
    client = ModelClient()
    out = client.generate_structured(
        skill_name="app_profile",
        prompt="test prompt",
        fallback_result={"degraded": True},
        route_key="app_profile.explainer",
    )

    # 6) 断言 fallback 生效
    assert out["status"] == "ok", f"expected ok after fallback, got {out['status']}"
    assert out["structured_result"] == {"summary": "fallback ok", "score": 0.5}, \
        "structured_result should come from Gemini fallback, not Claude"
    # 应该看到 fallback 日志
    assert "provider_fallback" in caplog.text.lower() or "fallback" in caplog.text.lower(), \
        f"expected provider_fallback log, got: {caplog.text}"


def test_model_client_no_fallback_when_claude_succeeds(monkeypatch):
    """Claude 调用成功 → 不触发 fallback，结果直接来自 Claude。"""
    from app.core.config import settings
    from app.core.model_client import ModelClient
    from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
    from app.core.providers.gemini_provider import GeminiProvider

    monkeypatch.setattr(settings, "model_mode", "vertex", raising=False)
    # R9 微调 6（同上）：双层 patch
    fake_cfg = {
        "providers": {
            "claude_maestro": {
                "endpoint": "https://maestro.test/v1/chat",
                "model": "claude-opus-4.7",
                "tier": "10x",
            }
        },
        "routes": {"app_profile.explainer": "claude_maestro"},
        "default_provider": "gemini",
    }
    monkeypatch.setattr("app.core.config.get_llm_config", lambda: fake_cfg)
    monkeypatch.setattr(
        "app.core.providers.claude_maestro_provider.get_llm_config",
        lambda: fake_cfg,
    )
    monkeypatch.setenv("MAESTRO_TOKEN", "test-token-stub")

    monkeypatch.setattr(
        ClaudeMaestroProvider,
        "generate_json",
        lambda self, p, response_schema=None, max_output_tokens=None: {
            "summary": "from claude",
            "score": 0.9,
        },
    )

    # Gemini 必须不被调用（如果调到说明 fallback 错误触发）
    def _gemini_must_not_be_called(*args, **kwargs):
        pytest.fail("Gemini should NOT be called when Claude succeeds")

    monkeypatch.setattr(GeminiProvider, "generate_json", _gemini_must_not_be_called)

    client = ModelClient()
    out = client.generate_structured(
        skill_name="app_profile",
        prompt="test prompt",
        fallback_result={"degraded": True},
        route_key="app_profile.explainer",
    )

    assert out["status"] == "ok"
    assert out["structured_result"] == {"summary": "from claude", "score": 0.9}
```

**验证命令**：

```powershell
python -m pytest tests/test_explainer_fallback_e2e.py -v
```

**期望**：2 tests passed。

> 该测试需 `fallback_chain` helper 在 `app/core/providers/base.py` 存在，且 `_build_default_provider` 在 vertex 模式下包装 `fallback_chain(claude, gemini, on_fallback=lambda f, t, e: logger.warning("provider_fallback %s→%s: %s", f, t, e))` —— 这两点是 Plan #01 R5.1 Phase 3 落地的内容，本 Plan 直接复用。

### Task 3.4 — 全量回归

```powershell
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v
```

**期望（R8 P1-A 锁定）**：
- `tests/` → **289 passed**（282 baseline + 5 Claude provider contract + 2 fallback e2e）
- `data_acquisition_agent/tests/` → **163 passed, 1 skipped**
- 任一偏离→ 立刻停下。`tests/` 出现非新增测试 FAIL → 可能是 Task 1.3 P0-A 硬约束被违反（`_log_payload_ready` 被覆盖），首先检查那里。

### Task 3.5 — Phase 3 commit `[complete]`

```powershell
# R8 P1-C: 禁用 `git add -A`——显式 add 清单。
# 本 Phase 3 只动 1 个文件：fallback e2e 测试。
git add tests/test_explainer_fallback_e2e.py
git diff --cached --stat
git status
# diff stat 应为准确 1 个文件。
git commit -m "test: explainer fallback chain verified [complete] explainer-trace-claude"
git push origin main
git log -1 --oneline
```

### 收尾 — TASK.md 标记 [x]

```powershell
# R8 P1-C: TASK.md 单独 commit，不计入本 Plan 的 4 commit 上限（属于交付收尾，类比 Plan #01 的 61f3051）。
# 在 TASK.md “当前进行中的功能”段把对应行从 [ ] 改为 [x] 并补 [complete] <Phase 3 commit hash> 2026-05-02。
git add TASK.md
git diff --cached --stat
git commit -m "chore: mark plan-02 [complete] in TASK.md"
git push origin main
git log -3 --oneline
```

---

## 完成标志

- 4 commits（baseline + Phase 1 + Phase 2 + Phase 3 [complete]）
- **8 个调用点**都通过 `route_key` 接入 routes（含 BehaviorExplainer L142 timeline 第二路）
- mock 模式零回归（282 passed + 163 passed, 1 skipped——R8 P1-A 锁定起点；Phase 3 末增加到 289 / 163）
- vertex 模式下 Claude 不可达自动 fallback Gemini 验证通过（`tests/test_explainer_fallback_e2e.py` 2 tests passed）
- `validate_llm_routes` 启动期识别 `[Spike Pending]` placeholder endpoint 并 warning（不阻断启动）
- `data_acquisition_agent/` 任何文件未动
- `grep -rn 'route_key=' app/runtime_skills/` 精确返回 8 行

**Step 8 后续（不计入本 Plan 的 4 commit 限制）**：本 Plan 全部 `[complete]` 后，用 `ai-code-review` skill 做白盒审计，产出 `docs/reviews/explainer-trace-claude-audit.md`（10 板块审计报告）；用 `module-dev-summary` skill 生成 `docs/reviews/explainer-trace-claude-summary.md`（面试导向技术总结）。
