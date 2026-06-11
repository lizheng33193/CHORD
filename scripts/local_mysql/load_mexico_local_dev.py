from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import pymysql


APP_TABLE = "app_install_list"
BEHAVIOR_TABLE = "behavior_events"
CREDIT_TABLE = "credit_report_raw"
LABEL_TABLE = "app_label_dictionary"
UNKNOWN_VALUE = "unknown"
MISSING_APP_PACKAGE = "__missing_app_package__"
DEFAULT_CHUNKSIZE = 20_000

DEFAULT_IMPORT_FILENAMES = {
    "app": "mex_17_withdraw_appdata_user_profile20260413.csv",
    "behavior": "mex_17_withdraw_burydata_user_profile20260413.csv",
    "credit": "mex17_withdraw_cdcdata_user_profile20260413.csv",
    "label": "Mexico_applist_label_new .csv",
}


def normalize_app_package(value: Any) -> str:
    return str(value or "").strip().lower()


def load_label_rows(csv_path: Path) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            app_package = normalize_app_package(row.get("app_package"))
            if not app_package:
                continue
            if app_package in rows:
                raise ValueError(f"duplicate app_package: {app_package}")
            rows[app_package] = {
                "app_package": app_package,
                "app_name": str(row.get("app_name") or "").strip(),
                "gp_category": str(row.get("gp_category") or "").strip(),
                "ai_category_level_1_CN": str(row.get("ai_category_level_1_CN") or "").strip(),
                "ai_category_level_2_CN": str(row.get("ai_category_level_2_CN") or "").strip(),
                "rating": str(row.get("rating") or "").strip(),
                "download_count": str(row.get("download_count") or "").strip(),
                "is_delisted": str(row.get("is_delisted") or "").strip(),
            }
    return rows


def join_app_chunk_with_labels(
    chunk: pd.DataFrame,
    labels: dict[str, dict[str, str]],
) -> tuple[pd.DataFrame, int]:
    joined = chunk.copy()
    joined["__normalized_app_package"] = joined["app_package"].map(normalize_app_package)
    label_df = pd.DataFrame(list(labels.values()))
    if label_df.empty:
        label_df = pd.DataFrame(
            columns=[
                "app_package",
                "app_name",
                "gp_category",
                "ai_category_level_1_CN",
                "ai_category_level_2_CN",
            ]
        )
    label_df = label_df.rename(
        columns={
            "app_package": "__normalized_app_package",
            "app_name": "__label_app_name",
            "gp_category": "__label_gp_category",
            "ai_category_level_1_CN": "__label_ai_category_level_1_CN",
            "ai_category_level_2_CN": "__label_ai_category_level_2_CN",
        }
    )
    merged = joined.merge(label_df, how="left", on="__normalized_app_package", validate="many_to_one")
    unmatched = int(merged["__label_gp_category"].isna().sum())
    merged["app_name"] = merged["app_name"].fillna("").astype(str).str.strip()
    merged["app_name"] = merged["app_name"].where(merged["app_name"] != "", merged["__label_app_name"])
    merged["gp_category"] = merged["__label_gp_category"].fillna(UNKNOWN_VALUE)
    merged["ai_category_level_1_CN"] = merged["__label_ai_category_level_1_CN"].fillna(UNKNOWN_VALUE)
    merged["ai_category_level_2_CN"] = merged["__label_ai_category_level_2_CN"].fillna(UNKNOWN_VALUE)
    merged = merged.drop(
        columns=[
            "__normalized_app_package",
            "__label_app_name",
            "__label_gp_category",
            "__label_ai_category_level_1_CN",
            "__label_ai_category_level_2_CN",
        ]
    )
    return merged, unmatched


def collect_uid_sets(*, app_path: Path, behavior_path: Path, credit_path: Path) -> dict[str, set[str]]:
    return {
        "app": _read_uid_set(app_path, "uid"),
        "behavior": _read_uid_set(behavior_path, "uid"),
        "credit": _read_uid_set(credit_path, "user_uuid"),
    }


