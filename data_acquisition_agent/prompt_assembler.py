"""Prompt assembly + token estimation. See Design Doc §6.2/§6.3."""

from __future__ import annotations

from pathlib import Path as _Path

from .manifest import CountryManifest
from .redactor import redact
from .schemas import GenerateRequest


def _label_for_path(path_str: str, manifest) -> str:
    """路径 → manifest 上对应语义 label 的反查。

    必须用 resolve().as_posix() 规一化两侧路径：manifest 字段是 REPO_ROOT/<rel>
    （绝对 Path + 反斜杠）；router 返回的 file 可能是 INDEX.md 中写的相对正斜杠 path。
    不规一化集合相减永远不为空（N-20 修复点）。
    """
    from data_acquisition_agent.manifest import REPO_ROOT

    p = _Path(path_str)
    if not p.is_absolute():
        p = REPO_ROOT / p
    norm = p.resolve().as_posix()
    label_attr = (
        ("system_prompt", "system_prompt_md"),
        ("business_logic", "business_logic_md"),
        ("all_examples", "all_examples_md"),
        ("schema", "schema_md"),
        ("few", "few_md"),
    )
    for label, attr in label_attr:
        if _Path(getattr(manifest, attr)).resolve().as_posix() == norm:
            return label
    return "extra"


TOKEN_LIMIT = 800_000


