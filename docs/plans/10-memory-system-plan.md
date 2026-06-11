# Plan 10 — Memory 系统（4 级压缩 + Memory Flush + 长期记忆 four-class）

> **STATUS**: ✅ **IMPLEMENTED / SUPERSEDED BY SQLITE MEMORY V1 — 2026-05-25**
>
> 2026-05-25 实际落地版本已从本 Plan 早期的 `outputs/memory/{country}/{session_id}/*.jsonl` four-class 原型升级为 SQLite + FTS5 长期记忆子系统：
> - 默认数据库：`outputs/memory/memory.sqlite3`
> - 身份隔离：`user_id/project_id/country/status`
> - 写入策略：严格白名单 + redactor + dedupe + 低价值拒写
> - 召回策略：FTS5 / LIKE fallback + importance / confidence / recency 加权
> - 管理能力：`/api/orchestrator/memory/list|query|status`、手动 create、edit、archive、restore、soft delete
> - UI：NL Chat 内 Memory Inspector 管理抽屉
> - 评估：`tests/golden/memory_eval.py` + `tests/fixtures/golden/memory/eval_set.json`
>
> 本文件 2026-05-06 以前的内容保留为 Plan 10 历史设计记录；当前行为以 `docs/specs/memory-behavior-contract.md` 和实现代码为准。Checkpoint commit: `3c10d85 checkpoint(memory): sqlite long-term memory baseline`。
>
> **Legacy status**: ✅ **READY-TO-EXECUTE — v3.2** （v3.2 三轮把 P1/P2/P3 三处致命问题修干净；2026-05-06 paranoid 五点二轮复审补 Memory Flush 凭据扫描门 + load_session_memories 硬上限；待用户最终复审后正式执行）
>
> **v3.2 二轮 paranoid 五点复审修订点**（2026-05-06）：
> - **P1 凭据安全（CLAUDE.md §13 Zero Tolerance）**：v3.2 Task 3.1 `memory_flush` 直接把 LLM 提取出的 `extracted` 字典写盘，没有调 `data_acquisition_agent.redactor.redact()` 脱敏。用户在对话里贴 host/port/password / token / key / secret 时，LLM 可能把它们当事实抽到长期记忆里、明文存到 `outputs/memory/` 的 jsonl。修复：写盘前对每条 item 调 `redact(item)`，hits > 0 时记 warning + 用脱敏后文本写盘。与 Plan 07/08 prompt assembler / SQL judge 凭据扫描口径一致。
> - **P1 retrieval 硬上限**：v3.2 Task 4.1 `load_session_memories` 全量加载 `read_all_categories(country, session_id)` 后无截断 — 活跃用户 session 跑一个月可能 100+ 条，全部拼进 system_prompt 会爆 context。V1 加 `MAX_MEMORY_ITEMS = 50` 硬上限（取最近 50，read_all_categories 已按时间戳升序），超出记 warning。V2/V3 升 BM25 / 向量库后改按相似度 top-k。
>
> **v3.2 修订点**（对照 v3.1）：
> - **P1 致命**：v3.1 `compress_level_2` / `align_tool_pairs` 检查 `msg.get("tool_calls")` —— 但项目 `OrchestratorMessage` **没有 `tool_calls` 字段**（仅 role / content / tool_call_id / timestamp，见 [`schemas.py:103`](app/services/orchestrator_agent/schemas.py)）。L2 整段 no-op、HEAD_PROTECT=3 不成立（assistant 仅在 final 出现）。
>   修复（B 方案）：`compress_level_2(messages, tool_calls)` 改为接 `OrchestratorSession.tool_calls: list[ToolCallRecord]`，按 `(tool_name, json.dumps(input, sort_keys=True), json.dumps(output, sort_keys=True))` 三元组去重，相同 key 后续 `tool_call_id` 关联的 tool message content 替换为占位符。`HEAD_PROTECT=1`（仅保护首条 user）。Task 2.1 / Task 2.2 / Task 2.5 / Spec §3.3 / Spec §3.4 全量重写。
> - **P2 致命**：v3.1 七个测试 `monkeypatch.setattr("app.core.config.settings.project_root", tmp_path)` —— 但 `Settings.project_root` 是 `@property`、不是 declared field（[`config.py:61`](app/core/config.py)），pydantic v2 会抛 `ValueError`。
>   修复：`tools/memory.py` 暴露 `_project_root()` helper，所有路径函数走 helper，测试改 `monkeypatch.setattr("app.services.orchestrator_agent.tools.memory._project_root", lambda: tmp_path)`。Task 1.2 / 1.3 / 3.2 / 5.1 / 5.2 全量同步。Spec §6.1 同步增补。
> - **P3 高危（适用 Plan 09 范围，本 Plan 仅补一道 import smoke）**：Plan 09 v3.1 Task 0.1 未对 `requirements.txt` 做依赖前置体检，CI 缺包直接挂在 Phase 4。Plan 09 v3.2 Task 0.1 加 `Select-String -Pattern "sqlglot|pydantic|google-genai|google-cloud"` 体检 + 缺包 `exit 1`。本 Plan 10 不跑 CI、不依赖 sqlglot；v3.2 仅在 Phase 0 Task 0.1 补一道 Python import smoke（`from app.services.orchestrator_agent.schemas import OrchestratorMessage, ToolCallRecord`），避免 Phase 1 写试试时 import 挂在环境问题。
> - **P4 致命**：v3.1 Task 4.3 集成点 2 `oldString` 写的是 `content=llm_out.get("final_answer") or llm_out.get("thought", "")` —— 与实际 [`agent_loop.py L143`](app/services/orchestrator_agent/agent_loop.py) **一行不对**（实际 `content=decision["final_message"]`、`timestamp=datetime.now(timezone.utc)`、有 `save_session(session)`）；且 final 分支后立即 `return`（L155），插在那毫无意义。
>   修复：v3.2 重写 Task 4.3 集成点 2，把 patch 从 final 分支移到 tool dispatch 完成后（L272-277 块尾部），`oldString` / `newString` 全量对齐 ground truth，能 `git apply` 直接命中。
> - **简化**：v3.1 `ensure_context_fits` 入口 `_to_dicts` / 出口 `_to_orchestrator_messages` 转换冗余 — Phase 2 v3.2 后所有压缩函数原生接 `OrchestratorMessage`，去掉转换。Task 4.1 同步重写。
>
> **v3 / v3.1 修订点**（对照 v2 / v3，保留供溯源）：
> - **致命-1**：`ModelClient` **没有 `generate(prompt, route_key=...)` 方法**（同 Plan 09 已证实）。Task 2.3 summarizer.py / Task 3.1 memory_flush.py / Task 3.2 mock test 三处误用已重写为 `generate_structured(skill_name, prompt, fallback_result, response_schema, *, route_key)`。
> - **致命-2**：Task 4.3 集成点 1 判首轮的 `len(session.messages) == 0` **永远为 False**。现状：agent_loop.py L89-L91 在拼 system_prompt 之前已 `session.messages.append(OrchestratorMessage(role="user", ...))`；L99 拼 system_prompt 时 `len == 1`。修复：改判 `len(session.messages) == 1`。
> - **致命-3**：Task 4.3 说 `MODEL_MAX_TOKENS 从 budget.py 读`。实际 `app/services/orchestrator_agent/budget.py` 只有 `DEFAULT_BUDGET = 500_000`（session 累计，不是单轮 prompt 上限），无 `MODEL_MAX_TOKENS`。修复：在 `context_fit.py` 内部定义模块级常量 `MODEL_MAX_TOKENS_PER_TURN = 800_000`（gemini-2.5-flash 1M ctx 留 20% buffer）。
> - **致命-4**：Task 4.3 说「集成点 patch 待 Phase 0 读完 agent_loop.py 后才能写出」——作为执行型 Plan 这是占位（违反 Vibe 五点法第 5 条）。本轮反写 ground truth：assemble_system_prompt 调用在 L99，`for round_idx in range(MAX_ROUNDS)` 主循环 L101，Task 4.3 已给出精确 oldString/newString patch。
>
> **v3.1 二轮改**：v3 顶部声明已修 Task 3.1 但代码块未同步（`raw = client.generate(...)` 仍在）。v3.1 改为 `generate_structured` + `_FLUSH_RESPONSE_SCHEMA` + `_FALLBACK_FLUSH`，返回 dict 包含 `status / written / extracted` 供 Task 3.2 测试断言使用。Task 4.3 集成点 2 删「或」占位、给出精确 oldString/newString patch。
>
> **作者**: Codex / Claude（自动生成草稿）
> **日期**: 2026-05-05（v2 修订 2026-05-05） / 2026-05-06（v3 / v3.1 / v3.2 修订）
> **关联 Spec**: `docs/specs/10-memory-system-design.md`（同步 v3.2）
> **HEAD baseline**: `bd05240`（Phase 0 commit 时以 `git rev-parse HEAD` 实际值为准，不依赖 Plan 08 / 09）
> **预计 Phase 数**: 5

> Historical note (2026-06-03): 本 Plan 中引用的 `agent_loop.py::MAX_ROUNDS=15` 与旧 general-chat 主循环为历史实现背景；当前 live general-chat 行为已迁入 `GeneralChatFlow`，active status 以 `PLANNING.md` / decomposition spec 为准。

---

## 0. Baseline 共识

