# Design Doc 10 — Memory 系统（4 级压缩 + Memory Flush + 长期记忆 four-class）

> **STATUS**: ✅ **READY-FOR-PLAN — v3.2** （v3.2 三轮把 §3.3 L2 / §3.4 HEAD_PROTECT / §6.1 _project_root 三处与 ground truth 对不上的设计同步干净，待用户最终复审后正式进入 Plan 执行）
>
> **v3.2 三轮修订点**（对照 v3.1）：
> - **§3.3 L2 重写**：v3.1 伪代码 `if msg.get("tool_calls")` —— `OrchestratorMessage` 没有 `tool_calls` 字段（[`schemas.py:103`](app/services/orchestrator_agent/schemas.py)），整段 L2 是 no-op。v3.2 改 B 方案：基于 `OrchestratorSession.tool_calls: list[ToolCallRecord]` 去重，按 `(tool_name, json_input, json_output)` 三元组重复 → 后续 tool_call_id 关联的 tool message 替换占位符。
> - **§3.4 HEAD_PROTECT 同步**：v3.1 `HEAD_PROTECT = 3 # 首轮 user + 首轮 assistant + 可选 tool` 不成立，项目 assistant 仅在 final turn 由 `agent_loop.py L143` 一次 append。v3.2 改 `HEAD_PROTECT = 1`（仅保护首条 user）。
> - **§6.1 加 `_project_root()` helper**：`Settings.project_root` 是 `@property`、不是 declared field（[`config.py:61`](app/core/config.py)），pydantic v2 不允许 `monkeypatch.setattr(settings, "project_root", ...)`（抛 ValueError）。v3.2 在 `tools/memory.py` 暴露可被 monkeypatch 的 `_project_root()` 函数，`memory_write` / `memory_read` / `_memory_dir` 全部走 helper。
> - **§7.1 ensure_context_fits 同步**：v3.1 `compress_level_2(msgs)` 单参，v3.2 改为 `compress_level_2(msgs, session.tool_calls)` 注入 ToolCallRecord 列表。
>
> **v3.1 二轮修订点**（对照 v3，保留供溯源）：
> - **API 同步 (§3.4 / §3.6 / §3.7 / §4)**：v3 仅修顶部声明未走下文伪代码；以上 4 处 `llm_client.generate(...)` 全量重写为 `client.generate_structured(...)` + `payload = result["structured_result"]`。
> - **§2.1 同步**：`model_max_tokens` 与§8.1 + Plan 同名常量 `MODEL_MAX_TOKENS_PER_TURN` 对齐。
> - **§5.2 同步**：第一张存储结构图补 `{country}` 层，跳过「后续另加 country」双表迷惑。
> - **§6.1 代码注释**：修「它个路径選擇」「孔雀升级」 typo；§6.2 description 中字面量 `\u3002` 改为「。」。
> - **§7.1 同步**：`memory_read(session_id=, country=)` 与现有 `MemoryReadInput(key_pattern: str)` schema 不符，改为调 `read_all_categories(country, session_id)`。
> - **§10.5 同步**：V1 不支持跨 session、合实际 Plan Task 5.2 `same_session_recall`。
>
> **v3 修订点**（对照 v2）：
> - **API 同步**：Spec 全文出现的 `llm_client.generate(prompt, route_key=...)` 为设计伪代码。**真实落地走 `client.generate_structured(skill_name, prompt, fallback_result, response_schema=None, *, route_key=None) -> dict`**，然后从 `result["structured_result"]` 取 payload、并处理 `result["status"] == "model_unavailable"` 的 fallback 路径。Plan v3 Task 2.3 / Task 3.1 / Task 4.3 已给出精确代码。
> - **first-turn 识别**：§8.1 伪代码的 `len(session.messages) == 0` 在现有 `agent_loop.py` 中 **永远为 False**（用户首条消息在 L89-L91 已 append）。修复：改 `len == 1`；Plan v3 Task 4.3 已以 ground truth 重写 patch。
> - **MODEL_MAX_TOKENS 同步**：§8.1 伪代码中 `MODEL_MAX_TOKENS` 仅用于表达「单轮 prompt 上限」。现有 `budget.py` 仅有 `DEFAULT_BUDGET=500_000`（session 累计）。Plan v3 在 `context_fit.py` 定义模块常量 `MODEL_MAX_TOKENS_PER_TURN = 800_000`（gemini-2.5-flash 1M 留 20% buffer）。本 Spec 中 `MODEL_MAX_TOKENS` 读为 `MODEL_MAX_TOKENS_PER_TURN`。
>
> **作者**: Codex / Claude（自动生成草稿）
> **日期**: 2026-05-05（v2 修订 2026-05-05） / 2026-05-06（v3 / v3.1 / v3.2 修订）
> **关联 Plan**: `docs/plans/10-memory-system-plan.md`（同步 v3.2）
> **依赖前置**: 无强前置（与 Plan 08 / Plan 09 可并行；实际调用的是 `app/services/orchestrator_agent/`，本身已存在）
> **关联文档**:
> - Harness Engineering 学习笔记 §5 Memory 层（短期/长期 + 四类记忆 + Flush）
> - Harness Engineering 学习笔记 §6 Context 层（4 级压缩）
> - `app/services/orchestrator_agent/agent_loop.py`（现有 messages 处理逻辑，`MAX_ROUNDS=15`）