def _read_uid_set(path: Path, column: str) -> set[str]:
    values: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            value = str(row.get(column) or "").strip()
            if value:
                values.add(value)
    return values


def _connect_from_env():
    return pymysql.connect(
        host=os.getenv("DA_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DA_DB_PORT", "3307")),
        user=os.getenv("DA_DB_USER", "maps_user"),
        password=os.getenv("DA_DB_PASSWORD", ""),
        database=os.getenv("DA_DB_DATABASE", "user_profile"),
        charset="utf8mb4",
        local_infile=True,
        autocommit=False,
    )


def _iter_csv_chunks(csv_path: Path, *, chunksize: int) -> Iterable[pd.DataFrame]:
    return pd.read_csv(csv_path, encoding="utf-8-sig", chunksize=chunksize)


def _maybe_int(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    return int(float(text))


def _clean_text(value: Any, *, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none"}:
        return default
    return text


def _normalize_app_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    normalized = chunk.copy()
    for col in ("first_install_time", "last_update_time", "timestamp_"):
        if col in normalized.columns:
            normalized[col] = normalized[col].map(_maybe_int)
    normalized["uid"] = normalized["uid"].map(lambda value: _clean_text(value, default="") or "")
    normalized["app_name"] = normalized["app_name"].map(
        lambda value: _clean_text(value, default=UNKNOWN_VALUE) or UNKNOWN_VALUE
    )
    normalized["app_package"] = normalized["app_package"].map(
        lambda value: _clean_text(value, default=MISSING_APP_PACKAGE) or MISSING_APP_PACKAGE
    )
    normalized["create_at"] = normalized["create_at"].map(_clean_text)
    return normalized[
        [
            "uid",
            "app_name",
            "app_package",
            "first_install_time",
            "last_update_time",
            "gp_category",
            "ai_category_level_1_CN",
            "ai_category_level_2_CN",
            "timestamp_",
            "create_at",
        ]
    ]


def _normalize_behavior_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    normalized = chunk.copy()
    for col in ("servertimestamp", "timestamp_"):
        if col in normalized.columns:
            normalized[col] = normalized[col].map(_maybe_int)
    return normalized[
        [
            "uid",
            "servertimestamp",
            "timestamp_",
            "scenetype",
            "processtype",
            "eventname",
            "extend",
            "clientmodel",
            "clientosversion",
            "url",
            "refer",
            "ip",
        ]
    ]


def _normalize_credit_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    normalized = chunk.copy()
    normalized["uid"] = normalized["user_uuid"].astype(str).str.strip()
    return normalized[
        [
            "uid",
            "user_uuid",
            "apply_risk_id",
            "timestamp_",
            "code",
            "folioconsulta",
            "nombrescore",
            "valor",
            "razones",
            "consultas_detail_json",
            "creditos_detail_json",
            "dt",
            "rn",
        ]
    ]


def dataframe_records_for_mysql(df: pd.DataFrame) -> list[dict[str, Any]]:
    safe_df = df.astype(object).where(pd.notnull(df), None)
    return safe_df.to_dict(orient="records")


def _insert_dataframe(conn, table: str, df: pd.DataFrame) -> int:
    records = dataframe_records_for_mysql(df)
    if not records:
        return 0
    columns = list(df.columns)
    placeholders = ", ".join(["%s"] * len(columns))
    quoted_columns = ", ".join(f"`{col}`" for col in columns)
    sql = f"INSERT INTO `{table}` ({quoted_columns}) VALUES ({placeholders})"
    values = [tuple(row.get(col) for col in columns) for row in records]
    with conn.cursor() as cur:
        cur.executemany(sql, values)
    return len(values)


def _truncate_tables(conn, tables: list[str]) -> None:
    with conn.cursor() as cur:
        for table in tables:
            cur.execute(f"TRUNCATE TABLE `{table}`")


def _count_rows(conn, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM `{table}`")
        row = cur.fetchone()
    return int(row[0]) if row else 0


def run_import(
    *,
    import_root: Path,
    chunksize: int = DEFAULT_CHUNKSIZE,
    reset: bool = False,
) -> dict[str, Any]:
    app_path = import_root / DEFAULT_IMPORT_FILENAMES["app"]
    behavior_path = import_root / DEFAULT_IMPORT_FILENAMES["behavior"]
    credit_path = import_root / DEFAULT_IMPORT_FILENAMES["credit"]
    label_path = import_root / DEFAULT_IMPORT_FILENAMES["label"]

    uid_sets = collect_uid_sets(app_path=app_path, behavior_path=behavior_path, credit_path=credit_path)
    labels = load_label_rows(label_path)
    app_raw_rows = 0
    app_joined_rows = 0
    unmatched_app_packages = 0

    conn = _connect_from_env()
    try:
        if reset:
            _truncate_tables(conn, [APP_TABLE, BEHAVIOR_TABLE, CREDIT_TABLE, LABEL_TABLE])

        label_df = pd.DataFrame(list(labels.values()))
        _insert_dataframe(conn, LABEL_TABLE, label_df)

        for chunk in _iter_csv_chunks(app_path, chunksize=chunksize):
            app_raw_rows += len(chunk)
            joined, unmatched = join_app_chunk_with_labels(chunk, labels)
            normalized = _normalize_app_chunk(joined)
            app_joined_rows += _insert_dataframe(conn, APP_TABLE, normalized)
            unmatched_app_packages += unmatched

        for chunk in _iter_csv_chunks(behavior_path, chunksize=chunksize):
            _insert_dataframe(conn, BEHAVIOR_TABLE, _normalize_behavior_chunk(chunk))

        for chunk in _iter_csv_chunks(credit_path, chunksize=chunksize):
            _insert_dataframe(conn, CREDIT_TABLE, _normalize_credit_chunk(chunk))

        if app_joined_rows != app_raw_rows:
            raise ValueError(
                f"joined row count mismatch: app_raw_rows={app_raw_rows}, app_joined_rows={app_joined_rows}"
            )
        conn.commit()
        return {
            "rows": {
                APP_TABLE: _count_rows(conn, APP_TABLE),
                BEHAVIOR_TABLE: _count_rows(conn, BEHAVIOR_TABLE),
                CREDIT_TABLE: _count_rows(conn, CREDIT_TABLE),
                LABEL_TABLE: _count_rows(conn, LABEL_TABLE),
            },
            "app_raw_rows": app_raw_rows,
            "app_joined_rows": app_joined_rows,
            "unmatched_app_packages": unmatched_app_packages,
            "label_match_ratio": 0.0 if app_raw_rows == 0 else (app_raw_rows - unmatched_app_packages) / app_raw_rows,
            "uid_intersection": {
                "app": len(uid_sets["app"]),
                "behavior": len(uid_sets["behavior"]),
                "credit": len(uid_sets["credit"]),
                "all": len(uid_sets["app"] & uid_sets["behavior"] & uid_sets["credit"]),
            },
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load Mexico local-dev CSVs into the Docker MySQL sandbox.")
    parser.add_argument(
        "--import-root",
        default=os.path.join(os.getenv("MYSQL_SANDBOX_ROOT", "/Users/zhengli/Desktop/docker-data"), "mysql-import"),
        help="Directory containing the four raw CSV inputs.",
    )
    parser.add_argument("--chunksize", type=int, default=DEFAULT_CHUNKSIZE, help="CSV chunk size.")
    parser.add_argument("--reset", action="store_true", help="Truncate all local-dev tables before loading.")
    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    result = run_import(
        import_root=Path(args.import_root),
        chunksize=args.chunksize,
        reset=args.reset,
    )
    print(result)


if __name__ == "__main__":
    main()