### 0.1 关联文档
- Spec: `docs/specs/10-memory-system-design.md`
- `app/services/orchestrator_agent/agent_loop.py`（顶部 `MAX_ROUNDS = 15`，async generator 主循环）
- `app/services/orchestrator_agent/tools/memory.py`（V1 minimal，当前走 `MemoryWriteInput(key, value)` schema，写入 `outputs/orchestrator_memory/{safe_key}.txt`）— **本 Plan 扩展不重建**
- `app/services/orchestrator_agent/{session.py,session_store.py,budget.py,resilience.py,ack_bus.py,schemas.py}` 都已存在 — **本 Plan 不动**
- `app/services/orchestrator_agent/tools/__init__.py`（`get_tool_registry()` 已包含 memory_write/memory_read）— **本 Plan 不重复注册**
- Harness §5/§6（Memory + Context 层）

### 0.1.1 Surgical Hard Boundary（本 Plan 不动下列）
| 不动 | 原因 |
|---|---|
| `data_acquisition_agent/` 整目录 | 跨模块耦合，本 Plan 不涉及 |
| `agent_loop.py::MAX_ROUNDS = 15` | 现有熟断常量 |
| `agent_loop.py` SSE 事件推送 / ack_bus 接点 | 仅补 2 个调用点，不改事件结构 |
| `session_store.py` / `session.py` / `budget.py` / `resilience.py` / `ack_bus.py` | 现有模块保持不动 |
| `OrchestratorSession` schema（加 is_first_turn / country 字段） | 避免与现有 JSON 持久化冲突，本 Plan 用 `len(session.messages)==1` 推断首轮（v3 修复：L89-L91 已 append 用户首条消息，==0 永远 False）|
| `tools/{query_data,run_profile,run_trace,parse_uid_file}.py` | Surgical，仅动 `tools/memory.py` |

### 0.2 本 Plan 增加 4 个新文件 + 以补丁式修改 2 个现有文件
```
app/services/orchestrator_agent/
├── memory_manager.py    # ✨ 新增：4 级压缩 + align_tool_pairs
├── memory_flush.py      # ✨ 新增：压缩前提取关键事实
├── summarizer.py        # ✨ 新增：LLM 摘要封装（走 ModelClient route_key=memory.summarizer）
└── context_fit.py       # ✨ 新增：ensure_context_fits / load_session_memories 集成入口
```
以补丁式修改现有文件：
```
app/services/orchestrator_agent/
├── tools/memory.py      # ⚠️ 扩展：Four-class 路径识别 + 后兼容原 V1 平铺 key/value
└── agent_loop.py        # ⚠️ 仅 2 点：首轮 load_session_memories、每轮调 ensure_context_fits
```
> **说明（调整）**：二轮审核事实检查发现本 Plan **增加的是 4 个新文件**（原草稿漏计 `context_fit.py`）。`tools/__init__.py::get_tool_registry()` 已含 memory_write/memory_read，本 Plan 不重复注册。

### 0.3 ModelClient 强制声明
本 Plan 所有 LLM 调用（summarizer / iterative_summarize / memory_flush）必经 `app/core/model_client.py::ModelClient`。**禁止直接 `import google-genai`**（CLAUDE.md Zero Tolerance 第 5 条）。

### 0.4 baseline commit
```powershell
git commit --allow-empty -m "[baseline] plan-10 — before execution"
```

### 0.5 测试矩阵
- 单元：memory_tools / 4 级压缩各级 / flush
- 集成：15 轮（MAX_ROUNDS 上限）连续对话不撑爆
- 跨 session 召回验证

---

## 1. 范围

### 1.1 ✅ 包含
- `outputs/memory/{country}/{session_id}/*.jsonl` 数据结构
- `memory_write` / `memory_read` 工具
- 4 级分级压缩（L1/L2/L3/L4）+ 迭代更新
- Memory Flush（压缩前必做）
- 集成到 `agent_loop` 自动触发
- 国家命名空间隔离
- env var `MEMORY_COMPRESSION_ENABLED` 开关

### 1.2 ❌ 不包含
- Vector embedding 召回（V3）
- BM25 召回（V2）
- 跨 session 用户身份认证（V2）
- 长期记忆参与 prompt cache（V2）

---

## Phase 0 — Baseline 核对

### Task 0.1 摸清 agent_loop 与现有模块字段
```powershell
New-Item -ItemType Directory -Path .reports -Force | Out-Null   # v3.2 补：避免后续报告写入失败
Write-Host "=== HEAD ==="
git rev-parse HEAD
Write-Host "`n=== agent_loop.py 顶部 80 行 ==="
Get-Content app/services/orchestrator_agent/agent_loop.py -TotalCount 80
Write-Host "`n=== schemas.py OrchestratorSession / Message ==="
Select-String -Path app/services/orchestrator_agent/schemas.py -Pattern "class (OrchestratorMessage|OrchestratorSession|MemoryWriteInput|MemoryReadInput|ToolCallRecord)"
Write-Host "`n=== tools/__init__.py registry ==="
Get-Content app/services/orchestrator_agent/tools/__init__.py
Write-Host "`n=== tools/memory.py 全部 ==="
Get-Content app/services/orchestrator_agent/tools/memory.py
Write-Host "`n=== .gitignore outputs ==="
Select-String -Path .gitignore -Pattern outputs