> Historical note (2026-06-03): 本文中引用的 `agent_loop.py::MAX_ROUNDS=15` 与 pre-Phase 6 general-chat 主循环语义仅用于保留当时设计背景，当前 live `GeneralChatFlow` 路径已不依赖该 loop。

## Surgical Hard Boundary（硬约束）

| 不动的目录/文件 | 原因 |
|---|---|
| `data_acquisition_agent/` 整目录 | 本 Plan 不涉及，避免跨模块耦合 |
| `app/services/orchestrator_agent/agent_loop.py::MAX_ROUNDS=15` | 现有熟断常量，本 Plan 不改 |
| `agent_loop.py` 的 SSE 事件推送代码 | 仅在主循环补 2 个调用点，不改事件结构 |
| `session_store.py` / `session.py` / `budget.py` / `resilience.py` / `ack_bus.py` | 现有模块保持不动 |
| `tools/{query_data,run_profile,run_trace,parse_uid_file}.py` 4 个业务工具 | 本 Plan 只扩展 `tools/memory.py`，不动这 4 个 |

## ModelClient 强制声明

本 Plan 所有 LLM 调用（summarizer / iterative_summarize / memory_flush）**必经 `app/core/model_client.py::ModelClient`**。**禁止直接 `import google-genai`**（CLAUDE.md Zero Tolerance 第 5 条）。

## Pydantic Schema 对齐声明

现有 `agent_loop.py` 操作的 messages 不是裸 dict，而是 `app/services/orchestrator_agent/schemas.py::OrchestratorMessage`（Pydantic BaseModel）。本 Plan 压缩函数文档中的 `list[dict]` 注释是为了说明送进 LLM 的 dict 序列化形式；**实现必须用 `list[OrchestratorMessage]`**，调用点负责 `model_dump()` 转换。同时注意 `OrchestratorMessage.role` 仅 `Literal["user", "assistant", "tool"]`，**不含 "system"**——System Prompt 由 `system_prompt.assemble_system_prompt(country)` 独立拼接，不在 messages 列表头部。

---

## 0. 背景与目标

### 0.1 现状（以 git HEAD `bd05240` 为准 — Phase 0 PowerShell 已核对）
- `app/services/orchestrator_agent/` 已有多个全面运转的模块（**本 Plan 只扩展不重建**）：
  - `agent_loop.py`（顶部常量 `MAX_ROUNDS = 15`，async generator 主循环 + SSE 事件推送）
  - `tools/memory.py`（V1 minimal `memory_write` / `memory_read`，现调用 schema = `MemoryWriteInput(key, value)` / `MemoryReadInput(key_pattern)`，已在 `tools/__init__.py::get_tool_registry()` 注册）
  - `session.py`（ack 网关 + per-session query_cancelled 标志）
  - `session_store.py`（JSON 会话持久化 `outputs/orchestrator_sessions/` + atexit flush）
  - `budget.py`（Token 预算追踪，500K 上限 + 80% 警告 + 100% 硬截断）
  - `resilience.py`（连续失败熔断，K=3 次即终止）
  - `ack_bus.py`（per-session 用户授权汇合点）
  - `schemas.py`（`OrchestratorMessage` / `OrchestratorSession` / `MemoryWriteInput` / `MemoryReadInput` 都是 Pydantic BaseModel）
- **现有 `tools/memory.py` 实际写入路径**：`outputs/orchestrator_memory/{safe_key}.txt`（平铺单目录，未按国家/会话隔离、未按 four-class 分类）
- **现有 `OrchestratorSession`**：不含 `is_first_turn` / `country` 字段。本 Plan **不扩展 schema**，first-turn 识别采用 `len(session.messages) == 1` 推断（v3 修复：v2 误写为 `== 0`，但 agent_loop.py L89-L91 已在主循环前 append 用户首条消息，`== 0` 永远为 False）；country 从 `agent_loop.py` 现有 `_COUNTRY_RE` 提取逻辑复用
- **`outputs/`** 已在 `.gitignore`（第 5 行），本 Plan 新增的 `outputs/memory/...` 自动不进 git 追踪 ✅
- 已观察到的问题：
  - 长 session（30+ 轮）后 prompt 接近模型上限（gemini-2.5-flash 1M 还能撑，但成本递增）
  - **跨 session 用户偏好完全丢失**（用户每次新对话都要重述“我是 mx 的、喜欢中文回复”）
  - 工具结果膨胀（一次 `query_data` 可能返回 50KB JSON，全保留浪费 context）

### 0.2 目标
- **15 轮（MAX_ROUNDS 上限）连续对话不撑爆 Context**（自动 4 级压缩；超过 MAX_ROUNDS 由现有 agent_loop 终止机制兜底，不在本 Spec 范围）
- **同 session_id 多次连接的用户偏好可读回**（user 类记忆；V1 不支持跨 session，跨 session V2 加 user_id 后再做）
- **压缩前关键信息不丢失**（Memory Flush）
- **多次压缩信息不蒸发**（迭代更新而非重建）
- 不重建现有 `tools/memory.py` / `session_store.py` / `budget.py` / `resilience.py` — 只在其上扩展与另加新文件

### 0.3 设计依据：Harness §5 + §6

> §5：短期 messages + 长期 four-class 记忆（user/feedback/project/reference）。压缩前先 Memory Flush。
> §6：4 级压缩（Level 1 裁剪零成本 → Level 2 去重 → Level 3 LLM 摘要 → Level 4 fork 重建）。

---

## 1. 范围与非目标

