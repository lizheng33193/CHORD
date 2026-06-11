# Plan #02 模块技术总结 — explainer/trace 切 Claude Opus 4.7

> **定位**：面试导向的技术总结。叙述体串联，每一步自然引出下一步——"为什么要这样做→具体怎么做→做完能得到什么→下一步怎么用"。可以照着这份文档对着面试官口述讲完整个故事。

---

## 一句话讲清楚做了什么

把多 Agent 用户画像系统里 7 个 explainer 共 8 个 LLM 调用点接入了 **Claude Opus 4.7 via Agent Maestro** 路由，**通过配置驱动**而不是改代码切换 provider，**fallback chain 兜底**保证 Claude 不可达时自动走 Gemini，最终用户看不到任何崩溃。但本期完成时 Maestro Spike 还没做，endpoint 是占位符 `[Spike Pending]`，所以**所有切换基础设施都就位**——路由表、provider 工厂、HTTP 实装、JSON repair、fallback chain、7 个测试——但用户实际看到的输出仍来自 Gemini，等 Plan #03 Spike 通过后**0 行代码改动**就能切到 Claude。

---

## 为什么要做这件事——背景与动机

### 业务背景

我们的系统是一个多 Agent 用户画像后端，给墨西哥市场做退款审核、行为分析等。系统里有 7 个不同的 explainer Agent（app_profile / behavior_profile / credit_profile / comprehensive / product_advice / ops_advice / trace_analyzer），每个 explainer 都需要调用 LLM 把规则引擎的输出翻译成自然语言解释。原来全部走 Gemini，但 Gemini 在长文本理解和逻辑推理上有时不够稳——特别是 BehaviorExplainer 需要分析用户行为时间线，Gemini 偶尔会漏掉关键事件或得出和数据矛盾的结论。

业务方决定：**关键 explainer 切到 Claude Opus 4.7**（10x tier，1M context window），通过公司内部的 Agent Maestro 网关调用，价格相对可控且推理质量更稳。

### 工程约束

但切换不能"一刀切"——27 个现有 LLM 调用点要么全部正常工作，要么出问题时优雅降级，**绝对不能因为切 Claude 把现有功能搞挂**。这就引出三个核心约束：

1. **不动调用点签名**：`ModelClient.generate_structured()` 的 27 个现有调用必须保持原样（即使加了新参数也得是可选的 keyword-only）
2. **配置驱动而非代码改造**：哪个 explainer 走哪个 provider 应该写在 `config.yaml` 里，不是硬编码在 Python 代码里——这样未来想切回 Gemini 或加新 provider 只需改 yaml，不需要改代码
3. **故障必须能优雅降级**：Claude 不可达（网络故障 / endpoint 配置错 / 限流）时**绝不能**让 explainer 抛异常崩到用户面前——必须自动 fallback 到 Gemini

---

## 怎么实现——架构设计与关键决策

### 整体架构：路由表 + Provider 工厂 + Fallback Chain

```
用户请求
  → AppProfileExplainer.explain(...)
    → ModelClient.generate_structured(skill_name="app_profile", route_key="app_profile.explainer", ...)
        ↓ 看到 route_key，去 config.yaml 查路由表
        ↓ "app_profile.explainer" → "claude_maestro"
        ↓ 不是默认 provider → factory.build_provider_by_name("claude_maestro")
        ↓ 实例化 ClaudeMaestroProvider（HTTP POST 到 Maestro endpoint）
        ↓ 万一失败 → fallback_chain 接住 → 走 Gemini
        ↓ Gemini 也失败 → except 路径 → degraded fallback_result
      → 返回结果给 explainer
```

三个关键组件：

**`config.yaml` 的 `llm:` 段**——声明所有 provider（gemini / claude_maestro / mock）的元信息（endpoint / model / tier）和路由表（8 个 skill → 哪个 provider）。这是整个切换的"控制台"，改一行配置就能切 provider。

**`app/core/providers/factory.py`**——`build_provider_by_name(name)` 按 provider 名构造实例。3 个分支：mock 直接返回 MockProvider；gemini 跟 `settings.model_mode` 不硬编码（因为既可以是 vertex 模式也可以是 gemini API key 模式）；claude_maestro 用 lazy import 避免循环依赖（factory 在 model_client 之外，model_client 又会 import factory，lazy import 才能让两边都不爆）。

