# Design Doc #01 — ModelClient 多 Provider 重构

| 项 | 值 |
|---|---|
| 状态 | Draft |
| 创建日期 | 2026-05-02 |
| 作者 | v-yimingliu |
| 关联 | 此 Doc 不引用其他 Design Doc 章节号；依赖关系参见 PLANNING.md |

## 0. 一句话目标（Goal）

把 `app/core/model_client.py` 的单一 Gemini/Vertex 实现重构为多 Provider 抽象层，通过 `LLMProvider` 接口让 explainer / trace / orchestrator 调用方对底层 Provider 切换无感知；data_acquisition_agent 沿用现有 `ModelClient` 调用方式，零回归（153 测试基线锁死）。

## 1. 背景与目标

### 1.1 现状

`app/core/model_client.py` 当前是一个胖类：
- 内嵌 `mock` / `gemini` / `vertex` 三种模式分支（if/elif）
- 自带 `_RETRYABLE_PARSE_HINTS` 触发的单次重试
- 自带 JSON repair / 错误分类 / `model_trace` 拼装
- 27 处调用点（6 Skill explainer + trace_analyzer + data_acquisition_agent 等）直接 `from app.core.model_client import ModelClient`，并调用 `generate_structured(skill_name, prompt, fallback_result, response_schema)`

### 1.2 引入 Claude Opus 4.7（Maestro）的诉求

业务上需要让 Profile explainer / Trace / Orchestrator 自身这些"吃推理深度"的调用走 Claude Opus 4.7（经 Agent Maestro），而 data_acquisition_agent 仍然用 Gemini（成本/延迟权衡 + 153 测试基线锁死）。如果继续往 `model_client.py` 里加 if/elif 分支会让该文件更胖，并且让 data_acquisition_agent 间接受到改动影响。

### 1.3 目标（Surgical 原则）

- 抽离 Provider 接口（`LLMProvider` Protocol），让上层不感知具体 Provider
- `ModelClient` 退化为 Facade，保留向后兼容签名（`generate_structured` 签名一字不改）
- 270 测试 + 153 data_acquisition 测试零回归
- 调用点改动 ≤ 5%（红线，超出视为抽象设计失败）

## 2. 现状盘点

### 2.1 `ModelClient` 当前职责

| 职责 | 当前位置 | 重构后归属 |
|---|---|---|
| mock 模式分支 | `__init__` + `generate_structured` 入口 | `MockProvider` |
| Gemini API 调用（`google.genai` API key） | `_generate_with_gemini` | `GeminiProvider` |
| Vertex AI 调用（`google.genai` Vertex 模式） | `_generate_with_vertex` | `GeminiProvider`（Vertex 子模式） |
| `_RETRYABLE_PARSE_HINTS` 单次重试 | `_generate_with_retry` | Provider 内部（保留现有策略） |
| JSON repair + 错误分类 | `_classify_model_error` / `_parse_json_text` | 公共 utility（Provider-agnostic） |
| `model_trace` 拼装 | `generate_structured` 返回字段 | `ModelClient` Facade 仍负责 |

### 2.2 27 处调用点（按类型分组）

- 画像 6 Skill explainer：`app_profile / behavior_profile / credit_profile / comprehensive / product_advice / ops_advice`
- Trace 模块：`trace_analyzer/explainer.py`
- data_acquisition_agent：`orchestrator.py` 内部 `ModelClient` 调用
- 其余：测试 fixture / mock 注入点（约 18 处）

### 2.3 270 测试覆盖

- mock 模式：所有 Skill 单测（默认走 mock）
- vertex 模式：手动验证脚本 + Golden Test fixture
- 153 data_acquisition 测试：`mock_llm` fixture，绝对不能受影响

## 3. 设计原则