# v3.2 补：Python import smoke——提前暴露环境/依赖问题，不拖到 Phase 1 写试试时装库挂。
Write-Host "`n=== import smoke ==="
python -c "from app.core.model_client import ModelClient; from app.services.orchestrator_agent.schemas import OrchestratorMessage, ToolCallRecord, OrchestratorSession; from app.services.orchestrator_agent.tools.memory import memory_write, memory_read; print('imports OK')"
if ($LASTEXITCODE -ne 0) { Write-Error 'Plan 10 import smoke 失败——请先修复 google-genai / pydantic / app.core 环境问题'; exit 1 }
```
**记录项**（写入 `.reports/plan-10-phase0.txt`）：
- `MAX_ROUNDS` 实际值（预期 15）
- `OrchestratorMessage.role` 实际枚举（预期 `Literal["user", "assistant", "tool"]`，不含 system）
- `OrchestratorSession` 字段列表（预期不含 is_first_turn / country）
- `MemoryWriteInput` schema（预期 `key: str`、`value: str`——**不含** category/session_id/country）
- `tools/__init__.py::get_tool_registry()` 是否含 memory_write/memory_read（预期含，本 Plan 不重复注册）
- `tools/memory.py` 现写入路径（预期 `outputs/orchestrator_memory/{safe_key}.txt`）
- `.gitignore` 是否含 `outputs/`（预期含，代表 `outputs/memory/...` 自动不追踪）

### Task 0.2 token 消耗曲线 baseline（在 MAX_ROUNDS=15 限制下）
**手动步骤**（可选 — 若现有 e2e 测试环境完备则跑一次）：
1. 启动 OrchestratorAgent，跑一条复杂查询，本身就会在 MAX_ROUNDS 上限处被熟断被中断
2. 记录每轮 prompt token 数（可从 `budget.py` 日志读）
3. 写入 `.reports/plan-10-baseline-tokens.txt`

**预期**：token 单调递增，15 轮后接近上限的某个比例（表明压缩有价值）。**说明**：30 轮不可达（MAX_ROUNDS=15 硬熟断），原草稿 "30 轮" 描述是错误。

### Task 0.3 创建新路径下占位目录
```powershell
New-Item -ItemType Directory -Path outputs/memory/mx, outputs/memory/th -Force
# .gitignore 已含 outputs/，本目录自动不追踪。仅为 Phase 1 路径预热。
```

### Phase 0 commit
```powershell
git commit --allow-empty -m "chore(10): phase 0 baseline (max_rounds=15, schema audit)"
```

---

## Phase 1 — 扩展现有 `tools/memory.py`（不重建，后兼容）

### Task 1.1 现状确认（Phase 0 已读，本 Task 重记关键事实）
- 调用 schema：`MemoryWriteInput(key: str, value: str)` / `MemoryReadInput(key_pattern: str)`——**本 Plan 不动 schema**
- 老调用写入 `outputs/orchestrator_memory/{safe_key}.txt`——**本 Plan 后兼容保留**
- 后兼容策略：key 不含 `/` 拆出的 4 段路径 → 走老路径（不变能力）；key 是 `"{country}/{session_id}/{category}/{ts}"` 格式 → 走新路径 jsonl 追加

### Task 1.2 以补丁式重写 `tools/memory.py`（完整代码）
**Modify**: `app/services/orchestrator_agent/tools/memory.py`（**全文替换**）

**v3.2 修复**：上轮 v3.1 让测试 monkeypatch `settings.project_root`，但 `Settings.project_root` 是 `@property` non-declared field、pydantic v2 不允许 setattr —— 7 个测试 setup 会拖 `ValueError`。本 Task 加一个可被 monkeypatch 的 `_project_root()` helper，生产与现有 settings 等价、测试可 monkeypatch。

```python
"""memory_write / memory_read — V1 minimal local-JSON impl，
   Plan 10 Phase 1 扩展 four-class 路径识别 + 后兼容原 V1 平铺 key/value。

   schema 本身保持不变（MemoryWriteInput.key/value, MemoryReadInput.key_pattern）。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.services.orchestrator_agent.schemas import (
    MemoryWriteInput, MemoryWriteOutput,
    MemoryReadInput, MemoryReadOutput,
)


VALID_CATEGORIES = ("user", "feedback", "project", "reference")


def _project_root() -> Path:
    """v3.2：可被测试 monkeypatch 的路径入口。生产下走 settings.project_root。

    不能直接 `monkeypatch.setattr(settings, "project_root", tmp_path)`——
    settings.project_root 是 Settings 类的 @property、不是 declared field，
    pydantic v2 BaseModel 会报 ValueError。
    测试 monkeypatch：
        monkeypatch.setattr(
            "app.services.orchestrator_agent.tools.memory._project_root",
            lambda: tmp_path,
        )
    """
    return settings.project_root


def _legacy_dir() -> Path:
    p = _project_root() / "outputs" / "orchestrator_memory"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _new_dir(country: str, session_id: str) -> Path:
    p = _project_root() / "outputs" / "memory" / country / session_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _parse_four_class_key(key: str) -> tuple[str, str, str] | None:
    """返回 (country, session_id, category) 如果 key 是 four-class 格式，否则 None。"""
    parts = key.split("/", 3)
    if len(parts) >= 3 and parts[2] in VALID_CATEGORIES:
        return parts[0], parts[1], parts[2]
    return None


def memory_write(input_data: MemoryWriteInput) -> MemoryWriteOutput:
    parsed = _parse_four_class_key(input_data.key)
    if parsed is not None:
        country, session_id, category = parsed
        record = {
            "ts": datetime.now().isoformat(),
            "session_id": session_id,
            "country": country,
            "category": category,
            "content": input_data.value,
            "source": "memory_flush",
            "ttl_days": 90,
        }
        target = _new_dir(country, session_id) / f"{category}.jsonl"
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return MemoryWriteOutput(ok=True, path=str(target))

    # 后兼容：V1 minimal 平铺 key/value 写入
    safe_key = input_data.key.replace("/", "_").replace(".", "_")
    target = _legacy_dir() / f"{safe_key}.txt"
    target.write_text(input_data.value, encoding="utf-8")
    return MemoryWriteOutput(ok=True, path=str(target))


def memory_read(input_data: MemoryReadInput) -> MemoryReadOutput:
    parsed = _parse_four_class_key(input_data.key_pattern)
    if parsed is not None:
        country, session_id, category = parsed
        path = _new_dir(country, session_id) / f"{category}.jsonl"
        items: list[dict[str, str]] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                items.append(json.loads(line))
        return MemoryReadOutput(items=items)

    # 后兼容：V1 minimal 顺序
    base = _legacy_dir()
    items = []
    pattern = input_data.key_pattern.replace("*", "")
    for f in base.glob("*.txt"):
        if pattern in f.stem:
            items.append({"key": f.stem, "value": f.read_text(encoding="utf-8")})
    return MemoryReadOutput(items=items)


def read_all_categories(country: str, session_id: str) -> list[dict]:
    """全部四类记忆列表，load_session_memories 内部调用。

    v3.2 二轮 paranoid 修复：返回前按 `ts` 字段升序排序，保证调用方
    `items[-MAX_MEMORY_ITEMS:]`（Task 4.1 load_session_memories）取的真的是"最近 N 条"
    而不是 4 个 category 文件读取顺序的尾部。
    """
    out: list[dict] = []
    base = _new_dir(country, session_id)
    for cat in VALID_CATEGORIES:
        p = base / f"{cat}.jsonl"
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                out.append(json.loads(line))
    out.sort(key=lambda x: x.get("ts", ""))   # ✅ 按时间戳升序，调用方可安全 [-N:]
    return out
```

### Task 1.3 unit test
**预检查**: `tests/orchestrator_agent/` 目录是否存在：
```powershell
if (Test-Path tests/orchestrator_agent/) { Write-Host "OK" } else { New-Item -ItemType Directory -Path tests/orchestrator_agent -Force }
```
**Create**: `tests/orchestrator_agent/test_memory_tools.py`
**v3.2 修复**：monkeypatch 不能改 `settings.project_root`（@property non-declared field），改 monkeypatch `tools.memory._project_root` helper。
**完整代码**：
```python
from app.services.orchestrator_agent.schemas import MemoryWriteInput, MemoryReadInput
from app.services.orchestrator_agent.tools.memory import (
    memory_write, memory_read, read_all_categories,
)


MEMORY_MOD = "app.services.orchestrator_agent.tools.memory"


def test_legacy_flat_key_still_works(tmp_path, monkeypatch):
    monkeypatch.setattr(f"{MEMORY_MOD}._project_root", lambda: tmp_path)
    inp = MemoryWriteInput(key="hello", value="world")
    out = memory_write(inp)
    assert out.ok is True
    read_out = memory_read(MemoryReadInput(key_pattern="hello"))
    assert any(item["value"] == "world" for item in read_out.items)


def test_four_class_key_writes_jsonl(tmp_path, monkeypatch):
    monkeypatch.setattr(f"{MEMORY_MOD}._project_root", lambda: tmp_path)
    inp = MemoryWriteInput(
        key="mx/sess_001/user/20260505T140000",
        value="用户偏好中文",
    )
    out = memory_write(inp)
    assert out.ok is True
    assert out.path.endswith("user.jsonl")

    items = read_all_categories("mx", "sess_001")
    assert any(it["content"] == "用户偏好中文" for it in items)


def test_country_session_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(f"{MEMORY_MOD}._project_root", lambda: tmp_path)
    memory_write(MemoryWriteInput(key="mx/sA/user/01", value="A"))
    memory_write(MemoryWriteInput(key="mx/sB/user/01", value="B"))
    a_items = read_all_categories("mx", "sA")
    b_items = read_all_categories("mx", "sB")
    assert any(it["content"] == "A" for it in a_items)
    assert all(it["content"] != "A" for it in b_items)
```

### Task 1.4 验证 OrchestratorAgent 现有工具调用不破
```powershell
python -m pytest tests/test_orchestrator_agent_*.py -v 2>&1 | Select-String "passed|failed" | Select-Object -Last 3
```
**预期**：现有 OrchestratorAgent unit test 全过。

### Phase 1 commit
```powershell
git add app/services/orchestrator_agent/tools/memory.py tests/orchestrator_agent/
git commit -m "feat(10): phase 1 extend memory tools (four-class path, schema unchanged, backward compat)"
```

---

## Phase 2 — 4 级分级压缩

### Task 2.1 实现 4 级压缩（全部走 OrchestratorMessage + ToolCallRecord）
**Create**: `app/services/orchestrator_agent/memory_manager.py`

**v3.2 修复**（对照 v3.1）：
- v3.1 代码走 dict 且检查 `msg.get("tool_calls")` 字段——但 `OrchestratorMessage` 根本没有 `tool_calls` 字段，**L2 全程 no-op**。
- 项目 ground truth（[schemas.py](app/services/orchestrator_agent/schemas.py)）：`OrchestratorMessage = {role: Literal["user","assistant","tool"], content: str, tool_call_id: str | None, timestamp: datetime}`；assistant **仅在 final 时进 messages 一次**；tool 调用详情在 session-level `OrchestratorSession.tool_calls: list[ToolCallRecord]`，tool message 与 ToolCallRecord 通过 `tool_call_id` 关联。
- v3.2 重写：**所有函数输入类型为 `list[OrchestratorMessage]`**；L2 变为按 ToolCallRecord 去重（(tool_name, input_hash, output_hash) 同 key 仅保留首次，后续同 key 的 tool message content 替换为占位符）。HEAD_PROTECT 改 1（仅保留首条 user）。

**完整代码**：
```python
"""Multi-level message compression (Plan 10 Phase 2 / v3.2).
走项目原生 OrchestratorMessage + ToolCallRecord。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Callable

from app.services.orchestrator_agent.schemas import (
    OrchestratorMessage, ToolCallRecord,
)


TAIL_PROTECT = 5
HEAD_PROTECT = 1   # v3.2：仅保留首条 user（项目 assistant 只在 final append）
_TRUNCATED_PREFIX = "[已裁剪：原长度 "
_DEDUPED_MARKER = "[结果重复，已去重]"


def compress_level_1(messages: list[OrchestratorMessage]) -> list[OrchestratorMessage]:
    """L1：裁剪旧 tool message（content > 200 字符替为占位符，最近 TAIL_PROTECT 不动）。"""
    cutoff = max(0, len(messages) - TAIL_PROTECT)
    for msg in messages[:cutoff]:
        if msg.role == "tool" and isinstance(msg.content, str) and len(msg.content) > 200:
            msg.content = f"{_TRUNCATED_PREFIX}{len(msg.content)} 字符]"
    return messages


def _hash_payload(payload: object) -> str:
    """对 dict / list / str 动态序列化后取 md5；sort_keys 保证同构 dict 同哈希。"""
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def compress_level_2(
    messages: list[OrchestratorMessage],
    tool_calls: list[ToolCallRecord],
) -> list[OrchestratorMessage]:
    """L2：同 (tool_name, input_hash, output_hash) 重复调用只保留首次。

    后续同 key 的 tool message content 替换为 `_DEDUPED_MARKER`；
    最近 TAIL_PROTECT 消息对应的 tool_call_id 不去重。
    """
    if not tool_calls:
        return messages

    tail_ids = {
        m.tool_call_id for m in messages[-TAIL_PROTECT:]
        if m.role == "tool" and m.tool_call_id
    }

    seen_keys: dict[tuple[str, str, str], str] = {}
    duplicate_ids: set[str] = set()
    for rec in tool_calls:
        if rec.status != "done" or not rec.tool_call_id:
            continue
        if rec.tool_call_id in tail_ids:
            continue
        key = (
            rec.tool_name,
            _hash_payload(rec.input),
            _hash_payload(rec.output),
        )
        if key in seen_keys:
            duplicate_ids.add(rec.tool_call_id)
        else:
            seen_keys[key] = rec.tool_call_id

    for msg in messages:
        if msg.role == "tool" and msg.tool_call_id in duplicate_ids:
            msg.content = _DEDUPED_MARKER
    return messages


