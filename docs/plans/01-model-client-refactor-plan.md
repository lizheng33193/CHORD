# Plan #01 — ModelClient 多 Provider 重构

| 项 | 值 |
|---|---|
| 状态 | Pending（等待执行） |
| Design Doc | docs/specs/01-model-client-refactor-design.md |
| 依赖 | 无 |
| 后继 | Plan #02 / Plan #03 都依赖此 Plan 完成 |
| Phase 数 | 4（含 Phase 0 baseline） |
| Commit 策略 | 每 Phase 1 commit，最后一个标 `[complete] model-client-refactor` |

---

## Scope

**本 Plan 做**：
- 创建 `LLMProvider` Protocol + 共享元数据（`ProviderCapability` / `ProviderUnavailable`）
- `MockProvider`（真实实装）+ `GeminiProvider`（Phase 1 stub → Phase 2 真实代码迁入）
- `ModelClient` Facade 重构（保持 `generate_structured` 签名一字不改，27 个调用点零回归）
- `fallback_chain` helper + `last_token_usage` 三字段统计
- 至少 11 个 Provider 相关测试（5 contract + 2 facade + 2 fallback + ≥2 其它）

**本 Plan 不做**（明确边界，防 AI 越界）：
- 不切换任何 explainer 到 Claude（Plan #02 的事）
- 不创建 `ClaudeMaestroProvider`（Plan #02 Phase 1 的事——本 Plan `_build_default_provider` 仅做 try-import 隔离）
- 不动 `data_acquisition_agent/**`（Surgical Hard Boundary）
- 不动 `config.yaml` 业务条目（Plan #02 Task 1.1 的事）
- 不引入 SSE / async 接口（Plan #03 之后再说）

## 期望最终行为（Worked Example）

执行完 Phase 3 后，下面调用必须能跑：

```python
from app.core.model_client import ModelClient
from app.core.providers.mock_provider import MockProvider

client = ModelClient(provider=MockProvider())
out = client.generate_structured(
    skill_name="test_skill",
    prompt="hello world",
    fallback_result={"fallback": True},
)
# out == {
#   "status": "ok",
#   "structured_result": {"_mock": True, "prompt_preview": "hello world"},
#   "model_name": <settings.resolved_model_name>,
#   "prompt_preview": "hello world",
# }
# client.last_token_usage == {"prompt": >0, "completion": >0, "total": >0}
```

## 已知风险与开放问题

1. **跨 Plan 共享文件**：`app/core/providers/json_repair.py` 在本 Plan Phase 2 创建；Plan #02 Task 2.2 也声明创建——Plan #02 已加"前置检查跳过"逻辑。本 Plan 单跑无影响。
2. **Phase 2 契约语义反转**：`tests/test_provider_contract.py::test_gemini_provider_phase1_raises_unavailable` 在 Phase 1 断言 stub 抛错；Phase 2 把它改名为 `test_gemini_provider_unavailable_when_credentials_missing`（凭证缺失才抛错）——见 Task 2.4。
3. **fallback_chain 无凭证退化**：`_build_default_provider` 在 vertex 模式下 try-import `ClaudeMaestroProvider`，失败时退回纯 Gemini，单测用 monkeypatch 覆盖。Plan #01 单跑时 Plan #02 文件不存在，会自动走纯 Gemini 路径。
4. **`last_token_usage` 初始化时机**：Phase 2 改造 `__init__` 时立刻初始化为 `{"prompt": 0, "completion": 0, "total": 0}`，避免 `_record_usage` 调用前 `client.last_token_usage` 触发 `AttributeError`。Phase 3 只新增 `_record_usage` 方法和成功路径调用点。

## 修订记录

- R5.1 (2026-05-02) — Phase 3 同样改为 TDD RED→GREEN：Task 3.1 fallback 测试前置，Task 3.2 才加 `fallback_chain` helper；Task 3.3 token hook + generate_structured；Task 3.4 全量回归；Task 3.5 [complete] commit。三个 Phase 全部对齐 TDD 铁律。
- R5 (2026-05-02) — 按 Vibe Coding 方法论五点检查法收口：
  - 补 Scope / Worked Example / 已知风险 / 修订记录 段
  - Phase 1 重排为 TDD RED→GREEN 顺序（契约测试前置）
  - Phase 2 重排为 TDD RED→GREEN 顺序（Facade 测试前置）+ Task 2.2 拆为 2.2/2.3/2.4
  - 每 Task 加独立验证命令 + 期望输出
  - Task 3.2 给 `generate_structured` 完整最终版（不再"末尾调"口述）
  - `last_token_usage` 初始化前置到 Phase 2 Task 2.2
  - 修正 Phase 1 commit message（明确 Mock real / Gemini stub）