### 1.1 ✅ 范围内
| 项 | 说明 |
|---|---|
| 短期记忆 4 级分级压缩 | Level 1-4 逐级触发 |
| Memory Flush（压缩前必做） | 提取关键事实写入长期记忆 |
| 长期记忆 four-class | user / feedback / project / reference |
| memory_write / memory_read 工具 | 注册到 OrchestratorAgent |
| V1 召回策略 | 全量加载 + 按 session_id 过滤 |
| 集成到 agent_loop | 每轮检查 token usage > 85% 触发 |
| 国家命名空间隔离 | 长期记忆按 country 分子目录 |

### 1.2 ❌ 非目标
| 项 | 推迟到 | 理由 |
|---|---|---|
| Vector embedding 召回 | V3 / 记忆 > 50 条 | V1 全量注入够用（< 10 条） |
| BM25 召回 | V2 / 记忆 10-50 条 | V1 不需要 |
| 跨 session 用户身份强认证 | V2 | V1 用 cookie / IP 简单方案 |
| 长期记忆参与 prompt cache | V2 | 优化项，不影响功能 |
| 摘要质量评估闭环 | V2 | 先把基础压缩跑起来 |
| **重建现有 `tools/memory.py` / `session_store.py` / `budget.py` / `resilience.py`** | 不做 | 仅扩展与另加新文件 |
| **修改现有 4 个业务工具**（`tools/{query_data,run_profile,run_trace,parse_uid_file}.py`） | 不做 | Surgical：仅动 `tools/memory.py` |
| **修改 `MAX_ROUNDS=15`** | 不做 | 现有熟断常量 |
| **修改 `OrchestratorSession` schema**（加 `is_first_turn` / `country` 字段） | 不做 | 避免与 `session_store.py` JSON 持久化格式冲突；first-turn 推断以 `len(messages)==1` 代替（v3）|

---

## 2. 短期记忆（messages 列表）

### 2.1 触发阈值

```python
# app/services/orchestrator_agent/memory_manager.py
COMPRESSION_THRESHOLD = 0.85   # Context 使用 > 85% 触发

def should_compress(usage_ratio: float) -> bool:
    return usage_ratio > COMPRESSION_THRESHOLD
```

每轮 agent_loop 调 LLM 后检查 `response.usage.total_tokens / MODEL_MAX_TOKENS_PER_TURN`。

```python
# 每轮 agent_loop 末尾
def after_each_turn(response, session_state):
    used = response.usage.total_tokens
    max_ = MODEL_MAX_TOKENS_PER_TURN   # context_fit.py 模块级常量 = 800_000
    ratio = used / max_

    log_token_ratio(session_id, ratio)

    if should_compress(ratio):
        ensure_context_fits(session_state, country, max_tokens=MODEL_MAX_TOKENS_PER_TURN)
```

---

## 3. 4 级分级压缩（对应 Harness §6.2）

### 3.1 设计原则

> 从低成本到高成本逐级尝试，便宜的方法先用，解决了就不用贵的。

| 级别 | 方法 | 成本 | 释放比例 | 触发条件 |
|---|---|---|---|---|
| L1 | 裁剪旧 tool_result（> 200 字符替换为 [truncated]） | 零（本地） | 30-50% | 每次压缩都先做 |
| L2 | 缓存去重（同工具同参数同结果只留一份） | 极低 | 10-20% | L1 后仍超阈值 |
| L3 | LLM 摘要（现有 `gemini` provider 下的 gemini-2.5-flash 生成结构化摘要） | 中（1 次 LLM 调用） | 5-20× 压缩 | L1+L2 后仍 > 85% |
| L4 | Fork 子 Agent 全量重建 | 高 | 彻底释放 | L3 后仍超 |

### 3.2 Level 1 实现

```python
def compress_level_1(messages: list[dict]) -> list[dict]:
    """裁剪旧 tool_result，最近 5 轮不动"""
    TAIL_PROTECT = 5
    cutoff = max(0, len(messages) - TAIL_PROTECT)

    for i, msg in enumerate(messages[:cutoff]):
        if msg.get("role") == "tool":
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 200:
                msg["content"] = "[已裁剪：原长度 {} 字符]".format(len(content))
    return messages
```

### 3.3 Level 2 实现（缓存去重 — v3.2 重写：基于 ToolCallRecord）

> **v3.2 修复**：v3 / v3.1 伪代码检查 `msg.get("tool_calls")`——但项目 [`OrchestratorMessage`](app/services/orchestrator_agent/schemas.py) **没有 `tool_calls` 字段**（仅 role / content / tool_call_id / timestamp），整段 L2 是 no-op。
> 实际工具调用详情存放在 `OrchestratorSession.tool_calls: list[ToolCallRecord]`（见 schemas.py），tool message 与 ToolCallRecord 通过 `tool_call_id` 关联。
> v3.2 改为按 ToolCallRecord 去重：相同 `(tool_name, json.dumps(input, sort_keys=True), json.dumps(output, sort_keys=True))` 的调用只保留首次，后续 `tool_call_id` 对应的 tool message 内容替换为占位符；最近 `TAIL_PROTECT` 内的 tool 不动。

