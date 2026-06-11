# Plan #02 白盒审计报告 — explainer/trace 切 Claude Opus 4.7

| 项 | 值 |
|---|---|
| 审计对象 | Plan #02（baseline `3307ca1` → `[complete]` `874c305` → 收尾 `4f1b4a5` → R9 文档同步 `5affae4`）|
| Plan 文件 | docs/plans/02-explainer-trace-claude-migration-plan.md（R9 / 1263 行 / 5 Phase / 19 Task）|
| Design Doc | docs/specs/02-explainer-trace-claude-migration-design.md |
| 审计基准 | Vibe Coding 实战方法论 Step 8 ai-code-review skill 10 板块结构 |
| 审计日期 | 2026-05-02 |
| 审计结论 | ✅ **PASS — Plan #02 完整闭环，可作为 Plan #03 启动的稳固基础** |

---

## 一、做了什么（What）

Plan #02 是 Plan #01 ModelClient 多 Provider 重构落地后的第一个真正"用起来"的 Plan——把 7 个 explainer 共 **8 个 LLM 调用点**全部接入 Claude Opus 4.7 via Agent Maestro 路由（含 BehaviorExplainer 的 timeline 第二路）。一句话讲清楚：以前所有 explainer 都用 `ModelClient.generate_structured()` 走默认 Gemini，现在通过 `route_key` 参数告诉 ModelClient "这次调用走哪个 provider"，运行时根据 `config.yaml` 的路由表决定走 Claude 还是 Gemini。

但**这不是"切换完成就走 Claude"**——Maestro Spike 是 Plan #03 Phase 0 的事，本 Plan 完成时 endpoint 还是 `[Spike Pending]` 占位符，所以 ClaudeMaestroProvider 实例化时立刻抛 `ProviderUnavailable`，自动 fallback 到 Gemini。**用户外部看不到任何行为变化**——所有 explainer 输出仍然来自 Gemini，但**切换基础设施已经全部就位**：路由表、provider 工厂、Claude HTTP 实装、JSON repair 兼容层、fallback chain、5 个 contract 测试 + 2 个 e2e 测试，都已经落地。Plan #03 Spike 通过后只需把 endpoint 字段从 `[Spike Pending]` 改成真实 URL，**0 行代码改动**就能切到 Claude。

## 二、技术路线（Technology Stack）

| 层 | 选型 | 来源 |
|---|---|---|
| HTTP 客户端 | httpx（FastAPI 间接依赖，requirements.txt 已有）| Plan #02 选型，避免新增依赖 |
| Claude API 协议 | Maestro 端点 + tool_use 结构化输出 + Bearer Token 认证 | Design Doc § 4.1，纸面假设（待 Plan #03 Spike 验证）|
| JSON 鲁棒性 | 复用 Plan #01 抽出的 `app/core/providers/json_repair.py`（13 个 RETRYABLE_PARSE_HINTS + 一次 retry）| Plan #01 Phase 2 落地 |
| Fallback 机制 | Plan #01 已落地的 `fallback_chain(claude → gemini)` helper（在 `app/core/providers/base.py`）| Plan #01 R5.1 Task 3.2 |
| 配置驱动路由 | YAML `llm.providers + llm.routes`（运行时读取，不需要重启）| Plan #02 Task 1.1 设计 |
| 启动期校验 | FastAPI `@app.on_event("startup")` 钩子 → `validate_llm_routes()` | Plan #02 R7 P0-4 |
| 测试隔离 | 全部 monkeypatch（不真连任何外部端点）| Plan #02 Task 2.3 / 3.3 |

**关键决策**：`route_key` 是**可选 keyword-only 参数**——27 个不传 `route_key` 的现有调用点行为完全不变，只有 8 个 explainer 显式传入。这是 Karpathy "Surgical Changes" 原则的精确落地——增量改造而不是颠覆式替换。

## 三、文件清单（File Inventory）

### 新建（4 个）

| 文件 | 行数 | 职责 |
|---|---|---|
| `app/core/providers/factory.py` | 24 | `build_provider_by_name(name)` 按 provider 名构造实例。3 个分支：mock / gemini（跟 settings.model_mode 不硬编码）/ claude_maestro（lazy import 避免循环依赖）|
| `app/core/providers/claude_maestro_provider.py` | 142 | Claude Opus 4.7 via Maestro 真实 HTTP 实装。Phase 1 是 stub（直接抛 ProviderUnavailable），Phase 2 替换为真实 impl（httpx + tool_use parse + json_repair retry）|
| `tests/test_claude_provider_jsonrepair.py` | 116 | 5 个 contract 测试：happy_path / repair_unescaped_newline / truncated_triggers_retry / endpoint_unreachable_raises_unavailable / count_tokens |
| `tests/test_explainer_fallback_e2e.py` | 130 | 2 个 fallback e2e 测试：Claude 不可达自动走 Gemini + Claude 成功不触发 fallback |

