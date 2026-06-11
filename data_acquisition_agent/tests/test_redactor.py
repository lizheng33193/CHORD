"""test_redactor — Step 4 TDD."""

import pytest
from data_acquisition_agent.redactor import redact

CASES = [
    ("host='192.0.2.10'", "<DB_HOST>", "ip"),
    ("port=3306", "<DB_PORT>", "port"),
    ("user='e_fake_user'", "<DB_USER>", "user"),
    ("password='FAKE_PASSWORD_REDACTED'", "<DB_PASSWORD>", "password"),
    ("database='dm_fake_db'", "<DB_NAME>", "db"),
    ("token='abc123XYZ_fake'", "<TOKEN>", "token"),
    ("api_key='sk-FAKE'", "<API_KEY>", "api_key"),
    ("access_token='FAKE_AT'", "<ACCESS_TOKEN>", "access_token"),
    ("secret='FAKE_SECRET'", "<SECRET>", "secret"),
    ("Authorization: Bearer FAKE_BEARER_TOKEN", "<BEARER_TOKEN>", "bearer"),
    ("key='FAKE_KEY_VALUE'", "<KEY>", "key"),
]


@pytest.mark.parametrize("raw,placeholder,label", CASES)
def test_redact_each_pattern(raw, placeholder, label):
    out, hits = redact(raw)
    assert placeholder in out, f"{label}: {out}"
    assert hits >= 1


def test_redact_does_not_touch_sql_select_field():
    out, hits = redact("SELECT e_id, e_phone FROM t")
    assert out == "SELECT e_id, e_phone FROM t"
    assert hits == 0


def test_redact_word_boundary_no_false_positive_report_eq_3306():
    out, hits = redact("report=3306 AND export=3306")
    assert "<DB_PORT>" not in out
    assert hits == 0


def test_redact_word_boundary_no_false_positive_user_uuid():
    out, hits = redact("SELECT user_uuid FROM t WHERE user_id=1")
    assert out == "SELECT user_uuid FROM t WHERE user_id=1"
    assert hits == 0


def test_redact_does_not_touch_english_prose_password_word():
    # 英文文档中提到 password 字段名但未赋值，不应误报
    out, hits = redact("the password field is required and must be at least 8 chars")
    assert hits == 0
    assert "<DB_PASSWORD>" not in out