```python
import hashlib
import json
from app.services.orchestrator_agent.schemas import OrchestratorMessage, ToolCallRecord


def _hash_payload(payload: object) -> str:
    s = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def compress_level_2(
    messages: list[OrchestratorMessage],
    tool_calls: list[ToolCallRecord],
) -> list[OrchestratorMessage]:
    """同 (tool_name, input, output) 重复调用只保留首次；TAIL_PROTECT 内不动。"""
    TAIL_PROTECT = 5
    if not tool_calls:
        return messages

    tail_ids = {
        m.tool_call_id for m in messages[-TAIL_PROTECT:]
        if m.role == "tool" and m.tool_call_id
    }

    seen: dict[tuple[str, str, str], str] = {}
    duplicate_ids: set[str] = set()
    for rec in tool_calls:
        if rec.status != "done" or not rec.tool_call_id:
            continue
        if rec.tool_call_id in tail_ids:
            continue
        key = (rec.tool_name, _hash_payload(rec.input), _hash_payload(rec.output))
        if key in seen:
            duplicate_ids.add(rec.tool_call_id)
        else:
            seen[key] = rec.tool_call_id

    for msg in messages:
        if msg.role == "tool" and msg.tool_call_id in duplicate_ids:
            msg.content = "[结果重复，已去重]"
    return messages
```

> **HEAD_PROTECT 同步说明**：项目 assistant 仅在 final turn 被 append（agent_loop.py L143），HEAD_PROTECT=3 不成立 — `compress_level_3` 改 `HEAD_PROTECT=1`（仅保留首条 user）。详见 §3.4。

### 3.4 Level 3 实现（LLM 摘要）

**保护首尾，只压中间**：

```python
def compress_level_3(messages: list, llm_client) -> list:
    """LLM 摘要中间轮次。messages 是 Pydantic OrchestratorMessage 或 dict。"""
    # v3.2：项目 assistant 仅在 final turn append (agent_loop.py L143)
    # 中间轮次没有 assistant，HEAD_PROTECT=3 会把后续 tool message 误划进 head。
    HEAD_PROTECT = 1   # 仅保护首条 user
    TAIL_PROTECT = 5   # 最近 5 轮

    if len(messages) <= HEAD_PROTECT + TAIL_PROTECT:
        return messages   # 太短，无中间可压

    head = messages[:HEAD_PROTECT]
    tail = messages[-TAIL_PROTECT:]
    middle = messages[HEAD_PROTECT:-TAIL_PROTECT]

    # 切割边界对齐 tool_call/tool_result 对
    middle = align_tool_pairs(middle)

    # 调现有 ModelClient（gemini provider 下的 gemini-2.5-flash）生成结构化摘要。
    # v3.1：走 generate_structured + _SUMMARY_RESPONSE_SCHEMA（§3.5 末尾给），返 dict、从 structured_result 取。
    result = llm_client.generate_structured(
        skill_name="memory_summarizer",
        prompt=SUMMARY_TEMPLATE.format(messages=format_messages(middle)),
        fallback_result={"summary": "[摘要不可用：原始消息保留使用]"},
        response_schema=_SUMMARY_RESPONSE_SCHEMA,
        route_key="memory.summarizer",
    )
    summary = result["structured_result"]["summary"]

    # 拼回（摘要装进 assistant 角色，OrchestratorMessage.role 仅支持 user/assistant/tool）
    summary_msg = build_summary_message(
        content=f"[历史对话摘要 — 覆盖第 {HEAD_PROTECT+1} 至第 {len(messages)-TAIL_PROTECT} 轮]\n\n{summary}"
    )
    return head + [summary_msg] + tail
```

### 3.5 摘要模板（结构化）

```python
SUMMARY_TEMPLATE = """请对以下对话历史生成结构化摘要，按模板填写。

## 对话历史
{messages}

## 摘要模板
### Goal
（用户的原始目标，1-2 句）

### Decisions
（已经做出的关键决策，列表形式）

### Facts
（已经确认的事实数据，如 UID、订单号、用户偏好等，列表形式）

### Pending
（还在进行中或被阻塞的事项，列表形式）

### Next
（下一步计划，1-2 句）

要求：
- 总长度控制在 2000-5000 tokens
- 不要丢失任何 UID、订单号、关键金额等具体数据
- 用中文输出（如果对话以中文为主）
"""

# v3.1：generate_structured 需 response_schema，摘要输出包装为｛"summary": "..."｝ JSON。
_SUMMARY_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {"summary": {"type": "string"}},
    "required": ["summary"],
}
```

### 3.6 Level 4（Fork 重建）

```python
def compress_level_4(messages: list, llm_client) -> list:
    """最后手段：Fork 子 Agent 用大窗口模型生成完整摘要。走 ModelClient gemini provider。"""
    result = llm_client.generate_structured(
        skill_name="memory_summarizer",
        prompt=FULL_REBUILD_TEMPLATE.format(messages=format_messages(messages)),
        fallback_result={"summary": "[全量重建不可用]"},
        response_schema=_SUMMARY_RESPONSE_SCHEMA,
        route_key="memory.summarizer",   # gemini-2.5-flash 1M 窗口足够装全部历史
    )
    summary = result["structured_result"]["summary"]
    # OrchestratorMessage 没有 system role；System Prompt 独立拼接。只保留一条 assistant 摘要
    return [build_summary_message(content=summary)]
```

### 3.7 多次压缩防"信息蒸发"

**问题**: 一个跑了 200 轮的 Agent 可能压缩 5-6 次。如果每次都从头摘要，第 1 轮原始目标会被反复"稀释"。

**方案**: 迭代更新而非重建。