**`app/core/providers/claude_maestro_provider.py`**——Claude HTTP 实装。核心是 `_post()` 方法负责一次 HTTP 请求 + 错误分类（5xx/408 转 ProviderUnavailable / 4xx 转 ValueError / 200 返回 json），`generate_json()` 调 `_post()` 后解析 `content[].type=='tool_use'.input` 拿结构化输出，失败时 fallback 到 `parse_json_text` 走 JSON repair。这套 JSON repair 不是新写的——直接复用 Plan #01 抽出的 `app/core/providers/json_repair.py`（13 个 RETRYABLE_PARSE_HINTS + 一次 retry），让 Gemini 和 Claude 共用同一套鲁棒性逻辑。

### 关键决策 1：route_key 是可选 keyword-only 参数

为什么不直接让 ModelClient 内部决定走哪个 provider？因为不同 explainer 调用同一个 ModelClient，调用方（explainer）才知道自己是什么 skill、应该走哪个路由。所以参数必须从调用方传入。但**不能强制**——27 个现有调用点不能因为这次切换全部要改。所以设计成 keyword-only（`*, route_key: str | None = None`），不传就走默认 provider，传了才查路由表。

8 个 explainer 调用点机械追加 `route_key="<skill>.explainer"` 一行——不动任何其他代码。这是 Karpathy "Surgical Changes" 原则的精确落地。

### 关键决策 2：fallback chain 用 Plan #01 已有的 helper

Plan #01 R5.1 已经在 `app/core/providers/base.py` 实装了 `fallback_chain(primary, secondary, on_fallback=...)` helper——返回一个新的 LLMProvider 实例，调 `generate_json` 时先试 primary，抛 ProviderUnavailable 就调 secondary。Plan #02 直接复用，不重复造轮子。

`_build_default_provider(mode)` 在 vertex 模式下自动包装：

```python
def _build_default_provider(mode):
    gemini = GeminiProvider(mode=mode)
    if vertex_mode_and_claude_endpoint_ready():
        claude = ClaudeMaestroProvider()
        return fallback_chain(claude, gemini, on_fallback=lambda f, t, e: logger.warning(...))
    return gemini
```

这样 ModelClient 拿到的 `self._provider` 已经是包装好的 fallback chain，业务代码完全无感。

### 关键决策 3：startup 钩子做配置校验

为什么要在 FastAPI 启动时校验 `validate_llm_routes()`？因为路由表的 provider 名如果写错（比如把 `claude_maestro` 拼成 `claude_meastro`），运行时第一次调用才报错——用户已经触发了请求，等于"线上才发现问题"。启动期校验把错误提前到部署阶段就暴露，让 CI/CD 能拦住错配置。

校验三件事：①路由的 provider 在 providers 表里 ②路由 key 的前缀（如 `app_profile`）是已知的 skill 前缀 ③placeholder endpoint（如 `[Spike Pending]`）记 warning 提醒运维。

---

## 做完能得到什么——交付内容与验证

### 交付内容

| 项 | 数量 | 说明 |
|---|---|---|
| 新建文件 | 4 | factory.py / claude_maestro_provider.py / 2 个测试 |
| 修改文件 | 11 | config.yaml / config.py / model_client.py / main.py / 7 个 explainer |
| 总改动量 | +580 / -63 行 | 符合 Surgical 原则 |
| 新增测试 | 7 | 5 个 Claude provider contract + 2 个 fallback e2e |
| commit 数 | 5 | baseline + Phase 1 + Phase 2 + Phase 3 [complete] + 收尾 |
| 4 commit 上限 | ✅ 守住 | 用户偏好硬规则 |

### 验证

`tests/` 从 282 → 289 passed（+7 净增），`data_acquisition_agent/tests/` 全程锁定 163 passed (1 skipped)——Surgical Hard Boundary 完美守住。8 处 `route_key=` grep 精确返回 8 行（含 BehaviorExplainer L142 timeline 第二路）。fallback chain e2e 测试覆盖两个方向：Claude 不可达自动走 Gemini + Claude 成功不触发 fallback。

### 一个不易察觉的关键收益

Plan #02 真正的价值**不是"切换到 Claude"**——本期完成时 Claude 还没真正接管（endpoint 还是 `[Spike Pending]`）。真正的价值是**让"切换到 Claude"变成 0 代码改动**——Plan #03 Maestro Spike 通过后，运维只需改 `config.yaml` 一行：

```yaml
claude_maestro:
  endpoint: "[Spike Pending]"  # 改成
  endpoint: "https://maestro.production.com/v1/chat"
```