def align_tool_pairs(messages: list[OrchestratorMessage]) -> list[OrchestratorMessage]:
    """切割边界仅处理【首位是孤立 tool message】场景。

    项目 `OrchestratorMessage` 没有 tool_calls 字段，原原生语义 【tool 必须在带 tool_call 的 assistant 后】在本项目不适用：
    assistant 只在 final 出现一次，tool 调用中间全部只有 tool message + 平行 session.tool_calls。
    本函数只处理中段首位嶌点：如果首条是 tool（表示上个 tool 调用被压缩完后这里出现孤独 tool）跳过。
    """
    cleaned: list[OrchestratorMessage] = []
    for msg in messages:
        if not cleaned and msg.role == "tool":
            continue
        cleaned.append(msg)
    return cleaned


def _to_dicts(messages: list[OrchestratorMessage]) -> list[dict]:
    return [m.model_dump() for m in messages]


def compress_level_3(
    messages: list[OrchestratorMessage],
    summarize_fn: Callable[[list[dict]], str],
) -> list[OrchestratorMessage]:
    """L3：LLM 摘要中间轮次。summarize_fn 接 list[dict]。"""
    if len(messages) <= HEAD_PROTECT + TAIL_PROTECT:
        return messages

    head = messages[:HEAD_PROTECT]
    tail = messages[-TAIL_PROTECT:]
    middle = messages[HEAD_PROTECT:-TAIL_PROTECT]
    middle = align_tool_pairs(middle)

    summary_text = summarize_fn(_to_dicts(middle))
    summary_msg = OrchestratorMessage(
        role="assistant",
        content=(
            f"[历史对话摘要 — 覆盖第 {HEAD_PROTECT + 1} 至第 {len(messages) - TAIL_PROTECT} 轮]\n\n"
            f"{summary_text}"
        ),
        timestamp=datetime.now(timezone.utc),
    )
    return head + [summary_msg] + tail


def compress_level_4(
    messages: list[OrchestratorMessage],
    full_summarize_fn: Callable[[list[dict]], str],
) -> list[OrchestratorMessage]:
    """L4：Fork 子 Agent 全量重建。只保留一条 assistant 摘要。"""
    summary = full_summarize_fn(_to_dicts(messages))
    return [OrchestratorMessage(
        role="assistant",
        content=summary,
        timestamp=datetime.now(timezone.utc),
    )]
```

### Task 2.2 实现迭代更新
**Modify**: `memory_manager.py` 追加（v3.2：保持 OrchestratorMessage 类型一致）：
```python
def compress_iteratively(
    messages: list[OrchestratorMessage],
    summarize_fn: Callable[[list[dict]], str],
    iterative_summarize_fn: Callable[[str, list[dict]], str],
) -> list[OrchestratorMessage]:
    """检测已有摘要 → 修订而非重写。"""
    existing_idx: int | None = None
    for i, msg in enumerate(messages):
        if msg.role == "assistant" and isinstance(msg.content, str) and msg.content.startswith("[历史对话摘要"):
            existing_idx = i
            break

    if existing_idx is None:
        return compress_level_3(messages, summarize_fn)

    head = messages[:existing_idx]
    existing_summary = messages[existing_idx].content
    new_messages = messages[existing_idx + 1:-TAIL_PROTECT]
    tail = messages[-TAIL_PROTECT:]

    new_summary = iterative_summarize_fn(existing_summary, _to_dicts(new_messages))
    summary_msg = OrchestratorMessage(
        role="assistant",
        content=new_summary,
        timestamp=datetime.now(timezone.utc),
    )
    return head + [summary_msg] + tail
```

### Task 2.3 LLM 摘要封装（走 `ModelClient.generate_structured`）
**Create**: `app/services/orchestrator_agent/summarizer.py`
**关键修订**（对照 v2）：v2 误写 `client.generate(prompt, route_key=...)`——`ModelClient` **不存在此方法**（同 Plan 09）。唯一公开 LLM 调用 API 是 `generate_structured(skill_name, prompt, fallback_result, response_schema=None, *, route_key=None) -> dict[str, Any]`。摘要输出是自然语言字符串，本处用 response_schema 包装为 `{"summary": "..."}`。

**完整代码**:
```python
"""LLM-based summarization for compression (Plan 10 Phase 2).全走 ModelClient.generate_structured，路由 memory.summarizer."""
from typing import Any

from app.core.model_client import ModelClient


SUMMARY_TEMPLATE = """请对以下对话历史生成结构化摘要（输出 JSON，唯一字段 summary 为中文贯串文本）：

## 对话历史
{messages}

## 摘要模板（填入 summary 字段中）
### Goal（用户的原始目标）
### Decisions（已做的关键决策）
### Facts（确认的 UID / 订单号 / 关键数据）
### Pending（进行中或被阻塞的事项）
### Next（下一步计划）

要求：总长 2000-5000 tokens；不丢任何 UID/订单号/金额；保持原对话语种。

## 输出严格 JSON
{{"summary": "<在这里按上述模板贯串成 1 个连续的中文文本>"}}
"""

ITERATIVE_TEMPLATE = """以下是已有摘要：

{existing_summary}

以下是后续新对话：

{new_messages}

请在已有摘要基础上**修订**（不是重写），保留所有 Goal/UID/关键数据。
输出严格 JSON：
{{"summary": "<修订后的完整摘要贯串文本>"}}
"""

_SUMMARY_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}

_FALLBACK_SUMMARY = {"summary": "[摘要不可用：模型调用失败，原始消息保留使用]"}


def _extract_summary(generated: dict[str, Any]) -> str:
    payload = generated.get("structured_result", _FALLBACK_SUMMARY)
    return str(payload.get("summary", _FALLBACK_SUMMARY["summary"]))


def summarize_messages(messages: list[dict], client: ModelClient | None = None) -> str:
    client = client or ModelClient()
    msg_text = format_messages(messages)
    prompt = SUMMARY_TEMPLATE.format(messages=msg_text)
    result = client.generate_structured(
        skill_name="memory_summarizer",
        prompt=prompt,
        fallback_result=_FALLBACK_SUMMARY,
        response_schema=_SUMMARY_RESPONSE_SCHEMA,
        route_key="memory.summarizer",
    )
    return _extract_summary(result)


def iterative_summarize(existing: str, new_messages: list[dict],
                        client: ModelClient | None = None) -> str:
    client = client or ModelClient()
    msg_text = format_messages(new_messages)
    prompt = ITERATIVE_TEMPLATE.format(existing_summary=existing, new_messages=msg_text)
    result = client.generate_structured(
        skill_name="memory_summarizer",
        prompt=prompt,
        fallback_result={"summary": existing},  # 迭代失败时退回原摘要
        response_schema=_SUMMARY_RESPONSE_SCHEMA,
        route_key="memory.summarizer",
    )
    return _extract_summary(result)


def format_messages(messages: list[dict]) -> str:
    out = []
    for m in messages:
        if not isinstance(m, dict):
            m = m.model_dump()
        role = m.get("role", "?")
        content = str(m.get("content", ""))[:500]
        out.append(f"[{role}] {content}")
    return "\n".join(out)
```

### Task 2.4 config.yaml 添加 memory.summarizer 路由（平铺格式，走现有 gemini）
**Modify**: `config.yaml`。**重要修正**：现 providers 仅有 `gemini` / `claude_maestro` / `mock`，**无** `gemini_flash`；现 routes 都是平铺 `key: provider_name` 格式。本 Plan 不新增 provider，不使用 `{primary, fallback_chain}` 嵌套。
**oldString**（现有 routes 末两行）：
```yaml
    orchestrator_agent.decide: gemini
  default_provider: gemini
```
**newString**：
```yaml
    orchestrator_agent.decide: gemini
    memory.summarizer: gemini   # Plan 10 Phase 2 — 4 级压缩 LLM 摘要
  default_provider: gemini
```

### Task 2.5 unit test 4 级压缩
**Create**: `tests/orchestrator_agent/test_memory_manager.py`
**v3.2 修复**：走真实 `OrchestratorMessage` + `ToolCallRecord` Pydantic 模型（不是假 dict）。
**完整代码**：
```python
import uuid
from datetime import datetime, timezone

import pytest

