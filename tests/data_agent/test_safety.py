from app.data_agent.safety import run_sql_safety_gate


def test_safety_gate_blocks_angle_bracket_placeholders() -> None:
    result = run_sql_safety_gate(
        "SELECT uid FROM users WHERE uid IN (<target_users>)",
        "query_only",
        "mexico",
    )
    assert result["status"] == "blocked"
    assert any("target_users" in reason for reason in result["blocked_reasons"])


def test_safety_gate_blocks_brace_placeholders() -> None:
    result = run_sql_safety_gate(
        "SELECT uid FROM users WHERE dt >= '{{start_date}}' AND uid IN (${uid_list})",
        "query_only",
        "mexico",
    )
    assert result["status"] == "blocked"
    assert any("start_date" in reason or "uid_list" in reason for reason in result["blocked_reasons"])


def test_safety_gate_does_not_block_normal_comparisons() -> None:
    result = run_sql_safety_gate(
        "SELECT uid FROM users WHERE amount < 100 AND dt > '2026-01-01'",
        "query_only",
        "mexico",
    )
    assert result["status"] == "passed"