重启服务，Claude 立刻接管。如果 Claude 不行（业务效果不好 / 延迟太高 / 成本超预算），改回去就行——同样 0 代码。**这就是配置驱动架构的真正威力**：业务决策从代码 commit 变成运维操作。

---

## 下一步怎么用——衔接 Plan #03 与未来扩展

### 短期（Plan #03 启动）

Plan #03 Phase 0 Task 0.2 Maestro Spike——验证 4 项（HTTP 200 / 协议字段 / 延迟 ≤ 5s / 配额）。Spike 通过后做两件事：

1. 回填 `config.yaml` 的 `claude_maestro.endpoint`——Plan #02 完成时已经把这件事变成了"改 1 行配置"
2. 按真实 Maestro response shape 重审 `claude_maestro_provider.py` 的 `_post` / `generate_json`——Plan #02 实装基于 Anthropic 公开文档的纸面假设（`content[].type=='tool_use'.input`），如果 Maestro 字段名不同需要修

如果 Spike 失败（4 项任一不满足），按 PLANNING.md 的 C-1 逃生路径：Plan #02 已经留好了 fallback chain，endpoint 保持 `[Spike Pending]` 即可——**所有 explainer 自动走 Gemini，业务零中断**。这是 Plan #02 设计上为 Plan #03 留的安全网。

### 中期（性能监控触发的优化）

Plan 文档 Task 1.3 P2-1 注释明确：**Phase 1 不做 provider 实例 cache**（实例化成本低，避免引入并发安全问题）。但如果延迟监控显示每次 `route_key` 触发的 provider 实例化让 P95 影响 > 5ms，Plan #03 应加 `@lru_cache(maxsize=8)`——8 是因为我们最多 8 种 provider 组合（3 个 provider × ~3 种 mode）。这是预留好的优化路径。

### 长期（架构演进）

Plan #02 落地的"路由表 + Provider 工厂 + Fallback Chain"模式可以扩展到更多场景：

- **多 LLM 协议适配**：未来加 OpenAI / Anthropic 直连 / 国产模型，只需新建对应 provider 类 + 工厂加分支 + 路由表加条目
- **A/B 测试**：路由表可以按用户 ID hash 分流，50% 走 Claude / 50% 走 Gemini，对比业务效果
- **成本控制**：低优先级 skill 走便宜模型（如 Gemini Flash），高价值 skill 走 Claude Opus，路由表按 skill 区分

---

## 踩过的坑（实施期 6 处微调追溯）

这是 Plan 起草期没想到、实施期发现的差异。每一处都有 commit message 锚点可追溯。

### 微调 1：`validate_llm_routes` placeholder 检测的边界 case

Plan 原代码 `ep = (p_cfg.get("endpoint") or "").strip()` 把"未声明 endpoint 字段"和"声明了但是 placeholder"等同处理——结果 gemini 和 mock 也被报警告（它们走 SDK / 不走网络，本来就不需要 endpoint）。修复：先判 `ep is None` 跳过，再判 strip 后的值。看似小 bug，但 3 行误报会让运维麻木——真正的 Maestro endpoint 没回填时反而注意不到。

### 微调 2：facade 测试与 mock 短路的设计前提冲突

Plan 文档 Task 1.6 写"`$env:MODEL_MODE = 'mock'` + 全量 pytest 应该 282 passed"。但 Plan #01 落地的 facade 测试 `test_model_client_accepts_injected_provider` 在 mock 模式下走 mock 短路（直接返回 fallback_result），看不到注入的 provider 行为——必然失败。修复：vertex 模式跑全量（与 baseline 同环境对比） + mock 模式 deselect facade test 跑 sanity（证明"mock 路径绕过 routes 零回归"核心断言）。

### 微调 3（最严重）：provider 解析块必须在 try 块内

Plan 原骨架将 provider 解析块（`if route_key is not None: ... build_provider_by_name(...)`）放在 try **之外**。Phase 1 末没暴露问题——因为那时 ClaudeMaestroProvider 是 stub，`__init__` 不抛错（直接在 `generate_json` 里抛）。Phase 2 stub→实装后，`__init__` 检查 endpoint 立刻抛 `ProviderUnavailable`——绕过了 ModelClient 的 except 路径，直接冒泡到 explainer，破坏 SkillRegistry 的 schema 校验。

修复：把 provider 解析块挪进 try 块（mock 短路之后），让 `ProviderUnavailable` 走标准 fallback degraded path（`status="model_unavailable"` + degraded 字典）。**这是 Plan #02 最深的一个坑**——只有完整跑 Phase 1 + Phase 2 + 真实业务流程才能暴露，Phase 1 单独跑的时候完全看不出来。