1. **Karpathy Surgical Changes**：不该改的不改。`ModelClient` 公开签名一字不改，调用点零修改即可受益于新 Provider。
2. **接口先于实现**：先定义 `LLMProvider` Protocol，再实装 Provider，最后让 `ModelClient` 委托给 Provider。
3. **Provider Capability 显式化**：`supports_streaming` / `supports_json_mode` / `max_context_tokens` / `supports_tools` 写在元数据里，路由决策不靠隐式假设。
4. **mock 模式始终可用**：测试和本地开发不依赖任何外部网络。
5. **fallback 链显式声明**：Provider A 失败 → Provider B，写在配置里，不写死在代码里。

## 4. 接口设计

### 4.1 `LLMProvider` Protocol

```python
# app/core/providers/base.py（重构后新建）
from typing import Protocol, Any, Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapability:
    supports_streaming: bool
    supports_json_mode: bool
    max_context_tokens: int
    supports_tools: bool


class LLMProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    @property
    def capability(self) -> ProviderCapability: ...

    def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]: ...

    def generate_text(
        self,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str: ...

    def stream(self, prompt: str) -> Iterator[str]: ...

    def count_tokens(self, text: str) -> int: ...
```

### 4.2 `ProviderCapability` 枚举

| 字段 | Mock | Gemini | ClaudeMaestro |
|---|---|---|---|
| `supports_streaming` | False | True | True |
| `supports_json_mode` | True | True | True（tool_use 模拟） |
| `max_context_tokens` | 100K | 1M（Gemini 2.5 flash） | 1M（Opus 4.7 10x tier）/ 200K（45x tier） |
| `supports_tools` | False | True | True |

### 4.3 `ModelClient` Facade（向后兼容）

```python
# app/core/model_client.py（重构后保留同名，签名一字不改）
class ModelClient:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.mode = settings.model_mode
        self._provider = provider or _build_default_provider(self.mode)
        # 其他属性（model_name / api_key 等）保留，避免外部代码引用断裂

    def generate_structured(
        self,
        skill_name: str,
        prompt: str,
        fallback_result: dict[str, Any],
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        # 内部委托给 self._provider.generate_json()
        # 外层包装 status / structured_result / model_name / prompt_preview / model_trace
        ...
```

## 5. Provider 实现规范

### 5.1 `GeminiProvider`

- 封装现有 `_generate_with_gemini` + `_generate_with_vertex` 代码（不改实现细节）
- 通过构造参数区分 API key 模式 vs Vertex 模式
- `provider_name = "gemini"`

### 5.2 `ClaudeMaestroProvider`

- 通过 Agent Maestro 端点调 Claude Opus 4.7
- 端点 URL / 认证 token / 协议（OpenAI 兼容 vs Anthropic 原生）标 `[Spike Pending]`，由 Plan #03 Phase 0 Task 0.2 Maestro Spike 跑通后回填
- `provider_name = "claude_maestro"`

### 5.3 `MockProvider`

- 行为与现有 `ModelClient.mode == "mock"` 分支完全一致
- 用于测试和本地无凭据开发
- `provider_name = "mock"`

## 6. Provider 选择策略

### 6.1 配置驱动

`config.yaml` 新增段（本 Doc 只规范契约，**不在本期落地**——Plan #02 才真正引入新配置）：

```yaml
llm:
  providers:
    gemini:
      mode: vertex          # api_key | vertex
      model: gemini-2.5-flash
    claude_maestro:
      endpoint: "[Spike Pending]"
      model: claude-opus-4.7
      tier: 10x             # 10x | 45x
    mock:
      enabled_in: ["test", "local"]
  routes:                   # 调用点级路由（Plan #02 落地）
    default: gemini
```

### 6.2 调用点路由表

本 Doc 不直接引入 `routes` 配置；只规范 `LLMProvider` 接口。具体路由（哪个 Skill 走哪个 Provider）由 Plan #02 落地。

### 6.3 环境变量兜底

`MODEL_MODE` 维持现有 mock / vertex / gemini 三档语义。当 `MODEL_MODE=mock` 时，`_build_default_provider` 返回 `MockProvider`，绕过任何路由表。