from app.services.orchestrator_agent.schemas import (
    OrchestratorMessage, ToolCallRecord,
)
from app.services.orchestrator_agent.memory_manager import (
    compress_level_1, compress_level_2, compress_level_3,
    align_tool_pairs,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user(content: str) -> OrchestratorMessage:
    return OrchestratorMessage(role="user", content=content, timestamp=_now())


def _assistant(content: str) -> OrchestratorMessage:
    return OrchestratorMessage(role="assistant", content=content, timestamp=_now())


def _tool(content: str, tool_call_id: str) -> OrchestratorMessage:
    return OrchestratorMessage(
        role="tool", content=content, tool_call_id=tool_call_id, timestamp=_now(),
    )


def _record(tool_name: str, tool_call_id: str, input_: dict, output: dict | None = None) -> ToolCallRecord:
    return ToolCallRecord(
        tool_name=tool_name,
        tool_call_id=tool_call_id,
        input=input_,
        output=output,
        status="done" if output is not None else "running",
        started_at=_now(),
        finished_at=_now() if output is not None else None,
    )


def test_l1_truncates_old_tool_messages():
    msgs = [
        _user("q1"),
        _tool("x" * 500, "tc1"),
        _user("q2"),
        _tool("y" * 500, "tc2"),
        _user("q3"),
        _tool("z" * 500, "tc3"),
        _user("q4"),
        _user("q5"),
        _tool("w" * 500, "tc4"),   # 靠末五个，应保留
        _user("q6"),
        _assistant("final"),
    ]
    compress_level_1(msgs)
    assert "已裁剪" in msgs[1].content
    assert msgs[-3].content == "w" * 500   # 末五不动


def test_l2_dedupes_repeated_tool_calls_via_tool_call_records():
    same_input = {"country": "mx", "request": "查个人"}
    same_output = {"uids": [1, 2, 3]}
    records = [
        _record("query_data", "tc1", same_input, same_output),
        _record("query_data", "tc2", same_input, same_output),  # 重复
        _record("query_data", "tc3", same_input, same_output),  # 重复
    ]
    msgs = [
        _user("q"),
        _tool('{"uids": [1, 2, 3]}', "tc1"),
        _user("q"),
        _tool('{"uids": [1, 2, 3]}', "tc2"),
        _user("q"),
        _tool('{"uids": [1, 2, 3]}', "tc3"),
        # 末五保护
        _user("q4"), _user("q5"), _user("q6"), _user("q7"), _user("q8"),
    ]
    compress_level_2(msgs, records)
    deduped = [m for m in msgs if m.role == "tool" and "去重" in m.content]
    assert len(deduped) >= 1


def test_l2_skips_recent_tool_within_tail_protect():
    same_input = {"x": 1}
    same_output = {"y": 2}
    records = [
        _record("query_data", "tc_old", same_input, same_output),
        _record("query_data", "tc_new", same_input, same_output),  # 重复但靠末
    ]
    msgs = [
        _user("q"),
        _tool("old", "tc_old"),
        # 充 5 个末保护位
        _user("q1"), _user("q2"), _user("q3"), _user("q4"),
        _tool("new", "tc_new"),  # 末 5 内
    ]
    compress_level_2(msgs, records)
    new_msg = next(m for m in msgs if m.tool_call_id == "tc_new")
    assert new_msg.content == "new"   # 末保护位不动


def test_align_tool_pairs_drops_orphan_leading_tool():
    msgs = [
        _tool("orphan", "tc_x"),   # 首位孤立 tool
        _user("q"),
        _assistant("a"),
    ]
    cleaned = align_tool_pairs(msgs)
    assert cleaned[0].role == "user"


def test_l3_summarizes_middle_with_head_protect_1(monkeypatch):
    captured = {}

    def fake_summarize(dicts: list[dict]) -> str:
        captured["count"] = len(dicts)
        return "FAKE_SUMMARY"

    msgs = [
        _user("first user"),                    # head
        _tool("r1", "tc1"), _user("q1"),
        _tool("r2", "tc2"), _user("q2"),         # middle (4 条)
        _user("q3"), _user("q4"), _user("q5"), _user("q6"), _user("q7"),  # tail 5
    ]
    out = compress_level_3(msgs, fake_summarize)
    assert out[0].content == "first user"
    assert any("FAKE_SUMMARY" in m.content for m in out)
    assert out[-1].content == "q7"
```

### Phase 2 commit
```bash
git add app/services/orchestrator_agent/memory_manager.py app/services/orchestrator_agent/summarizer.py config.yaml tests/orchestrator_agent/test_memory_manager.py
git commit -m "feat(10): phase 2 four-level compression + iterative update"
```

---

## Phase 3 — Memory Flush

### Task 3.1 实现 memory_flush
**Create**: `app/services/orchestrator_agent/memory_flush.py`
**关键修订**（对照 v2）：v2 误写 `client.generate(prompt, route_key=...)`——`ModelClient` **不存在此方法**（同 Plan 09）。全走 `generate_structured(skill_name, prompt, fallback_result, response_schema, *, route_key) -> dict[str, Any]`。返回 dict 含 `status / structured_result / model_name / prompt_preview`，从 `result["structured_result"]` 取 four-class payload。

**完整代码**（v3）：
```python
"""Memory Flush — extract key facts before compression (Plan 10 Phase 3).走 ModelClient.generate_structured，路由 memory.summarizer。"""
from datetime import datetime
from typing import Any

from app.core.model_client import ModelClient
from app.services.orchestrator_agent.schemas import MemoryWriteInput
from .summarizer import format_messages
from app.services.orchestrator_agent.tools.memory import memory_write


FLUSH_PROMPT = """从以下对话中提取关键事实，分类输出 JSON：

## 对话
{messages}

## 输出严格 JSON
{{
  "user": ["用户偏好/身份相关，最多 5 条"],
  "feedback": ["用户对 Agent 的纠正/反馈，最多 5 条"],
  "project": ["项目进展/已做决策，最多 5 条"],
  "reference": ["外部资源链接/工具入口，最多 5 条"]
}}

要求：宁缺毋滥，只提取真正重要的；空类返回 []。
"""


_FLUSH_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "user": {"type": "array", "items": {"type": "string"}},
        "feedback": {"type": "array", "items": {"type": "string"}},
        "project": {"type": "array", "items": {"type": "string"}},
        "reference": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["user", "feedback", "project", "reference"],
}


_FALLBACK_FLUSH: dict[str, Any] = {
    "user": [], "feedback": [], "project": [], "reference": [],
}


def memory_flush(
    messages: list,
    session_id: str,
    country: str = "mx",
    client: ModelClient | None = None,
) -> dict:
    """提取关键事实写入长期记忆。

    返回：{"status": "ok"|"model_unavailable", "written": {...}, "extracted": {...}}
    messages：OrchestratorMessage 列表或 dict 列表，底层统一 model_dump。
    """
    client = client or ModelClient()
    msg_text = format_messages(messages)
    prompt = FLUSH_PROMPT.format(messages=msg_text)
    result = client.generate_structured(
        skill_name="memory_flush",
        prompt=prompt,
        fallback_result=_FALLBACK_FLUSH,
        response_schema=_FLUSH_RESPONSE_SCHEMA,
        route_key="memory.summarizer",
    )
    status = result.get("status", "ok")
    extracted = result.get("structured_result", _FALLBACK_FLUSH)

    written = {"user": 0, "feedback": 0, "project": 0, "reference": 0}
    if status == "ok":
        # v3.2 P1 凭据安全门（CLAUDE.md §13 Zero Tolerance）：LLM 提取出的事实可能含原始凭据
        # （用户在对话里贴了 host/port/password / token / key / secret）。写盘前必须调用
        # `data_acquisition_agent.redactor.redact()` 脱敏。用同一套 redactor 保证与 Plan 07/08
        # prompt assembler / SQL judge 凭据扫描口径一致。
        from data_acquisition_agent.redactor import redact
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        for category in written:
            for idx, item in enumerate(extracted.get(category, [])):
                if not isinstance(item, str) or not item:
                    continue
                redacted_item, hits = redact(item)
                if hits > 0:
                    # 发现凭据过 redact：记一条 warning log（不报错不中断）、用脱敏后的文本写盘
                    import logging
                    logging.getLogger(__name__).warning(
                        "memory_flush 检出凭据并脱敏 session=%s category=%s hits=%d",
                        session_id, category, hits,
                    )
                key = f"{country}/{session_id}/{category}/{ts}_{idx}"
                write_result = memory_write(MemoryWriteInput(key=key, value=redacted_item))
                if write_result.ok:
                    written[category] += 1
    # status == "model_unavailable"时不写盘（fallback 全空），extracted 仍返供上层调用者采用。
    return {"status": status, "written": written, "extracted": extracted}
```

### Task 3.2 unit test
**Create**: `tests/orchestrator_agent/test_memory_flush.py`
**v3.2 修复**：monkeypatch 改为 `tools.memory._project_root`（v3.1 走 settings.project_root 会被 pydantic 拒绝）。mock `generate_structured` 返 dict 包装、与 Task 3.1 重写后的 `memory_flush` 一致。
**完整代码**：
```python
from unittest.mock import MagicMock
from app.services.orchestrator_agent.memory_flush import memory_flush


MEMORY_MOD = "app.services.orchestrator_agent.tools.memory"


def test_flush_writes_extracted_facts(tmp_path, monkeypatch):
    monkeypatch.setattr(f"{MEMORY_MOD}._project_root", lambda: tmp_path)
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = {
        "status": "ok",
        "structured_result": {
            "user": ["用户偏好中文"],
            "feedback": [],
            "project": ["本周做双国上线"],
            "reference": [],
        },
        "model_name": "gemini-2.5-flash",
        "prompt_preview": "从...",
    }
    messages = [{"role": "user", "content": "我想做双国"}]
    result = memory_flush(messages, "s1", "mx", client=mock_client)
    assert result["written"]["user"] == 1
    assert result["written"]["project"] == 1
    assert result["written"]["feedback"] == 0
    assert result["status"] == "ok"