SYSTEM_PROMPT_ENGINE = """\
# === core_persona_and_directives ===
你是资深跨国数据架构师与 BI 引擎，是数据开发流水线上的"首席架构把控者"与"终极代码审计员"。
- 极度严谨：对数据准确性、表名、字段真实性有"病态"般的追求。绝不捏造任何不存在的字段，绝不假设未在知识库中出现的数据结构。
- 拒绝平庸：厌恶"一镜到底"的意大利面条式 SQL，必须使用 CTE（WITH...AS）构建清晰、模块化、可读性极强的流水线代码。
- 禁止自作聪明：严禁随意注释或省略条件。知识库或用户需求中指定的过滤渠道（如 user_source）必须在 WHERE 子句硬过滤，绝不允许注释掉或视为冗余。
- 三步走铁律：处理任何取数/建表请求时，必须严格、无条件地执行【前置专业思维链路】→【工业级代码生成】→【后置极其严谨的自检复查报告】这三大阶段，绝不允许跳过思考直接给代码。

# === four_knowledge_base_assets ===
你的大脑完全依赖以下四个核心文件，按定义的边界和顺序调用：
(1) 多国业务逻辑.md（业务语义层与黑话字典）：业务大脑，解决"我们要什么"。第一步必查黑话定义（mob1、eKYC 拦截、复借首贷等），挖掘隐藏的前置条件、时间截断窗口、特定业务线过滤逻辑。
(2) all_example.md（跨国全局最佳实践库）：全局经验池，解决"别人是怎么做的"。检索其他国家相似目标客群的代码，提取宏观 CTE 架构、多表 JOIN 逻辑和业务流转漏斗思路作为结构参考。严禁直接带入参考国家的表名/字段，必须保持"纯逻辑骨架"。
(3) schema.md（物理数据底座与字典约束）：物理基石，解决"底表到底长什么样"。绝对真理来源——核对目标国真实表名、分区键(dt)、时间字段名、UID 字段名（uid / user_uuid / individual_uuid）及类型，进行本地化字段替换。
(4) few.md（目标国原生验证代码与本地化 quirks）：目标国生存指南，解决"这个国家有什么特殊坑位"。重点观察其代码风格——参考代码怎么写就怎么写，没写的绝不允许自己加戏。捕捉目标国独有的"脏数据过滤逻辑"与"字段异化映射"。本地化字段替换时，本文件优先级高于一切。

# === three_phase_execution_engine ===
🟢 阶段一：生成代码前的专业思维链路 (Pre-Generation Chain of Thought)
此阶段不可输出正式代码，必须展示拆解、对比、迁移、排雷过程。
- Step 1.1 需求锚定：明确【目标国家】、【目标客群】、【最终动作】。
- Step 1.2 业务逻辑深度解析（via 多国业务逻辑.md）：剖析目标客群的全部隐式条件，逐条列出所有硬性业务规则，严禁脑补字典中不存在的逻辑。
- Step 1.3 跨国经验检索与逻辑迁移（via all_example.md）：寻找其他国家相同/相似业务的代码骨架，仅提取分步建表/多表 JOIN 的 CTE 漏斗模型与防爆抽样结构，保持纯逻辑骨架。
- Step 1.4 本地化映射与物理碰撞（via schema.md & few.md）：拿参考代码与目标国 schema/few 进行"碰撞"——目标国时间字段、渠道标识、时区处理、主键差异是什么？few 示例是否做了时区转换？做了就照做，没做就保持原样不要过度设计。明确列出即将使用的真实底表名与核心字段名。

🔵 阶段二：工业级代码生成 (Industrial Code Generation)
- 架构强制：复杂逻辑必须 CTE 分层剥离。
- 防 OOM 强制：严守 few.md 与 多国业务逻辑.md 的边界限制规范，时间边界/排序限制必须原样保留。
- 注释规范：清晰中文注释，解释每段 CTE 的业务意图与本地化特殊处理。

🔴 阶段三：极其严苛的后置交叉复查报告 (Post-Generation Audit Report)
扮演苛刻 Code Reviewer，将代码与四大知识库二次对齐，输出《审计复查报告》：
- 维度 A 物理层字段真实性自检：SELECT/WHERE/ON 每个关键字段是否在 schema.md 对应表中真实存在？JOIN 的 UID 键是否匹配？
- 维度 B 跨国迁移水土不服自检：是否遗漏 few.md 中目标国特有逻辑（渠道过滤等）？
- 维度 C 业务灵魂完整度自检：对照 多国业务逻辑.md，隐式黑话条件是否 100% 兑现？

# === mandatory_output_template ===
绝对遵守以下 Markdown 结构，不可缺少任何大标题：

🧠 阶段一：架构师专业思维链路 (Chain of Thought)
1. 需求基准锚定
   - 📍 目标国家：[填写]
   - 🎯 目标客群：[填写]
   - 🛠️ 交付动作：[建表 / 抽样取数 / 埋点拼接等]
2. 业务语义深度解析 (via 多国业务逻辑.md)
   - [详述：客群完整生命周期定义、时间窗口、截断规则等]
3. 跨国经验检索与宏观架构 (via all_example.md)
   - [详述：借鉴哪个国家的哪段代码？提取了怎样的 CTE 漏斗模型或表连接思路？]
4. 本地化物理映射与排雷 (via schema.md & few.md)
   - 🔍 目标国底表确认：[库名.表名]
   - 🔑 核心主键与字段映射：[参考国字段 A → 目标国字段 B]
   - ⚠️ 目标国特有暗坑预警：[时区、特殊包名、风控标识]

💻 阶段二：工业级代码交付 (Industrial Code Generation)
交付物 1：[如：客群圈选建表 SQL] —— 严谨 CTE + 详细中文注释
交付物 2：[如：抽样取数代码]

🕵️ 阶段三：终极交叉自检复查报告 (Audit & Review Report)
✅ A. 物理底座真实性核查 (Schema Audit)
   [ ] 表名核对 / [ ] 字段核对 —— 经查 schema.md，未捏造字段。
✅ B. 目标国本地化核查 (Localization Audit)
   [ ] 经查 few.md，目标国特有 [规则] 已在代码第 [X] 行强制执行。
✅ C. 业务黑话完整度核查 (Business Logic Audit)
   [ ] 经查 多国业务逻辑.md，[黑话术语] 所要求的前置/后置条件已在 [CTE 模块] 完全实现。
💡 架构师最终裁定与提示：[结论 / 注意事项]
"""


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    cjk = sum(1 for c in text if '一' <= c <= '鿿')
    other = len(text) - cjk
    return int(cjk * 1.5 + other / 4)


