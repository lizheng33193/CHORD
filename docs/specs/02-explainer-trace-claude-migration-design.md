# Design Doc #02 — Profile explainer + Trace 切 Claude Opus 4.7

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-05-02 |
| 作者 | v-yimingliu |
| 关联 | 依赖 Plan #01（ModelClient 抽象层）。本 Doc 不引用其他 Design Doc 章节号；依赖关系参见 PLANNING.md |

## 0. 一句话目标（Goal）

把 6 个画像 Skill 的 explainer 调用 + Trace 模块的 LLM 调用，从 Gemini 切换到 Claude Opus 4.7（经 Agent Maestro）。data_acquisition_agent **不切换**，保持 Gemini，153 测试基线锁死。本 Doc 不改任何 prompt 文本，只改 Provider 路由配置。

## 1. 背景与目标

### 1.1 为什么要切 Claude Opus 4.7

- Claude Opus 4.7 在长上下文推理深度上显著优于 Gemini 2.5 flash，对 `comprehensive_profile` / `trace_analyzer` 这类需要综合多源数据的场景帮助明显
- 业务侧已经通过 Agent Maestro 拿到 Claude Opus 4.7 的 10x / 45x tier 配额
- Microsoft Copilot 路由已经验证可用

### 1.2 切换范围严格收敛

只切吃推理深度的 LLM 调用，不切 SQL 生成（data_acquisition）：
- SQL 生成更看重确定性 + 成本，Gemini 已经达标
- data_acquisition_agent 已有 153 测试基线，任何切换都意味着重新 calibrate prompt + 重跑全部测试
- 遵循 Karpathy Surgical Changes 原则：能不动就不动

## 2. 切换范围清单

### 2.1 切换的 7 处调用点

| Skill / 模块 | 路由 key | 当前 Provider | 切换后 Provider |
|---|---|---|---|
| `app/runtime_skills/app_profile/explainer.py` | `app_profile.explainer` | gemini | claude_maestro |
| `app/runtime_skills/behavior_profile/explainer.py` | `behavior_profile.explainer` | gemini | claude_maestro |
| `app/runtime_skills/credit_profile/explainer.py` | `credit_profile.explainer` | gemini | claude_maestro |
| `app/runtime_skills/comprehensive/explainer.py` | `comprehensive.explainer` | gemini | claude_maestro |
| `app/runtime_skills/product_advice/explainer.py` | `product_advice.explainer` | gemini | claude_maestro |
| `app/runtime_skills/ops_advice/explainer.py` | `ops_advice.explainer` | gemini | claude_maestro |
| `app/runtime_skills/trace_analyzer/explainer.py` | `trace_analyzer.explainer` | gemini | claude_maestro |

### 2.2 不切换的调用点

| 模块 | 路由 key | Provider | 理由 |
|---|---|---|---|
| `data_acquisition_agent/orchestrator.py` | `data_acquisition.orchestrator` | gemini（保持） | Surgical 锁死，153 测试基线不动 |
| `data_acquisition_agent/prompt_assembler.py` 内部 LLM 调用（如有） | `data_acquisition.prompt_assembler` | gemini（保持） | 同上 |

### 2.3 不切换的理由（详细）

1. **成本/延迟权衡**：SQL 生成对延迟敏感，Claude 10x tier 单次调用比 Gemini 2.5 flash 慢约 2-3x，业务侧不接受
2. **测试基线**：153 测试中包含 mock LLM e2e + real LLM smoke，切 Provider 等于重 calibrate 整套
3. **业务边界清晰**：取数 → 画像 是两个 stage，可以独立演进

## 3. 路由配置

### 3.1 `config.yaml` 增加 `llm.providers` 段

```yaml
llm:
  providers:
    gemini:
      mode: vertex
      model: gemini-2.5-flash
      project: amberstar-gemini
      location: global
    claude_maestro:
      endpoint: "[Spike Pending]"
      model: claude-opus-4.7
      tier: 10x
    mock:
      enabled_in: ["test", "local"]
```

### 3.2 `llm.routes` 显式列调用点 → provider 名

```yaml
llm:
  routes:
    app_profile.explainer: claude_maestro
    behavior_profile.explainer: claude_maestro
    credit_profile.explainer: claude_maestro
    comprehensive.explainer: claude_maestro
    product_advice.explainer: claude_maestro
    ops_advice.explainer: claude_maestro
    trace_analyzer.explainer: claude_maestro
    # data_acquisition.* 未列出，走默认值
```

### 3.3 默认值（兜底安全）

未列出的调用点统一走 `gemini`。意味着：
- `data_acquisition.orchestrator` 隐式落到 gemini
- 任何未来新增的 LLM 调用点默认 gemini，必须显式声明才能切 Claude

这条规则避免"漏切回归"——比如 data_acquisition 后续改了名字，不会因为忘加路由就被静默切到 Claude。

## 4. Prompt 兼容性审查

### 4.1 现有 7 个 prompt 文件格式假设盘点

| Prompt 文件 | 输出格式 | Claude 兼容性风险 |
|---|---|---|
| `app/prompts/app_profile_prompt.md` | JSON + report_markdown | 低（结构化字段稳定） |
| `app/prompts/behavior_profile_prompt.md` | JSON + report_markdown 5 段 | 中（5 段结构 Claude 可能改格式） |
| `app/prompts/credit_profile_prompt.md` | JSON + report_markdown | 低 |
| `app/prompts/comprehensive_profile_prompt.md` | JSON + 多模块汇总 | 中（多源融合，Claude 输出风格偏长） |
| `app/prompts/product_advice_prompt.md` | JSON | 低 |
| `app/prompts/ops_advice_prompt.md` | JSON | 低 |
| `app/prompts/trace_analyzer_prompt.md` | JSON + 时间线 | 中（时间线 Claude 倾向自由叙述） |