def test_flush_falls_back_when_model_unavailable(tmp_path, monkeypatch):
    """v3 新增：status=model_unavailable 时 written 全 0、不 raise。"""
    monkeypatch.setattr(f"{MEMORY_MOD}._project_root", lambda: tmp_path)
    mock_client = MagicMock()
    mock_client.generate_structured.return_value = {
        "status": "model_unavailable",
        "structured_result": {"user": [], "feedback": [], "project": [], "reference": []},
        "model_name": "gemini-2.5-flash",
        "prompt_preview": "",
    }
    result = memory_flush([{"role": "user", "content": "hi"}], "s2", "mx", client=mock_client)
    assert result["written"] == {"user": 0, "feedback": 0, "project": 0, "reference": 0}
    assert result["status"] == "model_unavailable"
```

### Phase 3 commit
```bash
git add app/services/orchestrator_agent/memory_flush.py tests/orchestrator_agent/test_memory_flush.py
git commit -m "feat(10): phase 3 memory flush"
```

---

## Phase 4 — 集成到 agent_loop

### Task 4.1 实现 ensure_context_fits + load_session_memories
**Create**: `app/services/orchestrator_agent/context_fit.py`
**v3.2 修复**（对照 v3.1）：
- v3.1 在入口把 `OrchestratorMessage` 转 dict、出口转回——与 Phase 2 v3.2 重写后不再需要 dict 转换（压缩函数原生接 OrchestratorMessage）。本文件去掉 `_to_dicts` / `_to_orchestrator_messages`。
- L2 现需 `session.tool_calls`，`ensure_context_fits` 接 session 后传 `session.tool_calls`。

**完整代码**:
```python
"""ensure_context_fits + load_session_memories (Plan 10 Phase 4 / v3.2)."""
from __future__ import annotations

import os

from .memory_flush import memory_flush
from .memory_manager import (
    compress_level_1, compress_level_2,
    compress_iteratively, compress_level_4,
)
from .summarizer import summarize_messages, iterative_summarize
from .tools.memory import read_all_categories


COMPRESSION_THRESHOLD = 0.85

# v3 修复：`MODEL_MAX_TOKENS` 不存在于 budget.py（实际只有 DEFAULT_BUDGET=500_000，
# 那是 session 累计 token 上限，不是单轮 prompt 窗口）。本常量在模块级提供单轮上限：
# gemini-2.5-flash context window = 1_048_576 tokens，留 20% buffer。
MODEL_MAX_TOKENS_PER_TURN = 800_000


def estimate_tokens(messages: list) -> int:
    """简单估算：每个字符约 0.3 token（CJK 加权，算 //3 走底）。
    接 list[OrchestratorMessage] 或 list[dict] 均可。
    """
    total = 0
    for m in messages:
        if hasattr(m, "content"):
            content = m.content
        else:
            content = m.get("content", "")
        if isinstance(content, str):
            total += len(content) // 3
    return total


def load_session_memories(session_id: str, country: str = "mx") -> str:
    """首轮加载长期记忆，用于拼接进 system_prompt（不进 messages）。

    v3.2 P1 修复：活跃用户可能一个 session 累积 >> 50 条记忆，全量拼接会爆 context。
    V1 硬上限 = 50 条（按记忆顺序取最近 50，read_all_categories 返回已按时间戳升序）。
    V2/V3 升级 BM25 / 向量库后可按相似度取 top-k，不再需要硬上限。
    """
    items = read_all_categories(country, session_id)
    if not items:
        return ""

    # V1 硬上限：超 50 条仅保留最近 50 条，防 context 爆炸
    MAX_MEMORY_ITEMS = 50
    if len(items) > MAX_MEMORY_ITEMS:
        import logging
        logging.getLogger(__name__).warning(
            "load_session_memories session=%s country=%s 记忆 %d 超 %d，仅加载最近 %d 条",
            session_id, country, len(items), MAX_MEMORY_ITEMS, MAX_MEMORY_ITEMS,
        )
        items = items[-MAX_MEMORY_ITEMS:]

    by_cat = {"user": [], "feedback": [], "project": [], "reference": []}
    for it in items:
        cat = it.get("category")
        if cat in by_cat:
            by_cat[cat].append(it.get("content", ""))

    parts = ["## 历史记忆"]
    for cat, contents in by_cat.items():
        if contents:
            parts.append(f"### {cat}")
            for c in contents:
                parts.append(f"- {c}")
    return "\n".join(parts)


def ensure_context_fits(session, country: str, max_tokens: int) -> bool:
    """返回是否做了压缩。session = OrchestratorSession（session.messages = list[OrchestratorMessage]）。"""
    if os.getenv("MEMORY_COMPRESSION_ENABLED", "1") == "0":
        return False

    if estimate_tokens(session.messages) / max_tokens < COMPRESSION_THRESHOLD:
        return False

    # 1. Memory Flush（必做）——提取关键事实到长期记忆
    memory_flush(session.messages, session.session_id, country or "mx")

    # 2. 4 级压缩——全部接 OrchestratorMessage、不转 dict
    msgs = session.messages
    msgs = compress_level_1(msgs)
    if estimate_tokens(msgs) / max_tokens > COMPRESSION_THRESHOLD:
        msgs = compress_level_2(msgs, session.tool_calls)
    if estimate_tokens(msgs) / max_tokens > COMPRESSION_THRESHOLD:
        msgs = compress_iteratively(msgs, summarize_messages, iterative_summarize)
    if estimate_tokens(msgs) / max_tokens > COMPRESSION_THRESHOLD:
        msgs = compress_level_4(msgs, summarize_messages)

    session.messages = msgs
    return True
```

### Task 4.2 （合并到 4.1）load_session_memories 已在 context_fit.py 一起实现
说明：按 Spec §8.1 集成思路，`load_session_memories` 与 `ensure_context_fits` 同文件为 `context_fit.py` 提供，避免拆到 `agent_loop.py`。

### Task 4.3 集成到 agent_loop 主循环（v3.2 精确 patch，以 ground truth 为准）
**Modify**: `app/services/orchestrator_agent/agent_loop.py`
**严格要求**：仅 2 个集成点。**不动 MAX_ROUNDS / SSE / ack_bus / budget / resilience**。

**v3.2 二轮修复**（对照 v3.1）：v3.1 集成点 2 oldString 写的是 `content=llm_out.get("final_answer") or llm_out.get("thought", "")` —— **与实际代码一行不对**：实际是 `content=decision["final_message"]`、用 `datetime.now(timezone.utc)`、final 分支后立即 `return`（L155）插在那毫无意义。v3.2 把集成点 2 改到「tool 调用结果 append 之后、下一轮 for 循环之前」(L272 之后)，给出能 `git apply` 直接命中的精确 oldString/newString。

ground truth（已过 grep + read_file 验证 2026-05-06 v3.2 重核）：
- L19: `from app.core.model_client import ModelClient`
- L29: `from app.services.orchestrator_agent.system_prompt import assemble_system_prompt`
- L30: `from app.services.orchestrator_agent.tools import get_tool_registry`
- L33: `MAX_ROUNDS = 15`
- L83: `async def run_agent_loop(...)`
- L89-L91: `session.messages.append(OrchestratorMessage(role="user", ...))` —— 在主循环前已 append 用户首条消息
- L98: `detected_country = _detect_country(prompt)`
- L99: `system_prompt = assemble_system_prompt(detected_country)`
- L101: `for round_idx in range(MAX_ROUNDS):`
- L138-155: final 分支（`if decision.get("final_message"):` ... `return`）—— **final 后立即 return，不可在这里插压缩**
- L272-277: `# 7) Append tool result for next round` + `session.messages.append(...)` + `save_session(session)` —— 主循环末尾、下一轮 for 顶之前，是真正的压缩插入点
- L279-280: `# MAX_ROUNDS reached without final` + `yield {"type": "error", ...}`

---

**集成点 1**：首轮加载长期记忆（拼进 system_prompt）

**Patch 1 — import（oldString 含 L29-L30 两行 import 上下文，避免与其它 import 撞）**：

*oldString*：
```python
from app.services.orchestrator_agent.system_prompt import assemble_system_prompt
from app.services.orchestrator_agent.tools import get_tool_registry
```
*newString*：
```python
from app.services.orchestrator_agent.system_prompt import assemble_system_prompt
from app.services.orchestrator_agent.context_fit import (
    ensure_context_fits, load_session_memories,
    MODEL_MAX_TOKENS_PER_TURN,
)
from app.services.orchestrator_agent.tools import get_tool_registry
```

**Patch 2 — 首轮拼接长期记忆（oldString 含 L98-L101 上下文）**：

*oldString*：
```python
    detected_country = _detect_country(prompt)
    system_prompt = assemble_system_prompt(detected_country)

    for round_idx in range(MAX_ROUNDS):
```
*newString*：
```python
    detected_country = _detect_country(prompt)
    system_prompt = assemble_system_prompt(detected_country)

    # Plan 10 Phase 4 集成点 1：首轮拼接长期记忆（不进 messages，仅拼 system_prompt）。
    # ground truth: L89-L91 已在主循环前 append 用户首条消息，所以首轮时 len(messages) == 1。
    if detected_country and len(session.messages) == 1:
        memory_context = load_session_memories(session.session_id, detected_country)
        if memory_context:
            system_prompt = system_prompt + "\n\n" + memory_context

    for round_idx in range(MAX_ROUNDS):
```

