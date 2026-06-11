# Plan #03 — Orchestrator Agent 核心（R10.2）

| 项 | 值 |
|---|---|
| 状态 | Pending（等待执行） |
| Design Doc | docs/specs/03-orchestrator-agent-design.md |
| 依赖 | Plan #01（[complete] model-client-refactor）；Plan #02 可并行或先后，Task 0.3 自适应 |
| 后继 | Plan #04（前端对话 Tab）+ 未来 Plan #2.5（da-agent 多国扩展） |
| Phase 数 | 5（Phase 0 baseline + Maestro Spike；Phase 1-4 实施） |
| Commit 策略 | 每 Phase 1 commit，最后一个标 `[complete] orchestrator-agent`；commit 前先展示 diff 等用户确认 |

> Historical note (2026-06-03): 本 Plan 中关于 pre-Phase 6 general-chat 主 LLM/tool loop 与 `MAX_ROUNDS=15` live 约束的描述已被后续 Flow 迁移 supersede，当前行为以 active docs 和实现代码为准。

---

## Scope

### 本 Plan 做

- 6 工具骨架 + 实装（5 业务工具 + 2 memory entry，1 个独立 `load_skill` 入口）
- Pydantic v2 schemas（输入/输出/会话/工具调用记录）
- JSON 文件会话持久化 + atexit + `--resume`
- Resilience：tenacity retry / Provider fallback / `MAX_ROUNDS=15` / 连续工具失败 K=3 阈值
- per-session token budget（80% 软警告 / 100% 硬阻断）
- UID 双层校验（通用安全层 + 国别业务层 V1 stub）
- Knowledge 层：6 国 `skills/*.md` 落地 + `load_skill(country)` 工具
- System Prompt v1（完整文本嵌入 Plan 与代码仓）
- Agent Loop 主循环 + ACK 时序（query_data 分支用 `wait_ack`）
- SSE 路由：`POST /api/orchestrator/chat`、`POST /sessions/{id}/ack`、`GET /sessions/{id}`
- Golden Test：5 个 fixture + Rubric + Judge prompt + **真跑通的 runner**（mock LLM + mock Judge）
- 至少 6 + 6 + N 个新增测试，全部 RED→GREEN

### 本 Plan 不做（明确边界，防 AI 越界）

- 不动 `data_acquisition_agent/**`（Surgical Hard Boundary，163 测试基线零回归）
- 不实现 `data_acquisition_agent` 6 国扩展（co/pe/cl/br 在 da-agent 不存在；本 Plan 仅 V1 锁 mexico）
- 不动 Plan #01 的 Provider 抽象层文件
- 不切换 Plan #02 的 explainer 路由（独立 Plan）
- 不动前端任何文件（Plan #04）
- 不写真实 LLM 调用的端到端测试（端到端测试统一用 mock）

### 跨 Plan 契约保护（R6 P0-3 硬约束 — Surgical Hard Boundary）

> Plan #02 R8 P0-A 实施期事故复盘的硬教训：覆盖 Plan #01 落地的 baseline 三块代码会破坏下游依赖（grafana log query / caplog 断言 / Plan #03 budget 模块）。本 Plan 全程**严禁**修改下列 Plan #01/#02 落地的契约：

| 文件/契约 | 严禁修改的原因 |
|---|---|
| `app/core/model_client.py::generate_structured` 的 mock 短路 / `self._log_payload_ready` / `self._record_usage` / except 路径 | Plan #02 R8 P0-A 落地的 baseline 4 块；agent_loop 调 `generate_structured(route_key="orchestrator_agent.decide")` 依赖 `last_token_usage` 三字段准确性（budget 模块直接读取） |
| `app/core/providers/{base,mock_provider,gemini_provider,json_repair,factory,claude_maestro_provider}.py` | Plan #01 + Plan #02 落地的 Provider 抽象层 + Maestro 实装；本 Plan 只是 ModelClient 的下游消费者 |
| `app/core/config.py::validate_llm_routes` + `get_llm_config` + `llm_provider_for` | Plan #02 R9 微调 1 修过 placeholder 检测 bug，本 Plan 不再动 |
| `app/main.py` 的 `@app.on_event("startup")` 钩子 | Plan #02 已挂 `validate_llm_routes` 调用；本 Plan 只追加 `app.include_router(orchestrator_router)` |
| 7 个 explainer.py 8 个 `route_key=` 调用点 | Plan #02 已落地，零回归基线 |
| `data_acquisition_agent/**` | Surgical Hard Boundary，163 测试基线锁定 |

**违反此边界的修改一律退回**。如执行期发现确实需要改 → **停下开代价会议**，不能"我顺手改一下"。

### V1 国别支持范围（关键决策）

| 国别 | Plan #03 V1 行为 | 原因 |
|---|---|---|
| mexico | 完整支持（query_data 走 da-agent mexico manifest） | da-agent 163 测试基线已覆盖 mexico |
| thailand / indonesia / pakistan / philippines | `query_data` 抛 `NotImplementedError("V1 未启用，等 Plan #2.5 da-agent 多国扩展")` | da-agent 已有 placeholder yaml，但 manifest 未实装 |
| co / pe / cl / br | 完全不支持，`query_data` 入参校验直接抛 `ValueError` | da-agent 没有这些国别枚举 |
| 6 国 `skills/*.md` | **全部落盘**（th/mx/co/pe/cl/br 6 文件，分析师人工查阅用） | knowledge 层独立于 da-agent，V1 完整 |

