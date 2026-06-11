"""Trace analyzer route integration tests (FastAPI TestClient)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.trace import router as trace_router


CSV_HEADER = "uid,servertimestamp,timestamp_,scenetype,processtype,eventname,extend,clientmodel,clientosversion,url,refer,ip"


def _app() -> FastAPI:
    a = FastAPI()
    a.include_router(trace_router)
    return a


def test_route_data_missing_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.model_mode", "mock")
    client = TestClient(_app())
    resp = client.get("/api/trace/UNKNOWN_UID")
    assert resp.status_code == 404
    assert resp.json()["status"] == "data_missing"


def test_route_ok_path_mock_mode(tmp_path, monkeypatch):
    uid = "RT1"
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    rows = [f'{uid},{1773000000000 + i*1000},{1773000000000 + i*1000},kyc,kyc,'
            f'field-edit,"{{\\"field\\":\\"id_no\\"}}",m,15,https://x/kyc,null,1.1'
            for i in range(50)]
    (base / f"{uid}.csv").write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.model_mode", "mock")

    client = TestClient(_app())
    resp = client.get(f"/api/trace/{uid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "model_unavailable"  # mock mode
    assert body["uid"] == uid
    assert len(body["friction_hotspots"]) >= 1


def test_route_insufficient_events_returns_200(tmp_path, monkeypatch):
    uid = "RT2"
    base = tmp_path / "behavior" / "by_uid"
    base.mkdir(parents=True, exist_ok=True)
    rows = [f'{uid},{1773000000000 + i*1000},x,home,home,page_onResume,"{{}}",m,15,https://x/,null,1'
            for i in range(3)]
    (base / f"{uid}.csv").write_text(CSV_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    monkeypatch.setattr("app.core.config.settings.data_dir", str(tmp_path))
    monkeypatch.setattr("app.core.config.settings.model_mode", "mock")

    client = TestClient(_app())
    resp = client.get(f"/api/trace/{uid}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "insufficient_events"
