"""V1 follow-up: prompt_assembler must include a strong DDL guard so the
LLM defaults to query_only unless the user's NL request explicitly asks
to build/persist a table.
"""

from __future__ import annotations

from data_acquisition_agent.manifest import load_manifest
from data_acquisition_agent.prompt_assembler import assemble_prompt
from data_acquisition_agent.schemas import GenerateRequest


def test_prompt_contains_query_only_default_rule():
    manifest = load_manifest("mexico")
    req = GenerateRequest(
        natural_language_request="查询墨西哥最近 7 天活跃用户",
        target_country="mexico",
    )
    prompt, _, _, _ = assemble_prompt(req, manifest)
    # Must explicitly tell the model to default to query_only.
    assert "query_only" in prompt
    assert 'sql_kind="build_table_script"' in prompt or "build_table_script" in prompt
    # Strong DDL guard sentence must mention explicit user intent words.
    lowered = prompt.lower()
    assert "explicit" in lowered  # build_table_script ONLY when explicit