> **注意**：本 Plan 的 6 国 skills/*.md 用 `th/mx/co/pe/cl/br` 短码，与 da-agent `mexico/indonesia/pakistan/thailand/philippines` 全称不一致——这是设计取舍：skills/*.md 是 Orchestrator Agent 的国别分析手册，与 da-agent 取数器解耦。`query_data` 在 V1 内做"短码 → da-agent 全称"映射（仅 mexico 可走通；其它路径全部 reject）。

---

## 期望最终行为（Worked Example）

执行完 Phase 4 后，下面这条 SSE 流必须能正常跑通（mock 模式 + mexico）：

**步骤 1**：启 mock 模式服务
```powershell
$env:MODEL_MODE="mock"
uvicorn app.main:app --reload --port 8000
```

**步骤 2**：发起 chat 请求
```powershell
curl -N -X POST http://localhost:8000/api/orchestrator/chat `
  -H "Content-Type: application/json" `
  -d '{"prompt": "看下 UID MX0001 的行为轨迹"}'
```

**步骤 3**：期望 SSE 事件序列（顺序）
```
data: {"type": "session_started", "session_id": "<uuid>"}
data: {"type": "tool_started", "tool_call_id": "<id>", "tool_name": "run_trace", "input": {"uid": "MX0001", "days": 7}}
data: {"type": "tool_completed", "tool_call_id": "<id>", "tool_name": "run_trace", "output": {"events": [...], "summary": {...}}, "status": "ok"}
data: {"type": "final", "final_message": "...", "total_rounds": 1, "total_tokens": <int>, "confidence": 0.7}
data: {"type": "done"}
```

**步骤 4**：跑全量测试
```powershell
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v
```

期望：`tests/` 289 passed；`data_acquisition_agent/tests/` 163 passed (1 skipped)。

---

## 已知风险与开放问题

1. **Maestro Spike 失败的逃生路径（C-1）**：Phase 0 Task 0.2 的 4 项验证任一不满足则降级到 Gemini MVP，详见 Task 0.2 内嵌 C-1 流程。
2. **6 国 mismatch（已锁定 V1 范围）**：见上方 "V1 国别支持范围"。Plan #2.5 实现 da-agent 多国扩展后，本 Plan 的 `_ChildAgent.run_query` 会自动支持其它 4 国；不需要改本 Plan 代码，只需要 da-agent 加 manifest。
3. **路径选型与 Design Doc § 3.2 冲突**：Plan #03 V1 落 `app/services/orchestrator_agent/`；Design Doc § 3.2 写的是 `app/runtime_skills/orchestrator_agent/`。**本 Plan 落 `app/services/`**——语义上 Orchestrator Agent 是分析编排层（与现有 `app/services/orchestrator.py` 一脉相承），而非 SkillRegistry 注册的 Skill。**Phase 1 Task 1.1 同步修改 Design Doc § 3.2**（仅 1 行路径字符串，不改设计语义）。
4. **`ExecuteResponse` 不含 `uids` 字段**：实际 `ExecuteResponse.filenames`（per-uid bucket 切片落盘）+ `total_uids` + `rows_per_uid`（dict[str, int]）。`_ChildAgent.execute()` 必须从 `rows_per_uid.keys()` 反推 UID 列表，详见 Task 1.5 完整代码块。
5. **`GenerateResponse` 不含 `artifact_path` / `rows_estimated`**：实际 `GenerateResponse.sql` + `GenerateResponse.sql_kind`。`_ChildAgent.run_query()` 直接传 sql 字符串给 execute，不存中间 artifact 文件——`artifact_path` 在 `QueryDataOutput` 里改名为 `sql_text` 即可（已在 schema 修订）；`rows_estimated` 改由 `executor.precheck_row_count` 在 execute 阶段获取。
6. **`TargetAction` 没有 `GENERATE`**：实际枚举 `BUILD_TABLE / EXTRACT / BUILD_TABLE_AND_EXTRACT`。V1 走 `EXTRACT`（仅 query_only）。
7. **`shared_orchestrator` 单例已存在但 V1 不复用**（R8 P0-B 修正）：`app/services/orchestrator.py:304` 已导出 `shared_orchestrator = AnalysisOrchestrator()`，但 V1 `run_profile` 工具刻意 per-call 实例化 `AnalysisOrchestrator()`——避免共享缓存在多 session 并发时跨用户污染。未来 Plan #2.6 可评估是否切换到 `shared_orchestrator` + 加 session_id-aware 缓存键。
8. **`AnalysisOrchestrator` 没有 `country` 参数**：现有 `analyze_module(uid, module, application_time)` 签名固定。V1 国别在 Orchestrator Agent 层判定（System Prompt 里 LLM 自己决定调哪个 country 的 query_data），下游 `analyze_module` 不需要 country。
9. **`TraceAnalyzer.analyze` 返回 dict，但字段不是 `events / summary`**：实际由 `TraceAssembler.assemble()` 装配，字段需 grep 确认（Phase 1 Task 1.4 实施时 fallback 用 `out.get("events", [])` / `out.get("summary", {})`，找不到字段则 RunTraceOutput 字段全空但不抛错——下游 LLM 自适应）。
10. **`last_token_usage` 接入点**：Plan #01 R5 已固化 `client.last_token_usage = {"prompt", "completion", "total"}` 三字段；agent_loop 直接读 `client.last_token_usage["total"]` 累加到 session.total_tokens。
11. **Context Window 200K 上限风险（V1 不做压缩）**（R7 P1-4 新增）：每轮 LLM call 重发全量 messages，
   query_data 大输出（200 UID + run_profile 每 UID dump 1KB）+ 高轮次会导致单次 prompt 逼近
   Claude Opus 4.7 的 200K tokens 上限。Budget（500K）**不能**保护 Context Window 溢出。
   V1 接受此风险：budget 500K + MAX_ROUNDS=15 已限流；实际溢出 → Provider 抛
   InvalidRequestError → agent_loop except 分支结束 session（status=error）。
   Plan #2.7 加上下文压缩（Harness §6 Context 层）。

---

## 修订记录

- **R10.2 (2026-05-02)** — baseline 实测发现 da-agent tests 153→163（Plan #02 [complete] 874c305 落地后未回填到 Plan #03 / PLANNING.md / TASK.md / Design Doc）。R6 P0-5 实施期微调追溯锚点机制：把 Plan #03 内 11 处 + PLANNING.md 5 处 + TASK.md 3 处 + Design Doc 3 处共 22 处 "153" 相关基线数与现实对齐。零代码风险，文档对齐补丁。
- **R10.1 (2026-05-02)** — 第 5 轮审核修补 R10 P1-1 自身遗留的 NEW-P0（1 P0 / 0 P1 / 0 P2）：
  - **NEW-P0（R10 P1-1 未在执行流里落地）**：R10 P1-1 要求 Task 1.7 同步修 Design Doc § 13 line 611，但原 Task 1.8 add 清单未列 `docs/specs/03-orchestrator-agent-design.md`、期望段 “git diff 仅在 5 个范围” 也不包含它。执行人只能：要么跳同步修 Design Doc（R10 P1-1 实质失效），要么同步修后在 Phase 1/2/3 commit 期间反复触发 “Changes not staged for commit 为空” 违反。
  - 修法：Task 1.8 add 清单加一段条件 add（类比 R9 P1-1 docs/plans/ 模式）+ 期望段补 R10 P1-1 可选范围 + Task 4.4 add 清单注释明确 “§ 13 修订已在 Phase 1 完成、此处 add 仅针对 Task 4.3 prompt 调优”，避免两 Phase 重复 add 冲突。
- **R10 (2026-05-02)** — 第 4 轮审核修补（R9 自引入 1 个硬阻塞 P0 + 3 P1 + 1 P2，最后一轮 clean-up）：
  - **P0（R9 自引入的硬阻塞 — 不修会永久卡 Phase 4 [complete] commit）**：R9 P1-2 PowerShell 校验命令写的 `IndexOf('## Appendix A')` 与 Design Doc 实际标题「## 附录 A」（中文）不匹配。验证：`docs/specs/03-orchestrator-agent-design.md:663` 实际为「## 附录 A — System Prompt v1 完整文本」。原 R9 命令 IndexOf 返回 -1 → `Write-Error "Design Doc 缺 Appendix A 段"; exit 1` → 最后一个 commit 永久被堵。修为同时识别中英文两种写法。同时同步修 Task 4.3 + 完成标志段中 “Appendix A” 变 “附录 A”。
  - **P1-1（Design Doc § 13 line 611 Task 编号错位）**：Design Doc 写“Task 1.6 把附录 A 写入 ...”，但 Plan #03 实际 Task 1.6 是 6 国 skills/*.md，Task **1.7** 才是 System Prompt v1 落盘。类比顶部已知风险 #3 已要求 “Task 1.1 同步修 Design Doc § 3.2”，本处加一行要求：Task 1.7 同步修 Design Doc § 13 中“Task 1.6”→“Task 1.7”（1 行文本修订）。
  - **P1-2（“5-commit 预算”与实际 6 commit 不一致）**：R7 P0-2 已把 commit 数从 5 改成 6，但二级标题 `## Plan #03 [complete] 后的延伸工作（不计入 5-commit 预算）` 未同步。改为 `不计入 6-commit 预算`。R6 修订记录段中的 “5-commit 上限” 是历史描述，保留不动。
  - **P1-3（Task 1.8 期望输出未同步 R9 P1-1 闭环）**：Task 1.8 add 清单已加上可选 +1 个 `docs/plans/03-orchestrator-agent-plan.md`，但期望输出段 `git diff 仅在 ...` 范围未补 docs/plans/。补上一句 “可选范围 docs/plans/03-orchestrator-agent-plan.md（仅当 Phase 0.5 修过 Plan 时）”。
  - **P2（System Prompt v1 fence 落盘说明）**：Task 1.7 用 4 反引号 fence 嵌套 ```` ```` markdown … ``` ````，执行人可能误把外层也写进落盘文件。在 fence 上方加一句：“落盘时只写 fence 内部内容，不含外层 ```` markdown 与 ```` 行”。
- **R9 (2026-05-02)** — 第 3 轮严格审核一致性 sweep（3 P0 + 2 P1 + 3 P2，专门修补 R7/R8 修订时漏同步的内部矛盾，不改架构、不改 commit 数）：
  - **P0-1（中文 unicode escape 错字 → 中文场景 country detection 永久失效）**：R7 P0-3 给 Task 3.3 写的 `_COUNTRY_RE` / `_NAME_TO_CODE` 把「墨西哥」误打成「\u5893\u897f\u54e5」（U+5893 = 墓，U+58A8 才是墨）。验证：`'\u5893\u897f\u54e5'` 实际解码为「墓西哥」。改为直接中文字面量（5 处中文国名 + 6 国短码 + 6 个英文国名），R8 P0-A 已经证明 Plan 内 UTF-8 中文字面量稳定可用，没必要再走 escape。
  - **P0-2（Task 0.5.5 数字与 Task 1.8 期望对撞）**：R7 P0-3 把 Phase 1 测试数 19→20 时只改了 Task 1.8 的“20 passed”，Task 0.5.5 baseline 回填表里 4 处 `+19` 没跟着改。回填表全部刷成 `+20`，下游 `+19+13` → `+20+13` / `+19+13+7` → `+20+13+7` / `+19+13+7+5` → `+20+13+7+5`。
  - **P0-3（Task 1.4 grep 注释与已知风险 #7 互相矛盾）**：R8 P0-B 修了顶部已知风险 #7 但漏扫 Task 1.4 顶部 grep 验证注释。注释仍写“无 shared_orchestrator 模块级单例”，与已知风险 #7 描述完全相反。改为“存在 shared_orchestrator @ orchestrator.py:304，但 V1 工具刻意 per-call 实例化（详见已知风险 #7）”。
  - **P1-1（Phase 0.5 不一致修 Plan 的 commit 路径闭环）**：Phase 0.5 自称“不写代码、不 commit、不改任何文件”，但 Task 0.5.4/0.5.5 又要求“不一致 → 先修 Plan + 受影响 Task 才能进 Phase 1” + “实施期亲改 Plan”。这两条互斥，导致 Plan 文档修订无 commit 追溯。补充“Phase 0.5 修 Plan 的差异作为 Phase 1 commit 的一部分（一并 git add Plan 文件 + 代码文件），commit message 加段‘Phase 0.5 实施期 Plan 文档微调：<差异列表>’”。
  - **P1-2（System Prompt v1 vs Design Doc Appendix A 字面一致性自动验证）**：完成标志声明“与 Design Doc Appendix A 一字不差”，但 Plan 内无任何 diff 命令做自动验证，未来 R10/R11 改 Design Doc 时极易漂移。Task 4.4 add 清单后追加 PowerShell 校验段，提取 Appendix A 与 system_prompt_v1.md 比对失败则 exit 1。
  - **P2-1（Task 1.8 显式 add 清单从整目录改成显式 7 文件）**：原 `git add app/services/orchestrator_agent/` 整目录 add，如果 Phase 1 实施期为了调试提前在该目录建了 Phase 2 文件（session_store.py 等），会误带 Phase 2 文件进 Phase 1 commit。改成显式列举 7 个文件路径，与 Phase 2/3 add 清单互斥。
  - **P2-2（Task 1.3 删末尾自相矛盾的歧义句）**：原文“`tools/__init__.py` 已含 stub 注册。**新建空 `__init__.py`** for tools 包：实际上 `tools/__init__.py` 上面已写。”内部矛盾（“已含”vs“新建空”），Task 1.3 第一段已新建 tools/__init__.py 含 registry，多余的歧义句直接删掉。
  - **P2-3（Task 3.4 替换 # 5) 块的 oldString 边界 anchor）**：原文“替换为下面的版本”没明示替换范围。补充 oldString anchor：从 `# 5) Execute tool` 一直到 `tool_completed yield 块` 整段。
- **R8 (2026-05-02)** — 可执行性 audit 修补（1 P0-A 硬阻塞 + 1 P0-B 事实错误），仅修除“开跑前会翻车”点：
  - **P0-A（硬阻塞）：Task 3.1 移除 `pytest-asyncio` 依赖**。grep 验证：`requirements.txt` 未含 pytest-asyncio；`importlib.util.find_spec("pytest_asyncio")` 返回 False。原 Task 3.1 用 `@pytest.mark.asyncio` + `async def` 会在 Phase 3 RED 阶段直接 ERROR，且 escape hatch `pip install pytest-asyncio` 不在 add 清单里违反“一个人能执行完”。改为 `asyncio.run(_drive())` 同步驱动（与 Task 4.2 Golden runner 风格一致），零新依赖。
  - **P0-B（事实错误）：已知风险 #7 修正为 `shared_orchestrator` 真实存在**。grep 验证 `app/services/orchestrator.py:304` 实际导出了 `shared_orchestrator = AnalysisOrchestrator()`。V1 仍维持 per-call 实例化决策，但描述要准、不能误导后续维护者。
- **R7 (2026-05-02)** — Vibe Coding 严格审核修补（5 P0 + 6 P1，未改变总体架构、仅补上质量缺口）：
  - **P0-1：Task 3.6 期望测试数 6→7 passed** — Task 3.1 实际写了 7 个测试（3 ack_bus + 1 agent_loop + 3 routes），原期望漏算 1 个。
  - **P0-2：完成标志 5→6 commit** — 原漏算 Task 0.4 Maestro Spike wire-up commit；commit 序列为 `[baseline]` → Maestro Spike wire-up → Phase 1 → Phase 2 → Phase 3 → Phase 4 `[complete]`。
  - **P0-3：Task 3.3 注入 Knowledge 层 country detection**— 设计与实现脱节的关键缺陷。System Prompt v1 承诺按 country code 自动注入 skill md，但原 Task 3.3 `assemble_system_prompt()` 未传 country，Harness 11 层 Knowledge 层在 V1 全面缺失。修为在首轮 LLM call 前用 keyword regex 提取 country code。
  - **P0-4：Task 3.4 ack_bus import 加 inline 注释** — 防未来重构者把 query_data 分支里的 function-local import 上提到 module top，造成 Task 4.2 monkeypatch 失效 + Phase 4 case_05 卡 600s 超时。
  - **P0-5：Task 3.6 main.py 行 diff 注释从 +1 改为 +5** — Task 3.5 实际给的 main.py 补丁是 3 行（注释 + import + include_router），原 Task 3.6 “+1 行”检查会让 commit 卸住。
  - **P1-1：新建 `tests/conftest.py` 重定向 outputs/** — 防 session_store + memory 测试副作用污染生产 outputs/ 目录（Phase 1/2/3/4 跑完会写 30+ 个 test session JSON）。
  - **P1-2：Phase 0.5 加 Task 0.5.5 锚定 tests/ baseline 数量** — 原“270 + N”中 N 为变量，执行时无法判断“少了的测试是 Plan #02 未落地还是本 Plan 破坏了”。
  - **P1-3：Task 4.2 _mock_judge docstring 加 limitation** — 明示仅检查工具名序列严格匹配，不验证参数 / final_message；mock=pass 不等于真实 LLM Judge=pass。
  - **P1-4：已知风险加第 11 项 Context Window 200K** — budget 500K 不能保护 200K context window；V1 接受溢出 → Provider 抛 InvalidRequestError。
  - **P1-5：Phase 0.5 Task 0.5.1 grep 加 ExecuteRequest cross-field validator** — 验证 da-agent schemas 是否存在 `output_bucket=behavior + output_format=json` 的 cross-field 限制，防 Task 1.5 `_ChildAgent.execute` 默认参数被拒。
  - **P1-6：System Prompt query_data V1 限制提前到第 1 行** — 原 V1 限制在第 5-6 行，LLM 阅读注意力衰减导致误报 6 国均可用。
- **R6 (2026-05-02)** — Plan #02 [complete] (4f1b4a5) 后、Plan #03 执行前的 audit，同步 Plan #01/#02 实施期验证有效的 5 项工程纪律 + 3 项 P1 增强：
  - **P0-1: 新增 Phase 0.5 —— Codebase Baseline 校对（只读，不产生 commit）**。实施前 grep 验证本 Plan 顶部 `已知风险与开放问题` 第 1-10 项上游契约是否仅与 Plan #01/#02 落地后一致，不一致则先修 Plan 再执行。Plan #02 R7 P1-2 实施期验证该机制防住 6 处隐式错位（包括 BehaviorExplainer L142 timeline、model_client.py provider 解析块位置、fallback_chain 间接命中等），为 Plan #03 必选工程纪律。
  - **P0-2: 每 Phase commit 前加“事故预防清单”**。吸取 Plan #02 a94c776 事故教训（`git commit --allow-empty` 误带外部 modified 文件进 commit）+ Plan #02 多窗口并行 HEAD 异常事故。每个 Phase commit 前必跑：`git rev-parse HEAD` / `git fetch github` / `git log github/main..HEAD --oneline` / `git log HEAD..github/main --oneline` / `git status` 五联，确认 HEAD 同步 + staging 干净后，再用显式 `git add <文件名列表>`（禁用 `git add -A`），贴 `git diff --cached --stat` + `git status` 给用户对照，等“OK commit”才执行。
  - **P0-3: 跨 Plan 契约保护硬约束**（Surgical Hard Boundary）。Plan #03 agent_loop 调 `client.generate_structured(route_key="orchestrator_agent.decide")` 依赖 Plan #02 R8 P0-A 落地的 try-block 内 provider 解析 + `_log_payload_ready` 保留 + `_record_usage` 保留 三块 baseline。本 Plan 明令：不动 `app/core/model_client.py` / `app/core/providers/**` / `app/core/config.py::validate_llm_routes` / 7 个 explainer.py 任何一行。如发现需要改 → 停下开代价会议，不能衰冲实施。
  - **P0-4: Phase 0 Task 0.3 自适应分支精简**。Plan #02 已 [complete] (4f1b4a5)，`config.yaml` 已含完整 `llm:` 段 + 8 个 routes。原分支 A/B 逻辑过时。本 Plan Task 0.3 现只需（1）grep 验证 `orchestrator_agent.decide` 是否在 routes 里，如不在需补一行；（2）回填真实 endpoint。不需要“补全 llm 段”分支 B。
  - **P0-5: 实施期微调追溯锤点机制**。吸取 Plan #02 R9 经验（6 处实施期 Plan 与现实差异全部记入 commit message）。本 Plan 执行期如发现任何 Plan 与现实不一致（上游契约 / 文档描述 / 预期数字），必须在当前 Phase commit message 加一段 "实施期 Plan 文档微调 N：<描述> + Plan #03 文档待 [complete] 后同步修订"，Plan #03 [complete] 后一次性做 R7 统一修订 commit（不计入 5-commit 上限，类似 Plan #02 R9 5affae4）。
  - **P1-1: `query_data` 函数 docstring 强化** —— 明确"仅供单测 / 外部调用者 facade，生产路径走 agent_loop 的 6 阶段拆分调用，ACK gate 仅在 agent_loop 内硬编码"，防止后续维护者误把 ACK 写到 `query_data` 内导致单测同步阻塞。
  - **P1-2: `case_05_query_data_mx` 补 ACK auto-resolve hack 注释** —— Phase 4 case_05 用 `monkeypatch.setattr(ack_bus.open_ack, ...)` 自动放行 ACK 仅限于 Golden Test，明示生产路径 `orchestrator_routes.py::ack` 仍走真实人工 ACK，monkeypatch 不入生产代码。
  - **P1-3: Phase 0.5 Task 0.5.1 加一行 BehaviorExplainer 双路 grep** —— 验证 Plan #02 R9 微调 6 落地的 `behavior_profile.timeline` route_key 仍在（L129 + L142 共 2 行），缺一行即 abort（Plan #02 R9 5affae4 未真正生效，本 Plan budget 路由预算会失准）。
- **R5 (2026-05-02)** — 按 Vibe Coding 方法论五点检查法 + Plan #01 R5 收口标准全面重写：
  - 头部新增 `## Scope` / `## 期望最终行为` / `## 已知风险与开放问题` / `## 修订记录` 4 段
  - **修复 R4 全部上游契约错误（7 处）**：`shared_orchestrator` 单例 / `analyze` 签名 / `GenerateResponse.artifact_path` / `ExecuteRequest.artifact_path` / `TargetAction.GENERATE` / `TargetCountry` 国别 / `ExecuteResponse.uids`
  - **TDD 顺序重排**：Phase 1/2/3 全部 RED→GREEN（先写测试看必失败 → 实装看通过）
  - **Phase 3 Task 3.1 拆为 4 个子 Task**：ack_bus / agent_loop 主循环 / agent_loop ACK 分支 / FastAPI routes
  - **新增 Phase 4 Golden Test Closeout**：commit 数 4→5；Golden runner 真跑通（mock LLM + mock Judge），不再 `pytest.skip`
  - 6 国 mismatch V1 决策：仅 mexico 走真，其它 4 国 stub；6 国 skills/*.md 仍全建（独立于 da-agent）
  - System Prompt v1 完整文本嵌入 Plan（不再"复制 Design Doc Appendix A"）
  - 每 Phase commit 前显式声明"先 `git diff` 展示变更等用户确认"
  - session.py 一次到位（Phase 1 直接 `dict + threading.Lock`，不再 Phase 1 全局 → Phase 2 重写）
  - 移除未使用的 `with_safe_default` 装饰器（YAGNI）
  - 路径选型敲定 `app/services/orchestrator_agent/`，同步修订 Design Doc § 3.2
- **R4 (2026-04-30)** — 内嵌 P0/P1 修补散点：budget 字段 / fallback 字段 / ACK async / session-bound / Plan #02 解耦
- **R3 (2026-04-29)** — 自审 9/9 PASS，无代码变更
- **R2 (2026-04-28)** — 修补 18 个 P0 + 9 个 P1
- **R1 (2026-04-27)** — R1 修订
- **R0 (2026-04-26)** — 初始版本

---

## Phase 0 — Baseline + Maestro Spike（**Blocking Gate**）

### Task 0.1 — 验证 Plan #01 已 `[complete]` + baseline 测试

**操作步骤**：

```powershell
cd C:\Users\v-yimingliu\agent-userprofile\CHORD
git log --oneline | Select-String "complete.*model-client-refactor"
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v
git status
git commit --allow-empty -m "[baseline] orchestrator-agent"
```

**期望输出**：
- `git log` 找到 `[complete] model-client-refactor` 行（Plan #01 已落地）
- `tests/` → 270 + N passed（N = Plan #01/#02 累计新增；R5 起不再硬编码 N）
- `data_acquisition_agent/tests/` → 163 passed (1 skipped)
- `git status` 干净
- baseline commit 已创建

**验证命令**：
```powershell
git log -1 --oneline
# 期望：[baseline] orchestrator-agent
```

### Task 0.2 — Maestro Spike（Blocking Gate）

**目的**：验证 Claude Opus 4.7 via Agent Maestro 端点真实可用、协议字段兼容、配额够用。**Spike 通过才能进 Phase 1**。

**Spike 验证步骤**：

1. 取得 Maestro 端点 URL + 认证 token（向团队管理员申请，**不在 Plan 中明文**）
2. 用最小 Python 脚本发一个测试请求（一次性脚本，Spike 完后删除）：

**新建文件**：`scratch/spike_maestro.py`

```python
"""One-shot Maestro Spike (delete after Phase 0 commit)."""

import os
import time

import requests

ENDPOINT = os.environ["MAESTRO_ENDPOINT"]
TOKEN = os.environ["MAESTRO_TOKEN"]

t0 = time.perf_counter()
resp = requests.post(
    ENDPOINT,
    headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    json={
        "model": "claude-opus-4.7",
        "tier": "10x",
        "messages": [{"role": "user", "content": "回复一个 JSON: {\"ok\": true}"}],
        "max_tokens": 100,
    },
    timeout=30,
)
elapsed = time.perf_counter() - t0
print(f"status_code={resp.status_code}")
print(f"elapsed_sec={elapsed:.2f}")
print(f"body={resp.text[:500]}")
```

3. 验证 4 项**通过条件**：
   - HTTP 200
   - 返回结构包含 `content` / `tool_use` / 等价字段（与 Anthropic Messages API 对齐）
   - 单次响应延迟 ≤ 5s
   - 配额信息（剩余次数）足以支撑后续 Plan 实施 + 5-10 次 Golden Test 校准

4. **Spike 通过** → 端点 URL 回填到 `config.yaml` 的 `llm.providers.claude_maestro.endpoint`，删除 `scratch/spike_maestro.py`，进入 Task 0.3。

#### Spike 失败的逃生路径（C-1）

如果 4 项中任一不满足：

1. **立即停止** Plan #03 后续 Phase
2. 执行 4 项降级动作：
   - **Plan #01 不阻塞**：保留 Provider 抽象层（基础设施，独立有价值）
   - **Plan #02 路由暂不切**：保留 `config.yaml` 的 `llm.routes` 但 `claude_maestro` 实际指向 fallback Gemini，等 Maestro 恢复后再切
   - **Plan #03 改用 Gemini MVP**：`SYSTEM_PROMPT_V1` 改用 Gemini 2.5 Flash 跑通 MVP，Phase 1-4 继续，但 `route_key` 全部走 Gemini
   - **Plan #04 推迟**：等 Plan #03 MVP 跑通后再启动
3. 写一份逃生记录到 `docs/reviews/maestro-spike-failure-{YYYY-MM-DD}.md`，记录 4 项验证结果 + 4 项降级动作执行情况 + 重新启动 Spike 的触发条件
4. **commit message**：`docs: maestro spike failed, plan #03 degrade to gemini mvp`

逃生路径执行后，本 Plan 后续凡涉及 `claude_maestro` 的步骤改为 `gemini`，Spike 重新通过后再回切（届时只需改 `config.yaml`，无需改代码）。

### Task 0.3 — 替换 config.yaml `claude_maestro` 段的 endpoint 占位

**修改文件**：`config.yaml`

**前置假设（R6 P0-4 已校准）**：Plan #02 [complete] (4f1b4a5) 已写入 `claude_maestro:` provider 段 + `endpoint: "[Spike Pending]"` 占位 + 7 个 explainer route + `behavior_profile.timeline` route。Phase 0.5 Task 0.5.2 grep 已验证。本 Task 只做 2 件事：

1. 把 `endpoint: "[Spike Pending]"` 替换为 Spike 通过后回填的真实 URL
2. 在 `routes:` 段末尾追加 `orchestrator_agent.decide: claude_maestro` 一行（Plan #02 没加这个 route，归属 Plan #03）

**操作**：用编辑器 / `python -c` 脚本只改 2 行，**不动**其它已有 yaml 段。完整目标状态（仅展示 `llm:` 段，其它 yaml 段保持原样）：

```yaml
llm:
  providers:
    gemini:
      mode: vertex
      model: gemini-2.5-flash
      project: amberstar-gemini
      location: global
    claude_maestro:
      endpoint: "https://<回填的真实 endpoint>"   # ← R6 P0-4：从 [Spike Pending] 替换为真实 URL
      auth_method: "bearer_token"
      auth_env: "MAESTRO_TOKEN"
      model: claude-opus-4.7
      tier: 10x
      timeout_sec: 30
    mock:
      enabled_in: ["test", "local"]
  routes:
    app_profile.explainer: claude_maestro          # Plan #02 已加
    behavior_profile.explainer: claude_maestro      # Plan #02 已加
    behavior_profile.timeline: claude_maestro       # Plan #02 R9 微调 6 已加
    credit_profile.explainer: claude_maestro        # Plan #02 已加
    comprehensive.explainer: claude_maestro          # Plan #02 已加
    product_advice.explainer: claude_maestro         # Plan #02 已加
    ops_advice.explainer: claude_maestro             # Plan #02 已加
    trace_analyzer.explainer: claude_maestro         # Plan #02 已加
    orchestrator_agent.decide: claude_maestro        # ← Plan #03 新增（本 Task）
  default_provider: gemini
```

**Spike 失败时的替代动作**（C-1 逃生路径）：
- `endpoint` 保持 `"[Spike Pending]"` 不动 → ModelClient 自动 fallback 到 `default_provider: gemini`（Plan #01 R5.1 fallback_chain 兜底）
- `orchestrator_agent.decide: claude_maestro` 路由仍然写入（不影响 fallback）
- Phase 1+ 继续按 Gemini MVP 跑（Spike 重新通过后只需改 endpoint 一行）

> **凭据安全**：
> - `MAESTRO_TOKEN` 通过环境变量注入，**绝不**写到 `config.yaml` / 代码 / 日志 / 提示词
> - `endpoint` URL 写入 `config.yaml` 入仓**不是凭据泄露**（端点 URL 公开可知，权限由 token 把守）
> - `config.yaml` **不应进 .gitignore**——它含有 vertex baseline 配置必须入仓

**验证命令**：
```powershell
python -c "import yaml; cfg = yaml.safe_load(open('config.yaml', encoding='utf-8')); routes = cfg.get('llm', {}).get('routes', {}); print('endpoint:', cfg.get('llm', {}).get('providers', {}).get('claude_maestro', {}).get('endpoint', '<missing>')); print('orchestrator_agent.decide:', routes.get('orchestrator_agent.decide', '<missing>'))"
# Spike 通过期望：endpoint: https://...   orchestrator_agent.decide: claude_maestro
# Spike 失败期望：endpoint: [Spike Pending]   orchestrator_agent.decide: claude_maestro（fallback 到 gemini）
```

### Task 0.4 — Phase 0 commit（R6 P0-2 事故预防清单 + 显式 add 清单 + 等“OK commit”）

**事故预防清单**（commit 前必跑，吸取 Plan #02 a94c776 / 多窗口并行 HEAD 异常事故教训）：

```powershell
# 1）确认 HEAD 真实位置（避免“印象中的 HEAD”事故）
git rev-parse HEAD

# 2）fetch + 对比 remote
git fetch github
git log github/main..HEAD --oneline   # 期望为空（本地不领先）
git log HEAD..github/main --oneline   # 期望为空（remote 不领先）
# 如 HEAD..github/main 不为空 → git pull --ff-only github main

# 3）检查工作树状态
git status
# 期望：Changes not staged 只有 config.yaml（Spike 回填后）；Untracked 仅外部产物（如 04-*-audit.md）；staging 区为空
```

**显式 add 清单 + 对照**：

```powershell
# 禁用 git add -A。只 add config.yaml。
git add config.yaml
git diff --cached --stat
git status
# 期望：
# - diff --cached --stat 恒为 1 个文件 (config.yaml)
# - status 里 Changes to be committed 仅 config.yaml
# - Changes not staged for commit 为空（config.yaml 已 staged）
# - Untracked 仅外部产物
```

**贴 diff stat + status 给用户对照，等“OK commit”才执行**：

```powershell
git commit -m "feat(orchestrator): Maestro Spike passed, claude_maestro endpoint wired"
# 或 Spike 失败：git commit -m "docs: maestro spike failed, plan #03 degrade to gemini mvp"
git push origin main
git log -1 --oneline
```

**验证命令**：
```powershell
git log -1 --oneline
# 期望：feat(orchestrator): Maestro Spike passed... 或 docs: maestro spike failed...
git log github/main..HEAD --oneline
# 期望为空（push 后本地与 remote 同步）
```

---

## Phase 0.5 — Codebase Baseline 校对（只读，不产生 commit）【R6 P0-1 新增】

> 用户偏好硬规则：“执行前加 Phase 0 核对：先只读检查 baseline skeleton 的实际类名/字段名是否与 Plan 一致”。Plan #02 R7 P1-2 实施期验证该机制防住 6 处隐式错位。本 Phase 运完后用真实输出对比本 Plan 顶部《已知风险与开放问题》 1-10 项，不一致什么都不写——先修 Plan 再进 Phase 1。

### Task 0.5.1 — grep 跨 Plan 上游契约（Plan #01 R5.1 + Plan #02 R9 落地后状态）

```powershell
Write-Output "==== ModelClient.generate_structured 契约 ===="
Select-String -Path "app/core/model_client.py" -Pattern "def generate_structured|route_key|self\._log_payload_ready|self\._record_usage|self\._provider|self\.last_token_usage" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }

Write-Output "==== fallback_chain 为置验证 ===="
Select-String -Path "app/core/providers/base.py" -Pattern "def fallback_chain" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }

Write-Output "==== AnalysisOrchestrator.analyze_module 签名 ===="
Select-String -Path "app/services/orchestrator.py" -Pattern "class AnalysisOrchestrator|def analyze_module|SUPPORTED_MODULES" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }

Write-Output "==== TraceAnalyzer.analyze 返回字段（重点跳朋取 events / summary） ===="
Select-String -Path "app/runtime_skills/trace_analyzer/analyzer.py" -Pattern "class TraceAnalyzer|def analyze|return" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }
Select-String -Path "app/runtime_skills/trace_analyzer/assembler.py" -Pattern "def assemble|return|events|summary" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }

Write-Output "==== data_acquisition_agent 兑现契约 ===="
Select-String -Path "data_acquisition_agent/schemas.py" -Pattern "class TargetCountry|class TargetAction|class GenerateRequest|class ExecuteRequest|class GenerateResponse|class ExecuteResponse|sql_kind|approved_by|output_bucket|output_format" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }

Write-Output "==== R7 P1-5：ExecuteRequest cross-field validator（output_bucket × output_format 兼容性） ===="
Select-String -Path "data_acquisition_agent/schemas.py" -Pattern "model_validator|@validator|root_validator" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }
# 期望：如有 cross-field validator，手动打开 schemas.py 读该段逻辑，确认 bucket=behavior + format=json 组合不被拒。
# 不兼容 → abort，Task 1.5 _ChildAgent.execute 需调默认参数，同时修顶部 P4 上游契约。

Write-Output "==== executor.run_execute_pipeline 返回字段（rows_per_uid keys 反推 UID） ===="
Select-String -Path "data_acquisition_agent/executor.py" -Pattern "def run_execute_pipeline|rows_per_uid|filenames|total_uids|metadata" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }

Write-Output "==== R6 P1-3：BehaviorExplainer 双路 route_key 赯在（Plan #02 零回归基线） ===="
Select-String -Path "app/runtime_skills/behavior_profile/explainer.py" -Pattern "route_key=" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }
# 期望：点 2 行——一行是 decide （route_key="behavior_profile.explainer"），另一行是 timeline （route_key="behavior_profile.timeline"）。
# 不到 2 行 → abort，Plan #02 R9 微调 6 未落地，本 Plan budget 路由预算会不准。
```

**期望输出并对照**（与本 Plan 顶部《已知风险与开放问题》比对）：

| 项 | 预期（顶部已知风险描述） | 不一致如何处理 |
|---|---|---|
| `def generate_structured(..., *, route_key: str \| None = None)` | 需存在（Plan #02 [complete] 后落地）| 缺失 → abort，Plan #02 未真正 [complete] |
| `self._log_payload_ready(skill_name, structured_result)` | 需存在（本 Plan **不动**）| 缺失 → abort，grafana / caplog 受损 |
| `self._record_usage(prompt, json.dumps(...))` | 需存在（budget 依赖）| 缺失 → abort，budget 模块将一直读到 0 token |
| `def fallback_chain(primary, secondary, *, on_fallback=None)` | 在 base.py 存在 | 缺失 → abort，Plan #01 R5.1 未落地 |
| `analyze_module(uid, module, application_time=None)` | 签名与顶部描述一致 | 不一致 → 修顶部 P5 上游契约，同步 Task 1.4 `run_profile.py` |
| `TargetCountry` 5 个枚举（mexico/indonesia/pakistan/thailand/philippines）| 与顶部 P6 上游契约一致 | 不一致 → 修顶部 + 同步 Task 1.5 `_COUNTRY_MAP` |
| `TargetAction` 3 个枚举（build_table/extract/build_table_and_extract）| 与顶部 P6 上游契约一致 | 不一致 → 修顶部 + 同步 Task 1.5 |
| `ExecuteResponse` 含 `rows_per_uid` / `metadata.row_count_total` | 与顶部 P4 上游契约一致 | 不一致 → 修顶部 + 同步 Task 1.5 `_ChildAgent.execute` |

### Task 0.5.2 — grep `orchestrator_agent.decide` route 是否已在 config.yaml（R6 P0-4 驱动）

```powershell
Select-String -Path "config.yaml" -Pattern "orchestrator_agent\.decide|claude_maestro|\[Spike Pending\]" |
    ForEach-Object { "L$($_.LineNumber): $($_.Line.Trim())" }
```

**期望**：
- `claude_maestro:` + `endpoint: "[Spike Pending]"` 已存在（Plan #02 落地）
- `orchestrator_agent.decide: claude_maestro` 路由 —— **可能在 / 可能不在**（Plan #02 只加了 7 个 explainer.* + behavior_profile.timeline，未加 orchestrator_agent.decide）
- 不在 → Task 0.3 需补一行；Task 0.4 commit 同时包含该补丁
- 在 → Task 0.3 仅需替换 endpoint，简单

### Task 0.5.3 — grep providers/ 目录状态

```powershell
Get-ChildItem app/core/providers/ -File | Format-Table Name, Length
```

**期望**：`__init__.py` / `base.py` / `mock_provider.py` / `gemini_provider.py` / `json_repair.py` / `factory.py` / `claude_maestro_provider.py` 全部存在（Plan #01 + #02 累计）。

### Task 0.5.4 — 不一致时的处理

- 任一 grep 结果与顶部《已知风险》不一致 → **先修 Plan 顶部 + 受影响的 Task（常见 Task 1.4/1.5），然后才能进 Phase 1**
- Plan #01 缺关键契约 / Plan #02 缺路由 → **abort**，打开 Plan #01/#02 补齐
- 全部一致 → 进 Task 0.5.5

### Task 0.5.5 — 锚定 tests/ baseline 测试数量（R7 P1-2 新增）

```powershell
python -m pytest tests/ --collect-only -q 2>&1 | Select-String "tests? collected" | Select-Object -Last 1
# 例输出："289 tests collected"  → N = 289 - 270 = 19
```

**回填位点**：拿到具体数量后，手动回填下面 6 处原实验期望（实施期亲改 Plan，R6 P0-5 微调追溯机制记录到 commit message）：

| 位置 | 原文 | 回填后 |
|---|---|---|
| Task 0.1 期望输出 | `tests/` → 270 + N passed | `tests/` → <实际数字> passed |
| Task 1.8 期望输出 | `tests/` → 270 + N + 20 passed | `tests/` → <baseline+20> passed |
| Task 2.5 期望输出 | 270 + Phase 1/2 累计 passed | <baseline+20+13> passed |
| Task 3.6 期望输出 | 270 + Phase 1/2/3 累计 passed | <baseline+20+13+7> passed |
| Task 4.4 期望输出 | 270 + Phase 1/2/3/4 累计 passed | <baseline+20+13+7+5> passed |

> R9 P0-2 修订：R7 P0-3 把 Phase 1 测试数 19→20（追加 `test_assemble_system_prompt_default_no_country_section`），上表 4 处 `+19` 同步改 `+20`。Phase 1/2/3/4 累计 = 20+13+7+5 = 45。

**不一致处理**：如 collect-only 输出 < 270 → abort，Plan #01/#02 未真正落地。

> 本 Phase **默认**不写代码、不 commit、不改任何文件，只跑 grep / collect-only 命令验证事实底座。
>
> **R9 P1-1 闭环**：如 Task 0.5.4 / 0.5.5 发现不一致需要修 Plan 文档，被改的 Plan 文件作为 Phase 1 Task 1.8 commit 的一部分一并 `git add`（Task 1.8 add 清单本来就含 Plan 文件路径——见 Task 1.8 R9 P2-1 修订），Phase 1 commit message 追加一段 `Phase 0.5 实施期 Plan 文档微调：<差异列表>`，符合 R6 P0-5 实施期 Plan 文档微调追溯锚点机制。

---

## Phase 1 — 工具骨架 + Pydantic schemas + load_skill + System Prompt v1（TDD RED→GREEN）

> **TDD 铁律**：Task 1.1 先写契约测试看 RED，Task 1.2-1.7 实装看 GREEN，Task 1.8 跑全量 + 展示 diff + commit。违反此顺序（先实装后补测试）的方案直接打回。

### Task 1.1 — RED：先写契约测试（必失败）

**新建文件**：`tests/test_orchestrator_phase1.py`

**完整代码**：

```python
"""Phase 1 RED contract tests — must fail before implementation lands.

Covers:
- Pydantic schemas validation
- 6-tool registry shape
- load_skill / assemble_system_prompt path resolution
- session.py ACK gateway + per-session query_cancelled flag
"""

from __future__ import annotations

import pytest

from app.services.orchestrator_agent.schemas import (
    OrchestratorChatRequest, ParseUidFileInput, RunProfileInput,
    RunTraceInput, QueryDataInput,
    MemoryWriteInput, MemoryReadInput,
    OrchestratorSession,
)
from app.services.orchestrator_agent.tools import get_tool_registry
from app.services.orchestrator_agent.skills_loader import load_skill
from app.services.orchestrator_agent.system_prompt import (
    get_system_prompt_v1, assemble_system_prompt,
)
from app.services.orchestrator_agent.session import (
    is_query_cancelled, mark_query_cancelled, reset_query_cancelled,
)


# ---- Schemas ----

def test_chat_request_validates_min_length():
    with pytest.raises(ValueError):
        OrchestratorChatRequest(prompt="")


def test_chat_request_max_length():
    with pytest.raises(ValueError):
        OrchestratorChatRequest(prompt="a" * 4001)


def test_run_profile_input_validates_uids_min():
    with pytest.raises(ValueError):
        RunProfileInput(uids=[], app_time="2026-04-30", modules=["app"])


def test_run_profile_input_validates_uids_max():
    with pytest.raises(ValueError):
        RunProfileInput(uids=["a"] * 201, app_time="2026-04-30", modules=["app"])


def test_run_profile_input_app_time_required():
    with pytest.raises(ValueError):
        RunProfileInput(uids=["u1"], modules=["app"])


def test_run_trace_input_days_range():
    with pytest.raises(ValueError):
        RunTraceInput(uid="MX0001", days=0)
    with pytest.raises(ValueError):
        RunTraceInput(uid="MX0001", days=91)


def test_query_data_input_country_literal():
    # mexico 短码 mx 合法
    req = QueryDataInput(request="拉一批用户", country="mx")
    assert req.country == "mx"
    # 非 6 国之一（如 "us"）应当 Pydantic 拒绝
    with pytest.raises(ValueError):
        QueryDataInput(request="x", country="us")


def test_memory_write_key_pattern():
    with pytest.raises(ValueError):
        MemoryWriteInput(key="bad key with space", value="v")


def test_session_default_status_active():
    from datetime import datetime, timezone
    s = OrchestratorSession(
        session_id="abc", created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert s.status == "active"
    assert s.query_cancelled is False
    assert s.consecutive_failures == 0


# ---- Tools registry ----

def test_tool_registry_has_six_entries():
    reg = get_tool_registry()
    assert set(reg.keys()) == {
        "parse_uid_file", "run_profile", "run_trace",
        "query_data", "memory_write", "memory_read",
    }
    assert len(reg) == 6


# ---- Skills loader ----

def test_load_skill_unsupported_country():
    with pytest.raises(ValueError):
        load_skill("us")
    with pytest.raises(ValueError):
        load_skill("")


def test_load_skill_th_returns_content():
    content = load_skill("th")
    assert "泰国" in content or "th" in content.lower()
    assert "数据源" in content
    assert "UID 规范" in content


def test_load_skill_mx_returns_content():
    content = load_skill("mx")
    assert "墨西哥" in content or "mx" in content.lower()
    assert "MXN" in content


def test_load_skill_all_six_countries_exist():
    for c in ["th", "mx", "co", "pe", "cl", "br"]:
        content = load_skill(c)
        assert len(content) > 200, f"{c}.md too short, expected ≥ 200 chars"


# ---- System Prompt ----

def test_get_system_prompt_v1_loads():
    prompt = get_system_prompt_v1()
    assert "Orchestrator Agent" in prompt
    assert "parse_uid_file" in prompt
    assert "query_data" in prompt


def test_assemble_system_prompt_includes_country_section():
    prompt = assemble_system_prompt("th")
    assert "国别规则" in prompt
    assert "th" in prompt.lower()


def test_assemble_system_prompt_default_no_country_section():
    """R7 P0-3：country=None 时 base prompt 不包含“国别规则”段，
    防 Knowledge 层被错误注入。"""
    prompt = assemble_system_prompt(None)
    assert "国别规则" not in prompt


# ---- Session ACK gateway + query_cancelled ----

def test_query_cancelled_default_false():
    reset_query_cancelled("test-session-1")
    assert is_query_cancelled("test-session-1") is False


def test_mark_and_reset_query_cancelled():
    sid = "test-session-2"
    reset_query_cancelled(sid)
    mark_query_cancelled(sid)
    assert is_query_cancelled(sid) is True
    reset_query_cancelled(sid)
    assert is_query_cancelled(sid) is False


def test_query_cancelled_per_session_isolated():
    reset_query_cancelled("sess-A")
    reset_query_cancelled("sess-B")
    mark_query_cancelled("sess-A")
    assert is_query_cancelled("sess-A") is True
    assert is_query_cancelled("sess-B") is False
```

**验证命令**：

```powershell
python -m pytest tests/test_orchestrator_phase1.py -v
```

**期望输出**：**全部 errors / failures**（`ImportError: No module named 'app.services.orchestrator_agent'`）。**必须看到失败**——这是 RED 状态。

> 这个失败是 TDD 驱动 Task 1.2-1.7 实装的契约。如果 Task 1.1 直接通过了，说明被测代码已存在——那么本 Task 自身就有问题，必须重写测试或先回滚相关代码。

#### Task 1.1 末尾附带：新建 `tests/conftest.py`（R7 P1-1）

> 原因：`session_store.create_session()` 走 `_DIRTY` → atexit `flush()` → 写 `outputs/orchestrator_sessions/<uuid>.json`。
> Phase 1 + 2 + 3 + 4 跑完会有 30+ 个测试 session JSON 写入生产 outputs/，污染现有输出目录。
> conftest.py autouse fixture 重定向到 `tmp_path`，表完后自动清理。

```python
"""Test fixtures for Orchestrator Agent (R7 P1-1).

重定向 session_store 与 memory 的输出目录到 tmp_path，防测试副作用污染 outputs/。
仅在含 orchestrator_agent 模块 import 的测试里生效，其它已有测试不受影响。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _redirect_orchestrator_outputs(tmp_path, monkeypatch):
    """Auto-redirect orchestrator session/memory dirs to tmp_path during tests."""
    try:
        from app.services.orchestrator_agent import session_store
        from app.services.orchestrator_agent.tools import memory as memory_mod
    except ImportError:
        # Phase 1 RED 阶段模块不存在，跳过重定向（测试会以 ImportError 失败 → RED 预期）
        return
    monkeypatch.setattr(
        session_store, "_sessions_dir",
        lambda: tmp_path / "orchestrator_sessions",
    )
    monkeypatch.setattr(
        memory_mod, "_memory_dir",
        lambda: tmp_path / "orchestrator_memory",
    )
```

### Task 1.2 — GREEN：实装 `schemas.py`

**新建文件**：`app/services/orchestrator_agent/__init__.py`（空文件，包标识）

```python
"""Orchestrator Agent — natural-language analytics orchestration."""
```

**新建文件**：`app/services/orchestrator_agent/schemas.py`

```python
"""Pydantic v2 schemas for Orchestrator Agent inputs / outputs / sessions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# 6 国短码（与 docs/skills/orchestrator/*.md 文件名对齐）
# 注意：与 data_acquisition_agent.TargetCountry 全称（mexico/...）不一致，
# V1 只 mexico 走真，其它 5 国 query_data 直接 reject（见 Task 1.5）。
CountryCode = Literal["th", "mx", "co", "pe", "cl", "br"]

# Profile 模块（与 AnalysisOrchestrator.SUPPORTED_MODULES 对齐）
ProfileModule = Literal["app", "behavior", "credit", "comprehensive", "product", "ops"]


# ===== Top-level chat request =====

class OrchestratorChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = None


# ===== 6 工具的 Input / Output Schemas =====

class ParseUidFileInput(BaseModel):
    file_path: str = Field(..., description="UID 文件本地路径，必须在 data/id_files/ 下")


class ParseUidFileOutput(BaseModel):
    uids: list[str]
    source_path: str
    duplicates_removed: int


class RunProfileInput(BaseModel):
    uids: list[str] = Field(..., min_length=1, max_length=200)
    app_time: str = Field(..., description="ISO8601 格式 application_time")
    modules: Optional[list[ProfileModule]] = None  # None = 默认 ["app"]


class RunProfileOutput(BaseModel):
    results: list[dict[str, Any]]
    cache_hits: int = 0
    cache_misses: int = 0


class RunTraceInput(BaseModel):
    uid: str
    days: int = Field(7, ge=1, le=90)


class RunTraceOutput(BaseModel):
    events: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)


class QueryDataInput(BaseModel):
    request: str = Field(..., min_length=1, max_length=2000)
    country: CountryCode


class QueryDataOutput(BaseModel):
    uids: list[str]
    rows_actual: int
    sql_text: str          # 已脱敏
    rows_estimated: int = -1


class MemoryWriteInput(BaseModel):
    key: str = Field(..., pattern=r"^[a-zA-Z0-9_/.-]+$", max_length=200)
    value: str = Field(..., max_length=20000)


class MemoryWriteOutput(BaseModel):
    ok: bool
    path: str


class MemoryReadInput(BaseModel):
    key_pattern: str = Field(..., max_length=200)


class MemoryReadOutput(BaseModel):
    items: list[dict[str, str]] = Field(default_factory=list)


# ===== Session 持久化 schemas =====

class ToolCallRecord(BaseModel):
    tool_name: str
    tool_call_id: str
    input: dict[str, Any]
    output: dict[str, Any] | None = None
    status: Literal["pending", "running", "done", "error"]
    started_at: datetime
    finished_at: datetime | None = None


class OrchestratorMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_call_id: str | None = None
    timestamp: datetime


class OrchestratorSession(BaseModel):
    session_id: str
    created_at: datetime
    updated_at: datetime
    messages: list[OrchestratorMessage] = Field(default_factory=list)
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    total_tokens: int = 0
    final_message: str | None = None
    confidence: float | None = None
    status: Literal["active", "completed", "error", "budget_exceeded"] = "active"
    # 同 session 内任一 query_data ACK 被拒绝则置 True，后续 query_data 直接 reject
    query_cancelled: bool = False
    # 连续工具失败计数，达 K=3 强制结束 session
    consecutive_failures: int = 0
```

**验证命令**：

```powershell
python -c "from app.services.orchestrator_agent.schemas import OrchestratorChatRequest, OrchestratorSession; from datetime import datetime, timezone; s = OrchestratorSession(session_id='x', created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)); print(s.status, s.query_cancelled, s.consecutive_failures)"
# 期望：active False 0
```

### Task 1.3 — GREEN：6 工具 stub 注册（含 memory V1 minimal 完整代码）

**新建文件**：`app/services/orchestrator_agent/tools/__init__.py`

```python
"""Orchestrator Agent tools registry.

V1 注册 6 个工具入口。memory_write / memory_read 是 V1 minimal 实装（本地 JSON 写盘），
其它 4 工具在 Task 1.4-1.5 实装；Task 1.3 阶段 4 工具均为 NotImplementedError stub。
"""

from app.services.orchestrator_agent.tools.parse_uid_file import parse_uid_file
from app.services.orchestrator_agent.tools.run_profile import run_profile
from app.services.orchestrator_agent.tools.run_trace import run_trace
from app.services.orchestrator_agent.tools.query_data import query_data
from app.services.orchestrator_agent.tools.memory import memory_write, memory_read

__all__ = [
    "parse_uid_file", "run_profile", "run_trace",
    "query_data", "memory_write", "memory_read",
    "get_tool_registry",
]


def get_tool_registry() -> dict:
    return {
        "parse_uid_file": parse_uid_file,
        "run_profile": run_profile,
        "run_trace": run_trace,
        "query_data": query_data,
        "memory_write": memory_write,
        "memory_read": memory_read,
    }
```

**新建文件**：`app/services/orchestrator_agent/tools/parse_uid_file.py`（stub）

```python
"""parse_uid_file — Task 1.4 实装。"""

from app.services.orchestrator_agent.schemas import ParseUidFileInput, ParseUidFileOutput


def parse_uid_file(input_data: ParseUidFileInput) -> ParseUidFileOutput:
    raise NotImplementedError("parse_uid_file: implemented in Task 1.4")
```

**新建文件**：`app/services/orchestrator_agent/tools/run_profile.py`（stub）

```python
"""run_profile — Task 1.4 实装。"""

from app.services.orchestrator_agent.schemas import RunProfileInput, RunProfileOutput


def run_profile(input_data: RunProfileInput) -> RunProfileOutput:
    raise NotImplementedError("run_profile: implemented in Task 1.4")
```

**新建文件**：`app/services/orchestrator_agent/tools/run_trace.py`（stub）

```python
"""run_trace — Task 1.4 实装。"""

from app.services.orchestrator_agent.schemas import RunTraceInput, RunTraceOutput


def run_trace(input_data: RunTraceInput) -> RunTraceOutput:
    raise NotImplementedError("run_trace: implemented in Task 1.4")
```

**新建文件**：`app/services/orchestrator_agent/tools/query_data.py`（stub）

```python
"""query_data — Task 1.5 实装（含 _ChildAgent facade + ACK）。"""

from app.services.orchestrator_agent.schemas import QueryDataInput, QueryDataOutput


def query_data(input_data: QueryDataInput) -> QueryDataOutput:
    raise NotImplementedError("query_data: implemented in Task 1.5")
```

**新建文件**：`app/services/orchestrator_agent/tools/memory.py`（V1 minimal 实装，**完整代码**）

```python
"""memory_write / memory_read — V1 minimal local-JSON impl.

V1 只支持本地文件 KV，不跨 session 持久。
V2 升级到 Redis / SQLite KV（独立 Plan，不在本 Plan 内）。
"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings
from app.services.orchestrator_agent.schemas import (
    MemoryWriteInput, MemoryWriteOutput,
    MemoryReadInput, MemoryReadOutput,
)


def _memory_dir() -> Path:
    p = settings.project_root / "outputs" / "orchestrator_memory"
    p.mkdir(parents=True, exist_ok=True)
    return p


def memory_write(input_data: MemoryWriteInput) -> MemoryWriteOutput:
    safe_key = input_data.key.replace("/", "_").replace(".", "_")
    target = _memory_dir() / f"{safe_key}.txt"
    target.write_text(input_data.value, encoding="utf-8")
    return MemoryWriteOutput(ok=True, path=str(target))


def memory_read(input_data: MemoryReadInput) -> MemoryReadOutput:
    base = _memory_dir()
    items: list[dict[str, str]] = []
    pattern = input_data.key_pattern.replace("*", "")
    for f in base.glob("*.txt"):
        if pattern in f.stem:
            items.append({"key": f.stem, "value": f.read_text(encoding="utf-8")})
    return MemoryReadOutput(items=items)
```

**新建文件**：`app/services/orchestrator_agent/session.py`（一次到位：dict + threading.Lock）

```python
"""Session-bound ACK gateway + per-session query_cancelled flag.

Phase 2 Task 2.2 接入真实 SessionStore 时只追加 wire-up，本文件结构不再变。
"""

from __future__ import annotations

import threading
from typing import Callable

_LOCK = threading.Lock()
_ACK_PROVIDER: Callable[..., bool] | None = None
_PER_SESSION_CANCEL: dict[str, bool] = {}


def register_ack_provider(provider: Callable[..., bool]) -> None:
    """Wire SSE handler's ack_bus.wait_ack into this gateway.

    Provider signature:
        provider(session_id, sql_text, artifact_path, rows_estimated) -> bool
    """
    global _ACK_PROVIDER
    _ACK_PROVIDER = provider


def get_active_session_ack(
    session_id: str,
    sql_text: str,
    artifact_path: str = "",
    rows_estimated: int = -1,
) -> bool:
    """Block until user ACKs (via SSE → ack_bus). Default deny if not wired."""
    if _ACK_PROVIDER is None:
        return False
    return _ACK_PROVIDER(
        session_id=session_id,
        sql_text=sql_text,
        artifact_path=artifact_path,
        rows_estimated=rows_estimated,
    )


def is_query_cancelled(session_id: str) -> bool:
    with _LOCK:
        return _PER_SESSION_CANCEL.get(session_id, False)


def mark_query_cancelled(session_id: str) -> None:
    with _LOCK:
        _PER_SESSION_CANCEL[session_id] = True


def reset_query_cancelled(session_id: str) -> None:
    with _LOCK:
        _PER_SESSION_CANCEL.pop(session_id, None)
```

**验证命令**：

```powershell
python -c "from app.services.orchestrator_agent.tools import get_tool_registry; reg = get_tool_registry(); print(list(reg.keys()))"
# 期望：['parse_uid_file', 'run_profile', 'run_trace', 'query_data', 'memory_write', 'memory_read']

python -c "from app.services.orchestrator_agent.tools.memory import memory_write; from app.services.orchestrator_agent.schemas import MemoryWriteInput; o = memory_write(MemoryWriteInput(key='test_phase1', value='hello')); print(o.ok, o.path)"
# 期望：True <project>/outputs/orchestrator_memory/test_phase1.txt
```

### Task 1.4 — GREEN：实装 `parse_uid_file` + `run_profile` + `run_trace`（基于真实契约）

> **本 Task 已 grep 验证**：
> - `app/services/orchestrator.py:29` `class AnalysisOrchestrator` + `analyze_module(uid, module, application_time=None)` 签名固定
> - `app/services/orchestrator.py:304` **存在** `shared_orchestrator = AnalysisOrchestrator()` 模块级单例（R9 P0-3 修正：与已知风险 #7 描述对齐），但 V1 工具刻意 per-call 实例化以避免跨 session 缓存污染（详见已知风险 #7）
> - `app/runtime_skills/trace_analyzer/analyzer.py` `class TraceAnalyzer` + `def analyze(self, uid, context=None) -> dict` + 模块级 `def build_context(uid, country_code=None, enable_llm_explanation=True)`
> - `TraceAnalyzer.analyze` 返回 dict，字段由 `TraceAssembler.assemble()` 装配；V1 用 `out.get("events", [])` / `out.get("summary", {})` fallback，找不到键则空但不抛错
> - `AnalysisOrchestrator.SUPPORTED_MODULES = {"app", "behavior", "credit", "comprehensive", "product", "ops"}`

**修改文件**：`app/services/orchestrator_agent/tools/parse_uid_file.py`（替换 stub 内容）

```python
"""parse_uid_file — UID 文件解析；防路径穿越 + 去重去空白。"""

from __future__ import annotations

import re

from app.core.config import settings
from app.services.orchestrator_agent.schemas import (
    ParseUidFileInput, ParseUidFileOutput,
)

_UID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_BASE = "data/id_files"


def parse_uid_file(input_data: ParseUidFileInput) -> ParseUidFileOutput:
    """Parse UID file under data/id_files/. 防路径穿越 + 去重去空白。"""
    base = (settings.project_root / _BASE).resolve()
    target = (settings.project_root / input_data.file_path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise PermissionError(
            f"file_path must be under {_BASE}: got {input_data.file_path}"
        )
    if not target.exists():
        raise FileNotFoundError(f"UID file not found: {target}")
    seen: set[str] = set()
    uids: list[str] = []
    duplicates = 0
    with open(target, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or not _UID_REGEX.match(line):
                continue
            if line in seen:
                duplicates += 1
                continue
            seen.add(line)
            uids.append(line)
    return ParseUidFileOutput(
        uids=uids, source_path=str(target), duplicates_removed=duplicates,
    )
```

**修改文件**：`app/services/orchestrator_agent/tools/run_profile.py`（替换 stub 内容）

```python
"""run_profile — 薄封装 AnalysisOrchestrator.analyze_module()。

V1 决策：per-call 实例化 AnalysisOrchestrator（成本可接受），不引入模块级单例。
modules 默认 ["app"]；遍历 (uid × module) 调 analyze_module。
"""

from __future__ import annotations

from typing import Any

from app.services.orchestrator import AnalysisOrchestrator
from app.services.orchestrator_agent.schemas import (
    RunProfileInput, RunProfileOutput,
)


def run_profile(input_data: RunProfileInput) -> RunProfileOutput:
    orch = AnalysisOrchestrator()
    modules = input_data.modules or ["app"]
    results: list[dict[str, Any]] = []
    for uid in input_data.uids:
        for mod in modules:
            r = orch.analyze_module(
                uid=uid, module=mod, application_time=input_data.app_time,
            )
            results.append({"uid": uid, "module": mod, "result": r})
    return RunProfileOutput(
        results=results,
        cache_hits=0,
        cache_misses=len(input_data.uids) * len(modules),
    )
```

**修改文件**：`app/services/orchestrator_agent/tools/run_trace.py`（替换 stub 内容）

```python
"""run_trace — 薄封装 TraceAnalyzer.analyze()。"""

from __future__ import annotations

from app.runtime_skills.trace_analyzer.analyzer import TraceAnalyzer, build_context
from app.services.orchestrator_agent.schemas import RunTraceInput, RunTraceOutput


def run_trace(input_data: RunTraceInput) -> RunTraceOutput:
    """Run trace analysis for a single UID.

    V1：days 字段保留但不传给 build_context（下游 N 天阈值走 trace_analyzer 内部配置）。
    返回 dict 字段不确定，用 .get() fallback 防 KeyError。
    """
    analyzer = TraceAnalyzer()
    ctx = build_context(input_data.uid)
    out = analyzer.analyze(uid=input_data.uid, context=ctx)
    return RunTraceOutput(
        events=out.get("events", []),
        summary=out.get("summary", {}),
    )
```

**验证命令**：

```powershell
python -c "from app.services.orchestrator_agent.tools.run_trace import run_trace; from app.services.orchestrator_agent.schemas import RunTraceInput; o = run_trace(RunTraceInput(uid='MX0001', days=7)); print(type(o.events), type(o.summary))"
# 期望：<class 'list'> <class 'dict'>（即使下游真实数据没有匹配 UID，fallback 仍返回空 list/dict 不抛错）
```

### Task 1.5 — GREEN：实装 `query_data`（_ChildAgent facade + 真实 ExecuteRequest）

> **本 Task 已 grep 验证**：
> - `data_acquisition_agent/orchestrator.py:43` `class DataAcquisitionOrchestrator.generate(request: GenerateRequest) -> GenerateResponse`
> - `data_acquisition_agent/executor.py:103` `def run_execute_pipeline(request: ExecuteRequest, *, request_id: str) -> dict`，返回字段：`request_id, output_bucket, output_format, filenames, written_file_count, total_uids, rows_per_uid, metadata`（**无** `uids` 字段，从 `rows_per_uid.keys()` 反推）
> - `data_acquisition_agent/schemas.py:17` `class TargetCountry(str, Enum)` 仅枚举 5 国全称：`mexico/indonesia/pakistan/thailand/philippines`
> - `data_acquisition_agent/schemas.py:25` `class TargetAction(str, Enum)` 仅枚举 3 项：`build_table/extract/build_table_and_extract`（**无** `GENERATE`）
> - `data_acquisition_agent/schemas.py:50` `GenerateRequest(natural_language_request, target_country, target_action)`
> - `data_acquisition_agent/schemas.py:115` `ExecuteRequest(approved_sql, sql_kind, target_country, approved_by, output_bucket, output_format, uid_column='uid', overwrite=True, ...)`
> - `GenerateResponse` **无** `artifact_path` / `rows_estimated` 字段；rows estimated 由 `executor.precheck_row_count` 在 execute 阶段获取

**V1 国别映射策略**（关键决策）：

| Plan #03 短码 | da-agent 全称 | V1 行为 |
|---|---|---|
| `mx` | `mexico` | 走真实 generate → ACK → execute 链 |
| `th` | `thailand`（da-agent 有 placeholder yaml） | `ManifestNotImplemented` → reject 但不抛 ValueError |
| `co/pe/cl/br` | （da-agent 不存在） | `ValueError("country not supported in V1")` 在工具入口拦截 |

**修改文件**：`app/services/orchestrator_agent/tools/query_data.py`（替换 stub 内容）

```python
"""query_data — Parent-Child 隔离 + ACK；不动 data_acquisition_agent 任何文件。

ACK 时序由 agent_loop.py 接管（避免同步 wait_ack 阻塞 SSE event loop）。
本文件提供 _ChildAgent facade（agent_loop 直接调）+ query_data() 单测/兼容函数。

V1 国别支持：mx → mexico；th → thailand（da-agent 抛 ManifestNotImplemented）；
co/pe/cl/br 直接拒绝；其它 country code 在 QueryDataInput 已被 Pydantic 拒绝。
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

# 仅 import，不修改 data_acquisition_agent 任何文件
from data_acquisition_agent.orchestrator import DataAcquisitionOrchestrator
from data_acquisition_agent.executor import run_execute_pipeline
from data_acquisition_agent.schemas import (
    GenerateRequest, ExecuteRequest, TargetCountry, TargetAction,
)

from app.services.orchestrator_agent.schemas import QueryDataInput, QueryDataOutput


_PROHIBITED_SQL = re.compile(
    r"\b(DELETE|DROP|TRUNCATE|UPDATE|INSERT)\b", re.IGNORECASE,
)

# Plan #03 短码 → da-agent TargetCountry 映射
_COUNTRY_MAP: dict[str, TargetCountry] = {
    "mx": TargetCountry.MEXICO,
    "th": TargetCountry.THAILAND,
    # co/pe/cl/br 不在 da-agent，工具入口直接拒绝
}


@dataclass
class _ChildResult:
    sql_text: str
    rows_estimated: int  # V1 由 da-agent execute 阶段返回；generate 阶段固定 -1


class _ChildAgent:
    """Per-call facade；不保留状态，不修改 data_acquisition_agent。"""

    def __init__(self, country: str) -> None:
        if country not in _COUNTRY_MAP:
            raise ValueError(
                f"V1 query_data does not support country={country!r}; "
                f"only mx (and stub th) supported. See Plan #03 Scope."
            )
        self._country = _COUNTRY_MAP[country]
        self._orch = DataAcquisitionOrchestrator()

    def run_query(self, request_text: str) -> _ChildResult:
        """Generate SQL via da-agent. Returns sql_text；rows_estimated=-1（待 execute 阶段）。"""
        gen_req = GenerateRequest(
            natural_language_request=request_text,
            target_country=self._country,
            target_action=TargetAction.EXTRACT,
        )
        gen_resp = self._orch.generate(gen_req)
        sql_text = gen_resp.sql or ""
        return _ChildResult(sql_text=sql_text, rows_estimated=-1)

    def execute(
        self,
        sql_text: str,
        *,
        approved_by: str = "orchestrator_agent",
        output_bucket: str = "behavior",
        output_format: str = "json",
    ) -> dict:
        """Execute approved SQL. Returns {uids, rows_actual}.

        - output_bucket V1 默认 "behavior"（与 query_data 用法对齐：拉一批 UID 用于跑画像）
        - output_format V1 默认 "json"（避免 app bucket→csv 强制约束）
        - UID 列表从 rows_per_uid.keys() 反推（ExecuteResponse 无 uids 字段）
        """
        rid = uuid.uuid4().hex
        exe_req = ExecuteRequest(
            approved_sql=sql_text,
            sql_kind="query_only",
            target_country=self._country,
            approved_by=approved_by,
            output_bucket=output_bucket,
            output_format=output_format,
        )
        exe_resp = run_execute_pipeline(exe_req, request_id=rid)
        rows_per_uid = exe_resp.get("rows_per_uid", {}) or {}
        uids = list(rows_per_uid.keys())
        rows_actual = int(exe_resp.get("metadata", {}).get("row_count_total", 0))
        return {"uids": uids, "rows_actual": rows_actual}


# ANTI-PATTERN: Do not expose require_confirmation as a tool argument.
# If the LLM can pass require_confirmation=False, prompt injection can
# bypass the security ACK gate. ACK is hardcoded inside agent_loop.

def query_data(input_data: QueryDataInput) -> QueryDataOutput:
    """Single-shot query path — 仅供单测 / 外部调用者 facade。

    生产路径（agent_loop.py）**不**走本函数——agent_loop 直接导入 `_ChildAgent`,
    拆成6 个阶段调用：run_query → SSE preview → ACK gate → wait_ack → execute → SSE final.
    ACK 控制仅在 agent_loop 内部硬编码，本函数不涉及 ACK（所以单测能同步跑完）。
    """
    child = _ChildAgent(country=input_data.country)
    try:
        gen = child.run_query(input_data.request)
        sql_text = gen.sql_text
        if _PROHIBITED_SQL.search(sql_text):
            raise ValueError("Prohibited SQL keyword detected in generated SQL")
        execute_out = child.execute(sql_text)
        return QueryDataOutput(
            uids=execute_out["uids"],
            rows_actual=execute_out["rows_actual"],
            sql_text=sql_text,
            rows_estimated=gen.rows_estimated,
        )
    finally:
        del child  # per-call 即丢
```

**验证命令**（不调真实 da-agent，仅验证 import + ValueError 路径）：

```powershell
python -c "from app.services.orchestrator_agent.tools.query_data import _ChildAgent; import pytest; pytest.raises(ValueError, _ChildAgent, country='co'); print('co rejected ok')"
# 期望：co rejected ok
```

### Task 1.6 — GREEN：6 国 `skills/*.md` + `skills_loader.py`

> 6 个文件 V1 baseline 直接落盘，每个文件 ≥ 30 行实际内容。具体业务阈值（流失天数 / GMV / 节假日）业务方确认后用 `<!-- V1 baseline，业务方确认后更新 -->` 注释定位修订点。

**新建文件**：`docs/skills/orchestrator/th.md`

```markdown
# 泰国（th）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/th/*.csv`
- 行为事件：`data/behavior/th/*.csv`
- 征信数据：`data/credit/th/*.json`
- UID 文件：`data/id_files/th/*.txt`

## UID 规范
- UID 长度 8-32 字符（与 Plan #03 Phase 2 `uid_whitelist._PATTERNS["th"]` 同步）
- 字符集：[a-zA-Z0-9_-]
- 示例：`TH000123` / `th_user_456`

## 关键时区
- Asia/Bangkok (UTC+7)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59 (UTC+7)

## 流失定义（默认）
- 30 天无下单 = 流失
- "上周流失" = 上周内最后一次活跃距今 ≥ 30 天

## 货币
- 单位：THB
- Behavior Profile `value_estimation` 输入按 THB 处理；汇报时不做汇率换算

## 常见取数模板（query_data 触发示例）
- "上周流失下单用户" → 限定时区 UTC+7，过滤上周内有下单记录且最近 30 天无活跃
- "高价值用户" → 单笔 GMV ≥ 1000 THB
- "新增注册" → 按 created_at 过滤，注意时区转换

## V1 query_data 状态
- **stub**：da-agent V1 未启用 thailand manifest，`query_data(country="th")` 抛 `ManifestNotImplemented`
- 解锁条件：Plan #2.5 da-agent 多国扩展 + thailand manifest 实装

## 节假日
- 默认按工作日计算；具体节假日 → `docs/skills/orchestrator/holidays/th.md`（按需扩展）
```

**新建文件**：`docs/skills/orchestrator/mx.md`

```markdown
# 墨西哥（mx）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/mx/*.csv`
- 行为事件：`data/behavior/mx/*.csv`
- 征信数据：`data/credit/mx/*.json`
- UID 文件：`data/id_files/mx/*.txt`

## UID 规范
- UID 长度 4-32 字符（与 Plan #03 Phase 2 `uid_whitelist._PATTERNS["mx"]` 同步）
- 字符集：[a-zA-Z0-9_-]
- 示例：`MX0001` / `mx_user_123`

## 关键时区
- America/Mexico_City (UTC-6 / 夏令时 UTC-5)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59（按本地时区）

## 流失定义（默认）
- 30 天无下单 = 流失

## 货币
- 单位：MXN

## 常见取数模板
- "上周流失下单用户" → 参考 `data_acquisition_agent/demo0/` 的 mob1 数据集
- "高价值用户" → 单笔 GMV ≥ 1000 MXN

## V1 query_data 状态
- **可用**：da-agent V1 mexico manifest 已实装，163 测试基线已覆盖
- 调用：`query_data(request=..., country="mx")` 走 generate → ACK → execute 链

## 节假日
- 默认按工作日计算；具体节假日按需扩展
```

**新建文件**：`docs/skills/orchestrator/co.md`

```markdown
# 哥伦比亚（co）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/co/*.csv`
- 行为事件：`data/behavior/co/*.csv`
- 征信数据：`data/credit/co/*.json`
- UID 文件：`data/id_files/co/*.txt`

## UID 规范
- UID 长度 4-32 字符
- 字符集：[a-zA-Z0-9_-]

## 关键时区
- America/Bogota (UTC-5)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59

## 流失定义（默认）
- 30 天无下单 = 流失

## 货币
- 单位：COP（哥伦比亚比索；金额数值大，注意 int64 溢出）

## 常见取数模板
- "高价值用户" → 单笔 GMV ≥ 100,000 COP（V1 占位阈值，业务方确认后更新）

## V1 query_data 状态
- **不支持**：da-agent V1 没有 colombia manifest 也没有枚举值。`query_data(country="co")` 在工具入口直接抛 `ValueError("V1 query_data does not support country='co'")`
- 解锁条件：业务方确认 colombia 接入需求 → da-agent 增加 colombia 枚举 + manifest（独立 Plan）

## 节假日
- 默认按工作日计算
```

**新建文件**：`docs/skills/orchestrator/pe.md`

```markdown
# 秘鲁（pe）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/pe/*.csv`
- 行为事件：`data/behavior/pe/*.csv`
- 征信数据：`data/credit/pe/*.json`
- UID 文件：`data/id_files/pe/*.txt`

## UID 规范
- UID 长度 4-32 字符
- 字符集：[a-zA-Z0-9_-]

## 关键时区
- America/Lima (UTC-5)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59

## 流失定义（默认）
- 30 天无下单 = 流失

## 货币
- 单位：PEN（秘鲁索尔）

## 常见取数模板
- "高价值用户" → 单笔 GMV ≥ 200 PEN（V1 占位阈值）

## V1 query_data 状态
- **不支持**：与 co 同；`query_data(country="pe")` 入口拒绝
- 解锁条件：与 co 同

## 节假日
- 默认按工作日计算
```

**新建文件**：`docs/skills/orchestrator/cl.md`

```markdown
# 智利（cl）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/cl/*.csv`
- 行为事件：`data/behavior/cl/*.csv`
- 征信数据：`data/credit/cl/*.json`
- UID 文件：`data/id_files/cl/*.txt`

## UID 规范
- UID 长度 4-32 字符
- 字符集：[a-zA-Z0-9_-]

## 关键时区
- America/Santiago (UTC-4 / 夏令时 UTC-3)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59

## 流失定义（默认）
- 30 天无下单 = 流失

## 货币
- 单位：CLP（智利比索；金额数值大，注意 int64 溢出）

## 常见取数模板
- "高价值用户" → 单笔 GMV ≥ 50,000 CLP（V1 占位阈值）

## V1 query_data 状态
- **不支持**：与 co 同
- 解锁条件：与 co 同

## 节假日
- 默认按工作日计算
```

**新建文件**：`docs/skills/orchestrator/br.md`

```markdown
# 巴西（br）分析规则

<!-- V1 baseline，业务方确认后更新 -->

## 数据源
- App 安装数据：`data/app/br/*.csv`
- 行为事件：`data/behavior/br/*.csv`
- 征信数据：`data/credit/br/*.json`
- UID 文件：`data/id_files/br/*.txt`

## UID 规范
- UID 长度 4-32 字符
- 字符集：[a-zA-Z0-9_-]

## 关键时区
- America/Sao_Paulo (UTC-3 / 夏令时 UTC-2)
- 业务定义"上周" = 周一 00:00 ~ 周日 23:59

## 流失定义（默认）
- 30 天无下单 = 流失

## 货币
- 单位：BRL（巴西雷亚尔）

## 常见取数模板
- "高价值用户" → 单笔 GMV ≥ 200 BRL（V1 占位阈值）

## V1 query_data 状态
- **不支持**：与 co 同
- 解锁条件：与 co 同

## 节假日
- 默认按工作日计算
```

**新建文件**：`app/services/orchestrator_agent/skills_loader.py`

```python
"""load_skill — knowledge layer for country-specific analysis rules."""

from __future__ import annotations

from app.core.config import settings


_SUPPORTED = {"th", "mx", "co", "pe", "cl", "br"}


def load_skill(country: str) -> str:
    """Load country-specific skills md content.

    Raises:
        ValueError: country not in 6 supported codes.
        FileNotFoundError: skills md missing on disk.
    """
    if country not in _SUPPORTED:
        raise ValueError(
            f"Unsupported country code: {country!r}. "
            f"Supported: {sorted(_SUPPORTED)}"
        )
    path = settings.project_root / "docs" / "skills" / "orchestrator" / f"{country}.md"
    if not path.exists():
        raise FileNotFoundError(f"Skills file not found: {path}")
    return path.read_text(encoding="utf-8")
```

**验证命令**：

```powershell
python -c "from app.services.orchestrator_agent.skills_loader import load_skill; print(len(load_skill('mx'))); print(load_skill('mx')[:50])"
# 期望：长度 ≥ 800；前 50 字符 # 墨西哥（mx）分析规则
```

### Task 1.7 — GREEN：System Prompt v1 完整文本（嵌入 Plan + 落盘）

**新建文件**：`app/prompts/orchestrator_system_prompt_v1.md`

> 完整文本如下（与 Design Doc § 附录 A 一致；本 Plan 自包含，不依赖任何外部"复制粘贴"指令）。
>
> **⚠️ 落盘说明（R10 P2）**：下面是 4 反引号 fence 包裹 3 反引号 fence 的嵌套结构（准确讲是 “\`\`\`\`markdown…\`\`\`\`”包住「System Prompt 原文 + 其内部的 \`\`\`json 代码块」）。落盘时**只写 fence 内部内容**（从 `You are the Orchestrator Agent...` 起、到 `Never produce both keys in the same response.` 止），**不含**外层 \`\`\`\`markdown 和 \`\`\`\` 两行。Task 4.4 的 R9 P1-2 校验命令会逐字节 diff Design Doc 附录 A vs system_prompt_v1.md，多几个反引号会被当场拦下。
>
> **R10 P1-1 同步项**：本 Task 落盘 system_prompt_v1.md 后，必须同步修 Design Doc `docs/specs/03-orchestrator-agent-design.md` § 13 中该行（约 line 611）的 “Task 1.6 把附录 A 写入 ...” → “Task 1.7 把附录 A 写入 ...”，使 Design Doc 与本 Plan Task 编号一致。该行修订随 Task 4.4 add 清单一起进 [complete] commit（面上不需额外 commit）。

````markdown
You are the Orchestrator Agent for the Mexico/SEA user-profile analytics platform.
Your job is to help analysts run multi-step user-profile investigations using
natural language requests. You orchestrate a fixed set of tools; you do NOT
write code, do NOT invent SQL, and do NOT execute anything outside the
provided tools.

# Your Tools (6 entries, 5 responsibility groups)

1. parse_uid_file(file_path: str) -> list[str]
   Parse a local UID text/CSV file. Returns deduplicated UID list.

2. run_profile(uids: list[str], app_time: str, modules: list[str] | None = None)
   Run profile analysis for one or many UIDs. Default modules=["app"]; pass
   modules=["app","behavior","credit","comprehensive","product","ops"] to
   include the full skill set. Caching is handled internally.

3. run_trace(uid: str, days: int = 7)
   Return single-UID behavior trace analysis (timeline + churn root cause).

4. query_data(request: str, country: "mx")  # ⚠️ V1: ONLY "mx" works.
   "th" returns ManifestNotImplemented; "co/pe/cl/br" raise ValueError at
   the tool entrypoint. Do NOT call query_data for any country other than
   "mx" — the call will fail and waste a round.
   Submit a natural-language data extraction request. Internally generates
   SQL, asks the user to ACK the SQL, then executes and returns a UID list.
   ACK is enforced by the security layer; you cannot disable it.

5. memory_write(key: str, value: str) -> bool
   Persist a key-value pair across rounds (V1 local-JSON; not cross-session).

6. memory_read(key_pattern: str) -> list[{key, value}]
   Read previously persisted values matching the given key pattern.

# Knowledge Skills (load on demand)

You have access to 6 country-specific analysis playbooks under
docs/skills/orchestrator/{country}.md. The Agent runtime injects the
relevant skill content into the system prompt automatically when a country
code is detected in the user request — you do NOT call any load_skill tool.

A single session may load at most 3 country skills (the runtime enforces this).

# Decision Rules

- If user provides UIDs directly (or a UID file path), call parse_uid_file
  (if file) then run_profile.
- If user describes a cohort in natural language ("流失下单用户" / "高风险逾期"),
  call query_data first to materialize the UID list, then run_profile.
- For single-UID deep behavioral investigation, call run_trace instead of
  run_profile (or in addition to it).
- Always extract the country code explicitly. If ambiguous, ask the user.
- Always extract app_time explicitly (default to "today" only if user clearly
  means "now").

# Output Style

- Keep your reasoning concise; do not narrate every internal thought.
- After all tools complete, write a 5-section Markdown summary:
  1. 用户请求理解 (1-2 lines)
  2. 取数与画像执行情况 (which tools ran, key counts)
  3. 关键发现 (3-5 bullets, evidence-backed)
  4. 风险与不确定性 (data gaps, model fallbacks)
  5. 推荐下一步 (concrete analyst actions)
- Use plain Chinese; do not use emoji.

# Hard Boundaries

- Never invent UIDs that did not come from a tool call.
- Never generate SQL outside query_data. Never execute SQL directly.
- If the user asks for something outside the tool set (e.g. "send me an email"),
  refuse politely and suggest a tool-supported alternative.
- If a tool returns an error, surface it and ask the user how to proceed
  rather than retrying blindly more than 3 times.
- If the per-session token budget warning fires (80%), warn the user and
  suggest summarizing or ending the session.
- If the per-session token budget hard limit fires (100%), the system will
  end the session automatically; tell the user clearly.

# Output Protocol (the runtime parses this — follow exactly)

Respond with a single JSON object on each round:

```json
{
  "tool_call": {"name": "<tool_name>", "arguments": {<schema-conforming kwargs>}}
}
```

OR (when you have all needed information):

```json
{
  "final_message": "<5-section markdown>",
  "confidence": <float 0.0-1.0>
}
```

Never produce both keys in the same response.
````

**新建文件**：`app/services/orchestrator_agent/system_prompt.py`

```python
"""Orchestrator Agent System Prompt v1 loader + country skill assembly."""

from __future__ import annotations

from app.core.config import settings


def get_system_prompt_v1() -> str:
    """Read the canonical System Prompt v1 from disk."""
    path = (
        settings.project_root
        / "app" / "prompts" / "orchestrator_system_prompt_v1.md"
    )
    if not path.exists():
        raise FileNotFoundError(
            f"System Prompt v1 missing: {path}. "
            "Plan #03 Phase 1 Task 1.7 落地的文件被误删，请从 git 历史恢复。"
        )
    return path.read_text(encoding="utf-8")


def assemble_system_prompt(country: str | None = None) -> str:
    """Assemble base prompt + country skill (lazy injection)."""
    base = get_system_prompt_v1()
    if country is None:
        return base
    from app.services.orchestrator_agent.skills_loader import load_skill
    skill_md = load_skill(country)
    return f"{base}\n\n## 国别规则（自动注入：{country}）\n\n{skill_md}"
```

**验证命令**：

```powershell
python -c "from app.services.orchestrator_agent.system_prompt import assemble_system_prompt; p = assemble_system_prompt('mx'); print(len(p), '国别规则' in p, 'parse_uid_file' in p)"
# 期望：长度 ≥ 3500；True True
```

### Task 1.8 — 跑全部测试 → 事故预防清单 → 显式 add 清单 → 等“OK commit”

**操作步骤**（R6 P0-2 事故预防清单）：

```powershell
# 1) 跑 Phase 1 测试看 GREEN
python -m pytest tests/test_orchestrator_phase1.py -v

# 2) 跑全量回归（保证没把现有 282 + 163 测试搞坏）
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v

# 3) 事故预防清单（吸取 Plan #02 a94c776 教训）
git rev-parse HEAD                                # 确认 HEAD 真实位置
git fetch github
git log github/main..HEAD --oneline               # 期望：Phase 0 commit （1 行）
git log HEAD..github/main --oneline               # 期望为空
git status                                        # 检查工作树

# 4) 显式 add 清单（R9 P2-1：禁用整目录 add，显式列举 Phase 1 落地的所有文件，
#    与 Phase 2/3 add 清单互斥，防 Phase 1 实施期为调试预建的 Phase 2 文件被误带进 commit）
git add app/services/orchestrator_agent/__init__.py `
        app/services/orchestrator_agent/schemas.py `
        app/services/orchestrator_agent/session.py `
        app/services/orchestrator_agent/system_prompt.py `
        app/services/orchestrator_agent/skills_loader.py `
        app/services/orchestrator_agent/tools/__init__.py `
        app/services/orchestrator_agent/tools/parse_uid_file.py `
        app/services/orchestrator_agent/tools/run_profile.py `
        app/services/orchestrator_agent/tools/run_trace.py `
        app/services/orchestrator_agent/tools/query_data.py `
        app/services/orchestrator_agent/tools/memory.py `
        app/prompts/orchestrator_system_prompt_v1.md `
        docs/skills/orchestrator/th.md `
        docs/skills/orchestrator/mx.md `
        docs/skills/orchestrator/co.md `
        docs/skills/orchestrator/pe.md `
        docs/skills/orchestrator/cl.md `
        docs/skills/orchestrator/br.md `
        tests/conftest.py `
        tests/test_orchestrator_phase1.py
# R9 P1-1：如 Phase 0.5 Task 0.5.4/0.5.5 修了 Plan 文档，把它一并 add 进 Phase 1 commit
#         （仅当 git status 显示 docs/plans/03-orchestrator-agent-plan.md 有 modified 时执行）
git status -- docs/plans/03-orchestrator-agent-plan.md
git add docs/plans/03-orchestrator-agent-plan.md   # 没有 diff 则跳过此行
# R10 P1-1：如 Task 1.7 同步修了 Design Doc § 13 Task 编号（“Task 1.6”→“Task 1.7”），把它一并 add 进 Phase 1 commit
#         （仅当 git status 显示 docs/specs/03-orchestrator-agent-design.md 有 modified 时执行）
git status -- docs/specs/03-orchestrator-agent-design.md
git add docs/specs/03-orchestrator-agent-design.md   # 没有 diff 则跳过此行
git diff --cached --stat
git status
# 期望：staging 区包含 20 个文件（11 个 services 包 + 1 个 prompt + 6 个 skills + 1 个 conftest + 1 个 phase1 测试），
#       视 Phase 0.5 是否修过 Plan 决定额外 +1 个 docs/plans/ 文件
#       Changes not staged for commit 为空；Untracked 仅外部产物

# 5) 贴 diff stat + status 给用户对照，等“OK commit”才执行
git commit -m "feat(orchestrator): phase 1 — schemas + 6 tools + skills + system prompt v1 (TDD)"
# 如本 Phase 发现实施期 Plan 与现实差异（R6 P0-5），额外加 -m 段记录微调 N
# 如 Phase 0.5 修过 Plan，额外加 -m 段记录“Phase 0.5 实施期 Plan 文档微调：<差异列表>”（R9 P1-1）
git push origin main
git log -1 --oneline
```

**期望输出**：
- `tests/test_orchestrator_phase1.py` → 20 passed（R7 P0-3 新增 default_no_country_section 使 19→20）
- `tests/` → 309 passed（零回归）
- `data_acquisition_agent/tests/` → 163 passed (1 skipped)
- git diff 仅在 `app/services/orchestrator_agent/`、`app/prompts/orchestrator_system_prompt_v1.md`、`docs/skills/orchestrator/`、`tests/conftest.py`、`tests/test_orchestrator_phase1.py` 范围内；
  **可选范围 R10 P1-3**：仅当 Phase 0.5 修过 Plan 文档时，额外包含 `docs/plans/03-orchestrator-agent-plan.md`；
  **可选范围 R10 P1-1**：Task 1.7 同步修了 Design Doc § 13 Task 编号时，额外包含 `docs/specs/03-orchestrator-agent-design.md`（1 行文本修订，与 Task 4.4 的同名文件条件 add 互斥）

**验证命令**：
```powershell
git log -1 --oneline
# 期望：feat(orchestrator): phase 1 — schemas + 6 tools + skills + system prompt v1 (TDD)
```

---

## Phase 2 — Session 持久化 + Resilience + Token budget + UID 白名单（TDD RED→GREEN）

> **TDD 顺序**：Task 2.1 先写测试（RED），Task 2.2-2.4 实装（GREEN），Task 2.5 跑全量 + 展示 diff + commit。

### Task 2.1 — RED：Phase 2 契约测试（必失败）

**新建文件**：`tests/test_orchestrator_phase2.py`

**完整代码**：

```python
"""Phase 2 RED contract tests: session_store / resilience / budget / uid_whitelist."""

from __future__ import annotations

import threading
import time

import pytest

from app.services.orchestrator_agent.session_store import (
    create_session, get_session, save_session, flush,
)
from app.services.orchestrator_agent.budget import (
    check_and_increment, BudgetExceeded, DEFAULT_BUDGET,
)
from app.services.orchestrator_agent.uid_whitelist import validate_uid
from app.services.orchestrator_agent.resilience import (
    check_consecutive_failures, ConsecutiveFailures, CONSECUTIVE_FAILURE_LIMIT,
)


# ---- session_store ----

def test_session_create_and_load_round_trip(tmp_path, monkeypatch):
    sess = create_session()
    save_session(sess)
    flush()
    loaded = get_session(sess.session_id)
    assert loaded is not None
    assert loaded.session_id == sess.session_id


def test_get_session_returns_none_for_unknown():
    assert get_session("definitely-not-existing-xxx") is None


def test_session_round_trip_preserves_query_cancelled_and_consecutive():
    sess = create_session()
    sess.query_cancelled = True
    sess.consecutive_failures = 2
    save_session(sess)
    flush()
    loaded = get_session(sess.session_id)
    assert loaded.query_cancelled is True
    assert loaded.consecutive_failures == 2


# ---- budget ----

def test_budget_warning_at_80_percent():
    sess = create_session()
    out = check_and_increment(sess, int(DEFAULT_BUDGET * 0.85))
    assert out["warn"] is True
    assert out["percentage"] >= 0.8


def test_budget_below_80_no_warning():
    sess = create_session()
    out = check_and_increment(sess, int(DEFAULT_BUDGET * 0.5))
    assert out["warn"] is False


def test_budget_hard_stop_over_100_percent():
    sess = create_session()
    sess.total_tokens = 0
    with pytest.raises(BudgetExceeded):
        check_and_increment(sess, DEFAULT_BUDGET + 1)


# ---- uid_whitelist ----

def test_uid_whitelist_th_valid():
    assert validate_uid("TH000123", "th") is True


def test_uid_whitelist_th_too_short():
    assert validate_uid("TH0", "th") is False  # th 要求长度 8-32


def test_uid_whitelist_mx_valid():
    assert validate_uid("MX0001", "mx") is True


def test_uid_whitelist_unknown_country():
    assert validate_uid("U001", "us") is False


# ---- resilience: consecutive_failures ----

def test_consecutive_failures_resets_on_ok():
    sess = create_session()
    sess.consecutive_failures = 2
    check_consecutive_failures(sess, "ok")
    assert sess.consecutive_failures == 0


def test_consecutive_failures_increments_on_error():
    sess = create_session()
    sess.consecutive_failures = 0
    check_consecutive_failures(sess, "error")
    assert sess.consecutive_failures == 1


def test_consecutive_failures_raises_at_limit():
    sess = create_session()
    sess.consecutive_failures = CONSECUTIVE_FAILURE_LIMIT - 1
    with pytest.raises(ConsecutiveFailures):
        check_consecutive_failures(sess, "error")
```

**验证命令**：
```powershell
python -m pytest tests/test_orchestrator_phase2.py -v
```

**期望输出**：**全部 errors**（`ImportError: No module named 'app.services.orchestrator_agent.session_store'`）。

### Task 2.2 — GREEN：`session_store.py`（含 atexit + flush）

**新建文件**：`app/services/orchestrator_agent/session_store.py`

```python
"""JSON-based session store with atexit flush and resume support."""

from __future__ import annotations

import atexit
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.core.config import settings
from app.services.orchestrator_agent.schemas import OrchestratorSession


_LOCK = threading.Lock()
_DIRTY: set[str] = set()
_CACHE: dict[str, OrchestratorSession] = {}


def _sessions_dir() -> Path:
    p = settings.project_root / "outputs" / "orchestrator_sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def create_session() -> OrchestratorSession:
    sid = uuid.uuid4().hex
    now = datetime.now(timezone.utc)
    sess = OrchestratorSession(session_id=sid, created_at=now, updated_at=now)
    with _LOCK:
        _CACHE[sid] = sess
        _DIRTY.add(sid)
    return sess


def get_session(session_id: str) -> OrchestratorSession | None:
    with _LOCK:
        if session_id in _CACHE:
            return _CACHE[session_id]
    path = _sessions_dir() / f"{session_id}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    sess = OrchestratorSession.model_validate(data)
    with _LOCK:
        _CACHE[session_id] = sess
    return sess


def save_session(sess: OrchestratorSession) -> None:
    sess.updated_at = datetime.now(timezone.utc)
    with _LOCK:
        _CACHE[sess.session_id] = sess
        _DIRTY.add(sess.session_id)


def flush() -> None:
    with _LOCK:
        for sid in list(_DIRTY):
            sess = _CACHE.get(sid)
            if not sess:
                continue
            path = _sessions_dir() / f"{sid}.json"
            path.write_text(sess.model_dump_json(indent=2), encoding="utf-8")
        _DIRTY.clear()


atexit.register(flush)
```

**验证命令**：
```powershell
python -c "from app.services.orchestrator_agent.session_store import create_session, save_session, flush, get_session; s = create_session(); save_session(s); flush(); s2 = get_session(s.session_id); print(s.session_id == s2.session_id)"
# 期望：True
```

### Task 2.3 — GREEN：`resilience.py`（retry + consecutive_failures，移除 with_safe_default）

**新建文件**：`app/services/orchestrator_agent/resilience.py`

```python
"""Orchestrator Agent resilience: tenacity retry + consecutive failure tripwire.

Note: Plan #01 已在 Provider 层做 retry；本模块仅做 agent_loop 级别的
连续失败 tripwire。tenacity import 保留供未来 agent_loop 重试 LLM 决策时用。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 连续工具失败上限：达此值则强制结束 session
CONSECUTIVE_FAILURE_LIMIT = 3


class ConsecutiveFailures(Exception):
    """Raised when too many tool calls return error in a row."""


def check_consecutive_failures(session, tool_status: str) -> None:
    """Update session.consecutive_failures and raise if exceeds limit.

    Call this after every tool execution in agent_loop.
    - tool_status == 'ok'    → reset to 0
    - tool_status == 'error' → +1; raise ConsecutiveFailures at limit
    """
    if tool_status == "ok":
        session.consecutive_failures = 0
        return
    session.consecutive_failures = getattr(session, "consecutive_failures", 0) + 1
    if session.consecutive_failures >= CONSECUTIVE_FAILURE_LIMIT:
        raise ConsecutiveFailures(
            f"{CONSECUTIVE_FAILURE_LIMIT} consecutive tool failures; aborting session"
        )
```

**验证命令**：
```powershell
python -c "from app.services.orchestrator_agent.resilience import CONSECUTIVE_FAILURE_LIMIT, ConsecutiveFailures; print(CONSECUTIVE_FAILURE_LIMIT, ConsecutiveFailures.__name__)"
# 期望：3 ConsecutiveFailures
```

### Task 2.4 — GREEN：`budget.py` + `uid_whitelist.py`

**新建文件**：`app/services/orchestrator_agent/budget.py`

```python
"""Per-session token budget with 80% warning + 100% hard stop."""

from __future__ import annotations


DEFAULT_BUDGET = 500_000


class BudgetExceeded(Exception):
    pass


def check_and_increment(session, used_tokens: int, limit: int = DEFAULT_BUDGET) -> dict:
    """Add used_tokens to session.total_tokens; raise BudgetExceeded if over limit."""
    session.total_tokens += used_tokens
    pct = session.total_tokens / limit
    if pct >= 1.0:
        raise BudgetExceeded(
            f"Session {session.session_id} exceeded budget {limit}; total={session.total_tokens}"
        )
    return {
        "used": session.total_tokens,
        "limit": limit,
        "percentage": pct,
        "warn": pct >= 0.8,
    }
```

**新建文件**：`app/services/orchestrator_agent/uid_whitelist.py`

```python
"""UID format whitelist per country (业务正确性层；安全层在工具入口)."""

from __future__ import annotations

import re

# V1 占位规则；业务方确认后调整
_PATTERNS = {
    "th": re.compile(r"^[a-zA-Z0-9_-]{8,32}$"),
    "mx": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
    "co": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
    "pe": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
    "cl": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
    "br": re.compile(r"^[a-zA-Z0-9_-]{4,32}$"),
}


def validate_uid(uid: str, country: str) -> bool:
    pat = _PATTERNS.get(country)
    if pat is None:
        return False
    return bool(pat.match(uid))
```

**验证命令**：
```powershell
python -c "from app.services.orchestrator_agent.uid_whitelist import validate_uid; print(validate_uid('MX0001', 'mx'), validate_uid('TH0', 'th'), validate_uid('U001', 'us'))"
# 期望：True False False
```

### Task 2.5 — 跑全部测试 → 事故预防清单 → 显式 add 清单 → 等“OK commit”

**操作步骤**（R6 P0-2 事故预防清单）：

```powershell
# 1) Phase 2 GREEN
python -m pytest tests/test_orchestrator_phase2.py -v

# 2) Phase 1 + Phase 2 联合（确保 Phase 2 没破坏 Phase 1）
python -m pytest tests/test_orchestrator_phase1.py tests/test_orchestrator_phase2.py -v

# 3) 全量回归
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v

# 4) 事故预防清单（commit 前必跑，吸取 Plan #02 a94c776 / 多窗口并行 HEAD 异常事故教训）
git rev-parse HEAD                       # 确认 HEAD 真实位置
git fetch github
git log github/main..HEAD --oneline      # 期望仅 [baseline] + Phase 1 commit；本地不应领先于 remote 之外的内容
git log HEAD..github/main --oneline      # 期望为空；不为空 → git pull --ff-only github main
git status                               # 期望：仅 Phase 2 新增 5 个文件待 add；外部 modified/untracked 应保持不变

# 5) 显式 add 清单（禁用 git add -A）
git add app/services/orchestrator_agent/session_store.py `
        app/services/orchestrator_agent/resilience.py `
        app/services/orchestrator_agent/budget.py `
        app/services/orchestrator_agent/uid_whitelist.py `
        tests/test_orchestrator_phase2.py
git diff --cached --stat                 # 期望：恒为 5 个文件
git status                               # 期望：Changes to be committed 仅上述 5 个；Changes not staged 不含 Phase 2 文件；Untracked 仅外部产物

# 6) 贴 diff stat + status 给用户对照，等“OK commit”才执行
git commit -m "feat(orchestrator): phase 2 — session store + resilience + budget + uid whitelist (TDD)"
git push origin main
git log -1 --oneline
```

**实施期 Plan 文档微调追溯锚点**（R6 P0-5）：commit message 里如有任何 Plan #03 与现实不一致的地方（字段名 / 行号 / 测试数）→ 在 commit body 加一段 `实施期 Plan 文档微调 N: <描述>，待 [complete] 后 R7 同步`。

**期望输出**：
- `tests/test_orchestrator_phase2.py` → 13 passed
- 全量 `tests/` → 322 passed，零回归
- `data_acquisition_agent/tests/` → 163 passed (1 skipped)
- `git log github/main..HEAD --oneline` 末态为空（push 后本地与 remote 同步）

---

## Phase 3 — SSE Agent Loop + ACK 时序 + 路由（拆 4 子 Task；TDD RED→GREEN）

> **拆分理由**：原 R4 Task 3.1 单 Task 含 agent_loop + ack_bus + routes + main.py 注册，远超方法论 2-5 分钟单 Task 边界。R5 拆为 4 个子 Task，每个 Task 独立可验证。**4 个子 Task 共用 1 个 Phase 3 commit**（不增加 commit 数）。

### Task 3.1 — RED：Phase 3 契约测试（必失败）

**新建文件**：`tests/test_orchestrator_phase3.py`

```python
"""Phase 3 RED contract tests: ack_bus + agent_loop main loop + ACK branch + routes."""

from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest


# ---- ack_bus ----

def test_ack_bus_resolve_returns_value():
    from app.services.orchestrator_agent.ack_bus import (
        open_ack, resolve_ack, wait_ack,
    )
    sid = "phase3-ack-1"
    ev = open_ack(sid)
    # 在另一个线程 resolve
    def resolver():
        time.sleep(0.05)
        resolve_ack(sid, True)
    t = threading.Thread(target=resolver)
    t.start()
    result = wait_ack(sid, timeout_sec=2.0)
    t.join()
    assert result is True


def test_ack_bus_timeout_returns_none():
    from app.services.orchestrator_agent.ack_bus import open_ack, wait_ack
    sid = "phase3-ack-timeout"
    open_ack(sid)
    result = wait_ack(sid, timeout_sec=0.1)
    assert result is None


def test_ack_bus_unknown_session_resolve_returns_false():
    from app.services.orchestrator_agent.ack_bus import resolve_ack
    assert resolve_ack("definitely-not-opened", True) is False


# ---- agent_loop main loop (mock LLM) ----

# R8 P0-A：用 asyncio.run 同步驱动 async generator，不依赖 pytest-asyncio
# （requirements.txt 未含 pytest-asyncio，与 Task 4.2 Golden runner 风格一致）。
def test_agent_loop_mock_run_trace_completes(monkeypatch):
    """Mock LLM 返回 run_trace tool_call → 然后 final → 验证 SSE 事件序列。"""
    import asyncio

    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session

    # Patch ModelClient.generate_structured 返回 deterministic decisions
    decisions = iter([
        {"status": "ok", "structured_result": {
            "tool_call": {"name": "run_trace", "arguments": {"uid": "MX0001", "days": 7}},
        }},
        {"status": "ok", "structured_result": {
            "final_message": "## 用户请求理解\n查 MX0001 轨迹\n", "confidence": 0.7,
        }},
    ])
    class _FakeClient:
        last_token_usage = {"prompt": 100, "completion": 50, "total": 150}
        def generate_structured(self, **kwargs):
            return next(decisions)
    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _FakeClient(),
    )
    # Patch run_trace 直接返回固定值，避免依赖 trace_analyzer 真实数据
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_trace.run_trace",
        lambda inp: type("X", (), {
            "model_dump": lambda self, mode="json": {"events": [], "summary": {}},
        })(),
    )

    sess = create_session()

    async def _drive():
        events = []
        async for evt in run_agent_loop(session=sess, prompt="看 MX0001 轨迹"):
            events.append(evt)
        return events

    events = asyncio.run(_drive())

    types = [e.get("type") for e in events]
    assert "session_started" in types
    assert "tool_started" in types
    assert "tool_completed" in types
    assert "final" in types


# ---- FastAPI routes ----

def test_orchestrator_chat_route_returns_sse(monkeypatch):
    monkeypatch.setenv("MODEL_MODE", "mock")
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    with client.stream(
        "POST", "/api/orchestrator/chat",
        json={"prompt": "你好"},
    ) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")


def test_get_session_returns_404_for_unknown():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.get("/api/orchestrator/sessions/definitely-not-existing")
    assert r.status_code == 404


def test_ack_route_unresolved_returns_false():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.post(
        "/api/orchestrator/sessions/never-opened/ack",
        json={"confirm": True},
    )
    assert r.status_code == 200
    assert r.json() == {"resolved": False}
```

**验证命令**（R8 P0-A：本 Plan **不依赖 pytest-asyncio**，async generator 用 `asyncio.run()` 同步驱动）：
```powershell
python -m pytest tests/test_orchestrator_phase3.py -v
```

**期望输出**：**全部 errors**（`ImportError: No module named 'app.services.orchestrator_agent.ack_bus'` / `'agent_loop'`）。

### Task 3.2 — GREEN：`ack_bus.py`（最小实装）

**新建文件**：`app/services/orchestrator_agent/ack_bus.py`

```python
"""Per-session ACK rendezvous via threading.Event."""

from __future__ import annotations

import threading
from typing import Optional

_LOCK = threading.Lock()
_PENDING: dict[str, dict] = {}


def open_ack(session_id: str) -> threading.Event:
    """Register a session as awaiting ACK."""
    ev = threading.Event()
    with _LOCK:
        _PENDING[session_id] = {"event": ev, "result": None}
    return ev


def resolve_ack(session_id: str, confirm: bool) -> bool:
    """SSE handler calls this when user POST /sessions/{id}/ack."""
    with _LOCK:
        slot = _PENDING.get(session_id)
    if slot is None:
        return False
    slot["result"] = confirm
    slot["event"].set()
    return True


def wait_ack(session_id: str, timeout_sec: float = 600.0) -> Optional[bool]:
    """Block until resolve_ack or timeout. Returns confirm value or None on timeout."""
    with _LOCK:
        slot = _PENDING.get(session_id)
    if slot is None:
        return None
    slot["event"].wait(timeout=timeout_sec)
    with _LOCK:
        result = _PENDING.pop(session_id, {}).get("result")
    return result
```

**验证命令**：
```powershell
python -m pytest tests/test_orchestrator_phase3.py::test_ack_bus_resolve_returns_value tests/test_orchestrator_phase3.py::test_ack_bus_timeout_returns_none tests/test_orchestrator_phase3.py::test_ack_bus_unknown_session_resolve_returns_false -v
# 期望：3 passed
```

### Task 3.3 — GREEN：`agent_loop.py` 主循环（不含 ACK 分支）

**新建文件**：`app/services/orchestrator_agent/agent_loop.py`

```python
"""Agent Loop: drive LLM ↔ tools ↔ session for one user prompt.

Phase 3 Task 3.3 — 主循环（含工具 dispatch + budget + consecutive_failures），
**query_data 走普通工具路径**（无 ACK 时序）。

Phase 3 Task 3.4 在本文件追加 ACK 分支特殊处理，工具中 query_data 单独拆开。
"""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator

from app.core.model_client import ModelClient
from app.services.orchestrator_agent.budget import (
    BudgetExceeded, check_and_increment,
)
from app.services.orchestrator_agent.resilience import (
    ConsecutiveFailures, check_consecutive_failures,
)
from app.services.orchestrator_agent.schemas import (
    OrchestratorMessage, OrchestratorSession, ToolCallRecord,
)
from app.services.orchestrator_agent.session_store import save_session
from app.services.orchestrator_agent.system_prompt import assemble_system_prompt
from app.services.orchestrator_agent.tools import get_tool_registry


MAX_ROUNDS = 15

# R7 P0-3 Knowledge 层注入：在首轮 LLM call 前用 keyword regex 从 prompt 中提取 country code，
# 传给 assemble_system_prompt(country) 动态拼接对应 docs/skills/orchestrator/{country}.md。
# V1 只走名字/短码粗粒度匹配，匹不到 → country=None → base prompt 不含国别规则段（LLM 需问用户）。
# R9 P0-1：使用中文字面量而非 unicode escape，避免 \u5893 (墓) 与 \u58a8 (墨) 视觉混淆造成的隐蔽 bug。
_COUNTRY_RE = re.compile(
    r"\b(th|mx|co|pe|cl|br)\b|墨西哥|泰国|哥伦比亚|秘鲁|智利|巴西|"
    r"thailand|mexico|colombia|peru|chile|brazil",
    re.IGNORECASE,
)
_NAME_TO_CODE = {
    "墨西哥": "mx", "mexico": "mx",
    "泰国": "th", "thailand": "th",
    "哥伦比亚": "co", "colombia": "co",
    "秘鲁": "pe", "peru": "pe",
    "智利": "cl", "chile": "cl",
    "巴西": "br", "brazil": "br",
}


def _detect_country(prompt: str) -> str | None:
    """V1 粗粒度提取：keyword + 2-位短码 regex。匹不到返回 None。"""
    m = _COUNTRY_RE.search(prompt)
    if not m:
        return None
    raw = m.group(0).lower()
    return raw if len(raw) == 2 else _NAME_TO_CODE.get(raw)


def _input_schema_for(tool_name: str):
    from app.services.orchestrator_agent import schemas as S
    return {
        "parse_uid_file": S.ParseUidFileInput,
        "run_profile": S.RunProfileInput,
        "run_trace": S.RunTraceInput,
        "query_data": S.QueryDataInput,
        "memory_write": S.MemoryWriteInput,
        "memory_read": S.MemoryReadInput,
    }[tool_name]


def _build_llm_input(system_prompt: str, messages: list) -> str:
    parts = [system_prompt, "\n\n--- 对话历史 ---\n"]
    for m in messages:
        parts.append(f"[{m.role}] {m.content}\n")
    parts.append("\n--- 请输出下一步决策 JSON ---\n")
    return "".join(parts)


async def run_agent_loop(
    session: OrchestratorSession,
    prompt: str,
) -> AsyncGenerator[dict, None]:
    yield {"type": "session_started", "session_id": session.session_id}

    session.messages.append(OrchestratorMessage(
        role="user", content=prompt, timestamp=datetime.now(timezone.utc),
    ))
    save_session(session)

    client = ModelClient()
    tool_registry = get_tool_registry()
    # R7 P0-3 Knowledge 层注入：从 prompt 提取 country code，动态拼接国别规则段。
    # 匹不到 → country=None → base prompt 不含国别规则，LLM 需问用户。
    detected_country = _detect_country(prompt)
    system_prompt = assemble_system_prompt(detected_country)

    for round_idx in range(MAX_ROUNDS):
        # 1) LLM 决策（同步 generate_structured 用 to_thread 包装）
        llm_input = _build_llm_input(system_prompt, session.messages)
        try:
            llm_out = await asyncio.to_thread(
                client.generate_structured,
                skill_name="orchestrator_agent",
                prompt=llm_input,
                fallback_result={
                    "final_message": "AI 服务暂时不可用，请稍后重试",
                    "tool_call": None,
                    "confidence": 0.0,
                },
                route_key="orchestrator_agent.decide",
            )
        except Exception as exc:
            yield {"type": "error", "message": str(exc)}
            session.status = "error"
            save_session(session)
            return

        # 2) Budget 累加（last_token_usage 来自 Plan #01 R5 契约）
        try:
            usage = getattr(client, "last_token_usage", {}) or {}
            budget = check_and_increment(session, int(usage.get("total", 0)))
        except BudgetExceeded as exc:
            yield {"type": "error", "message": str(exc)}
            session.status = "budget_exceeded"
            save_session(session)
            return
        if budget["warn"]:
            yield {"type": "budget_warning", **budget}

        decision = llm_out.get("structured_result", {}) or {}

        # 3) Final?
        if decision.get("final_message"):
            session.final_message = decision["final_message"]
            session.confidence = decision.get("confidence")
            session.status = "completed"
            save_session(session)
            yield {
                "type": "final",
                "final_message": decision["final_message"],
                "total_rounds": round_idx + 1,
                "total_tokens": session.total_tokens,
                "confidence": session.confidence or 0.0,
            }
            return

        # 4) Tool call
        tool_call = decision.get("tool_call")
        if not tool_call:
            yield {"type": "error", "message": "LLM did not produce final or tool_call"}
            session.status = "error"
            save_session(session)
            return

        tool_name = tool_call["name"]
        tool_input = tool_call["arguments"]
        tool_call_id = uuid.uuid4().hex

        record = ToolCallRecord(
            tool_name=tool_name, tool_call_id=tool_call_id,
            input=tool_input, status="running",
            started_at=datetime.now(timezone.utc),
        )
        session.tool_calls.append(record)
        save_session(session)
        yield {
            "type": "tool_started",
            "tool_call_id": tool_call_id,
            "tool_name": tool_name,
            "input": tool_input,
        }

        # 5) Execute tool
        # Phase 3 Task 3.3 主循环：query_data 走普通工具路径（与其它工具一致）；
        # Phase 3 Task 3.4 把 query_data 拆出 ACK 分支特殊路径。
        try:
            tool_fn = tool_registry[tool_name]
            schema_cls = _input_schema_for(tool_name)
            input_obj = schema_cls(**tool_input)
            output_obj = await asyncio.to_thread(tool_fn, input_obj)
            output = output_obj.model_dump(mode="json")
            record.output = output
            record.status = "done"
            record.finished_at = datetime.now(timezone.utc)
            save_session(session)
            yield {
                "type": "tool_completed",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "output": output,
                "status": "ok",
            }
        except Exception as exc:
            record.status = "error"
            record.output = {"error": str(exc)}
            record.finished_at = datetime.now(timezone.utc)
            save_session(session)
            yield {
                "type": "tool_completed",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "output": {"error": str(exc)},
                "status": "error",
            }

        # 6) Consecutive failure tripwire
        try:
            check_consecutive_failures(session, record.status)
        except ConsecutiveFailures as exc:
            yield {"type": "consecutive_tool_failures", "message": str(exc)}
            session.status = "error"
            save_session(session)
            return

        # 7) Append tool result for next round
        session.messages.append(OrchestratorMessage(
            role="tool", tool_call_id=tool_call_id,
            content=json.dumps(record.output, ensure_ascii=False),
            timestamp=datetime.now(timezone.utc),
        ))
        save_session(session)

    # MAX_ROUNDS reached without final
    yield {"type": "error", "message": f"Max rounds {MAX_ROUNDS} reached"}
    session.status = "error"
    save_session(session)
```

**验证命令**：
```powershell
python -m pytest tests/test_orchestrator_phase3.py::test_agent_loop_mock_run_trace_completes -v
# 期望：1 passed
```

### Task 3.4 — GREEN：`agent_loop.py` ACK 分支接入 query_data

**修改文件**：`app/services/orchestrator_agent/agent_loop.py`

**替换范围 anchor**（R9 P2-3 显式标定）：把 Task 3.3 中从 `        # 5) Execute tool` 起、到该 try/except 整个块结束（即包含整个 `try: ... except Exception as exc: ... yield {"type": "tool_completed", ...}` 直到 `# 6) Consecutive failure tripwire` 这一行**之前**的全部代码）替换为下面的 query_data ACK 分支版本：

```python
        # 5) Execute tool
        # query_data 走 ACK 时序分支（Step A: generate → Step B: yield awaiting → 
        # Step C: wait_ack → Step D: execute）；其它工具走普通路径。
        try:
            if tool_name == "query_data":
                # ⚠️ R7 P0-4：以下 3 个 function-local import **必须保持在函数体内**，
                # 不能上提到 module top。原因：Task 4.2 Golden runner 用
                # `monkeypatch.setattr(ack_bus, "open_ack", _patched_open_ack)` 自动放行 ACK，
                # 该 patch 生效依赖于函数运行时才从 module 重新取 open_ack。
                # 一旦上提到 module top → monkeypatch 失效 → case_05 卡 600s 超时。
                from app.services.orchestrator_agent.tools.query_data import _ChildAgent
                from app.services.orchestrator_agent.ack_bus import open_ack, wait_ack
                from app.services.orchestrator_agent.session import (
                    is_query_cancelled, mark_query_cancelled,
                )

                # 同 session 内之前 ACK 拒绝过 → 直接拒，不进 generate
                if is_query_cancelled(session.session_id):
                    raise PermissionError("user cancelled in this session")

                child = _ChildAgent(country=tool_input["country"])

                # Step A: 同步阻塞操作放 to_thread（generate SQL）
                qr = await asyncio.to_thread(child.run_query, tool_input["request"])

                # Step B: 显式 yield awaiting_user_ack（非阻塞，立即 flush 给前端）
                yield {
                    "type": "awaiting_user_ack",
                    "tool_call_id": tool_call_id,
                    "sql_text": qr.sql_text,
                    "rows_estimated": qr.rows_estimated,
                }

                # Step C: 等 ACK（threading.Event 用 to_thread 包，不卡 event loop）
                open_ack(session.session_id)
                confirm = await asyncio.to_thread(wait_ack, session.session_id, 600.0)
                if not confirm:
                    mark_query_cancelled(session.session_id)
                    raise PermissionError("User rejected SQL execution")

                # Step D: ACK 通过 → 执行
                execute_out = await asyncio.to_thread(child.execute, qr.sql_text)
                output = {
                    "uids": execute_out["uids"],
                    "rows_actual": execute_out["rows_actual"],
                    "sql_text": qr.sql_text,
                    "rows_estimated": qr.rows_estimated,
                }
            else:
                tool_fn = tool_registry[tool_name]
                schema_cls = _input_schema_for(tool_name)
                input_obj = schema_cls(**tool_input)
                output_obj = await asyncio.to_thread(tool_fn, input_obj)
                output = output_obj.model_dump(mode="json")

            record.output = output
            record.status = "done"
            record.finished_at = datetime.now(timezone.utc)
            save_session(session)
            yield {
                "type": "tool_completed",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "output": output,
                "status": "ok",
            }
        except Exception as exc:
            record.status = "error"
            record.output = {"error": str(exc)}
            record.finished_at = datetime.now(timezone.utc)
            save_session(session)
            yield {
                "type": "tool_completed",
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
                "output": {"error": str(exc)},
                "status": "error",
            }
```

**验证命令**：
```powershell
# Task 3.3 的测试仍然通过（query_data 不在 mock decision 里，分支不被触发）
python -m pytest tests/test_orchestrator_phase3.py::test_agent_loop_mock_run_trace_completes -v
# 期望：1 passed
```

### Task 3.5 — GREEN：FastAPI routes + main.py 注册

**新建文件**：`app/api/orchestrator_routes.py`

```python
"""Orchestrator Agent FastAPI routes (SSE chat + session GET + ACK)."""

from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.orchestrator_agent.ack_bus import resolve_ack
from app.services.orchestrator_agent.agent_loop import run_agent_loop
from app.services.orchestrator_agent.schemas import OrchestratorChatRequest
from app.services.orchestrator_agent.session_store import (
    create_session, get_session,
)


router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])


@router.post("/chat")
async def chat_endpoint(req: OrchestratorChatRequest) -> StreamingResponse:
    if req.session_id:
        sess = get_session(req.session_id)
        if sess is None:
            raise HTTPException(404, f"Session {req.session_id} not found")
    else:
        sess = create_session()

    async def event_stream() -> AsyncGenerator[bytes, None]:
        async for evt in run_agent_loop(session=sess, prompt=req.prompt):
            yield f"data: {json.dumps(evt, ensure_ascii=False)}\n\n".encode("utf-8")
        yield b'data: {"type": "done"}\n\n'

    return StreamingResponse(event_stream(), media_type="text/event-stream")


class _AckBody(BaseModel):
    confirm: bool


@router.post("/sessions/{session_id}/ack")
async def ack_endpoint(session_id: str, body: _AckBody) -> dict:
    ok = resolve_ack(session_id, body.confirm)
    return {"resolved": ok}


@router.get("/sessions/{session_id}")
async def get_session_endpoint(session_id: str) -> dict:
    sess = get_session(session_id)
    if sess is None:
        raise HTTPException(404, f"Session {session_id} not found")
    return sess.model_dump(mode="json")
```

**修改文件**：`app/main.py`

> ⏸ 实施前先 read_file 确认 `app/main.py` 现有 `app.include_router` 调用风格；按现有风格在最后一个 `include_router` 之后追加。

在文件末尾或现有 `app.include_router` 区块追加：

```python
# Orchestrator Agent SSE chat (Plan #03)
from app.api.orchestrator_routes import router as orchestrator_router

app.include_router(orchestrator_router)
```

### Task 3.6 — 跑全部测试 → 事故预防清单 → 显式 add 清单 → 等“OK commit”

**操作步骤**（R6 P0-2 事故预防清单）：

```powershell
# 1) Phase 3 GREEN
python -m pytest tests/test_orchestrator_phase3.py -v

# 2) 全量回归
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v

# 3) 事故预防清单
git rev-parse HEAD
git fetch github
git log github/main..HEAD --oneline      # 期望：[baseline] + Phase 1 + Phase 2 commit
git log HEAD..github/main --oneline      # 期望为空；不为空 → git pull --ff-only github main
git status

# 4) 显式 add 清单（禁用 git add -A；agent_loop / ack_bus / routes / main.py / 测试 共 5 个）
# 注意：app/main.py 是 R6 P0-3 跨 Plan 契约保护范围内的“追加 include_router 块”——
#       本 Task add app/main.py 时允许加 ≤5 行（注释 + import + include_router 调用，R7 P0-5），
#       不允许动 startup 钩子或其它现有逻辑。
git add app/services/orchestrator_agent/agent_loop.py `
        app/services/orchestrator_agent/ack_bus.py `
        app/api/orchestrator_routes.py `
        app/main.py `
        tests/test_orchestrator_phase3.py
git diff --cached --stat                 # 期望：恒为 5 个文件，且 app/main.py 行 diff ≤5 行
git status                               # 期望：staged 仅 5 个；外部 modified/untracked 不动

# 5) 贴 diff stat + status 给用户对照，等“OK commit”才执行
git commit -m "feat(orchestrator): phase 3 — agent loop + ACK + SSE routes (TDD)"
git push origin main
git log -1 --oneline
```

**实施期 Plan 文档微调追溯锚点**（R6 P0-5）：commit message 里记录实施期 Plan 与现实差异，待 [complete] 后 R7 同步。

**期望输出**：
- `tests/test_orchestrator_phase3.py` → 7 passed（R7 P0-1 修正：3 ack_bus + 1 agent_loop + 3 routes）
- 全量 `tests/` → 329 passed
- `data_acquisition_agent/tests/` → 163 passed (1 skipped)
- `git log github/main..HEAD --oneline` 末态为空（push 后同步）

---

## Phase 4 — Golden Test Closeout（5 case 真跑通 + System Prompt 调优 + `[complete]`）

> Phase 4 把 Plan #03 的核心验收（Golden Test）落到能跑通的状态。**不再 `pytest.skip`**——用 mock LLM 注入 deterministic decision + mock Judge 返回 `verdict=pass`，验证完整链路。System Prompt v1 调优最多 3 轮，每轮跑分对比。

### Task 4.1 — Golden Cases fixture + Rubric + Judge prompt（直接落盘内容）

**新建目录**：`tests/golden/`

#### `tests/golden/case_01_loyal_th_user.json`

```json
{
  "case_id": "case_01_loyal_th_user",
  "prompt": "看下 UID TH000123 最近 7 天的行为轨迹，是忠诚用户吗？",
  "country": "th",
  "seed_uids": ["TH000123"],
  "expected_tools": ["run_trace"],
  "expected_final_topics": [
    "近 7 天活跃天数",
    "下单频次",
    "上次访问距今多久",
    "忠诚度结论"
  ],
  "expected_min_confidence": 0.6,
  "expected_ack_required": false
}
```

#### `tests/golden/case_02_churn_mx_batch.json`

```json
{
  "case_id": "case_02_churn_mx_batch",
  "prompt": "请批量分析 ./data/id_files/mx/sample.txt 里的用户，看哪些已经流失。",
  "country": "mx",
  "seed_uids": ["MX0001", "MX0002", "MX0003"],
  "expected_tools": ["parse_uid_file", "run_profile"],
  "expected_final_topics": [
    "流失判定标准（30 天无下单）",
    "流失用户名单",
    "可能原因分类"
  ],
  "expected_min_confidence": 0.6,
  "expected_ack_required": false
}
```

#### `tests/golden/case_03_credit_co_batch.json`

```json
{
  "case_id": "case_03_credit_co_batch",
  "prompt": "./data/id_files/co/sample.txt 里的哪些用户征信表现不佳？给出原因。",
  "country": "co",
  "seed_uids": ["CO_USR_001", "CO_USR_002"],
  "expected_tools": ["parse_uid_file", "run_profile"],
  "expected_final_topics": [
    "逐个 UID 征信评分",
    "负面信号（逾期 / 多头借贷）",
    "详细证据引用具体字段名"
  ],
  "expected_min_confidence": 0.55,
  "expected_ack_required": false
}
```

#### `tests/golden/case_04_trace_th_user.json`

```json
{
  "case_id": "case_04_trace_th_user",
  "prompt": "请分析 UID TH000456 近 30 天的轨迹，看是否有异常跳变。",
  "country": "th",
  "seed_uids": ["TH000456"],
  "expected_tools": ["run_trace"],
  "expected_final_topics": [
    "30 天轨迹主线",
    "异常跳变检测结果",
    "跳变上下文（后续是否恢复、是否重复发生）"
  ],
  "expected_min_confidence": 0.6,
  "expected_ack_required": false
}
```

#### `tests/golden/case_05_query_data_mx.json`

```json
{
  "case_id": "case_05_query_data_mx",
  "prompt": "帮我拉一批墨西哥上周流失且下单过的用户，然后逐个跑 App 画像。",
  "country": "mx",
  "seed_uids": [],
  "expected_tools": ["query_data", "run_profile"],
  "expected_ack_required": true,
  "expected_final_topics": [
    "SQL 逻辑详解（上周流失定义 + 下单过滤条件）",
    "拉出的 UID 数量 + 示例",
    "这批用户 App 画像聚合结论",
    "下一步建议"
  ],
  "expected_min_confidence": 0.55
}
```

> **注意**：原 R4 case_05 用 country="th"，但 V1 thailand 不可用（`query_data` reject）。R5 改为 country="mx" 走真实链。
>
> **R6 P1-2 补注 ACK auto-resolve hack**：本 case 走完整 ACK gate，Task 4.2 runner 里用 `monkeypatch.setattr("...ack_bus.open_ack", lambda *a, **kw: “auto-resolved”)` 路过 SSE 中间的人工点击步骤。这个 hack 仅限于 Golden Test（CI 表示“如果人拍ACK 会发生什么”）；V1 生产路径 `orchestrator_routes.py::ack` 仍必须走真实人工 ACK，monkeypatch 不出现在生产代码里。Plan #04 前端实现后验收最后一步。

#### `tests/golden/rubric.md`

```markdown
# Orchestrator Golden Test Rubric

按 Design Doc § 8.2 4 维 Rubric（每维 1-5 分，单条总分 4-20）。

## 4 维度

1. **工具选择准确性**（tool_selection）：选对工具 = 5；选错主工具 = 1
2. **工具顺序合理性**（tool_order）：query_data 先于 run_profile = 5；颠倒 = 1
3. **参数提取准确性**（param_extract）：country / app_time / uid 提取正确 = 5；缺失 = 2
4. **无幻觉**（no_hallucination）：不调不存在的工具 / 不编造 UID = 5；调不存在工具 = 1

## 通过线

- 单条 ≥ 16/20（每维 ≥ 4 分） → pass
- 12-15 → review
- ≤ 11 → fail

## Judge 选型

- Judge 模型：Claude Opus 4.7（10x tier，独立 Provider 实例）
- Judge prompt 模板：`tests/golden/judge_prompt.md`
- 5-10 次手工对齐校准（Design Doc § 8.5）：偏差 > 1 分 → 调措辞，重跑；偏差 < 1 分才信任 LLM Judge 自动跑
- **Phase 4 V1 用 mock Judge 跑通 runner，5-10 次手工对齐校准放在 Plan #03 [complete] 后单独迭代**
```

#### `tests/golden/judge_prompt.md`

```markdown
# Orchestrator Golden Judge Prompt

你是一个评测 Agent。给定一个 Orchestrator Agent 的会话日志，按照 4 维 Rubric 打分。

## 输入

- prompt: {{prompt}}
- expected_tools: {{expected_tools}}
- expected_final_topics: {{expected_final_topics}}
- agent_session_log: {{agent_session_log}}

## 输出 JSON

```json
{
  "scores": {
    "tool_selection": <0-5>,
    "tool_order": <0-5>,
    "param_extract": <0-5>,
    "no_hallucination": <0-5>
  },
  "total": <0-20>,
  "verdict": "pass" | "review" | "fail",
  "rationale": "<分项理由 + 主要扣分点>"
}
```
```

### Task 4.2 — Golden Test runner（mock LLM + mock Judge，**真跑通**）

**新建文件**：`tests/test_orchestrator_golden.py`

```python
"""Golden Test runner: drive run_agent_loop with deterministic mock LLM,
collect session log, feed to mock Judge, assert verdict == 'pass'.

V1 用 mock LLM + mock Judge 验证 runner 链路真跑通（不依赖真实 LLM 配额）。
Plan #03 [complete] 后再做 5-10 次手工对齐校准（独立迭代，非本 Plan）。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


GOLDEN_DIR = Path(__file__).parent / "golden"


def _build_mock_decisions(case: dict) -> list[dict]:
    """根据 case.expected_tools 拼出 deterministic LLM decision 序列。

    每个工具一轮 tool_call decision，最后一轮 final decision。
    """
    decisions = []
    for tool in case["expected_tools"]:
        if tool == "parse_uid_file":
            args = {"file_path": f"data/id_files/{case['country']}/sample.txt"}
        elif tool == "run_profile":
            args = {
                "uids": case["seed_uids"] or ["MOCK_UID"],
                "app_time": "2026-04-30",
                "modules": ["app"],
            }
        elif tool == "run_trace":
            args = {"uid": case["seed_uids"][0], "days": 7}
        elif tool == "query_data":
            args = {"request": case["prompt"], "country": case["country"]}
        else:
            args = {}
        decisions.append({
            "status": "ok",
            "structured_result": {
                "tool_call": {"name": tool, "arguments": args},
            },
        })
    # Final
    final_md = "\n".join(f"## {t}\n占位\n" for t in case["expected_final_topics"])
    decisions.append({
        "status": "ok",
        "structured_result": {
            "final_message": final_md,
            "confidence": 0.7,
        },
    })
    return decisions


def _mock_judge(case: dict, session_log: list) -> dict:
    """Mock Judge：检查工具序列与 case.expected_tools 一致 → verdict=pass。

    R7 P1-3 KNOWN LIMITATIONS（V1 mock Judge 范围明示）：
    - 仅检查工具名序列严格匹配 expected_tools
    - 不验证 tool 入参（country / app_time / uid 提取准确性）
    - 不验证 final_message 是否覆盖 expected_final_topics
    - 不检测幻觉（如 LLM 反返伪造不存在的 UID）
    - mock=pass 不等于“真实 LLM Judge=pass”

    真实 LLM Judge 5-10 次手工对齐校准 → Plan #03 [complete] 后独立迭代
    （见 “Plan #03 [complete] 后的延伸工作” §2）。
    """
    actual_tools = [
        e["tool_name"] for e in session_log
        if e.get("type") == "tool_started"
    ]
    if actual_tools == case["expected_tools"]:
        return {
            "scores": {
                "tool_selection": 5,
                "tool_order": 5,
                "param_extract": 5,
                "no_hallucination": 5,
            },
            "total": 20,
            "verdict": "pass",
            "rationale": "mock Judge: tool sequence matches exactly",
        }
    return {
        "scores": {"tool_selection": 1, "tool_order": 1, "param_extract": 1, "no_hallucination": 1},
        "total": 4,
        "verdict": "fail",
        "rationale": f"actual={actual_tools} expected={case['expected_tools']}",
    }


@pytest.mark.parametrize("case_path", sorted(GOLDEN_DIR.glob("case_*.json")))
def test_golden_case(case_path, monkeypatch):
    case = json.loads(case_path.read_text(encoding="utf-8"))

    # 跳过 V1 不支持的国别（country in co/pe/cl/br + tool 含 query_data）
    if "query_data" in case["expected_tools"] and case["country"] in {"co", "pe", "cl", "br", "th"}:
        pytest.skip(f"V1 query_data only supports mexico; case country={case['country']}")

    decisions = iter(_build_mock_decisions(case))

    class _FakeClient:
        last_token_usage = {"prompt": 100, "completion": 50, "total": 150}
        def generate_structured(self, **kwargs):
            return next(decisions)

    monkeypatch.setattr(
        "app.services.orchestrator_agent.agent_loop.ModelClient",
        lambda: _FakeClient(),
    )

    # Mock 各工具：返回固定结构，避免真实数据依赖
    def _mk_output(tool_name):
        if tool_name == "parse_uid_file":
            return type("X", (), {"model_dump": lambda self, mode="json": {
                "uids": case.get("seed_uids", []), "source_path": "mock", "duplicates_removed": 0,
            }})()
        if tool_name == "run_profile":
            return type("X", (), {"model_dump": lambda self, mode="json": {
                "results": [], "cache_hits": 0, "cache_misses": 0,
            }})()
        if tool_name == "run_trace":
            return type("X", (), {"model_dump": lambda self, mode="json": {
                "events": [], "summary": {},
            }})()
        return type("X", (), {"model_dump": lambda self, mode="json": {}})()

    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.parse_uid_file.parse_uid_file",
        lambda inp: _mk_output("parse_uid_file"),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_profile.run_profile",
        lambda inp: _mk_output("run_profile"),
    )
    monkeypatch.setattr(
        "app.services.orchestrator_agent.tools.run_trace.run_trace",
        lambda inp: _mk_output("run_trace"),
    )

    # query_data ACK 分支：mock _ChildAgent + auto-resolve ACK
    if "query_data" in case["expected_tools"]:
        from unittest.mock import MagicMock
        mock_qr = MagicMock()
        mock_qr.sql_text = "SELECT uid FROM users LIMIT 10"
        mock_qr.rows_estimated = 10

        class _MockChild:
            def __init__(self, country): pass
            def run_query(self, req): return mock_qr
            def execute(self, sql): return {"uids": ["MOCK_UID"], "rows_actual": 1}
        monkeypatch.setattr(
            "app.services.orchestrator_agent.tools.query_data._ChildAgent",
            _MockChild,
        )

        # auto-resolve ACK
        import threading
        from app.services.orchestrator_agent.ack_bus import resolve_ack
        def _auto_ack():
            import time as _t
            _t.sleep(0.1)
            resolve_ack(_session_id_holder["sid"], True)
        _session_id_holder = {"sid": None}

        original_open_ack = None
        from app.services.orchestrator_agent import ack_bus
        original_open_ack = ack_bus.open_ack
        def _patched_open_ack(sid):
            _session_id_holder["sid"] = sid
            ev = original_open_ack(sid)
            threading.Thread(target=_auto_ack, daemon=True).start()
            return ev
        monkeypatch.setattr(ack_bus, "open_ack", _patched_open_ack)

    # Drive agent loop
    from app.services.orchestrator_agent.agent_loop import run_agent_loop
    from app.services.orchestrator_agent.session_store import create_session
    sess = create_session()

    async def _drive():
        events = []
        async for evt in run_agent_loop(session=sess, prompt=case["prompt"]):
            events.append(evt)
        return events

    events = asyncio.run(_drive())

    # Feed to mock Judge
    verdict_obj = _mock_judge(case, events)
    assert verdict_obj["verdict"] == "pass", (
        f"Golden case {case['case_id']} failed: {verdict_obj['rationale']}"
    )
```

**验证命令**：
```powershell
python -m pytest tests/test_orchestrator_golden.py -v
# 期望：5 cases；3 passed + 2 skipped（th case_01/case_04 跳过；mx case_02/case_05 通过；co case_03 跳过）
# 实际：case_01 (th run_trace) 不含 query_data → 不跳，验证通过
#       case_03 (co parse+run_profile) 不含 query_data → 不跳，验证通过
#       case_05 (mx query_data) 真走 ACK 链 → 通过
#       全部 5 passed
```

> **R5 修订**：上面注释里的"3 passed + 2 skipped"先按 case 内容核算——case_01 (th, run_trace 不含 query_data) → 不 skip 通过；case_03 (co, parse+run_profile 不含 query_data) → 不 skip 通过；case_04 (th, run_trace 不含 query_data) → 不 skip 通过；最终 **5 passed, 0 skipped**。

### Task 4.3 — System Prompt v1 调优（最多 3 轮）

**操作步骤**：

```powershell
# 1) 跑一次 Golden Test 拿 baseline
python -m pytest tests/test_orchestrator_golden.py -v --tb=short

# 2) 看每个 case 的 verdict + rationale
#    - 如果 verdict=pass：跳过本 Task
#    - 如果有 case fail/review：分析 rationale 找 System Prompt 缺哪类指令

# 3) 改 app/prompts/orchestrator_system_prompt_v1.md（**Plan 内允许改这个文件**，
#    但必须同步更新 docs/specs/03-orchestrator-agent-design.md 附录 A）
#    建议关注点：
#    - tool_selection 低分 → 在 "Decision Rules" 加更明确的工具选用规则
#    - tool_order 低分 → 加 "query_data must precede run_profile in cohort flows"
#    - param_extract 低分 → 在 "Output Protocol" 加示例 JSON
#    - no_hallucination 低分 → 加 "If unsure, ask the user; never invent UIDs"

# 4) 重跑 Golden Test 看跑分变化
python -m pytest tests/test_orchestrator_golden.py -v

# 5) 最多 3 轮，仍不通过则记入 docs/reviews/orchestrator-prompt-tuning.md，
#    Plan #03 仍可 [complete]，但 Phase 4 commit message 注明 "tuning incomplete"
```

**完成判据**：
- 全部 5 case verdict=pass，或者
- 已跑 3 轮调优仍有 case 不 pass，记录到 `docs/reviews/orchestrator-prompt-tuning.md`

### Task 4.4 — 全量回归 → 事故预防清单 → 显式 add 清单 → 等“OK commit” `[complete]`

**操作步骤**（R6 P0-2 事故预防清单）：

```powershell
# 1) 全量回归
python -m pytest tests/ -v
python -m pytest data_acquisition_agent/tests/ -v

# 2) 事故预防清单
git rev-parse HEAD
git fetch github
git log github/main..HEAD --oneline      # 期望：[baseline] + Phase 1 + Phase 2 + Phase 3 commit
git log HEAD..github/main --oneline      # 期望为空；不为空 → git pull --ff-only github main
git status                               # 期望：仅 Phase 4 新增 + Task 4.3 调优过的文件待 add

# 3) 显式 add 清单（禁用 git add -A）
#    - tests/golden/ 整目录
#    - tests/test_orchestrator_golden.py
#    - app/prompts/orchestrator_system_prompt_v1.md
#    - docs/specs/03-orchestrator-agent-design.md（仅当 Task 4.3 调优后改了 design doc 才 add；
#      注：§ 13 Task 编号修订已在 Phase 1 Task 1.8 commit 完成，此处 add 仅针对 Task 4.3 的 prompt 调优改动）
git add tests/golden/ `
        tests/test_orchestrator_golden.py `
        app/prompts/orchestrator_system_prompt_v1.md
# 仅在 Task 4.3 调优后 design doc 有 diff 才 add（§ 13 修订不走这里，走 Phase 1）：
git status -- docs/specs/03-orchestrator-agent-design.md
git add docs/specs/03-orchestrator-agent-design.md   # 没有 diff 则跳过此行
git diff --cached --stat                 # 期望：3-4 个文件 / 目录
git status                               # 期望：staged 仅上述清单；外部 modified/untracked 不动

# 4) R9 P1-2 + R10 P0：System Prompt v1 vs Design Doc 附录 A 字面一致性自动验证
#    （commit 前必跑，保证完成标志的“一字不差”可执行）
#    R10 P0 修正：Design Doc 实际用中文 “## 附录 A”（见 docs/specs/03-orchestrator-agent-design.md:663），
#    不是英文 “## Appendix A”，下面 IndexOf 同时识别两种写法。
$prompt = Get-Content -Raw app/prompts/orchestrator_system_prompt_v1.md
$design = Get-Content -Raw docs/specs/03-orchestrator-agent-design.md
# 提取 Design Doc 的附录 A 段（约定：## 附录 A 或 ## Appendix A 起，到下一个 "\n## " 标题止）
$appAStart = $design.IndexOf('## 附录 A')
if ($appAStart -lt 0) { $appAStart = $design.IndexOf('## Appendix A') }
if ($appAStart -lt 0) { Write-Error "Design Doc 缺 附录 A / Appendix A 段"; exit 1 }
$appATail = $design.Substring($appAStart)
$nextHeader = $appATail.IndexOf("`n## ", 5)
$appA = if ($nextHeader -gt 0) { $appATail.Substring(0, $nextHeader) } else { $appATail }
# 跳过附录 A 的标题行 + 空行，对齐 system_prompt_v1.md 文件内容
$appABody = ($appA -split "`n", 2)[1].Trim()
if ($appABody -ne $prompt.Trim()) {
    Write-Error "System Prompt v1 与 Design Doc 附录 A 漂移：完成标志声明的‘一字不差’未达成"
    Write-Output "--- diff hint (first 200 chars of each) ---"
    Write-Output "prompt v1   : $($prompt.Trim().Substring(0, [Math]::Min(200, $prompt.Trim().Length)))"
    Write-Output "appendix A  : $($appABody.Substring(0, [Math]::Min(200, $appABody.Length)))"
    exit 1
}
Write-Output "✅ 附录 A vs system_prompt_v1.md: byte-identical (R9 P1-2 / R10 P0)"

# 5) 贴 diff stat + status 给用户对照，等“OK commit”才执行
git commit -m "feat(orchestrator): phase 4 — golden test runner + 5 cases + system prompt v1 tuned [complete] orchestrator-agent"
git push origin main
git log -1 --oneline
```

**实施期 Plan 文档微调追溯锚点**（R6 P0-5）：本 Plan 全部 [complete] 后，把 Phase 1/2/3/4 commit message 里所有“实施期 Plan 文档微调 N”条目汇总，做一次 R10 同步修订 commit（不计入 6-commit 上限，类似 Plan #02 R9 5affae4）。

**期望输出**：
- `tests/test_orchestrator_golden.py` → 5 passed
- 全量 `tests/` → 334 passed，零回归
- `data_acquisition_agent/tests/` → 163 passed (1 skipped)
- 最后一个 commit message 含 `[complete] orchestrator-agent`

**验证命令**：
```powershell
git log --oneline | Select-String "complete.*orchestrator-agent"
# 期望：找到 1 行 [complete] orchestrator-agent
git log github/main..HEAD --oneline
# 期望为空（push 后本地与 remote 同步）
```

---

## 完成标志

- **6 个 commit**（R7 P0-2 修正）：`[baseline] orchestrator-agent` + Maestro Spike wire-up + Phase 1 + Phase 2 + Phase 3 + Phase 4 `[complete]`
- Phase 0 Maestro Spike 通过（或按 C-1 逃生路径降级到 Gemini MVP）
- Phase 1 RED→GREEN 闭环：6 工具 + schemas + 6 国 skills/*.md + System Prompt v1 全部嵌入 Plan 落盘，20 测试 passed（R7 P0-3 加 default_no_country_section 使 19→20）
- Phase 2 RED→GREEN 闭环：session_store + resilience + budget + uid_whitelist，13 测试 passed
- Phase 3 RED→GREEN 闭环：ack_bus + agent_loop（含 ACK 分支）+ 3 个 SSE 路由，7 测试 passed（R7 P0-1）3
- Phase 4 RED→GREEN 闭环：5 Golden Cases + Rubric.md + Judge prompt + 真跑通的 runner（mock LLM + mock Judge），5 测试 passed
- System Prompt v1 完整版本入 `app/prompts/orchestrator_system_prompt_v1.md`，与 Design Doc 附录 A 一字不差
- 所有 Phase 末尾的 commit 都先 `git diff` 展示，等用户确认再 commit
- `data_acquisition_agent/` 下任何文件零修改，163 测试基线零回归
- Plan #03 内**没有**任何 `pytest.skip` 作为最终验收手段（Golden runner 真跑通）
- 6 国 V1 边界明确：mexico 走真，thailand stub，其它 4 国 reject

## Plan #03 [complete] 后的延伸工作（不计入 6-commit 预算）

1. **Plan #2.5（独立 Plan）**：扩展 `data_acquisition_agent` TargetCountry 加 `colombia/peru/chile/brazil` 4 国 + manifest yaml + tests。完成后无需改本 Plan 代码（`_ChildAgent._COUNTRY_MAP` 加 4 行映射即可）。
2. **System Prompt 真实 LLM 校准（独立 Plan）**：用真实 Claude Opus 4.7 跑 5 个 Golden Cases，与 mock Judge 输出对齐校准 5-10 次，把人工打分 vs LLM Judge 打分偏差降到 ≤ 1 分。校准产出更新到 `tests/golden/rubric.md`。
3. **白盒审计**：用 `ai-code-review` skill 基于 baseline `[baseline] orchestrator-agent` 到 HEAD 做 git diff 审计，产出 `docs/reviews/orchestrator-agent-audit.md`。
4. **模块技术总结**：用 `module-dev-summary` skill 生成 `docs/reviews/orchestrator-agent-summary.md`（面试导向）。