---

**集成点 2**：每轮 tool 结果 append 后检查压缩（v3.2 重写：插在 L272-277 块尾部）

> **关键**：final 分支（L138-155）后立即 `return`，**不能**在 final 分支内插压缩。真正的「下一轮 LLM call 之前」窗口在 tool 调用完成、tool message append 落盘之后、`for` 循环回到顶部之前。

**Patch 3 — tool dispatch 完成后压缩（oldString 含 L272-280 完整段，避免与其他 `save_session(session)` 冲突）**：

*oldString*：
```python
        # 7) Append tool result for next round
        session.messages.append(OrchestratorMessage(
            role="tool", tool_call_id=tool_call_id,
            content=json.dumps(record.output, ensure_ascii=False),
            timestamp=datetime.now(timezone.utc),
        ))
        save_session(session)

    # MAX_ROUNDS reached without final
    yield {"type": "error", "message": f"Max rounds {MAX_ROUNDS} reached"}
```
*newString*：
```python
        # 7) Append tool result for next round
        session.messages.append(OrchestratorMessage(
            role="tool", tool_call_id=tool_call_id,
            content=json.dumps(record.output, ensure_ascii=False),
            timestamp=datetime.now(timezone.utc),
        ))
        save_session(session)

        # Plan 10 Phase 4 集成点 2：本轮工具结果落盘后、下一轮 LLM 调用前检查压缩。
        # 仅在 messages token 估值 / max_tokens > 0.85 时触发，否则 no-op。
        ensure_context_fits(
            session,
            country=detected_country or "mx",
            max_tokens=MODEL_MAX_TOKENS_PER_TURN,
        )

    # MAX_ROUNDS reached without final
    yield {"type": "error", "message": f"Max rounds {MAX_ROUNDS} reached"}
```

> **为什么不在 final 分支也加？** —— final 分支后立即 `return`，本轮 messages 不会再进下一轮 LLM；同时若用户再发新 prompt 会调用 `run_agent_loop` 新一轮、首轮会通过集成点 1 重新加载长期记忆，故 final 路径无需压缩。

**验证命令**：
```powershell
python -m pytest tests/orchestrator_agent/ -v 2>&1 | Select-String "passed|failed" | Select-Object -Last 3
```
**预期**：Phase 1 + 2 + 3 新增测试全过，现有 OrchestratorAgent 测试不破。

### Task 4.4 （已合并）memory_write/memory_read 工具注册 — 跳过
**说明**：现有 `app/services/orchestrator_agent/tools/__init__.py::get_tool_registry()` 已包含 `memory_write` / `memory_read`。**本 Plan 不重复注册**（原草稿写的 `tools.py` 路径不存在，实际是 `tools/__init__.py`）。如需为 system_prompt 补充主推荐描述，可选 Modify `system_prompt.py`，但不在本 Plan 范围。

### Phase 4 commit
```powershell
git add app/services/orchestrator_agent/context_fit.py app/services/orchestrator_agent/agent_loop.py
git commit -m "feat(10): phase 4 ensure_context_fits + load_session_memories (no MAX_ROUNDS / SSE change)"
```

---

## Phase 5 — 验收 + [complete]

### Task 5.1 15 轮（MAX_ROUNDS 上限）连续 E2E 测试
**Create**: `tests/orchestrator_agent/test_long_session.py`
**说明**：MAX_ROUNDS=15 是现有熔断常量，本测试不打破，仅验证 15 轮内 token 增长触发压缩后总量不超阈值。
**完整代码**:
```python
"""Long session simulation (Plan 10 Phase 5)."""
from datetime import datetime

from app.services.orchestrator_agent.schemas import OrchestratorMessage, OrchestratorSession
from app.services.orchestrator_agent.context_fit import (
    ensure_context_fits, estimate_tokens,
)


def _make_session() -> OrchestratorSession:
    return OrchestratorSession(
        session_id="test_long",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )


def test_compression_kicks_in_when_threshold_exceeded(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.memory._project_root",
        lambda: tmp_path,
    )
    # 禁用真实 LLM，memory_flush / summarize_messages / iterative_summarize 全走 mock
    monkeypatch.setattr(
        "app.services.orchestrator_agent.context_fit.memory_flush",
        lambda *a, **kw: {"written": {"user": 0, "feedback": 0, "project": 0, "reference": 0}},
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.context_fit.summarize_messages",
        lambda msgs: "[mock summary]",
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.context_fit.iterative_summarize",
        lambda old, new: "[mock iterative summary]",
    )

    state = _make_session()
    MAX_TOKENS = 2_000   # 测试用小窗口

    for i in range(15):   # MAX_ROUNDS 上限
        now = datetime.now()
        state.messages.append(OrchestratorMessage(
            role="user", content=f"问题 {i}: " + "x" * 200, timestamp=now,
        ))
        state.messages.append(OrchestratorMessage(
            role="assistant", content="回答 " + "y" * 200, timestamp=now,
        ))
        ensure_context_fits(state, country="mx", max_tokens=MAX_TOKENS)

    final_tokens = estimate_tokens(state.messages)
    assert final_tokens < MAX_TOKENS, f"Final {final_tokens} > max {MAX_TOKENS}"
```

### Task 5.2 同-session_id 多次连接召回验证
**Create**: `tests/orchestrator_agent/test_same_session_recall.py`
**说明**: V1 仅支持 同一 session_id 在多次连接中复用记忆（不是跨 user，不是跨 session_id）。原草稿的"跨 session"命名误导，本 Plan 改为 `same_session_recall`。V2 加 user_id 后才能真正跨 session。
**完整代码**:
```python
from app.services.orchestrator_agent.schemas import MemoryWriteInput
from app.services.orchestrator_agent.tools.memory import memory_write
from app.services.orchestrator_agent.context_fit import load_session_memories


def test_same_session_id_recall_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.memory._project_root",
        lambda: tmp_path,
    )
    memory_write(MemoryWriteInput(
        key="mx/s1/user/01", value="用户偏好中文回复",
    ))
    ctx = load_session_memories("s1", "mx")
    assert "用户偏好中文回复" in ctx
    # 不同 session_id 应读不到
    ctx_other = load_session_memories("s_other", "mx")
    assert "用户偏好中文回复" not in ctx_other
```

### Task 5.3 Memory Flush 落盘验证
**手动步骤**:
1. 启动 OrchestratorAgent，跑 15 轮（MAX_ROUNDS 上限）
2. 触发压缩（人工调低阈值可能需要 patch，只验证路径）
3. 检查 `outputs/memory/mx/{session_id}/*.jsonl` 应有内容
```powershell
Get-ChildItem outputs/memory/mx/ -Recurse -File | Select-Object FullName
```

### Task 5.4 兜底开关精确断言
**Create**: `tests/orchestrator_agent/test_compression_disabled.py`
**完整代码**:
```python
from datetime import datetime

from app.services.orchestrator_agent.schemas import OrchestratorMessage, OrchestratorSession
from app.services.orchestrator_agent.context_fit import ensure_context_fits


def test_disabled_via_env(monkeypatch):
    monkeypatch.setenv("MEMORY_COMPRESSION_ENABLED", "0")
    state = OrchestratorSession(
        session_id="s", created_at=datetime.now(), updated_at=datetime.now(),
    )
    # 填充到超阈值
    for _ in range(20):
        state.messages.append(OrchestratorMessage(
            role="user", content="x" * 5000, timestamp=datetime.now(),
        ))
    n_before = len(state.messages)
    did_compress = ensure_context_fits(state, country="mx", max_tokens=1_000)
    assert did_compress is False
    assert len(state.messages) == n_before   # 未压缩，messages 不变
```

### Task 5.5 全量回归
```powershell
python -m pytest tests/ -v 2>&1 | Select-String "passed|failed" | Select-Object -Last 3
```
**预期**: 数字 ≥ baseline + 本 Plan 新增 memory 测试。

### Task 5.6 [complete] commit + push
```powershell
git commit --allow-empty -m "[complete] plan-10 — memory system with 4-level compression + flush"
git push origin main
```

---

## 五点检查法（自审）

