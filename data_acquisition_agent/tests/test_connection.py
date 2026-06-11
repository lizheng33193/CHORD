import os, pytest
from unittest.mock import MagicMock, patch
from data_acquisition_agent.connection import (open_starrocks_connection,
    DbUnreachableError, _RedactedConnection)

ENV = {"DA_DB_HOST": "10.0.0.1", "DA_DB_PORT": "9030",
       "DA_DB_USER": "ro_user", "DA_DB_PASSWORD": "fake_pw_xyz",
       "DA_DB_DATABASE": "dm_fake"}

def test_open_reads_env_at_call_time(monkeypatch):
    """§6.1 凭据应在 open 时才从 os.environ 读，而非 import 时。"""
    for k, v in ENV.items(): monkeypatch.setenv(k, v)
    fake_conn = MagicMock()
    with patch("data_acquisition_agent.connection.pymysql.connect",
               return_value=fake_conn) as m:
        with open_starrocks_connection(request_id="rid-1") as conn:
            assert conn is not None
        m.assert_called_once()
        kwargs = m.call_args.kwargs
        assert kwargs["host"] == "10.0.0.1"
        assert kwargs["port"] == 9030
        assert kwargs["user"] == "ro_user"
        assert kwargs["password"] == "fake_pw_xyz"
        assert kwargs["database"] == "dm_fake"
    fake_conn.close.assert_called_once()

def test_open_missing_env_raises_db_unreachable(monkeypatch):
    monkeypatch.delenv("DA_DB_PASSWORD", raising=False)
    for k, v in ENV.items():
        if k != "DA_DB_PASSWORD": monkeypatch.setenv(k, v)
    with pytest.raises(DbUnreachableError):
        with open_starrocks_connection(request_id="rid-2"):
            pass

def test_open_driver_exception_wrapped(monkeypatch):
    """§6.4 driver 异常 → DbUnreachableError，不带原 message。"""
    for k, v in ENV.items(): monkeypatch.setenv(k, v)
    with patch("data_acquisition_agent.connection.pymysql.connect",
               side_effect=Exception("Access denied for user 'x'@'y'")):
        with pytest.raises(DbUnreachableError) as ei:
            with open_starrocks_connection(request_id="rid-3"):
                pass
        # 不携带原始 message
        assert "Access denied" not in str(ei.value)
        assert "fake_pw_xyz" not in str(ei.value)

def test_redacted_connection_repr_no_credentials(monkeypatch):
    for k, v in ENV.items(): monkeypatch.setenv(k, v)
    fake_conn = MagicMock()
    with patch("data_acquisition_agent.connection.pymysql.connect",
               return_value=fake_conn):
        with open_starrocks_connection(request_id="rid-4") as conn:
            r = repr(conn)
            assert "10.0.0.1" not in r
            assert "fake_pw_xyz" not in r
            assert "ro_user" not in r
            assert "dm_fake" not in r

def test_close_called_even_on_inner_exception(monkeypatch):
    for k, v in ENV.items(): monkeypatch.setenv(k, v)
    fake_conn = MagicMock()
    with patch("data_acquisition_agent.connection.pymysql.connect",
               return_value=fake_conn):
        with pytest.raises(RuntimeError):
            with open_starrocks_connection(request_id="rid-5") as conn:
                raise RuntimeError("inner")
    fake_conn.close.assert_called_once()