- R4 (2026-04-30) — P0-C: `_build_default_provider` 内嵌 fallback_chain 自动包装；P1-A: contract test 改"凭证缺失"语义；P0-A 跨 Plan json_repair 去重
- R3 (2026-04-29) — 自审 9/9 PASS，无代码变更
- R2 (2026-04-28) — 修补 18 个 P0 + 9 个 P1
- R1 (2026-04-27) — R1 修订
- R0 (2026-04-26) — 初始版本

---

## Phase 0 — Baseline

### Task 0.1 — 跑现有测试基线 + commit baseline

**操作步骤**：

```powershell
cd C:\Users\v-yimingliu\agent-userprofile\CHORD
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v
git status
# Phase 0 仅跑测试、不改代码，所以 git status 可能干净；必须加 --allow-empty 避免 commit abort。
git commit --allow-empty -m "[baseline] model-client-refactor"
```

**期望输出**：
- `tests/` → 270 passed
- `data_acquisition_agent/tests/` → 153 passed, 1 skipped
- `git status` 干净
- baseline commit 创建

**验证命令**：
```powershell
git log -1 --oneline
# 期望：[baseline] model-client-refactor
```

---

## Phase 1 — TDD 实装 LLMProvider Protocol + Mock + Gemini Provider

> **TDD 铁律**：先写契约测试看 RED → 再创建 Provider 把测试转 GREEN → 提交。
> 违反此顺序（先实现后补测试）的方案直接打回。

### Task 1.1 — RED：先写契约测试（必失败）

**新建文件**：`tests/test_provider_contract.py`

**完整代码**：

```python
"""Provider接口契约测试 — 确保所有Provider 遵循 LLMProvider Protocol。"""

from __future__ import annotations

import pytest

from app.core.providers import LLMProvider, ProviderUnavailable
from app.core.providers.mock_provider import MockProvider
from app.core.providers.gemini_provider import GeminiProvider


@pytest.fixture(params=["mock", "gemini"])
def provider(request) -> LLMProvider:
    if request.param == "mock":
        return MockProvider()
    return GeminiProvider(mode="gemini")


def test_provider_implements_protocol(provider: LLMProvider) -> None:
    assert isinstance(provider, LLMProvider)
    assert provider.provider_name in {"mock", "gemini"}


def test_provider_capability_shape(provider: LLMProvider) -> None:
    cap = provider.capability
    assert isinstance(cap.supports_streaming, bool)
    assert isinstance(cap.supports_json_mode, bool)
    assert isinstance(cap.max_context_tokens, int)
    assert cap.max_context_tokens > 0
    assert isinstance(cap.supports_tools, bool)


def test_provider_count_tokens_returns_positive(provider: LLMProvider) -> None:
    assert provider.count_tokens("hello world") >= 1


def test_mock_provider_generate_json_returns_canned() -> None:
    p = MockProvider()
    out = p.generate_json("prompt", response_schema=None)
    assert out["_mock"] is True


def test_gemini_provider_phase1_raises_unavailable() -> None:
    """Phase 1 契约：GeminiProvider stub 抛 ProviderUnavailable。
    Phase 2 Task 2.4 会把此用例改名为 test_gemini_provider_unavailable_when_credentials_missing。"""
    p = GeminiProvider(mode="gemini")
    with pytest.raises(ProviderUnavailable):
        p.generate_json("prompt")
```

**验证命令**：

```powershell
python -m pytest tests/test_provider_contract.py -v
```

**期望输出**：5 errors（`ImportError: cannot import name 'LLMProvider' from 'app.core.providers'` 或 `ModuleNotFoundError`）。**必须看到失败**——这是 RED 状态，证明测试在驱动实装而不是事后追认。

### Task 1.2 — GREEN：创建 `app/core/providers/__init__.py` + `base.py`

**新建文件**：
- `app/core/providers/__init__.py`
- `app/core/providers/base.py`

**`base.py` 完整代码**：

```python
"""LLMProvider Protocol and shared capability metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterator, Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderCapability:
    """Provider feature flags consumed by routing decisions."""

    supports_streaming: bool
    supports_json_mode: bool
    max_context_tokens: int
    supports_tools: bool


class ProviderUnavailable(Exception):
    """Raised when a Provider cannot serve the call (network / auth / quota)."""


@runtime_checkable
class LLMProvider(Protocol):
    """Provider-agnostic LLM interface."""

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

**`__init__.py` 内容**：

```python
"""LLM Provider abstraction layer."""

from app.core.providers.base import (
    LLMProvider,
    ProviderCapability,
    ProviderUnavailable,
)

__all__ = ["LLMProvider", "ProviderCapability", "ProviderUnavailable"]
```

**验证命令**：

```powershell
python -m pytest tests/test_provider_contract.py -v
```

**期望输出**：仍 5 errors，但错误类型变成 `ModuleNotFoundError: No module named 'app.core.providers.mock_provider'`（base import 已通；mock/gemini 子模块还没建）。

### Task 1.3 — GREEN：创建 `mock_provider.py`

**新建文件**：`app/core/providers/mock_provider.py`

**完整代码**：

```python
"""Mock provider for tests and local-no-credential development."""