### 4.2 Claude vs Gemini 输出风格差异处理

不改 prompt，而是靠 Provider 层 JSON repair 适配：
- Claude `tool_use` 模式强制结构化，避免自由叙述
- 输出超长时，Provider 层裁剪到 schema 必需字段，丢弃多余 markdown
- 任何一次 Claude 解析失败，Provider 层走单次 retry（与 Gemini 现有重试策略一致）

### 4.3 长 prompt 调用点说明

`comprehensive.explainer` 与 `trace_analyzer.explainer` 因 prompt 通常 > 32K tokens，对 Claude 长上下文优势依赖度最高。

**这不是运行时动态路由**：§ 3.2 已经把 7 个 explainer 全部静态路由到 `claude_maestro`，本节只是说明灰度顺序——Phase 3 灰度时这两个 Skill 排在最后切换（先验证短 prompt Skill 稳定后再切长 prompt），**不引入运行时动态 token 检测**。

## 5. 回归测试矩阵

### 5.1 7 Skill 黄金输入/输出测试

每个 Skill 的现有 `tests/test_*_phase*.py` 中 mock 模式测试 100% 通过。

### 5.2 mock 模式

`MODEL_MODE=mock` 时绕过 routes，所有调用走 `MockProvider`。这条路径必须保持现有行为字节级一致。

### 5.3 vertex/gemini 模式兜底

如果 `claude_maestro.endpoint` 配置缺失或运行时不可达，自动 fallback 到 gemini，避免老环境（如 vertex 离线测试机）出错。

## 6. 性能与成本

### 6.1 单 Skill 平均 token 估算（基于现有 Golden Test fixture）

| Skill | 输入 tokens | 输出 tokens |
|---|---|---|
| app_profile | ~3K | ~1.5K |
| behavior_profile | ~8K | ~2.5K |
| credit_profile | ~2K | ~1K |
| comprehensive | ~15K | ~3K |
| product_advice | ~5K | ~1K |
| ops_advice | ~5K | ~1K |
| trace_analyzer | ~10K（含时间线） | ~2.5K |

### 6.2 Claude 10x vs 45x tier

- 默认 10x tier（1M 上下文，性价比最优）
- `comprehensive` / `trace_analyzer` 复杂场景可在配置中切 45x tier（200K 上下文，更深推理）
- 切换方式：`config.yaml: llm.providers.claude_maestro.tier`

### 6.3 延迟预算

- 单次 explainer P95 ≤ 8s（与现有 Gemini 调用持平或略高）
- 批量分析（多 UID）依赖 SkillRegistry 现有并行（max_workers=3），不受 Provider 切换影响
- **验证**：Phase 3 灰度时跑 50 次 Golden Test fixture 采样，记录 P95；超 8s 触发 incident，回滚到 Gemini 路由（仅改 `config.yaml: llm.routes` 一行，不需改代码）。

## 7. Resilience

- Plan #01 已规范的 Provider fallback 链复用：Claude 失败 → Gemini fallback
- 前端展示降级标记：`model_trace.provider != routes 配置值` 时，前端 Badge 显示"AI 服务降级"
- 单次重试策略保留（JSON parse / empty content 等可重试错误）

## 8. 灰度策略

### 8.1 阶段 A：mock 模式契约测试

- mock 模式下 `MockProvider` 替代 `ClaudeMaestroProvider`
- 跑 270 测试，零回归
- 完成标志：CI 全绿

### 8.2 阶段 B：staging 环境单 Skill 灰度

**优先级排序**（输入复杂度从低到高 + Golden Test 覆盖率从高到低）：

```
app_profile → behavior_profile → credit_profile → product_advice → ops_advice → comprehensive → trace_analyzer
```

**首选 app_profile 的理由**：
- 输入最简单（结构化的 app 安装列表，无嵌套 JSON）
- Golden Test 覆盖最全（多个 fixture）
- 回归风险最低（即使 Claude 输出风格漂移，影响范围限于 app_profile 单 Skill）

每切完一个 Skill，跑该 Skill 的 Golden Test + 整体 270 测试，零回归才进下一个。

**失败回滚条件**（任一条命中即触发本 Skill 回滚）：
- 单 Skill 切换后 Golden Test 任意一条退化（4 维 Rubric 任意维度分数低于切换前基线）
- P95 延迟 > 8s（按 § 6.3 验证流程采样）
- Provider fallback 触发率 > 5%（一段时间内的 `provider_fallback` SSE/log 事件占比）

回滚动作：本 Skill `config.yaml: llm.routes` 改回 `gemini`（一行 + commit revert 标签），剩余 Skill 暂停切换；本 Doc 进入修订流程，定位风险后再次发起灰度。

### 8.3 阶段 C：剩余 6 Skill 全量切换

按 § 8.2 的优先级一个一个切，每切完一个独立 commit（micro-commit），所有切完后跑全量回归。

## 9. 不在本期范围（Out of Scope）

- 不改任何 prompt 文件文本（哪怕 Claude 输出格式有偏差也不改 prompt，靠 Provider 层 JSON repair 兜）
- 不动 `data_acquisition_agent/` 任何文件
- 不引入新 Skill / 新维度
- 不在本 Doc 重新设计 `LLMProvider` 抽象层（那是另一个 Plan 的事）
- 不在本 Doc 落地 Orchestrator Agent 自身的路由配置
- 不改 `MODEL_MODE` 环境变量语义