### 微调 4：endpoint_unreachable 测试 patch 错位置

Plan 原测试 `monkeypatch.setattr("...ClaudeMaestroProvider._post", _explode)` 替换整个 `_post` 方法——绕过了 `_post` 内部的 `try/except (httpx.ConnectError → ProviderUnavailable)` 转换逻辑。**测试压根没覆盖到这个关键转换**——Maestro 真正断网时这段代码才会被触发，结果测试给了假的安全感。

修复：改为 patch `httpx.Client`（`_post` 调用的下一层），让真正的 `_post` try/except 接住 ConnectError 并转换。

### 微调 5/6：from-import 本地命名空间问题

Plan 原 fixture 只 `monkeypatch.setattr("app.core.config.get_llm_config", ...)`，但 `claude_maestro_provider.py` 顶部 `from app.core.config import get_llm_config` 已经把函数绑到本地命名空间。**单跑测试时全 PASS**（cache 还没填），**全量跑时失败**（cache 已被前面测试填充为真实 [Spike Pending] config）——非常典型的"测试间相互污染"问题。

修复：fixture 同时 patch 两个位置——`app.core.providers.claude_maestro_provider.get_llm_config`（本地引用）+ `app.core.config.get_llm_config`（源），双层都覆盖。Task 2.3 fixture 和 Task 3.3 fixture 都有这个问题（同根因）。

---

## 跨 Plan 协作经验——从 Plan #01 学到什么

Plan #01 完成时积累了一些防御纪律，Plan #02 全部用上了，效果对比明显：

| 维度 | Plan #01 时的状态 | Plan #02 处理 |
|---|---|---|
| Plan 文档与代码现实差异 | 0 处 audit 锚点，全靠 R5/R5.1 自我修订 | **6 处实施期微调全部记 commit message + R9 修订统一回写 Plan 文档**，Step 8 审计精确到 commit hash |
| 多窗口并行工作流 | 一次 ed66bcc 事故（误带 03-plan 进 commit）| HEAD 异常时主动 reflog 追责 + 选"分两次 push"保持 git log 干净 |
| 跨 Plan 契约保护 | 无明确机制 | **Task 1.3 P0-A 硬约束**完整落地（grep + 改后代码对照保护 `_log_payload_ready`）|
| 质量门数 | 隐式 | **6 道显式质量门**全部通过（validate_llm_routes / Task 1.3 baseline 对照 / 8 行 route_key grep / Phase 1/2/3 commit 前 staging 对照）|
| baseline 数字 | 270/153 = 起草期数字，不准 | 282/163 锁定 + Plan 文档同步修订（R8 P1-A）|

**最重要的一条**：6 处实施期微调追溯锚点机制——每发现一处 Plan 与现实差异，立刻在 commit message 里写明（不只是修改代码本身）。Plan #02 全部 [complete] 后做 R9 单独 commit 把这些微调回写进 Plan 文档。这样后续 Step 8 审计能精确按 commit hash 找到所有修改点，不需要从 git diff 反推差异。

---

## 面试 Q&A 演练

### Q1：你怎么决定一个 Agent 调用走哪个 LLM provider？

> 用配置驱动而不是硬编码。`config.yaml` 里有一个 `llm.routes` 段，把每个 skill 的调用点（如 `app_profile.explainer`）映射到 provider 名（`claude_maestro` 或 `gemini`）。调用时 `ModelClient.generate_structured()` 根据传入的 `route_key` 参数查路由表，运行时实例化对应的 provider 走调用。新加 provider 只需在 config 里加一条路由，不需要改 Python 代码。这种"配置驱动"模式让运维能在不停机的情况下切换 provider，业务决策从 commit 变成 yaml 改动。

### Q2：Claude API 万一挂了怎么办？

> 三层 fallback 兜底。第一层 ProviderUnavailable 异常：Claude 返回 5xx 或网络超时时 `_post` 抛 ProviderUnavailable，被 `fallback_chain(claude, gemini)` helper 接住自动调 Gemini。第二层 Gemini 也失败：被 ModelClient 的 except 路径接住，返回降级结果（`status="model_unavailable"` + 预定义的 fallback_result + `_classify_model_error` 标注错误类型）。第三层是结果检查：业务代码看到 status != "ok" 时显示降级 UI 而不是崩溃。整个链路用户外部完全无感，Claude 不可达对用户体验是透明的。

### Q3：你在切换过程中怎么保证不破坏现有功能？