def assemble_prompt(request, manifest):
    """V2：用 router 选 md，再走原有 redact + TOKEN_LIMIT 流程。

    Zero Tolerance：
      - 每个 md 必须经过 redact()（hits 是 int，用 += hits 不要 += len(hits)）
      - SYSTEM_PROMPT_ENGINE 必须仅在 system_prompt md 紧后插入（不能提到顶部）
      - user_block 6 大段 byte-identical 保留
      - 末尾 raise ValueError(f"prompt_too_large: ...") 文案 byte-identical
      - 4-tuple 返回 (prompt, tokens, files, total_hits) 不变
    """
    from data_acquisition_agent.knowledge_base.router import route_knowledge
    from data_acquisition_agent.manifest import REPO_ROOT

    selected_paths = route_knowledge(
        query=request.natural_language_request,
        country=request.target_country.value,
        token_budget=int(TOKEN_LIMIT * 0.03),
    )

    sections = []
    files = []
    total_hits = 0

    # Bypass guard：当传入的 manifest 5 md 字段与 router 选出的真实路径无交集时（典型场景：
    # 测试用 tmp_path 构造合成 manifest），说明调用方已经显式指定了一组 md，应当尊重 manifest
    # 而不是 router 路由。这种情况下走原始 5-md 循环逻辑（不经 router）。
    manifest_md_set = {
        _Path(getattr(manifest, attr)).resolve().as_posix()
        for attr in (
            "system_prompt_md",
            "business_logic_md",
            "all_examples_md",
            "schema_md",
            "few_md",
        )
    }
    selected_norm = {
        (_Path(p) if _Path(p).is_absolute() else REPO_ROOT / p).resolve().as_posix()
        for p in selected_paths
    }
    use_router = bool(manifest_md_set & selected_norm)

    if not use_router:
        for label, p in [
            ("system_prompt", manifest.system_prompt_md),
            ("business_logic", manifest.business_logic_md),
            ("all_examples", manifest.all_examples_md),
            ("schema", manifest.schema_md),
            ("few", manifest.few_md),
        ]:
            raw = p.read_text(encoding="utf-8")
            red, hits = redact(raw)
            total_hits += hits
            sections.append(f"# === {label} ===\n{red}")
            if label == "system_prompt":
                sections.append(SYSTEM_PROMPT_ENGINE)
            files.append(str(p))
    else:
        has_system_prompt = any(
            _label_for_path(p, manifest) == "system_prompt"
            for p in selected_paths
            if _Path(p).exists()
        )
        if not has_system_prompt:
            raise RuntimeError(
                "router did not select system_prompt.md (always_inject contract broken). "
                "Check INDEX.md system_prompt entry has always_inject: true."
            )

        for path_str in selected_paths:
            p = _Path(path_str)
            if not p.is_absolute():
                p = REPO_ROOT / p
            if not p.exists():
                continue
            label = _label_for_path(path_str, manifest)
            raw = p.read_text(encoding="utf-8")
            red, hits = redact(raw)
            total_hits += hits
            sections.append(f"# === {label} ===\n{red}")
            if label == "system_prompt":
                sections.append(SYSTEM_PROMPT_ENGINE)
            files.append(path_str)
    user_block = (
        f"# === user_request ===\ncountry={request.target_country.value}\n"
        f"action={request.target_action.value if request.target_action else 'auto'}\n"
        f"request:\n{request.natural_language_request}\n\n"
        "Return ONLY a JSON object with EXACTLY these 5 top-level keys. ALL 5 keys MUST be present in every response — do NOT omit any key. Use null for unused string fields; use the default object for audit_report when no risk applies.\n"
        "\n"
        "Required keys (all 5 mandatory, no additions, no omissions):\n"
        "  - reasoning_summary: string (under 300 words; never null, use \"\" if empty)\n"
        "  - sql: string or null (use null if no SQL is produced)\n"
        "  - sql_kind: 'query_only' or 'build_table_script' (MUST be one of these two literals; do NOT use 'select_data', 'extract', etc. If sql is null, set sql_kind to 'query_only'.)\n"
        "  - python: string or null (REQUIRED key; if Python is not needed, set \"python\": null — do NOT omit this key)\n"
        "  - audit_report: object — REQUIRED key, MUST always be present. Shape: {\"high_risk_ddl\": bool, \"final_verdict\": string}. If no risk applies, use the default: {\"high_risk_ddl\": false, \"final_verdict\": \"\"}.\n"
        "\n"
        "audit_report.high_risk_ddl must be true iff sql_kind=='build_table_script'.\n"
        "\n"
        "Minimal valid skeleton (illustrative — your real values go here, but every key shown below MUST appear):\n"
        "  {\n"
        "    \"reasoning_summary\": \"<your summary>\",\n"
        "    \"sql\": \"<select ...>\",\n"
        "    \"sql_kind\": \"query_only\",\n"
        "    \"python\": null,\n"
        "    \"audit_report\": {\"high_risk_ddl\": false, \"final_verdict\": \"\"}\n"
        "  }"
        "\n\n# === task_orientation ===\n"
        "0. STRICT DEFAULT: sql_kind MUST be \"query_only\" UNLESS the user's request literally contains an explicit build/persist/materialize intent (e.g. \"create a table\", \"build a result table\", \"persist\", \"materialize\", \"save into a new table\", \"建表\", \"物化\", \"落表\"). If unsure, choose \"query_only\". Returning \"build_table_script\" without explicit intent will be rejected and the request will fail.\n"
        "1. Default to sql_kind=\"query_only\" and return a single SELECT statement.\n"
        "2. Use sql_kind=\"build_table_script\" ONLY when the user explicitly asks to create, persist, save, materialize, or build a table.\n"
        "3. Do NOT generate Python code that connects to databases.\n"
        "4. Do NOT use pymysql, sqlalchemy, mysql.connector, starrocks connector, or any DB client in python.\n"
        "5. If SQL alone is sufficient to answer the request, set python to null.\n"
        "\n# === analyst_private_prefix ===\n"
        f"The analyst private table prefix is: {manifest.analyst_private_prefix}\n"
        "Any build_table_script DDL target MUST start with this exact prefix.\n"
        f"Example target: {manifest.analyst_private_prefix}<short_task_name>\n"
        "\n# === json_format_rules ===\n"
        "1. Output MUST be a single valid JSON object on one line or with properly escaped newlines.\n"
        "2. All newlines inside string values (especially sql and reasoning_summary) MUST be escaped as \\n — raw newlines will break JSON parsing.\n"
        "3. All double quotes inside string values MUST be escaped as \\\".\n"
        "4. Keep reasoning_summary under 300 words.\n"
        "5. Do NOT wrap the JSON in markdown code fences.\n"
        "6. Example of correctly escaped SQL: \"sql\": \"SELECT uid\\nFROM dwb.t\\nWHERE channel='MEX017'\\nLIMIT 100\""
    )
    sections.append(user_block)
    prompt = "\n\n".join(sections)
    tokens = estimate_tokens(prompt)
    if tokens > TOKEN_LIMIT:
        raise ValueError(f"prompt_too_large: {tokens} > {TOKEN_LIMIT}")
    try:
        from data_acquisition_agent.knowledge_base.budget_monitor import log_token_usage

        log_token_usage(
            query=request.natural_language_request,
            country=request.target_country.value,
            prompt_tokens=tokens,
            files=files,
        )
    except Exception:
        pass
    return prompt, tokens, files, total_hits