## 7. Resilience 与 Fallback

### 7.1 tenacity retry

保留现有 `_RETRYABLE_PARSE_HINTS` 触发的单次重试，迁移到 Provider 内部。

### 7.2 Provider 间 fallback 链

- `ClaudeMaestroProvider` 抛 `ProviderUnavailable` → 调用方捕获 → 切到 `GeminiProvider`
- 降级日志：`logger.warning("provider_fallback from=%s to=%s reason=%s", ...)`
- 调用方拿到的 `model_trace.provider` 字段反映实际使用的 Provider，便于前端展示降级状态

### 7.3 Token 预算 hook

- 每次调用结束后通过 `provider.count_tokens(prompt) + count_tokens(reply)` 上报
- `ModelClient` 暴露 `last_token_usage` 属性供 Orchestrator 层累加（per-session 500K 硬阻断在 Orchestrator 层做，本 Doc 只暴露 hook）

## 8. JSON Repair / Structured Output 兼容

### 8.1 共享工具

把现有 `_parse_json_text` / `_classify_model_error` 抽到 `app/core/providers/json_repair.py`，对所有 Provider 通用。

### 8.2 Provider 各自适配

| Provider | JSON 模式 | Repair 入口 |
|---|---|---|
| Gemini | `responseSchema` + `response_mime_type="application/json"` | 现有 retry prompt 拼接 |
| ClaudeMaestro | `tool_use` 强制结构化输出 | 解析 `tool_use.input` JSON；解析失败走 repair prompt 重试 |
| Mock | 直接返回 `fallback_result` | 不需要 repair |

## 9. 测试策略

### 9.1 Provider 接口契约测试

新建 `tests/test_provider_contract.py`：
- 同一组 case（包含 happy path / json parse 失败 / max tokens 截断）跑过每个 Provider
- 断言 `generate_json` 返回值结构一致

### 9.2 调用点回归矩阵

新建 `tests/test_model_client_facade.py`：
- 注入 `MockProvider` 跑现有 `ModelClient.generate_structured` 调用，断言外层包装字段（`status` / `structured_result` / `model_name` / `prompt_preview`）与重构前完全一致

### 9.3 270 测试零改动验证

CI 红线：跑 `python -m pytest tests/ -v` + `python -m pytest data_acquisition_agent/tests/ -v`，270 + 153 全过。

## 10. 迁移路径与风险

### 10.1 调用点改动 ≤ 5%

如果重构后必须修改 > 14 处调用点（27 × 5% ≈ 1.4，向上取整为 2-3 处），说明抽象设计不够好（Facade 不透明），需要回到 § 4.3 重新设计 Facade 签名。

### 10.2 mock 注入

`ModelClient.__init__` 接受可选 `provider` 参数，方便测试注入 `MockProvider` 的子类（用于断言调用次数 / 参数）。避免触发真实 API。

### 10.3 风险

- `ClaudeMaestroProvider` 端点协议未知（Maestro Spike 阻塞）。在 Plan #03 Phase 0 Task 0.2 跑通前，本 Doc 中所有 Maestro 字段标 `[Spike Pending]`，不做假设性规约。
- JSON repair 在 Claude `tool_use` 模式下可能不需要——保留 repair 入口但允许 Provider 跳过。

## 11. 不在本期范围（Out of Scope）

- 不改任何 prompt 文件内容
- 不切换具体调用点的 Provider 路由（哪个 Skill 用哪个 Provider 是另一个 Plan 的事）
- 不引入 `langchain` / `anthropic` SDK 直依赖；统一走 Maestro 端点
- 不动 `data_acquisition_agent/` 任何文件（含测试）
- 不改 `MODEL_MODE` 环境变量语义
- 不在本 Doc 落地 Orchestrator Agent / 前端 Tab / Eval 框架（各自有独立 Doc）