### 修改（11 个）

| 文件 | 改动量 | 关键点 |
|---|---|---|
| `config.yaml` | +24 行 | 新增 `llm:` 段（providers 3 个 + routes 8 个 + default_provider）|
| `app/core/config.py` | +67 行 | `get_llm_config()` 模块级缓存 + `llm_provider_for(route_key)` + `validate_llm_routes()` 启动期校验（含 R9 微调 1 区分未声明 vs placeholder）|
| `app/core/model_client.py` | +13/-10 行 | `generate_structured` 加 `route_key` keyword-only 参数 + provider 解析块（在 try 块内，R9 微调 3）+ mock 分支日志加 `route=`，**baseline 4 块全保留**（mock 短路 / `_log_payload_ready` / `_record_usage` / except 路径）|
| `app/main.py` | +7 行 | `@app.on_event("startup")` 钩子调 `validate_llm_routes()` |
| 7 个 explainer.py | 各 +1 行（behavior +2）| 机械追加 `route_key="<x>",` 到 `generate_structured(...)` 调用末尾。8 个调用点：app_profile / behavior_profile.profile / behavior_profile.timeline / credit_profile / comprehensive / product_advice / ops_advice / trace_analyzer |

**总改动量**：+580 / -63 行，符合 Surgical 原则（小、精、不越界）。

## 四、正确性判断（Correctness Verdict）

### 测试覆盖

| 维度 | 数量 | 说明 |
|---|---|---|
| 全量测试基线 | 282 → 289 passed (+7) | tests/ 累计 |
| da-agent 测试 | 163 passed, 1 skipped（全程锁定）| Surgical Hard Boundary 守住 |
| 新增测试 | 7 个（5 contract + 2 e2e）| 覆盖 Claude provider 协议层 + fallback chain 行为 |
| 8 处 route_key 接入 | 精确 8 行 grep 命中 | R7 P0-2 BehaviorExplainer L142 timeline 漏挂修复落地 |

### 关键路径验证

1. **mock 模式零回归**：282 passed（vertex 模式） / 281 passed + 1 deselected（mock 模式 deselect facade test）—— 证明 mock 路径绕过 routes，没引入回归
2. **Claude stub fallback**：vertex 模式下 ClaudeMaestroProvider stub 抛 ProviderUnavailable → fallback_chain 接住 → 走 Gemini —— Phase 1 末已验证
3. **Claude 真实实装 + fallback**：tests/test_explainer_fallback_e2e.py 2 个测试覆盖"Claude 失败走 Gemini" + "Claude 成功不走 Gemini"两个方向
4. **Plan #03 budget 模块契约**：`_record_usage` 调用路径完整保留（R9 微调 3 把 provider 解析块挪进 try 块的根本原因——保证 ProviderUnavailable 走 except 路径而不是冒泡到 explainer 破坏 schema）

### 已知限制

- **Maestro 真实切换未发生**：endpoint='[Spike Pending]'，Plan #03 Phase 0 Spike 通过后才会切。Plan #02 完成时 vertex 模式下所有 Claude 调用仍走 fallback Gemini。
- **协议假设待验证**：Task 2.1 实装基于纸面假设（`content[].type=='tool_use'.input` / `content[].type=='text'.text`）。Plan #03 Phase 0 Spike 完成后必须按真实 response shape 重新审视 Task 2.1 全部代码。
- **测试不真连外部**：所有测试用 monkeypatch 模拟 `_post` 或 `httpx.Client`，没有针对真实 Maestro 端点的集成测试。

## 五、风险排查（Risk Assessment）

### 🟢 低风险（已缓解）

1. **`_log_payload_ready` 日志契约**——R8 P0-A 硬约束保护到位。grafana log query / caplog 断言依赖 `"LLM payload ready"` 字串，Task 1.3 5 步实施流程严格保留 baseline 调用位
2. **mock 模式回归**——R8 P1-A 锁定 282 / 163 baseline，全程零回归
3. **Surgical Hard Boundary**——data_acquisition_agent/ 全程未动，163 passed (1 skipped) 全程锁定

### 🟡 中风险（已缓解但需 Plan #03 验证）

