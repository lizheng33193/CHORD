"""test_prompt_assembler — Step 4 TDD."""

import pytest
from data_acquisition_agent.prompt_assembler import estimate_tokens


def test_english_close_to_quarter_chars():
    assert 3 <= estimate_tokens("hello world hello world") <= 8


def test_chinese_weight_higher_than_english():
    en = estimate_tokens("a" * 100)
    zh = estimate_tokens("中" * 100)
    assert zh > en


def test_empty_zero():
    assert estimate_tokens("") == 0


from data_acquisition_agent.prompt_assembler import assemble_prompt, TOKEN_LIMIT
from data_acquisition_agent.manifest import load_manifest
from data_acquisition_agent.schemas import GenerateRequest
from app.data_knowledge.prompt_context import AssembledPromptContext


def test_assemble_mexico_includes_all_5_files():
    m = load_manifest("mexico")
    req = GenerateRequest(natural_language_request="建表 mob1 取 100 uid", target_country="mexico")
    prompt, tokens, files, redaction_hits = assemble_prompt(req, m)
    # Plan 07 Phase 4：router 按需选 md，always_inject (system_prompt + scheme + few)
    # 必到，business_logic / all_examples 视关键词命中 + 24K md-only budget 而定。
    assert len(files) >= 3
    assert any("system_prompt" in f for f in files), "system_prompt.md must always be selected"
    assert tokens > 0
    assert "建表 mob1 取 100 uid" in prompt
    assert isinstance(redaction_hits, int)


def test_assemble_redacts_synthetic_credentials(tmp_path):
    """构造含合成凭据的临时知识库 → 断 prompt 不含原文 + redaction_hits >= 2"""
    from data_acquisition_agent.manifest import CountryManifest
    def _w(name, body):
        p = tmp_path / name; p.write_text(body, encoding="utf-8"); return p
    sp = _w("sp.md", "ROLE")
    bl = _w("bl.md", "host='198.51.100.10'\npassword='FAKE_PASSWORD_XYZ'")
    ex = _w("ex.md", "examples")
    sc = _w("sc.md", "schema")
    fw = _w("fw.md", "few")
    m = CountryManifest(country="mexico", display_name="MX",
                        business_logic_md=bl, all_examples_md=ex, schema_md=sc,
                        few_md=fw, system_prompt_md=sp, sql_dialect="starrocks",
                        analyst_private_prefix="dm_model.yyp_tmp_")
    req = GenerateRequest(natural_language_request="x", target_country="mexico")
    prompt, _, _, hits = assemble_prompt(req, m)
    assert "198.51.100.10" not in prompt
    assert "FAKE_PASSWORD_XYZ" not in prompt
    assert hits >= 2


def test_assemble_raises_when_over_limit(monkeypatch):
    m = load_manifest("mexico")
    req = GenerateRequest(natural_language_request="x", target_country="mexico")
    monkeypatch.setattr("data_acquisition_agent.prompt_assembler.TOKEN_LIMIT", 10)
    with pytest.raises(ValueError, match="prompt_too_large"):
        assemble_prompt(req, m)


def test_assemble_injects_analyst_private_prefix():
    m = load_manifest("mexico")
    req = GenerateRequest(natural_language_request="x", target_country="mexico")
    prompt, _, _, _ = assemble_prompt(req, m)
    assert m.analyst_private_prefix in prompt
    assert "analyst private table prefix" in prompt.lower()
    assert "build_table_script DDL target MUST start with this exact prefix" in prompt


def test_assemble_includes_default_query_only_orientation():
    m = load_manifest("mexico")
    req = GenerateRequest(natural_language_request="x", target_country="mexico")
    prompt, _, _, _ = assemble_prompt(req, m)
    assert 'Default to sql_kind="query_only"' in prompt
    assert "explicitly asks to create, persist, save, materialize, or build a table" in prompt


def test_assemble_bans_python_db_clients():
    m = load_manifest("mexico")
    req = GenerateRequest(natural_language_request="x", target_country="mexico")
    prompt, _, _, _ = assemble_prompt(req, m)
    for banned in ("pymysql", "sqlalchemy", "mysql.connector", "starrocks connector"):
        assert banned in prompt
    assert "Do NOT generate Python code that connects to databases" in prompt


def test_assemble_includes_retrieved_context_when_provided():
    m = load_manifest("mexico")
    req = GenerateRequest(natural_language_request="查询首贷用户", target_country="mexico")
    retrieved = AssembledPromptContext(
        rendered_text="# === retrieved_glossary_terms ===\n- term=首贷; definition=首次成功放款用户",
        context_hash="ctx-hash",
        section_counts={"glossary_terms": 1},
        source_ids={"glossary_ids": [1]},
        trimmed=False,
    )
    prompt, _, _, _ = assemble_prompt(req, m, retrieved_context=retrieved)
    assert "# === retrieved_glossary_terms ===" in prompt
    assert "term=首贷" in prompt
