"""V2 Connection Layer. See docs/specs/data_acquisition_agent_v2.md §6.

凭据只在执行那一刻从 os.environ 读取；不入 Settings、不入 module-level 全局、
不入 repr / log / response。Driver: pymysql（StarRocks FE MySQL 协议兼容）。
"""

from __future__ import annotations

import os
import pymysql
from contextlib import contextmanager


class DbUnreachableError(Exception):
    def __init__(self, message: str = "database connection failed",
                 request_id: str = ""):
        super().__init__(message)
        self.message = message
        self.request_id = request_id


class _RedactedConnection:
    def __init__(self, raw): self._raw = raw
    def __repr__(self) -> str: return "<RedactedStarRocksConnection>"
    def __getattr__(self, name): return getattr(self._raw, name)
    def close(self): self._raw.close()


_REQUIRED_ENV = ("DA_DB_HOST", "DA_DB_PORT", "DA_DB_USER",
                 "DA_DB_PASSWORD", "DA_DB_DATABASE")


@contextmanager
def open_starrocks_connection(*, request_id: str):
    from app.core.config import settings
    try:
        for k in _REQUIRED_ENV:
            if not os.environ.get(k):
                raise DbUnreachableError(request_id=request_id)
        creds = {
            "host": os.environ["DA_DB_HOST"],
            "port": int(os.environ["DA_DB_PORT"]),
            "user": os.environ["DA_DB_USER"],
            "password": os.environ["DA_DB_PASSWORD"],
            "database": os.environ["DA_DB_DATABASE"],
            "connect_timeout": settings.da_query_timeout_seconds,
            "read_timeout": settings.da_query_timeout_seconds,
        }
        raw = pymysql.connect(**creds)
    except DbUnreachableError:
        raise
    except Exception:
        raise DbUnreachableError(request_id=request_id) from None
    conn = _RedactedConnection(raw)
    try:
        yield conn
    finally:
        try: conn.close()
        except Exception: pass