```python
def compress_iteratively(messages: list, llm_client) -> list:
    """检测是否已有摘要消息，如果有，让 LLM 修订而非重写.

    messages 为 list[OrchestratorMessage] 或 list[dict]；
    底层调用会统一 model_dump() 为 dict.
    """
    msg_dicts = [m if isinstance(m, dict) else m.model_dump() for m in messages]
    existing_summary_idx = None
    for i, msg in enumerate(msg_dicts):
        content = msg.get("content", "")
        if msg.get("role") == "assistant" and isinstance(content, str) and content.startswith("[历史对话摘要"):
            existing_summary_idx = i
            break

    if existing_summary_idx is None:
        return compress_level_3(messages, llm_client)

    head = messages[:existing_summary_idx]
    existing_summary = msg_dicts[existing_summary_idx]["content"]
    new_messages = messages[existing_summary_idx + 1: -TAIL_PROTECT]
    tail = messages[-TAIL_PROTECT:]

    new_summary_result = llm_client.generate_structured(
        skill_name="memory_summarizer",
        prompt=ITERATIVE_TEMPLATE.format(
            existing_summary=existing_summary,
            new_messages=format_messages([m if isinstance(m, dict) else m.model_dump() for m in new_messages]),
        ),
        fallback_result={"summary": existing_summary},  # 迭代失败退回原摘要
        response_schema=_SUMMARY_RESPONSE_SCHEMA,
        route_key="memory.summarizer",
    )
    new_summary = new_summary_result["structured_result"]["summary"]
    return head + [build_summary_message(content=new_summary)] + tail
```


ITERATIVE_TEMPLATE = """以下是一份已有的对话历史摘要：

{existing_summary}

以下是这份摘要之后发生的新对话：

{new_messages}

请在已有摘要基础上**修订**（不是重写）：
- 补充新决策、新事实
- 删除已经过时的 Pending 项
- 保留所有 Goal、UID、关键数据

输出更新后的完整摘要。
"""
```

---

## 4. Memory Flush（压缩前必做，对应 Harness §5.5）

### 4.1 流程

```
Context 使用 > 85%
  ↓
Memory Flush（先做）
  ├─ 提取 Goal（用户原始目标）→ 写入 user 类记忆
  ├─ 提取 Decisions（已做的关键决策）→ 写入 project 类记忆
  ├─ 提取 Facts（确认的 UID / 订单号 / 偏好）→ 写入 user / reference 类
  └─ 提取 Feedback（用户对 Agent 的纠正）→ 写入 feedback 类
  ↓
Context Compression（再做）
  └─ 4 级压缩
```

### 4.2 Flush 实现

```python
# app/services/orchestrator_agent/memory_flush.py
from app.core.model_client import ModelClient
from app.services.orchestrator_agent.schemas import MemoryWriteInput
from app.services.orchestrator_agent.tools.memory import memory_write

# v3.1：generate_structured 需 response_schema，flush 输出为 four-class 字典。
_FLUSH_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "user": {"type": "array", "items": {"type": "string"}},
        "feedback": {"type": "array", "items": {"type": "string"}},
        "project": {"type": "array", "items": {"type": "string"}},
        "reference": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["user", "feedback", "project", "reference"],
}


def memory_flush(messages: list, session_id: str, country: str,
                 client: ModelClient | None = None) -> dict:
    """从 messages 中提取关键事实，写入长期记忆。

    messages: list[OrchestratorMessage]（Pydantic）或 list[dict]（已 model_dump他）。
    """
    client = client or ModelClient()

    # 统一转为 dict 序列化形式进 LLM
    msg_dicts = [m if isinstance(m, dict) else m.model_dump() for m in messages]

    extraction_prompt = f"""从以下对话中提取关键事实，分类输出：

## 对话
{format_messages(msg_dicts)}

## 输出 JSON
{{
  "user": ["用户偏好/身份相关事实"],
  "feedback": ["用户对 Agent 的纠正/反馈"],
  "project": ["项目进展/已做决策"],
  "reference": ["外部资源链接/工具入口"]
}}

只提取真正重要的，宁缺毋滥。每类最多 5 条。
"""

    raw_result = client.generate_structured(
        skill_name="memory_flush",
        prompt=extraction_prompt,
        fallback_result={"user": [], "feedback": [], "project": [], "reference": []},
        response_schema=_FLUSH_RESPONSE_SCHEMA,
        route_key="memory.summarizer",
    )
    extracted = raw_result["structured_result"]
    status = raw_result.get("status", "ok")

    # 写入长期记忆库（走现有 memory_write tool API，**不新增 schema 字段**）
    written = {"user": 0, "feedback": 0, "project": 0, "reference": 0}
    if status == "ok":
        ts = datetime.now().strftime("%Y%m%dT%H%M%S")
        for category in ("user", "feedback", "project", "reference"):
            for idx, item in enumerate(extracted.get(category, [])):
                key = f"{country}/{session_id}/{category}/{ts}_{idx}"
                result = memory_write(MemoryWriteInput(key=key, value=item))
                if result.ok:
                    written[category] += 1
    return {"status": status, "written": written, "extracted": extracted}