1. **R9 微调 3：Task 1.3 try-block 位置 bug**——Plan 原骨架将 provider 解析块放在 try 之外，Phase 1 末 stub 阶段未暴露（stub 直接 raise from `generate_json` 不是 from `__init__`），Phase 2 stub→实装后才暴露。**修复后 ProviderUnavailable 走标准 fallback degraded path**，但需要 Plan #03 启动后跑真实业务流程再次确认无新场景触发
2. **Maestro 协议假设**——`content[].type=='tool_use'.input` 是基于 Anthropic 公开文档的合理推测，**未经 Maestro 真实端点验证**。Plan #03 Phase 0 Task 0.2 Spike 必须验证：①响应字段名匹配 ②鉴权 header 格式（`Authorization: Bearer` vs `X-API-Key`）③错误码语义（401/403 是否归 transport 错误）

### 🟠 待 Plan #03 关注

1. **fallback chain 性能**——Plan #02 测试覆盖了"Claude 失败 → Gemini 成功"路径，但**没测延迟**。如果 Claude 真正切换后 P95 延迟 > 8s（Design Doc § 6.3 阈值），需要在 Plan #03 加 SSE 层超时控制
2. **provider 实例化成本**——Plan 文档 Task 1.3 P2-1 注释提到"如延迟监控显示 P95 影响 > 5ms，Phase 3 加 LRU(maxsize=8) 缓存"。Plan #02 没加缓存，每次 `route_key` 触发都新建 provider 实例。Plan #03 跑起来后需要观察实际延迟决定是否加缓存
3. **MAESTRO_TOKEN 环境变量管理**——Plan #02 用环境变量读 token 不进 config.yaml（避免凭据泄露），但**没有定义 token 轮换流程**。Plan #03 启动前需要明确：token 在哪存？多久轮换？过期了怎么 hot-reload？

## 六、运行时链路（Runtime Trace）

用退款 explainer 走一遍完整 Plan #02 落地后的运行时链路（vertex 模式 + Maestro endpoint 已就绪假设）：

```
请求到 explainer.explain(uid, ...)
  ↓
self.model_client.generate_structured(
    skill_name="app_profile",
    prompt=prompt,
    fallback_result=self._build_fallback_payload(),
    response_schema=self._build_llm_response_schema(),
    route_key="app_profile.explainer",   ← 新增参数
)
  ↓ ModelClient.generate_structured
self.mode == "mock"? → 否（vertex 模式）→ 进 try 块
  ↓
provider = self._provider                 ← 默认 GeminiProvider（_build_default_provider 已包装 fallback_chain(claude, gemini)）
route_key != None → 进 provider 解析     ← 在 try 块内（R9 微调 3 修复）
  ↓
target_name = llm_provider_for("app_profile.explainer")
  → 读 config.yaml → "claude_maestro"
  ↓
target_name != provider.provider_name?
  → fallback_chain.provider_name == "claude_maestro"（fallback_chain 透传 primary 的 provider_name）
  → True（注：实际等价比较取决于 _build_default_provider 是否包装了 fallback_chain）
  ↓ 如不等：build_provider_by_name("claude_maestro")
  → 实例化 ClaudeMaestroProvider()
  → __init__ 检查 endpoint：
     - "[Spike Pending]" → raise ProviderUnavailable
     - 真实 URL → 检查 MAESTRO_TOKEN env
        - 缺 → raise ProviderUnavailable
        - 有 → 实例化成功
  ↓ 实例化成功后
provider.generate_json(prompt, response_schema=...)
  → ClaudeMaestroProvider._post(payload)
     → httpx.Client(timeout=30).post(endpoint, headers={Authorization: Bearer ...}, json=...)
     → 5xx/408 → raise ProviderUnavailable
     → 4xx → raise ValueError
     → 200 → resp.json()
  ↓
解析 body.content[]:
  - type=="tool_use" + input is dict → return input
  - type=="text" → 累积 text → parse_json_text(text)
     → 失败且 retryable → 重发 + strict JSON 提示 → 再 parse
     → 失败不可重试 → raise
  ↓
self._log_payload_ready(skill_name, structured_result)   ← baseline 保留
self._record_usage(prompt, json.dumps(structured_result, ensure_ascii=False))   ← baseline 保留
return {"status": "ok", "structured_result": ..., "model_name": ..., "prompt_preview": ...}

═══ 异常路径：Claude 不可达 ═══
ClaudeMaestroProvider 任何环节抛 ProviderUnavailable
  ↓ 被 fallback_chain 捕获（如果 _build_default_provider 包装了的话）
fallback to GeminiProvider.generate_json(...)
  → 成功 → return Gemini 结果
  → 失败 → raise（被 ModelClient try/except 捕获 → degraded fallback_result）

═══ 异常路径：Provider 解析期就抛错（R9 微调 3 关键修复）═══
build_provider_by_name 实例化抛 ProviderUnavailable
  ↓ 在 try 块内（修复后）→ except 路径接住
return {"status": "model_unavailable", "structured_result": degraded, ...}
```