| # | 检查项 | v2 | v3 | v3.1 | v3.2 |
|---|---|---|---|---|---|
| 1 | 精确文件路径 | ✅ | ✅ | ✅ | ✅ |
| 2 | 无占位符 | ✅ | ⚠️ Task 4.3 集成点 2 「或」占位 | ⚠️ Task 4.3 集成点 2 oldString 字段名（final_answer/thought）与 ground truth 不符（实际 `decision["final_message"]`）；插在 final 后但 final 立即 `return` 无效 | ✅ 修复：Task 4.3 集成点 2 重写为 tool dispatch 完成后插入（L272 后），oldString 完全对齐 agent_loop.py 实际代码 |
| 3 | 完整代码块 | ⚠️（summarizer / memory_flush 调不存在的 `client.generate()`） | ⚠️ Task 3.1 顶部声明修了但代码块未同步 | ⚠️ L2 检查 `msg.tool_calls`（不存在字段，整段 no-op）+ Task 4.1 dict 转换冗余 | ✅ 修复：Phase 2 全量原生 OrchestratorMessage + ToolCallRecord（B 方案 ToolCallRecord-级去重）；Phase 4 去 dict 转换冗余 |
| 4 | 验证命令 + 预期 | ✅ | ✅ | ✅ | ✅ Phase 0 Task 0.1 加 Python import smoke（提前暴露 google-genai / pydantic / app.core 环境问题） |
| 5 | 一个不熟悉项目的人能独立执行完 | ⚠️（Task 4.3 patch 占位「待 Phase 0 读出后才能写出」；`len == 0` 逻辑错） | ⚠️ Task 4.3 集成点 2 仍有「或」字样 + Task 3.1 API 误 | ⚠️ L2 整段 no-op + 7 个测试 monkeypatch `settings.project_root` 抛 ValueError + Task 4.3 集成点 2 oldString 与实际不符 | ✅ P1 ToolCallRecord-级 B 方案；P2 `_project_root()` helper；P3 import smoke；P4 Task 4.3 oldString 全量对齐 ground truth |

---

## 回滚预案

```powershell
$env:MEMORY_COMPRESSION_ENABLED="0"
```

无效则 `git reset --hard {baseline_commit}`。

---

## 风险登记

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 摘要"信息蒸发"导致目标丢失 | 中 | 高 | 迭代更新 + Memory Flush 双保险 |
| 切割边界破坏 tool_call/tool_result 配对 | 中 | 中 | align_tool_pairs() + unit test |
| Memory Flush 提取错（误判重要事实） | 中 | 中 | 仅辅助记忆，不替代 messages |
| outputs/memory 占磁盘 | 低 | 低 | TTL 90 天（V2 加清理脚本），现 .gitignore 已含 outputs/ |
| 集成点 patch 在现 agent_loop 不同实际函数签名上错位 | 中 | 高 | Phase 0 Task 0.1 必须读完 agent_loop.py 顶 80 行后再写 Task 4.3 patch |

---

## 测试矩阵

| 类别 | 范围 | 触发 |
|---|---|---|
| memory_tools 单元 | tests/orchestrator_agent/test_memory_tools.py | Phase 1/5 |
| 4 级压缩单元 | test_memory_manager.py | Phase 2/5 |
| Flush 单元 | test_memory_flush.py | Phase 3/5 |
| 15 轮（MAX_ROUNDS 上限）压缩 E2E | test_long_session.py | Phase 5 |
| 同 session_id 多次连接召回 | test_same_session_recall.py | Phase 5 |
| 兜底开关精确断言 | test_compression_disabled.py | Phase 5 |
| 全量回归 | tests/ | Phase 5 |

---

## TASK.md 记一行

```markdown
- [ ] Memory + 召回（Harness 长对话）→ docs/plans/10-memory-system-plan.md
```

---

## 附录 E、v3.2.1 Errata（4 项 MAJOR 警示，本 Plan 不改代码块，仅作为 Phase 执行时 Claude Code 必读防坊说明）2026-05-05 补

> 该列问题 v3.2 主 Plan 文本均已以默认代码路径领位（能跳完 Phase 0–5 所有验收），本 Errata 仅记录已知精度 / 性能 / 边界问题供未来 V2 / 执行时参考，不阻塞 Phase 获取 [complete] 标记。

### E1 (M1) `estimate_tokens` 估算精度底线不足

**现状**（Phase 4 Task 4.1 `context_fit.py`）：
```python
total += len(content) // 3   # CJK 加权 0.33 token/char
```

**问题**：
- 全中文场景实测偏差可能达 **低估 5–10%**（gemini-2.5-flash 实际 ≈ 0.4 token/char）。
- 接近 0.85 阈值时可能发生“估算 < 85% 不触发压缩，但真实已 87%+”，压缩启动延迟 1–2 轮。
- 50KB 以上的 tool_result（如 `query_data` 返 100 条）偏差更严重（JSON 密集）。

**Phase 4 运行时防坊**：调用 `ensure_context_fits` 的入口阈值从 0.85 下调为 **0.80**（留 5% buffer 补偏差）— Plan Phase 4 Task 4.3 按需在 patch newString 中调，不动其他位置。

**V2 路径**：改调 ModelClient 内置 `count_tokens(text, model_name)` API（genai SDK 原生接口）代替估算，误差应 < 1%。V1 不动。

### E2 (M2) `_project_root` monkeypatch 在跨 test 污染风险

**现状**（Phase 1 Task 1.3 单测）：
```python
MEMORY_MOD = "app.services.orchestrator_agent.tools.memory"
monkeypatch.setattr(f"{MEMORY_MOD}._project_root", lambda: tmp_path)
```

**问题**：
- `_project_root()` 内部访问 `settings.project_root`（`@property`）。若 conftest 级别有别的 test 修改了 settings 单例的其他属性（如 `data_source`），跨 test 运行顺序下 _project_root 可能读到奇怪状态。
- monkeypatch 作用于函数对象能隔离 _project_root 返回值，但不能隔离 settings 单例本身。

**Phase 1 运行时防坊**：`tests/orchestrator_agent/test_memory_tools.py` 所有 fixture 都加 `monkeypatch.delenv` / `monkeypatch.setenv` 清环境变量，或在 conftest.py 中加：
```python
@pytest.fixture(autouse=True)
def _reset_settings_singleton():
    yield
    # 清理可能被别的 test 污染的 settings 实例缓存。
    from app.core import config as cfg_mod
    cfg_mod._cached_settings = None  # 如果有这个设计
```

**V2 路径**：考虑把 settings 改为 `Annotated[Settings, Depends(get_settings)]` FastAPI 依赖注入模式，test 里正常 override。V1 不动。

### E3 (M3) `MAX_MEMORY_ITEMS = 50` 硬上限长期活跃用户记忆丢失

**现状**（Phase 4 Task 4.1 `load_session_memories`）：
```python
MAX_MEMORY_ITEMS = 50
if len(items) > MAX_MEMORY_ITEMS:
    items = items[-MAX_MEMORY_ITEMS:]   # 仅保留最近 50 条
```

**问题**：
- 单 session 运行 60+ 天，记忆可能 > 50 条 → 最旧条目**永远不被拼进 system_prompt**（但还在磁盘 outputs/memory/ 上）。
- WARN 日志高频打印（每轮评估压缩都评估一次）→ 日志爆炸。

**Phase 4 运行时防坊**：
1. `MAX_MEMORY_ITEMS` 限仅拍后 5 条 WARN 限频 1 次（加一个 `_warned_session_ids: set[str]` 变量）。
2. 在 `load_session_memories` 返回中加提示：`f"\n> 提示：本 session 容量已超 {MAX_MEMORY_ITEMS}，只加载最近条目"`。

**V2 路径**：考虑加一个 TTL cleanup job（按 `ttl_days: 90` 字段过期清理 outputs/memory/）+ 升级语义召回（跳出“最近 N 条”逻辑）。V1 不动。

### E4 (M4) `memory_flush` 内 `redact()` 逐条调用性能未定额

**现状**（Phase 3 Task 3.1 memory_flush.py）：
```python
for category in written:
    for idx, item in enumerate(extracted.get(category, [])):
        redacted_item, hits = redact(item)   # 逐条 redact（0–20 次/flush）
```

**问鎘**：
- `data_acquisition_agent/redactor.redact()` 未被本 Plan 取样 benchmark。按实测单次调用 ≈ 0.5–2 ms（20 次 = 10–40 ms）— 不会明显拖慢压缩。
- 但如果未来 V2 补了更多凭据模式（由 11 增加到 50+ family），会退化为 100–500 ms。

**Phase 3 运行时防坊**：
1. `memory_flush` 内 `redact` 的调用加 `time.perf_counter()` 打点，超 200 ms / per flush 记 WARN。
2. Phase 3 Task 3.2 单测 `test_memory_flush_extracts_four_classes` 加 timeout 约束：`@pytest.mark.timeout(2)`。

**V2 路径**：为 redactor 增加批量接口 `redact_batch(items: list[str]) -> list[tuple[str, int]]`，避免逐条正则重复初始化。V1 不动。

---

## 附录 F、依赖与调度说明—2026-05-05 补

- **Tier 0 共享前置已落（在项目根）**：
  - `requirements.txt` +3 行：`rank-bm25` / `jieba` / `sqlglot`。本 Plan 不使用 sqlglot，不受影响。
  - `config.yaml::llm.routes` +3 行：`memory.summarizer: gemini` / `sql_judge.l2: gemini` / `eval.judge: gemini`。**本 Plan Phase 2 Task 2.4 加路由 patch 可跳过**（已同步加进 config.yaml），仅需验证`Test-Path` + `python -c "from app.core.config import llm_provider_for; print(llm_provider_for('memory.summarizer'))"` 返回 `gemini`。
- **Phase 0 baseline test 数 N₀ = 164**（实测 2026-05-05 `pytest data_acquisition_agent/tests/ --collect-only`）。Plan 10 不依赖 da-agent，不需跟 164 化。mx 画像主仓 baseline N₀ 按 `pytest tests/ --collect-only` 现场开走。
- **与 Plan 07 / 08 / 09 冲突**：零。本 Plan 仅动 `app/services/orchestrator_agent/agent_loop.py` + `tools/memory.py`，同上 3 个 Plan 代码路径零交集。