```

---

## 5. 长期记忆 four-class（对应 Harness §5.3）

### 5.1 四类定义

| 类型 | 记什么 | 举例 | 谁创建 |
|---|---|---|---|
| **user** | 用户身份、偏好、沟通风格 | "用户偏好中文回复" | Memory Flush 自动 |
| **feedback** | 用户纠正了 Agent 的某个行为 | "用户不喜欢模板化回复" | 同上 |
| **project** | 当前项目的关键决策和进度 | "本周配送系统升级" | 同上 |
| **reference** | 外部系统入口和定位信息 | "退款审批 > ¥500 需主管确认" | 用户手动告知 / 半自动 |

### 5.2 存储结构

```
outputs/memory/
├── {session_id_1}/
│   ├── user.jsonl        ← 一行一条记忆（jsonl 便于追加）
│   ├── feedback.jsonl
│   ├── project.jsonl
│   └── reference.jsonl
└── {session_id_2}/
    └── ...
```

**为什么按 session_id 分目录而不是全局共享？**
- V1 简化：每个 session 独立，避免跨 session 污染
- V2 升级：跨 session 共享需要用户身份认证，留 user_id 字段预留扩展

**国家命名空间**:
```
outputs/memory/
├── mx/
│   └── {session_id}/...
└── th/
    └── {session_id}/...
```

### 5.3 单条记忆 schema

```json
{
  "ts": "2026-05-05T14:30:22",
  "session_id": "sess_abc123",
  "country": "mx",
  "category": "user",
  "content": "用户偏好中文回复",
  "source": "memory_flush",   // memory_flush | manual | tool_call
  "ttl_days": 90              // 90 天过期，可选
}
```

---

## 6. memory_write / memory_read 工具（注册到 OrchestratorAgent）

### 6.1 工具定义（扩展现有 `tools/memory.py`，不新建 `memory_tools.py`）

> **v3.2 增补**：`Settings.project_root` 是 `@property`、不是 declared field（[`app/core/config.py:61`](app/core/config.py)），pydantic v2 不允许 `monkeypatch.setattr(settings, "project_root", tmp_path)`（会抛 `ValueError`）。
> 解决：在 `tools/memory.py` 暴露一个可被 monkeypatch 的 `_project_root()` helper，生产下走 `settings.project_root`，测试用 `monkeypatch.setattr("app.services.orchestrator_agent.tools.memory._project_root", lambda: tmp_path)`。

```python
# app/services/orchestrator_agent/tools/memory.py（扩展后的完整代码示意）
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from app.core.config import settings
from app.services.orchestrator_agent.schemas import (
    MemoryWriteInput, MemoryWriteOutput,
    MemoryReadInput, MemoryReadOutput,
)

VALID_CATEGORIES = ("user", "feedback", "project", "reference")


def _project_root() -> Path:
    """v3.2：可被测试 monkeypatch 的路径入口。"""
    return settings.project_root


def _memory_dir(country: str = "mx", session_id: str = "_global") -> Path:
    p = _project_root() / "outputs" / "memory" / country / session_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def memory_write(input_data: MemoryWriteInput) -> MemoryWriteOutput:
    """写入长期记忆。

    兼容策略：
    - 老调用 `MemoryWriteInput(key, value)`——走原路径 `outputs/orchestrator_memory/{safe_key}.txt`
    - 新调用（`memory_flush` 使用）传入 key 为 `"{country}/{session_id}/{category}/{ts}"` 格式，
      走新路径 `outputs/memory/{country}/{session_id}/{category}.jsonl` 追加写入
    并会在底层完成路径选择，外部调用者看到同样的 MemoryWriteOutput。
    """
    parts = input_data.key.split("/", 3)
    if len(parts) == 4 and parts[2] in VALID_CATEGORIES:
        country, session_id, category, ts_or_id = parts
        record = {
            "ts": datetime.now().isoformat(),
            "session_id": session_id,
            "country": country,
            "category": category,
            "content": input_data.value,
            "source": "memory_flush",
            "ttl_days": 90,
        }
        target = _memory_dir(country, session_id) / f"{category}.jsonl"
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return MemoryWriteOutput(ok=True, path=str(target))

    # 后兼容：原 V1 minimal 平铺 key/value 写入
    safe_key = input_data.key.replace("/", "_").replace(".", "_")
    target = _project_root() / "outputs" / "orchestrator_memory" / f"{safe_key}.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(input_data.value, encoding="utf-8")
    return MemoryWriteOutput(ok=True, path=str(target))


def memory_read(input_data: MemoryReadInput) -> MemoryReadOutput:
    """读取长期记忆。key_pattern 支持两种语义：
    - "{country}/{session_id}/{category}" → 走新格式 jsonl、返回该类记忆列表
    - 其余 → 后兼容 V1 minimal 顺序，走原 `outputs/orchestrator_memory/*.txt`
    """
    parts = input_data.key_pattern.split("/")
    if len(parts) == 3 and parts[2] in VALID_CATEGORIES:
        country, session_id, category = parts
        path = _memory_dir(country, session_id) / f"{category}.jsonl"
        items: list[dict[str, str]] = []
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                items.append(json.loads(line))
        return MemoryReadOutput(items=items)

    # 后兼容：原 V1 minimal 顺序
    base = _project_root() / "outputs" / "orchestrator_memory"
    base.mkdir(parents=True, exist_ok=True)
    items = []
    pattern = input_data.key_pattern.replace("*", "")
    for f in base.glob("*.txt"):
        if pattern in f.stem:
            items.append({"key": f.stem, "value": f.read_text(encoding="utf-8")})
    return MemoryReadOutput(items=items)
