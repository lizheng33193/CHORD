# P0 诊断报告（2026-05-01）

## P0-1：编码乱码

### 现象
LLM 输出中文变成乱码（ï¿½ / ??? / replacement characters），影响所有中文叙述质量。

### 根因
`app/core/model_client.py` 第 208/262 行用 `str(response.text)` 提取 LLM 响应文本。
若 google-genai SDK 某些版本下 `response.text` 返回的是 `bytes` 或 protobuf 标量，`str()` 会产生 `b'\\xe4...'` 字面量而非正确的 UTF-8 解码。

### 修复方案（精确到文件+行号）
1. `app/core/model_client.py:208` 和 `:262`：
   ```python
   raw = response.text
   if isinstance(raw, bytes):
       raw = raw.decode("utf-8")
   else:
       raw = str(raw)
   ```
2. `app/core/model_client.py:286-288`（`_extract_text_from_candidates` 中的 `part.text`）：同样处理。
3. 验证方法：在 :209 前临时 `logger.debug("response.text type=%s repr=%s", type(response.text), repr(str(response.text)[:80]))`，跑一次真 LLM 看日志。

---

## P0-2：behavior_timeline_summary Unterminated string

### 现象
每次 behavior_profile 分析都触发：
```
WARNING: Retry LLM call skill=behavior_timeline_summary due_to=json_parse: Unterminated string
WARNING: Model unavailable for skill=behavior_timeline_summary: json_parse: Unterminated string
```

### 根因
1. LLM 输出超 `max_output_tokens`，被中途截断 → JSON 不完整 → `Unterminated string`
2. 重试时 `model_client.py:160-164` 把 `max_output_tokens` **压更小**（`min(settings.model_max_output_tokens, 8192)`），截断复发
3. timeline schema（`explainer.py:193-210`）对子结构无约束（`{"type":"object"}` 无 `properties`），模型自由展开导致输出膨胀

### 修复方案
1. `app/core/model_client.py:160-164`：重试时**不压小** `max_output_tokens`，保持原值或调高
2. 为 timeline 链单独配置更大输出上限（timeline 是 long-form 叙述，需要更多 token）
3. `explainer.py:193-210`：收紧 timeline schema，给 `timeline_narrative` 加 `properties` + `required`，限制模型输出结构
4. 检查 `timeline_input` 是否传入了完整事件流；若是，应使用压缩字段减少 input token 占用

---

## P0-3：churn_root_cause 字段穿透

### 现象
prompt 当前没产 6 种枚举值的 `churn_root_cause` 字段。Golden Test coverage 为 0。

### 根因
prompt / response_schema / explainer 三处对 `churn_root_cause` 的**位置约定不一致**：
- **Prompt**（behavior_profile_prompt.md L111）：要求写入**嵌套** `evidence.llm_behavior_profile` 内
- **Response schema**（explainer.py:170-191）：在**顶层**声明了 `churn_root_cause`
- **Explainer 解析**（explainer.py:78）：只读**顶层** `payload["churn_root_cause"]`

LLM 可能写到嵌套位置（按 prompt 指引），但 explainer 只读顶层 → 读不到 → 回退 `["no_clear_signal"]`。

### 修复清单（5 条）
1. `behavior_profile_prompt.md:25-29`：在顶层字段清单加入 `churn_root_cause`
2. `behavior_profile_prompt.md:77-88`：在 `evidence.llm_behavior_profile` 结构清单中显式列出 `churn_root_cause`
3. `behavior_profile_prompt.md:109-123`：改为"顶层 churn_root_cause **必填**，evidence 内可选镜像"
4. `explainer.py:78-83`：扩展回退路径——顶层缺失时，尝试从 `evidence.llm_profile.churn_root_cause` 读取
5. `explainer.py:170-191` schema：把 `churn_root_cause` 加入 `required`，`items` 改为 `enum` 列表

---

## 优先级建议

| 顺序 | 任务 | 理由 |
|---|---|---|
| 1 | **P0-3 churn_root_cause** | 最简单（改 prompt + 3 行 explainer），1h 可完成 |
| 2 | **P0-2 timeline 截断** | 改重试逻辑 + 收紧 schema，1-2h |
| 3 | **P0-1 编码乱码** | 需要加调试日志跑真 LLM 验证根因，2h |