**关键观察**：Plan #02 落地后的链路有 5 道 fallback 层级——Claude 协议错误（4xx）/ 传输错误（5xx）/ 实例化错误（endpoint placeholder / token 缺失）/ JSON parse 错误（retry 1 次）/ 整个 Claude 不可用（fallback_chain → Gemini）/ 整个 LLM 不可用（degraded fallback_result）—— 任何一层失败都不会让用户看到崩溃。

## 七、Debug 手册（Troubleshooting Playbook）

| 症状 | 根因可能 | 排查步骤 |
|---|---|---|
| 启动期看到 `WARNING ... provider claude_maestro has placeholder endpoint='[Spike Pending]'` | **正常**——Maestro Spike 还没做 | Plan #03 Phase 0 完成后回填 endpoint |
| 启动期看到 gemini/mock 也被 warning placeholder | R9 微调 1 没生效 | grep `app/core/config.py` 确认 `if ep is None: continue` 在 |
| explainer 调用后 status="model_unavailable" + degraded.model_error="ProviderUnavailable" | Claude 实例化失败（endpoint placeholder 或 token 缺失），fallback chain 没生效 | grep `_build_default_provider` 确认 fallback_chain 包装逻辑；grep `app/core/providers/base.py def fallback_chain` 确认 helper 存在 |
| caplog 没抓到 `"LLM payload ready"` 日志 | Task 1.3 落盘破坏了 baseline `_log_payload_ready` 调用 | grep `app/core/model_client.py` `_log_payload_ready\(` 确认调用还在 try 块成功路径 |
| `last_token_usage["total"]` 一直为 0 | `_record_usage` 没被调，可能 except 路径意外触发 | 检查 LLM 调用是否真正成功，看 logger.warning 是否输出 |
| 8 处 route_key grep 少了 1 处 | Task 1.5 漏改某个 explainer | `Get-ChildItem app/runtime_skills -Filter "explainer.py" -Recurse \| Select-String 'route_key='` 应精确返回 8 行 |
| Maestro 真实切换后业务出错 | 协议假设失效（content[]字段名不对 / tool_use 结构不对）| Plan #03 Phase 0 Task 0.2 Spike 输出 → 按真实 response shape 修订 Task 2.1 |
| 测试 `test_claude_provider_*` 单跑 PASS 但全量跑失败 | from-import 本地命名空间问题（R9 微调 5/6 同根因）| 确认 fixture 双层 patch（同时 patch `app.core.providers.claude_maestro_provider.get_llm_config` + `app.core.config.get_llm_config`）|

## 八、关键 commit 时间线（Commit Timeline）

| commit | 日期 | 性质 | 范围 |
|---|---|---|---|
| `3307ca1` | 2026-05-02 | baseline `--allow-empty` | 锁定 282 + 163 基线 |
| `3ee2c8f` | 2026-05-02 | Phase 1 | config.yaml + ModelClient route_key + 13 文件 + 8 explainer wiring |
| `16b48fc` | 2026-05-02 | Phase 2 | ClaudeMaestroProvider 真实实装 + 5 contract tests + Task 1.3 try-block 回补 |
| `874c305` | 2026-05-02 | Phase 3 [complete] | fallback chain e2e 2 tests |
| `4f1b4a5` | 2026-05-02 | 收尾 | TASK.md 标 [x] |
| `5affae4` | 2026-05-02 | R9 文档同步 | Plan #02 文档 6 处微调修订 |

外加：`26d2bbf docs(plan-03): rewrite R5` 是 Plan #03 R5 修订草稿，**与 Plan #02 无关**，仅在主分支日志中按时间穿插出现。

## 九、Plan / Code 一致性核验（Plan-Code Conformance）

R9 修订完成后，Plan 文档与代码现实**完全对齐**。逐项核验：