```

> **关键设计决策**：**不新建 `memory_tools.py`**，避免与现有 `tools/memory.py` 双轨。Plan Phase 1 以补丁式扩展 `tools/memory.py`，保证：
> 1. **schema 向后兼容**：`MemoryWriteInput(key, value)` 不变，老调用 “平铺 key/value” 的代码不出错
> 2. **存储路径平滑升级**：新格式 key="{country}/{session_id}/{category}/{ts}" 走 `outputs/memory/...`；后兼容路径 `outputs/orchestrator_memory/` 保留
> 3. four-class 判别在底层，**不增加 schema 字段**（避免与 `session_store.py` JSON 持久化冲突）

### 6.2 工具描述（现已在 `tools/__init__.py::get_tool_registry()` 注册）

现有 `tools/__init__.py` 已将 `memory_write` / `memory_read` 列入返回的字典（表明已注册）。本 Plan **不需重复注册**，仅可选在 system prompt 中补充主推荐描述。

```python
MEMORY_TOOL_DESCRIPTIONS = [
    {
        "name": "memory_write",
        "description": "保存重要信息到长期记忆库。当用户告知偏好、做出关键决策、或纠正你的某个行为时使用。four-class 调用请传 key=\"{country}/{session_id}/{category}/{ts}\" 格式。",
        "parameters": {
            "key": {"type": "string", "description": "路径式 key，推荐 '{country}/{session_id}/{category}/{ts}'"},
            "value": {"type": "string", "description": "要保存的内容、简洁描述"},
        },
    },
    {
        "name": "memory_read",
        "description": "查询当前 session 的长期记忆。新对话开始时建议先读取。请传 key_pattern=\"{country}/{session_id}/{category}\"。",
        "parameters": {
            "key_pattern": {"type": "string", "description": "查询 key 路径，推荐 '{country}/{session_id}/{category}'"},
        },
    },
]
```

---

## 7. V1 召回策略（全量加载）

### 7.1 V1 简化方案

```python
from app.services.orchestrator_agent.tools.memory import read_all_categories


def load_session_memories(session_id: str, country: str) -> str:
    """session 启动时全量加载，注入 System Prompt。

    v3.1：现有 `MemoryReadInput(key_pattern: str)` 无 country/session_id 字段，
    本函数直接调用 `read_all_categories(country, session_id)`——
    代码在 Phase 1 Task 1.2 扩展 `tools/memory.py` 时实现。
    """
    items = read_all_categories(country, session_id)
    if not items:
        return ""

    formatted = ["## 历史记忆"]
    by_category = {"user": [], "feedback": [], "project": [], "reference": []}
    for m in items:
        cat = m.get("category")
        if cat in by_category:
            by_category[cat].append(m.get("content", ""))

    for cat, contents in by_category.items():
        if contents:
            formatted.append(f"### {cat}")
            for item in contents:
                formatted.append(f"- {item}")

    return "\n".join(formatted)
```

### 7.2 升级路径

| 阶段 | 触发 | 召回方案 |
|---|---|---|
| V1 | 单 session 记忆 < 10 条 | 全量加载 |
| V2 | 跨 session / 单 session > 10 条 | BM25 关键词匹配（复用 Plan 07 索引） |
| V3 | 记忆 50+ 条 | Vector embedding 语义召回 |

---

## 8. 集成到 agent_loop

### 8.1 改造点

```python
# app/services/orchestrator_agent/agent_loop.py（伪代码改造 — Plan Phase 4 以实际函数签名为准）

async def agent_loop(session: OrchestratorSession, country: str | None, ...):
    # === 新增：首轮加载长期记忆（按 len(session.messages)==1 推断，v3修复：L89-L91 已 append 用户首条消息）===
    if len(session.messages) == 1 and country:
        memory_context = load_session_memories(
            session_id=session.session_id,
            country=country,
        )
        if memory_context:
            # 拼到 system_prompt（system_prompt 独立拼接，不进 messages）
            base_system = assemble_system_prompt(country)
            system_prompt = base_system + "\n\n" + memory_context
        else:
            system_prompt = assemble_system_prompt(country)
    else:
        system_prompt = assemble_system_prompt(country)

    # === 现有 while 循环保持不动（这里仅表示接点）===
    round_no = 0
    while round_no < MAX_ROUNDS:   # MAX_ROUNDS=15 本 Plan 不动
        response = await call_llm(system_prompt, session.messages, ...)
        session.messages.append(OrchestratorMessage(...))

        # === 新增：每轮检查是否需要压缩 ===
        ratio = response.usage.total_tokens / MODEL_MAX_TOKENS_PER_TURN
        if ratio > 0.85:
            ensure_context_fits(session, country, max_tokens=MODEL_MAX_TOKENS_PER_TURN)

        # ... tool dispatch 逻辑不动 ...
        round_no += 1


def ensure_context_fits(session: OrchestratorSession, country: str, max_tokens: int):
    """触发 Memory Flush + 4 级压缩。messages 为原位修改（v3.2：L2 接 session.tool_calls）。"""
    # 1. Memory Flush（必做）
    memory_flush(
        messages=session.messages,
        session_id=session.session_id,
        country=country or "mx",
    )

    # 2. 4 级压缩 — 全部接 list[OrchestratorMessage]，L2 额外接 session.tool_calls
    msgs = session.messages
    msgs = compress_level_1(msgs)
    if estimate_tokens(msgs) / max_tokens > 0.85:
        msgs = compress_level_2(msgs, session.tool_calls)   # v3.2：传 ToolCallRecord 列表
    if estimate_tokens(msgs) / max_tokens > 0.85:
        msgs = compress_iteratively(msgs, summarize_messages, iterative_summarize)
    if estimate_tokens(msgs) / max_tokens > 0.85:
        msgs = compress_level_4(msgs, summarize_messages)

    session.messages = msgs
