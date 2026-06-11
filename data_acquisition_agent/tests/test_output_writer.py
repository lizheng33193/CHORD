import pandas as pd, pytest
from data_acquisition_agent.output_writer import (validate_bucket_schema,
    OutputWriterError, APP_BUCKET_REQUIRED_COLUMNS, resolve_actual_column)
from data_acquisition_agent.schemas import ErrorType

def _app_df():
    return pd.DataFrame([{c: "x" for c in APP_BUCKET_REQUIRED_COLUMNS}])

def test_app_bucket_passes_with_seven_columns():
    validate_bucket_schema(_app_df(), output_bucket="app",
        output_format="csv", uid_column="uid", request_id="rid")

def test_app_bucket_rejects_missing_column():
    df = _app_df().drop(columns=["app_name"])
    with pytest.raises(OutputWriterError) as ei:
        validate_bucket_schema(df, output_bucket="app",
            output_format="csv", uid_column="uid", request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

def test_app_bucket_rejects_json_format():
    with pytest.raises(OutputWriterError) as ei:
        validate_bucket_schema(_app_df(), output_bucket="app",
            output_format="json", uid_column="uid", request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

def test_uid_column_must_exist():
    df = pd.DataFrame([{"id": "x"}])
    with pytest.raises(OutputWriterError) as ei:
        validate_bucket_schema(df, output_bucket="behavior",
            output_format="json", uid_column="uid", request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

def test_behavior_bucket_minimal_passes():
    df = pd.DataFrame([{"uid": "u1", "eventTime": "2026-05-29T00:00:00Z", "eventName": "login"}])
    validate_bucket_schema(df, output_bucket="behavior",
        output_format="json", uid_column="uid", request_id="rid")

def test_behavior_bucket_rejects_uid_only_payload():
    df = pd.DataFrame([{"uid": "u1"}])
    with pytest.raises(OutputWriterError) as ei:
        validate_bucket_schema(df, output_bucket="behavior",
            output_format="json", uid_column="uid", request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

def test_behavior_bucket_rejects_blank_key_fields():
    df = pd.DataFrame([{"uid": "u1", "eventTime": "", "eventName": " "}])
    with pytest.raises(OutputWriterError) as ei:
        validate_bucket_schema(df, output_bucket="behavior",
            output_format="json", uid_column="uid", request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

def test_credit_bucket_accepts_raw_alias_payload():
    df = pd.DataFrame([{
        "user_uuid": "u1",
        "valor": "720",
        "nombrescore": "FICO",
        "consultas_detail_json": "[]",
        "creditos_detail_json": "[]",
    }])
    validate_bucket_schema(df, output_bucket="credit",
        output_format="csv", uid_column="user_uuid", request_id="rid")

def test_credit_bucket_accepts_legacy_summary_payload():
    df = pd.DataFrame([{
        "uid": "u1",
        "credit_score_band": "B",
        "repayment_status": "stable",
        "risk_level": "low",
    }])
    validate_bucket_schema(df, output_bucket="credit",
        output_format="csv", uid_column="uid", request_id="rid")

def test_credit_bucket_rejects_uid_only_payload():
    df = pd.DataFrame([{"uid": "u1"}])
    with pytest.raises(OutputWriterError) as ei:
        validate_bucket_schema(df, output_bucket="credit",
            output_format="csv", uid_column="uid", request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

def test_credit_bucket_rejects_weak_meta_only_payload():
    df = pd.DataFrame([{
        "user_uuid": "u1",
        "timestamp_": "1772369656095",
        "code": "0",
        "apply_risk_id": "AR-1",
    }])
    with pytest.raises(OutputWriterError) as ei:
        validate_bucket_schema(df, output_bucket="credit",
            output_format="csv", uid_column="user_uuid", request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED

def test_resolve_actual_column_accepts_normalized_alias():
    df = pd.DataFrame([{"userUuid": "u1", "valor": "720"}])
    assert resolve_actual_column(df, "user_uuid") == "userUuid"


import json
from data_acquisition_agent.output_writer import build_per_uid_payloads

def test_app_csv_payloads_grouped_by_uid():
    df = pd.DataFrame([
        {"uid":"u1","app_name":"WA","app_package":"p","first_install_time":"t",
         "last_update_time":"t","gp_category":"g","ai_category_level_2_CN":"c"},
        {"uid":"u1","app_name":"FB","app_package":"p","first_install_time":"t",
         "last_update_time":"t","gp_category":"g","ai_category_level_2_CN":"c"},
        {"uid":"u2","app_name":"TG","app_package":"p","first_install_time":"t",
         "last_update_time":"t","gp_category":"g","ai_category_level_2_CN":"c"},
    ])
    items = build_per_uid_payloads(df, output_bucket="app", output_format="csv",
        uid_column="uid", approved_by="t", source_request_id=None,
        executed_at="2026-04-29T00:00:00", request_id="rid")
    assert len(items) == 2
    uids = [u for u, _ in items]
    assert sorted(uids) == ["u1", "u2"]
    u1_payload = next(p for u, p in items if u == "u1")
    assert b"WA" in u1_payload and b"FB" in u1_payload
    assert u1_payload.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM

def test_behavior_json_wraps_schema_version():
    df = pd.DataFrame([{"uid": "u1", "x": 1}, {"uid": "u1", "x": 2}])
    items = build_per_uid_payloads(df, output_bucket="behavior",
        output_format="json", uid_column="uid", approved_by="alice",
        source_request_id="src-1", executed_at="2026-04-29T00:00:00",
        request_id="rid")
    assert len(items) == 1
    uid, payload = items[0]
    obj = json.loads(payload.decode("utf-8"))
    assert obj["schema_version"] == "da_agent_v2"
    assert obj["uid"] == "u1"
    assert obj["source_meta"]["approved_by"] == "alice"
    assert obj["source_meta"]["source_request_id"] == "src-1"
    assert obj["source_meta"]["row_count"] == 2
    assert len(obj["rows"]) == 2

def test_behavior_csv_payload_no_wrapper():
    df = pd.DataFrame([{"uid": "u1", "x": 1}])
    items = build_per_uid_payloads(df, output_bucket="behavior",
        output_format="csv", uid_column="uid", approved_by="t",
        source_request_id=None, executed_at="t", request_id="rid")
    uid, payload = items[0]
    assert b"schema_version" not in payload
    assert b"x" in payload

def test_build_per_uid_payloads_accepts_resolved_uid_alias():
    df = pd.DataFrame([{"userUuid": "u1", "x": 1}, {"userUuid": "u2", "x": 2}])
    actual_uid_column = resolve_actual_column(df, "user_uuid")
    items = build_per_uid_payloads(df, output_bucket="behavior",
        output_format="csv", uid_column=actual_uid_column, approved_by="t",
        source_request_id=None, executed_at="t", request_id="rid")
    assert [uid for uid, _ in items] == ["u1", "u2"]


from pathlib import Path
from data_acquisition_agent.output_writer import write_per_uid_atomic

def test_write_creates_files_in_bucket(tmp_path):
    bucket = tmp_path / "app_by_uid"; bucket.mkdir()
    items = [("u1", b"hello"), ("u2", b"world")]
    filenames = write_per_uid_atomic(items, bucket_dir=bucket,
        output_format="csv", overwrite=True, request_id="rid")
    assert sorted(filenames) == ["u1.csv", "u2.csv"]
    assert (bucket / "u1.csv").read_bytes() == b"hello"
    assert (bucket / "u2.csv").read_bytes() == b"world"
    assert not list(bucket.glob(".tmp_*"))

def test_write_overwrite_false_conflict_raises(tmp_path):
    bucket = tmp_path / "app_by_uid"; bucket.mkdir()
    (bucket / "u1.csv").write_bytes(b"old")
    with pytest.raises(OutputWriterError) as ei:
        write_per_uid_atomic([("u1", b"new")], bucket_dir=bucket,
            output_format="csv", overwrite=False, request_id="rid")
    assert ei.value.error_type == ErrorType.RESULT_VALIDATION_FAILED
    assert (bucket / "u1.csv").read_bytes() == b"old"
    assert not list(bucket.glob(".tmp_*"))

def test_write_overwrite_true_replaces(tmp_path):
    bucket = tmp_path / "app_by_uid"; bucket.mkdir()
    (bucket / "u1.csv").write_bytes(b"old")
    write_per_uid_atomic([("u1", b"new")], bucket_dir=bucket,
        output_format="csv", overwrite=True, request_id="rid")
    assert (bucket / "u1.csv").read_bytes() == b"new"

def test_write_rolls_back_tmp_on_failure(tmp_path, monkeypatch):
    bucket = tmp_path / "app_by_uid"; bucket.mkdir()
    from data_acquisition_agent import output_writer as ow
    orig_replace = ow.os.replace
    calls = {"n": 0}
    def boom(src, dst):
        calls["n"] += 1
        if calls["n"] == 2: raise OSError("disk full")
        orig_replace(src, dst)
    monkeypatch.setattr(ow.os, "replace", boom)
    with pytest.raises(OutputWriterError) as ei:
        write_per_uid_atomic([("u1", b"a"), ("u2", b"b")],
            bucket_dir=bucket, output_format="csv", overwrite=True,
            request_id="rid")
    assert ei.value.error_type == ErrorType.OUTPUT_WRITE_FAILED
    assert not list(bucket.glob(".tmp_*"))

def test_write_returns_filenames_only_no_path(tmp_path):
    bucket = tmp_path / "behavior_by_uid"; bucket.mkdir()
    filenames = write_per_uid_atomic([("u1", b"x")], bucket_dir=bucket,
        output_format="json", overwrite=True, request_id="rid")
    for fn in filenames:
        assert "/" not in fn and "\\" not in fn


import os

def test_resolve_bucket_dir_from_settings():
    from app.core.config import settings
    from data_acquisition_agent.output_writer import resolve_bucket_dir
    assert str(resolve_bucket_dir("app")).endswith(
        settings.app_by_uid_dir.replace("/", os.sep))
    assert str(resolve_bucket_dir("behavior")).endswith(
        settings.behavior_by_uid_dir.replace("/", os.sep))
    assert str(resolve_bucket_dir("credit")).endswith(
        settings.credit_by_uid_dir.replace("/", os.sep))