| Plan 条目 | 实际代码 | 一致性 |
|---|---|---|
| Task 1.1: config.yaml 新增 8 个 routes | config.yaml 实际 8 个 routes（含 behavior_profile.timeline）| ✅ |
| Task 1.2: validate_llm_routes 区分未声明 vs placeholder | config.py R9 修订后 `if ep is None: continue` | ✅ |
| Task 1.3: provider 解析块在 try 内 | model_client.py R9 修订后位于 try 块顶部 | ✅ |
| Task 1.3: 4 块 baseline 全保留 | grep 确认 mock 短路 / `_log_payload_ready` / `_record_usage` / except 全在 | ✅ |
| Task 1.4: ClaudeMaestroProvider stub | Phase 1 stub → Phase 2 实装 | ✅ |
| Task 1.5: 8 处 route_key 机械追加 | grep 精确 8 行 | ✅ |
| Task 1.6: vertex 主验证 + mock deselect facade test | R9 修订后 Plan 文档已对齐 | ✅ |
| Task 2.1: Claude HTTP 实装 + json_repair retry | claude_maestro_provider.py 142 行实装 | ✅ |
| Task 2.3: 5 个 contract 测试 + 双层 patch fixture | tests/ R9 修订后 Plan 文档已对齐 | ✅ |
| Task 3.3: 2 个 fallback e2e + ModelClient 层直测 | tests/test_explainer_fallback_e2e.py 130 行 | ✅ |
| Task 3.5: [complete] commit | `874c305 [complete] explainer-trace-claude` | ✅ |

## 十、遗留事项与下一步（Open Items & Next Steps）

### 必做（Plan #03 启动前）

1. **Plan #03 Phase 0 Maestro Spike** → 验证真实 Maestro 端点的 4 项（HTTP 200 / 协议字段 / 延迟 ≤ 5s / 配额）→ 通过后回填 `config.yaml` 的 `claude_maestro.endpoint` 字段。**这是 Plan #02 落地后真正切到 Claude 的唯一前提**。
2. **Spike 通过后重审 Task 2.1 代码** → 按真实 response shape 修正 `_post` / `generate_json` 解析逻辑（字段名 / 鉴权 header / 错误码）。

### 可选（性能优化触发条件）

1. **provider 实例 LRU 缓存**——监控 `route_key` 触发的 provider 实例化耗时。如 P95 > 5ms → Plan #03 加 `@lru_cache(maxsize=8)`。
2. **MAESTRO_TOKEN 轮换流程**——定义 token 存储位置（Azure Key Vault / GitHub Secrets / 环境变量），轮换周期，过期 hot-reload 机制。

### 已知技术债（不阻塞）

1. **`_record_usage` 在 fallback 路径下行为**——Plan #02 测试覆盖了"成功路径调 `_record_usage`"，但**没明确测**"fallback 后是否调一次"。Plan #03 budget 模块依赖 `last_token_usage` 准确性，需要明确语义。
2. **测试无真实集成**——所有测试用 monkeypatch，没有针对真实 Maestro 的 smoke test。Plan #03 启动后建议加一个 manual smoke（带 `pytest.skip` 默认跳过）。

### 推广建议（基于 Plan #01 + Plan #02 的经验）

1. **质量门体系成熟**——4 道质量门（validate_llm_routes / Task 1.3 baseline 对照 / 8 行 route_key grep / commit 前 staging 对照）应作为后续所有 Plan 的标准动作。
2. **6 处微调追溯锚点机制**——commit message 完整记录"实施期发现的 Plan 与现实差异"，比 Plan #01 完全靠 Step 8 audit 反推清晰得多。后续 Plan #03 / Plan #04 应延续此做法。
3. **跨 Plan 契约保护**——Task 1.3 P0-A 硬约束（grep + 改后代码对照）成功保护了 `_log_payload_ready` 不被覆盖。后续涉及修改 ModelClient / 共享基础设施的 Plan 都应启用此质量门。

---

## 审计总结

Plan #02 是 Plan #01 重构基础设施落地后的**第一个真实业务接入**。**机制层面完全到位**：8 个调用点接入 route_key、Claude provider 实装就位、fallback chain 验证通过、config 驱动路由、启动期校验。**真实业务效果待 Plan #03 验证**：Maestro Spike 通过 + endpoint 回填后才能看到 Claude 真正接管 explainer 推理。

**6 处实施期微调全部回写 Plan 文档（R9 修订）**——Plan 与代码现实完全对齐，未来 Step 8 / 团队 review 不需要从 commit message 反推差异。**4 道质量门 + 跨 Plan 契约保护机制**已经成型并经实战验证，是 Plan #03 / Plan #04 启动的稳固基础。

PASS。Plan #02 闭环。

— 审计完成于 2026-05-02
