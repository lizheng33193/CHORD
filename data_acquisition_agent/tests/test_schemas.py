"""test_schemas — Step 4 TDD."""

import pytest
from pydantic import ValidationError
from data_acquisition_agent.schemas import GenerateResponse, AuditReport, GenerateMetadata


def _meta():
    return GenerateMetadata(model="m", token_estimate=0, knowledge_files_loaded=[], redaction_events=0, danger_scan_events=0, generated_at="t")


def test_sql_and_python_both_empty_rejected():
    with pytest.raises(ValidationError):
        GenerateResponse(request_id="r", target_country="mexico", reasoning_summary="x", sql=None, python=None, audit_report=AuditReport(high_risk_ddl=False, final_verdict="ok"), metadata=_meta())


def test_error_response_round_trip():
    """ErrorResponse 必须有 error_type / message / request_id 三字段，可被 model_dump(mode='json') 序列化"""
    from data_acquisition_agent.schemas import ErrorResponse, ErrorType
    e = ErrorResponse(error_type=ErrorType.CREDENTIAL_LEAK, message="x", request_id="rid-1")
    d = e.model_dump(mode="json")
    assert d["error_type"] == "credential_leak"
    assert d["message"] == "x"
    assert d["request_id"] == "rid-1"


def test_build_table_script_requires_high_risk_ddl_true():
    with pytest.raises(ValidationError):
        GenerateResponse(request_id="r", target_country="mexico", reasoning_summary="x",
            sql="CREATE TABLE dm_model.yyp_tmp_x AS SELECT 1", sql_kind="build_table_script",
            python=None, audit_report=AuditReport(high_risk_ddl=False, final_verdict="ok"), metadata=_meta())


def test_query_only_with_high_risk_ddl_true_rejected():
    with pytest.raises(ValidationError):
        GenerateResponse(request_id="r", target_country="mexico", reasoning_summary="x",
            sql="SELECT 1", sql_kind="query_only", python=None,
            audit_report=AuditReport(high_risk_ddl=True, final_verdict="ok"), metadata=_meta())


def test_sql_present_requires_sql_kind():
    with pytest.raises(ValidationError):
        GenerateResponse(request_id="r", target_country="mexico", reasoning_summary="x",
            sql="SELECT 1", sql_kind=None, python=None,
            audit_report=AuditReport(high_risk_ddl=False, final_verdict="ok"), metadata=_meta())


from data_acquisition_agent.schemas import ExecuteRequest


def test_app_bucket_requires_csv_format():
    with pytest.raises(ValidationError):
        ExecuteRequest(approved_sql="SELECT 1", sql_kind="query_only",
            target_country="mexico", approved_by="t",
            output_bucket="app", output_format="json", uid_column="uid")

def test_behavior_bucket_allows_json():
    ExecuteRequest(approved_sql="SELECT 1", sql_kind="query_only",
        target_country="mexico", approved_by="t",
        output_bucket="behavior", output_format="json", uid_column="uid")

def test_credit_bucket_allows_csv():
    ExecuteRequest(approved_sql="SELECT 1", sql_kind="query_only",
        target_country="mexico", approved_by="t",
        output_bucket="credit", output_format="csv", uid_column="uid")

def test_approved_sql_non_empty():
    with pytest.raises(ValidationError):
        ExecuteRequest(approved_sql="   ", sql_kind="query_only",
            target_country="mexico", approved_by="t",
            output_bucket="app", output_format="csv", uid_column="uid")

def test_uid_column_default_is_uid():
    r = ExecuteRequest(approved_sql="SELECT 1", sql_kind="query_only",
        target_country="mexico", approved_by="t",
        output_bucket="app", output_format="csv")
    assert r.uid_column == "uid"