from __future__ import annotations

from typing import Any, Iterator

from app.core.providers.base import LLMProvider, ProviderCapability


class MockProvider(LLMProvider):
    """Returns canned fallback results, never touches the network."""

    def __init__(self, model_name: str = "mock-model") -> None:
        self._model_name = model_name

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=False,
            supports_json_mode=True,
            max_context_tokens=100_000,
            supports_tools=False,
        )

    def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        return {"_mock": True, "prompt_preview": prompt[:200]}

    def generate_text(
        self,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str:
        return f"[mock] {prompt[:200]}"

    def stream(self, prompt: str) -> Iterator[str]:
        yield f"[mock] {prompt[:200]}"

    def count_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
```

**验证命令**：

```powershell
python -m pytest tests/test_provider_contract.py -v
```

**期望输出**：mock 相关用例转 PASS（`test_provider_implements_protocol[mock]` / `test_provider_capability_shape[mock]` / `test_provider_count_tokens_returns_positive[mock]` / `test_mock_provider_generate_json_returns_canned`），gemini 相关用例仍 ERROR（`ModuleNotFoundError: No module named 'app.core.providers.gemini_provider'`）。

### Task 1.4 — GREEN：创建 `gemini_provider.py`（Phase 1 stub）

**新建文件**：`app/core/providers/gemini_provider.py`

**完整代码**：

```python
"""Gemini / Vertex provider — Phase 1 stub. Real impl migrated in Phase 2."""

from __future__ import annotations

import os
from typing import Any, Iterator

from app.core.config import settings
from app.core.logger import get_logger
from app.core.providers.base import LLMProvider, ProviderCapability, ProviderUnavailable


logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    """Gemini API key mode + Vertex AI mode wrapped behind LLMProvider."""

    def __init__(self, mode: str = "gemini") -> None:
        if mode not in {"gemini", "vertex", "vertexai", "gemini-vertex"}:
            raise ValueError(f"GeminiProvider unsupported mode={mode}")
        self.mode = mode
        self.model_name = settings.resolved_model_name
        self.api_key = settings.resolved_gemini_api_key
        self.vertex_project_id = settings.vertex_project_id
        self.vertex_location = settings.vertex_location
        creds = settings.resolved_google_application_credentials
        if creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=True,
            supports_json_mode=True,
            max_context_tokens=1_000_000,
            supports_tools=True,
        )

    def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        # Phase 1 stub. Real impl migrated in Phase 2 Task 2.3.
        # 显式契约：Phase 1 永远抛 ProviderUnavailable，让契约测试可以验证错误路径
        # 而不触发真实 API 调用。Phase 2 真实代码迁入后，此分支只有"凭证缺失"才抛。
        raise ProviderUnavailable("GeminiProvider real impl migrated in Phase 2")

    def generate_text(
        self,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str:
        raise ProviderUnavailable("GeminiProvider real impl migrated in Phase 2")

    def stream(self, prompt: str) -> Iterator[str]:
        raise ProviderUnavailable("GeminiProvider streaming migrated in Phase 2")

    def count_tokens(self, text: str) -> int:
        # Phase 1 naive 估算；Phase 2 改为 google-genai client.models.count_tokens。
        return max(1, len(text) // 4)
```

**验证命令**：

```powershell
python -m pytest tests/test_provider_contract.py -v
```

**期望输出**：5 passed。RED → GREEN 转换完成。

### Task 1.5 — Phase 1 commit

```powershell
git add -A
git commit -m "feat(provider): LLMProvider Protocol + MockProvider real impl + GeminiProvider Phase1 stub + 5 contract tests [TDD red->green]"
```

> commit message 明确说明 Mock 是 real impl、Gemini 是 stub，避免后续 review 误解为两个都是 skeleton。

---

## Phase 2 — TDD 实装 ModelClient Facade + Gemini 真实代码迁移

> **TDD 顺序**：先写 Facade 行为测试看 RED → 改 ModelClient 看 GREEN → 迁移 Gemini 真实代码 → 反转契约测试语义 → 全量回归 → 提交。

### Task 2.1 — RED：先写 Facade 行为测试（必失败）

**新建文件**：`tests/test_model_client_facade.py`

**完整代码**：

```python
"""Verify ModelClient Facade preserves backward-compatible behavior."""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from app.core.model_client import ModelClient
from app.core.providers.base import LLMProvider, ProviderCapability


class _FakeProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "fake"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=False,
            supports_json_mode=True,
            max_context_tokens=8192,
            supports_tools=False,
        )

    def generate_json(self, prompt, response_schema=None, max_output_tokens=None):
        return {"echo": prompt[:50]}

    def generate_text(self, prompt, max_output_tokens=None):
        return prompt[:50]

    def stream(self, prompt: str) -> Iterator[str]:
        yield prompt[:50]

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_model_client_accepts_injected_provider() -> None:
    client = ModelClient(provider=_FakeProvider())
    out = client.generate_structured(
        skill_name="test_skill",
        prompt="hello world",
        fallback_result={"fallback": True},
    )
    assert out["status"] == "ok"
    assert out["structured_result"] == {"echo": "hello world"}
    assert "model_name" in out
    assert "prompt_preview" in out


def test_model_client_default_mock_mode(monkeypatch) -> None:
    monkeypatch.setenv("MODEL_MODE", "mock")
    from app.core.config import Settings
    monkeypatch.setattr("app.core.model_client.settings", Settings())
    client = ModelClient()
    out = client.generate_structured("s", "p", {})
    assert out["status"] == "ok"
```

**验证命令**：

```powershell
python -m pytest tests/test_model_client_facade.py -v
```

**期望输出**：2 个测试均 FAIL（`TypeError: __init__() got an unexpected keyword argument 'provider'`）。**必须看到失败**——这是 RED 状态。

### Task 2.2 — GREEN：改造 `ModelClient.__init__` 接受 provider 注入 + `_build_default_provider`

**修改文件**：`app/core/model_client.py`

**改造 `__init__` 完整最终版**（替换现有 `__init__`）：

```python
def __init__(self, provider: LLMProvider | None = None) -> None:
    self.mode = settings.model_mode
    self.model_name = settings.resolved_model_name
    self.api_key = settings.resolved_gemini_api_key
    self.vertex_project_id = settings.vertex_project_id
    self.vertex_location = settings.vertex_location
    creds = settings.resolved_google_application_credentials
    if creds:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds
    self._provider = provider or _build_default_provider(self.mode)
    # R5: 提前初始化避免 Phase 3 _record_usage 调用前 AttributeError。
    # Plan #03 Phase 2 budget 模块直接读 self.last_token_usage["total"]。
    self.last_token_usage: dict[str, int] = {"prompt": 0, "completion": 0, "total": 0}
```

**新增模块级函数 `_build_default_provider`**（放在 `class ModelClient` 之前）：

```python
def _build_default_provider(mode: str) -> LLMProvider:
    if mode == "mock":
        from app.core.providers.mock_provider import MockProvider
        return MockProvider()
    if mode in {"gemini", "vertex", "vertexai", "gemini-vertex"}:
        from app.core.providers.gemini_provider import GeminiProvider
        gemini = GeminiProvider(mode=mode)
        # R4 P0-C: vertex 模式且 Plan #02 已完成（claude_maestro endpoint 真实回填）时，
        # 自动包装 fallback_chain(claude → gemini)。
        # try-import 隔离：Plan #01 单跑时 ClaudeMaestroProvider 文件不存在也不影响。
        if mode in {"vertex", "vertexai", "gemini-vertex"}:
            try:
                from app.core.providers.claude_maestro_provider import ClaudeMaestroProvider
                from app.core.config import get_llm_config
                from app.core.providers.base import fallback_chain
                cfg = get_llm_config()
                ep = cfg.get("providers", {}).get("claude_maestro", {}).get("endpoint", "")
                if ep and ep != "[Spike Pending]":
                    claude = ClaudeMaestroProvider()
                    return fallback_chain(
                        claude, gemini,
                        on_fallback=lambda f, t, e: logger.warning(
                            "provider_fallback %s→%s: %s", f, t, e
                        ),
                    )
            except Exception:
                # ClaudeMaestroProvider 不存在 / config 未配 / 凭证缺失 → 退回纯 Gemini
                pass
        return gemini
    raise ValueError(f"Unsupported MODEL_MODE={mode}")
```

**model_client.py 顶部 import 补**（如已存在则跳过）：

```python
from app.core.logger import get_logger
from app.core.providers.base import LLMProvider

logger = get_logger(__name__)
```

> `fallback_chain` Phase 3 Task 3.1 才创建；本 Task 的 `_build_default_provider` 内部 try-import 已隔离失败路径，所以 Phase 2 单跑时 vertex 模式会走"退回纯 Gemini"分支，不报错。

**`generate_structured` 内部委托改造**：定位 `_generate_with_retry(...)` 调用点，整段替换为：

```python
structured_result = self._provider.generate_json(
    prompt,
    response_schema=response_schema,
)
```

> Phase 2 暂不调 `_record_usage`（该方法 Phase 3 Task 3.2 才创建）；本 Task 仅完成 Provider 委托。`generate_structured` 完整最终版见 Phase 3 Task 3.2。

**验证命令**：

```powershell
python -m pytest tests/test_model_client_facade.py -v
```

**期望输出**：2 passed。RED → GREEN 转换完成。

### Task 2.3 — 把 Gemini 真实代码迁到 `GeminiProvider` + 抽 `json_repair.py`

**新建文件**：`app/core/providers/json_repair.py`

**完整代码**（把 `model_client.py` 现有 `_parse_json_text` / `_repair_json_candidate` / `_RETRYABLE_PARSE_HINTS` 等纯函数迁过来）：

```python
"""JSON repair helpers — extracted from model_client._parse_json_text.

Pure functions, no LLM client dependency. Shared by GeminiProvider
(and any future Provider needing JSON repair on imperfect model output).
"""

from __future__ import annotations

import json
import re
from typing import Any


RETRYABLE_PARSE_HINTS: tuple[str, ...] = (
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


def _strip_code_fence(text: str) -> str:
    """Remove ```json ... ``` or ``` ... ``` fences if present."""
    text = text.strip()
    if text.startswith("```"):
        # 去掉首行 ```json / ```
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _repair_json_candidate(text: str) -> str:
    """Lightweight repair: strip trailing commas, fix common quote issues."""
    # 去掉 } 或 ] 前的尾随逗号
    text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def parse_json_text(text: str) -> dict[str, Any]:
    """Parse model text output as JSON, with code-fence stripping and repair retry.

    Raises ValueError with hint matching RETRYABLE_PARSE_HINTS on failure,
    so caller's tenacity retry can catch.
    """
    if not text or not text.strip():
        raise ValueError("Model response did not include text content")
    cleaned = _strip_code_fence(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        # 尝试修复
        try:
            repaired = _repair_json_candidate(cleaned)
            return json.loads(repaired)
        except json.JSONDecodeError as exc2:
            raise ValueError(f"json_repair_failed: {exc2}") from exc2
```

> 如果 baseline 的 `_parse_json_text` 实现比上面更复杂（如带额外的 brace-matching），把 baseline 的完整实现直接搬过来；保持函数名 `parse_json_text` 即可。

**修改文件**：`app/core/providers/gemini_provider.py`

**完整最终版**（替换 Phase 1 stub，整个文件覆盖）：

```python
"""Gemini / Vertex provider — Phase 2 real impl migrated from model_client.py."""

from __future__ import annotations

import os
from typing import Any, Iterator

from tenacity import (
    retry,
    retry_if_exception_message,
    stop_after_attempt,
    wait_fixed,
)

from app.core.config import settings
from app.core.logger import get_logger
from app.core.providers.base import LLMProvider, ProviderCapability, ProviderUnavailable
from app.core.providers.json_repair import RETRYABLE_PARSE_HINTS, parse_json_text


logger = get_logger(__name__)


class GeminiProvider(LLMProvider):
    """Gemini API key mode + Vertex AI mode wrapped behind LLMProvider."""

    def __init__(self, mode: str = "gemini") -> None:
        if mode not in {"gemini", "vertex", "vertexai", "gemini-vertex"}:
            raise ValueError(f"GeminiProvider unsupported mode={mode}")
        self.mode = mode
        self.model_name = settings.resolved_model_name
        self.api_key = settings.resolved_gemini_api_key
        self.vertex_project_id = settings.vertex_project_id
        self.vertex_location = settings.vertex_location
        creds = settings.resolved_google_application_credentials
        if creds:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(
            supports_streaming=True,
            supports_json_mode=True,
            max_context_tokens=1_000_000,
            supports_tools=True,
        )

    def _build_client(self):
        from google import genai
        if self.mode == "gemini":
            if not self.api_key:
                raise ProviderUnavailable("GEMINI_API_KEY is missing")
            return genai.Client(api_key=self.api_key)
        # vertex / vertexai / gemini-vertex
        if not self.vertex_project_id:
            raise ProviderUnavailable("VERTEX_PROJECT_ID is missing for MODEL_MODE=vertex")
        if not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            raise ProviderUnavailable(
                "GOOGLE_APPLICATION_CREDENTIALS is missing; point it to your service account key.json"
            )
        return genai.Client(
            vertexai=True,
            project=self.vertex_project_id,
            location=self.vertex_location,
        )

    def _build_config(self, response_schema, max_output_tokens):
        from google.genai import types
        config_kwargs: dict[str, Any] = {
            "response_mime_type": "application/json",
            "temperature": 0,
        }
        resolved = max_output_tokens if max_output_tokens is not None else settings.model_max_output_tokens
        if resolved:
            config_kwargs["max_output_tokens"] = resolved
        if response_schema:
            config_kwargs["response_json_schema"] = response_schema
        config_cls = getattr(types, "GenerateContentConfig", None)
        if not config_cls:
            return config_kwargs
        try:
            return config_cls(**config_kwargs)
        except TypeError as exc:
            if "max_output_tokens" in str(exc):
                cleaned = dict(config_kwargs)
                cleaned.pop("max_output_tokens", None)
                return config_cls(**cleaned)
            raise

    @retry(
        stop=stop_after_attempt(2),
        wait=wait_fixed(0.5),
        retry=retry_if_exception_message(match="|".join(RETRYABLE_PARSE_HINTS)),
        reraise=True,
    )
    def generate_json(
        self,
        prompt: str,
        response_schema: dict[str, Any] | None = None,
        max_output_tokens: int | None = None,
    ) -> dict[str, Any]:
        try:
            client = self._build_client()
            response = client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=self._build_config(response_schema, max_output_tokens),
            )
            logger.info("gemini transport ok mode=%s model=%s", self.mode, self.model_name)
            parsed = getattr(response, "parsed", None)
            if isinstance(parsed, dict):
                return parsed
            text = getattr(response, "text", None) or self._extract_text_from_response(response)
            return parse_json_text(str(text))
        except ProviderUnavailable:
            raise
        except Exception as exc:
            message = str(exc)
            if any(hint in message for hint in RETRYABLE_PARSE_HINTS):
                logger.warning("gemini retryable parse error: %s", message)
                raise
            logger.warning("gemini call failed mode=%s: %s", self.mode, message)
            raise ProviderUnavailable(message) from exc

    def generate_text(
        self,
        prompt: str,
        max_output_tokens: int | None = None,
    ) -> str:
        try:
            client = self._build_client()
            from google.genai import types
            config_cls = getattr(types, "GenerateContentConfig", None)
            cfg_kwargs: dict[str, Any] = {"temperature": 0}
            if max_output_tokens:
                cfg_kwargs["max_output_tokens"] = max_output_tokens
            cfg = config_cls(**cfg_kwargs) if config_cls else cfg_kwargs
            response = client.models.generate_content(
                model=self.model_name, contents=prompt, config=cfg,
            )
            return getattr(response, "text", None) or self._extract_text_from_response(response)
        except ProviderUnavailable:
            raise
        except Exception as exc:
            raise ProviderUnavailable(str(exc)) from exc

    def stream(self, prompt: str) -> Iterator[str]:
        # Phase 2 暂不实装 streaming（baseline model_client 也未启用），保留显式契约。
        # Plan #03 之后如启用 SSE，再覆盖此方法。
        raise ProviderUnavailable("GeminiProvider.stream not implemented")

    def count_tokens(self, text: str) -> int:
        # google-genai 提供 client.models.count_tokens；失败退回 naive 估算。
        try:
            client = self._build_client()
            resp = client.models.count_tokens(model=self.model_name, contents=text)
            return int(getattr(resp, "total_tokens", None) or max(1, len(text) // 4))
        except Exception:
            return max(1, len(text) // 4)

    def _extract_text_from_response(self, response: Any) -> str:
        candidates = getattr(response, "candidates", None) or []
        text_parts: list[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                t = getattr(part, "text", None)
                if t:
                    text_parts.append(str(t))
        if not text_parts:
            raise ValueError("Model response candidates were empty")
        return "\n".join(text_parts)
```

**修改文件**：`app/core/model_client.py`

**删除以下私有方法**（已迁出到 GeminiProvider / json_repair.py）：
- `_generate_with_gemini`
- `_generate_with_vertex`
- `_generate_with_retry`
- `_parse_json_text`
- `_repair_json_candidate`（如有）
- `_extract_text_from_response`（如有）
- `_RETRYABLE_PARSE_HINTS`（模块级常量）

> `tenacity` 已在 `requirements.txt`；如缺失先 `pip install tenacity`。

**验证命令**：

```powershell
python -m pytest tests/test_provider_contract.py tests/test_model_client_facade.py -v
```

**期望输出**：
- `test_provider_contract.py::test_gemini_provider_phase1_raises_unavailable` 现在变成 **FAIL**（因为 Gemini stub 已经不在了，真实 generate_json 在凭证缺失时才抛 ProviderUnavailable，但 fixture 不一定能保证清空凭证）—— 这是预期的 RED，Task 2.4 修复
- 其它 4 个 contract 测试 PASS
- 2 个 facade 测试 PASS

### Task 2.4 — 反转契约测试语义（Phase 1 stub 测试 → Phase 2 凭证缺失测试）

**修改文件**：`tests/test_provider_contract.py`

**操作**：删除 `test_gemini_provider_phase1_raises_unavailable` 函数，替换为：

```python
def test_gemini_provider_unavailable_when_credentials_missing(monkeypatch) -> None:
    """Phase 2 后契约：凭证缺失时 GeminiProvider 抛 ProviderUnavailable。"""
    from app.core.providers.gemini_provider import GeminiProvider
    from app.core.providers.base import ProviderUnavailable
    monkeypatch.setattr(
        "app.core.providers.gemini_provider.settings.resolved_gemini_api_key",
        "",
        raising=False,
    )
    monkeypatch.delenv("GOOGLE_APPLICATION_CREDENTIALS", raising=False)
    p = GeminiProvider(mode="gemini")
    with pytest.raises(ProviderUnavailable):
        p.generate_json("prompt")
```

**验证命令**：

```powershell
python -m pytest tests/test_provider_contract.py -v
```

**期望输出**：5 passed（4 原始 + 1 反转后的新测试）。

### Task 2.5 — 全量回归

**验证命令**：

```powershell
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v
```

**期望输出**：
- `tests/` → 270 + 7 (Phase 1+2 累计新增) = 277 passed
- `data_acquisition_agent/tests/` → 153 passed (1 skipped)
- 零回归

**回滚条件**：如果 `tests/` 出现非新增测试的失败（即原 270 中有失败），立即 `git reset --hard <Phase 1 commit hash>`，回到 Phase 1 末态，重新设计 Facade 委托逻辑（很可能是 `generate_structured` 的错误处理路径或 `_classify_model_error` 等旁路漏迁）。

### Task 2.6 — Phase 2 commit

```powershell
git add -A
git commit -m "refactor(model_client): delegate to LLMProvider + migrate Gemini real impl + extract json_repair [TDD red->green]"
```

---

## Phase 3 — TDD 实装 fallback_chain + Token hook + 收尾

> **TDD 顺序**：先写 fallback 测试看 RED → 加 fallback_chain helper 看 GREEN → token hook + generate_structured 完整版 → 全量回归 → 提交。

### Task 3.1 — RED：先写 fallback 测试（必失败）

**新建文件**：`tests/test_provider_fallback.py`

**完整代码**：

```python
"""Verify fallback_chain switches to secondary on ProviderUnavailable."""

from __future__ import annotations

from typing import Iterator

from app.core.providers.base import (
    LLMProvider,
    ProviderCapability,
    ProviderUnavailable,
    fallback_chain,
)


class _FailingProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "failing"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(False, True, 1024, False)

    def generate_json(self, prompt, response_schema=None, max_output_tokens=None):
        raise ProviderUnavailable("test")

    def generate_text(self, prompt, max_output_tokens=None):
        raise ProviderUnavailable("test")

    def stream(self, prompt: str) -> Iterator[str]:
        raise ProviderUnavailable("test")

    def count_tokens(self, text: str) -> int:
        return len(text)


class _OkProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "ok"

    @property
    def capability(self) -> ProviderCapability:
        return ProviderCapability(False, True, 1024, False)

    def generate_json(self, prompt, response_schema=None, max_output_tokens=None):
        return {"ok": True}

    def generate_text(self, prompt, max_output_tokens=None):
        return "ok"

    def stream(self, prompt: str) -> Iterator[str]:
        yield "ok"

    def count_tokens(self, text: str) -> int:
        return len(text)


def test_fallback_chain_switches_on_unavailable() -> None:
    chained = fallback_chain(_FailingProvider(), _OkProvider())
    assert chained.generate_json("p") == {"ok": True}


def test_fallback_chain_records_event() -> None:
    events: list[tuple[str, str]] = []
    chained = fallback_chain(
        _FailingProvider(),
        _OkProvider(),
        on_fallback=lambda f, t, e: events.append((f, t)),
    )
    chained.generate_json("p")
    assert events == [("failing", "ok")]
```

**验证命令**：

```powershell
python -m pytest tests/test_provider_fallback.py -v
```

**期望输出**：collection error 或 2 errors（`ImportError: cannot import name 'fallback_chain' from 'app.core.providers.base'`）。**必须看到失败**——这是 RED 状态。

### Task 3.2 — GREEN：fallback_chain helper

**修改文件**：`app/core/providers/base.py`

**新增函数**（追加到文件末尾）：

```python
def fallback_chain(
    primary: LLMProvider,
    secondary: LLMProvider,
    *,
    on_fallback: Callable[[str, str, Exception], None] | None = None,
) -> LLMProvider:
    """Wrap primary with automatic fallback to secondary on ProviderUnavailable."""
    class _ChainedProvider(LLMProvider):
        @property
        def provider_name(self) -> str:
            return primary.provider_name

        @property
        def capability(self) -> ProviderCapability:
            return primary.capability

        def generate_json(self, prompt, response_schema=None, max_output_tokens=None):
            try:
                return primary.generate_json(prompt, response_schema, max_output_tokens)
            except ProviderUnavailable as exc:
                if on_fallback:
                    on_fallback(primary.provider_name, secondary.provider_name, exc)
                return secondary.generate_json(prompt, response_schema, max_output_tokens)

        def generate_text(self, prompt, max_output_tokens=None):
            try:
                return primary.generate_text(prompt, max_output_tokens)
            except ProviderUnavailable:
                return secondary.generate_text(prompt, max_output_tokens)

        def stream(self, prompt):
            try:
                yield from primary.stream(prompt)
            except ProviderUnavailable:
                yield from secondary.stream(prompt)

        def count_tokens(self, text):
            return primary.count_tokens(text)

    return _ChainedProvider()
```

**验证命令**：

```powershell
python -c "from app.core.providers.base import fallback_chain; print('fallback_chain importable')"
python -m pytest tests/test_provider_fallback.py tests/test_provider_contract.py tests/test_model_client_facade.py -v
```

**期望输出**：
- 第一行打印 `fallback_chain importable`
- 9 passed（2 fallback + 5 contract + 2 facade，零回归）。RED → GREEN 转换完成。

### Task 3.3 — Token usage hook + `generate_structured` 完整最终版

**修改文件**：`app/core/model_client.py`

> `last_token_usage` 字段已在 Phase 2 Task 2.2 的 `__init__` 初始化，本 Task 仅新增 `_record_usage` 方法和 `generate_structured` 成功路径调用点。

**新增私有方法 `_record_usage`**（class `ModelClient` 内部）：

```python
def _record_usage(self, prompt: str, completion: str) -> None:
    prompt_tokens = self._provider.count_tokens(prompt)
    completion_tokens = self._provider.count_tokens(completion)
    self.last_token_usage = {
        "prompt": prompt_tokens,
        "completion": completion_tokens,
        "total": prompt_tokens + completion_tokens,
    }
```

**`generate_structured` 完整最终版**（Phase 3 末态，覆盖 Phase 2 的中间态）：

```python
def generate_structured(
    self,
    skill_name: str,
    prompt: str,
    fallback_result: dict[str, Any],
    response_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if self.mode == "mock":
        logger.info("ModelClient mock mode for skill=%s", skill_name)
        return {
            "status": "ok",
            "structured_result": fallback_result,
            "model_name": self.model_name,
            "prompt_preview": prompt[:200],
        }

    try:
        structured_result = self._provider.generate_json(
            prompt,
            response_schema=response_schema,
        )
        # R5: 仅成功路径末尾记 token usage（mock / except 路径不调，避免污染）
        self._record_usage(prompt, json.dumps(structured_result, ensure_ascii=False))
        logger.info(
            "ModelClient ok skill=%s provider=%s tokens=%d",
            skill_name, self._provider.provider_name, self.last_token_usage["total"],
        )
        return {
            "status": "ok",
            "structured_result": structured_result,
            "model_name": self.model_name,
            "prompt_preview": prompt[:200],
        }
    except Exception as exc:
        logger.warning(
            "Model unavailable skill=%s provider=%s err=%s",
            skill_name, self._provider.provider_name, exc,
        )
        degraded = dict(fallback_result)
        degraded["status"] = (
            degraded.get("status")
            if degraded.get("status") == "data_missing"
            else "model_unavailable"
        )
        degraded["model_error"] = self._classify_model_error(exc)
        return {
            "status": "model_unavailable",
            "structured_result": degraded,
            "model_name": self.model_name,
            "prompt_preview": prompt[:200],
        }
```

> **契约**：所有 Provider 通过 `LLMProvider.count_tokens` 统一为 `{prompt, completion, total}` 三字段。下游 Plan #03 Phase 3 budget 模块直接读 `self.last_token_usage['total']`，不解析 Provider 原生响应。`MockProvider` / `GeminiProvider` / `ClaudeMaestroProvider` 都必须在 `count_tokens` 中返回正整数，让 budget 可累加。
>
> 若 `_classify_model_error` 在 baseline 不存在，请保留 baseline 实际的错误分类逻辑（或退化为 `degraded["model_error"] = type(exc).__name__`）；本 Plan 不引入新方法。

**model_client.py 顶部 import 补**（如缺）：

```python
import json
```

**验证命令**：

```powershell
python -c "from app.core.model_client import ModelClient; c = ModelClient(); print('init ok, last_token_usage:', c.last_token_usage)"
python -m pytest tests/test_model_client_facade.py -v
```

**期望输出**：
- 第一行打印 `init ok, last_token_usage: {'prompt': 0, 'completion': 0, 'total': 0}`
- 2 passed（facade 测试零回归）

### Task 3.4 — 全量回归

**验证命令**：

```powershell
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v
```

**期望输出**：
- `tests/` → 270 + 9 (Phase 1+2+3 累计新增：5 contract + 2 facade + 2 fallback) = 279 passed
- `data_acquisition_agent/tests/` → 153 passed (1 skipped)
- 零回归

### Task 3.5 — Phase 3 commit `[complete]`

```powershell
git add -A
git commit -m "feat(provider): fallback_chain helper + token usage hook [complete] model-client-refactor [TDD red->green]"
```

---

## 完成标志

- 4 commits（baseline + Phase 1 + Phase 2 + Phase 3 [complete]）
- 调用点改动 ≤ 1 处（仅 `model_client.py` 内部）
- 270 + 153 测试零回归
- 新增至少 11 个 provider 相关测试用例

**Step 8 后续（不计入本 Plan 的 4 commit 限制）**：本 Plan 全部 `[complete]` 后，用 ai-code-review skill 做白盒审计，产出 `docs/reviews/model-client-refactor-audit.md`（10 板块审计报告）；用 module-dev-summary skill 生成 `docs/reviews/model-client-refactor-summary.md`（面试导向技术总结）。