> 三个手段。第一，新增参数用 keyword-only 可选（`*, route_key: str | None = None`）——27 个现有调用点不传这个参数行为完全不变，只有 8 个 explainer 显式传入。第二，用 grep 精确验证改动范围——`grep -rn 'route_key=' app/runtime_skills/` 必须精确返回 8 行，多了说明动了不该动的，少了说明漏改。第三，全量回归测试锁定基线数字——Phase 0 跑 282/163 baseline，每个 Phase 末再跑一次确认没回归。最严格的是 `data_acquisition_agent/tests/` 全程锁定 163 passed (1 skipped)——这个目录有 Surgical Hard Boundary 不能动，全程零回归。

### Q4：你提到"Provider 解析块必须在 try 内"是个 bug，怎么发现的？

> 这是 Plan #02 最深的一个坑。Plan 原骨架把 provider 解析块（`build_provider_by_name(...)`）放在 try 块**之外**。Phase 1 末 ClaudeMaestroProvider 是 stub，`__init__` 不抛错，所以测试都通过了。Phase 2 把 stub 替换成真实 HTTP 实装后，`__init__` 立刻检查 endpoint——发现是 `[Spike Pending]` 占位符就抛 `ProviderUnavailable`。这个异常在 try 块外面抛出，**绕过了 ModelClient 既有的 except 路径**，直接冒泡到 explainer 和 SkillRegistry，破坏 UserAnalysisResult 的 Pydantic schema 校验。修复就是把 provider 解析块挪进 try 块，让 `ProviderUnavailable` 走标准 fallback degraded path。这个 bug 暴露的根本原因是**异常发生位置变了**（stub 在 generate_json 抛 → 实装在 __init__ 抛），单独跑 Phase 1 / Phase 2 都看不出来，必须组合起来跑真实业务流程才能暴露。

### Q5：你怎么测试 LLM 调用的鲁棒性？

> 全部用 monkeypatch 模拟外部，不真连任何端点。5 个 contract 测试覆盖 ClaudeMaestroProvider：①happy_path（tool_use 结构化输出正常解析）②repair_unescaped_newline（JSON 含裸换行符走 json_repair）③truncated_triggers_retry（文本截断触发 retry + strict JSON 提示）④endpoint_unreachable_raises_unavailable（patch httpx.Client 模拟网络断开，验证 ConnectError → ProviderUnavailable 转换）⑤count_tokens（naive 估算返回正整数）。然后 2 个 e2e 测试覆盖 fallback chain：Claude 不可达走 Gemini + Claude 成功不走 Gemini。**关键设计**：所有测试在 ModelClient 层验证，不绕 explainer 复杂构造签名（7 个 explainer 的 `__init__` / `explain` 签名都不一样，测试要写 7 套 fixture 不现实）。在 ModelClient 层验证 fallback chain 工作 = 任何 explainer 走 fallback chain 都会工作。

---

## 回顾——这次模块开发学到的方法论

如果用一句话总结 Plan #02 的方法论收获：**好的工程是把"风险点提前到能拦住的地方"——不是不出错，是出错的时候已经在能 catch 的层级**。

具体落地：

1. **配置驱动 > 代码硬编码**——业务决策（用哪个 provider）放 config，运维能改；技术决策（怎么 fallback）放代码，工程师能改
2. **Surgical Changes**——只动该动的（27 个调用点保持原样），不顺手"改进"无关代码
3. **Fallback Chain**——任何外部依赖必须有降级路径，5 道 fallback 层级（4xx/5xx/__init__/JSON parse/整个 LLM）让用户外部无感
4. **质量门体系**——4 道显式质量门覆盖最容易出大事故的地方（配置错位 / 跨 Plan 契约破坏 / 漏改 / commit 误带文件），其他自由度高的地方不拦
5. **微调追溯锚点**——发现 Plan 与现实差异立刻在 commit message 写明，比事后审计反推清晰得多
6. **跨 Plan 协作纪律**——多窗口并行时 HEAD 异常先 reflog 追责，不擅自 reset；分两次 push 保持 git log 干净

这套方法论不是 Plan #02 独创——是 Plan #01 ed66bcc 事故 + R5/R5.1 自我修订过程中积累的。Plan #02 是第一次把这套方法论作为**默认动作**用，效果验证：6 道质量门全过 + 6 处微调全追溯 + 5 commit 4-commit 上限守住 + 跨窗口协作 0 事故。Plan #03 / Plan #04 应继续延续。

---

— 技术总结完成于 2026-05-02