```

> 其中两个集成点在 `agent_loop.py` 主函数：
> 1. **首轮阶段**（len(messages)==1、v3 修复）调用 `load_session_memories` 拼接进 system_prompt
> 2. **每轮 LLM 调用后**检查 `usage.total_tokens / MODEL_MAX_TOKENS_PER_TURN` 超阈值后调 `ensure_context_fits`
>
> Plan Phase 4 会以现有 `agent_loop.py` 实际函数签名为准输出精确 patch（oldString/newString）。

---

## 9. 开放问题

### 9.1 跨 session 用户身份怎么定义？
- 选项 A：cookie（前端浏览器存）
- 选项 B：登录态（需要先做登录）
- 选项 C：IP（不稳定）
- 选项 D：V1 不做跨 session（每 session 独立记忆）

> **推荐**: D（V1 不做），等 V2 有用户系统再加。

### 9.2 摘要模型走哪个 provider？
- 选项 A：现有 `gemini` provider（model=gemini-2.5-flash，成本低、质量中等）
- 选项 B：新增 `gemini_pro` provider（成本高、质量高）
- 选项 C：`mock`（单元测试与 dry-run）

> **推荐**：A（现有 `gemini`）。**不新增 gemini_pro / gemini_flash provider**，避免与 Spec-09 冲突。`config.yaml::llm.routes` 补一行 `memory.summarizer: gemini`（平铺格式）。Maestro Spike 通过后可翻为 `claude_maestro` 提质。

### 9.3 长期记忆是否参与 prompt cache？
- 选项 A：参与（写入后冻结，下个 session 才生效，省 75% 成本）
- 选项 B：不参与（每次实时刷新，但破坏 cache）

> **推荐**: B（V1 不参与），优先正确性。V2 再优化。

### 9.4 Memory Flush 触发频率？
- 选项 A：每次压缩前必做
- 选项 B：每 N 轮做一次（如 20 轮）
- 选项 C：用户主动触发（/save_memory 命令）

> **推荐**: A（必做），保证不丢信息。

---

## 10. 验收清单

### 10.1 Phase 0（baseline）
- [ ] `app/services/orchestrator_agent/agent_loop.py` 现有结构摸清
- [ ] 当前 messages 处理逻辑摸清（是否已有任何压缩）
- [ ] 测试一次"30 轮对话"看 token 消耗曲线

### 10.2 Phase 1-2（数据结构 + 工具）
- [ ] `outputs/memory/` 目录结构创建
- [ ] `memory_tools.py` memory_write / memory_read 实现 + unit test
- [ ] 工具注册到 OrchestratorAgent
- [ ] 跨 session 隔离验证（session A 写的不会被 session B 读到）

### 10.3 Phase 3（4 级压缩）
- [ ] `memory_manager.py` 4 级压缩实现 + unit test
- [ ] 切割边界对齐 tool_call/tool_result（无孤立消息）
- [ ] 迭代摘要（多次压缩信息不蒸发）unit test

### 10.4 Phase 4（Flush + 集成）
- [ ] `memory_flush.py` 实现 + unit test
- [ ] `ensure_context_fits` 集成到 agent_loop
- [ ] 15 轮（MAX_ROUNDS 上限）连续 E2E 测试不撑爆 Context（更长会话由 agent_loop MAX_ROUNDS 终止熔断兜底，不在本 Spec 验收）

### 10.5 Phase 5（验收）
- [ ] 压缩前 Memory Flush 落盘（人工查 outputs/memory/ 文件）
- [ ] 同 session_id 多次连接召回验证（session 1 写「用户偏好中文」→ 同一 session_id 重连后读到；V1 不支持跨 session，跨 session V2 加 user_id 后再做）
- [ ] env var `MEMORY_COMPRESSION_ENABLED=0` 能关闭整个压缩层

---

## 11. 风险与回退预案

### 11.1 已知风险

| 风险 | 概率 | 影响 | 缓解 |
|---|---|---|---|
| 摘要"信息蒸发"导致原始目标丢失 | 中 | 高 | 迭代更新 + Memory Flush 双保险 |
| 切割边界破坏 tool_call/tool_result 配对 | 中 | 中 | align_tool_pairs() 函数 + unit test |
| Memory Flush 提取的事实不准（LLM 误判） | 中 | 中 | 仅作为辅助记忆，不替代 messages |
| outputs/memory/ 占用磁盘 | 低 | 低 | TTL 90 天自动清理（V2 实现） |

### 11.2 回退预案

**触发条件**: Phase 5 验收发现压缩后 Agent 行为异常（忘记原始目标 / 重复执行已完成的任务）

**回退步骤**:
1. 设置 `MEMORY_COMPRESSION_ENABLED=0` 关闭压缩层
2. 保留 memory_write/memory_read 工具（不压缩仍然可用）
3. 排查是 Flush 提取错还是 L3 摘要错
4. 修复后再开启

---

## 12. 参考文档

- Harness Engineering 学习笔记 §5 Memory 层
- Harness Engineering 学习笔记 §6 Context 层
- `Agent面试题学习笔记.md` Q6 记忆四层体系 + Q9 记忆压缩四种方法
