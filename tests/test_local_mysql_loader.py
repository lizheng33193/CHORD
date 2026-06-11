from __future__ import annotations

import csv
from pathlib import Path

import pytest


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def test_load_label_rows_rejects_duplicate_app_package(tmp_path):
    from scripts.local_mysql.load_mexico_local_dev import load_label_rows

    path = tmp_path / "label.csv"
    _write_csv(
        path,
        ["app_package", "app_name", "gp_category", "ai_category_level_2_CN"],
        [
            {"app_package": "com.demo.a", "app_name": "A", "gp_category": "金融", "ai_category_level_2_CN": "借贷"},
            {"app_package": "com.demo.a", "app_name": "A2", "gp_category": "金融", "ai_category_level_2_CN": "钱包"},
        ],
    )

    with pytest.raises(ValueError, match="duplicate app_package"):
        load_label_rows(path)


def test_join_app_chunk_keeps_row_count_and_tracks_unmatched():
    import pandas as pd

    from scripts.local_mysql.load_mexico_local_dev import join_app_chunk_with_labels

    chunk = pd.DataFrame(
        [
            {
                "uid": "u1",
                "app_name": "Known",
                "app_package": "com.demo.known",
                "first_install_time": "1",
                "last_update_time": "2",
                "timestamp_": "3",
                "create_at": "2024-01-01 00:00:00",
            },
            {
                "uid": "u2",
                "app_name": "Unknown",
                "app_package": "com.demo.unknown",
                "first_install_time": "4",
                "last_update_time": "5",
                "timestamp_": "6",
                "create_at": "2024-01-01 00:00:00",
            },
        ]
    )
    labels = {
        "com.demo.known": {
            "app_package": "com.demo.known",
            "app_name": "Known Label",
            "gp_category": "金融",
            "ai_category_level_1_CN": "金融服务",
            "ai_category_level_2_CN": "借贷",
        }
    }

    joined, unmatched = join_app_chunk_with_labels(chunk, labels)

    assert len(joined) == len(chunk)
    assert unmatched == 1
    assert list(joined["ai_category_level_2_CN"]) == ["借贷", "unknown"]
    assert list(joined["gp_category"]) == ["金融", "unknown"]


def test_collect_uid_sets_reads_expected_columns(tmp_path):
    from scripts.local_mysql.load_mexico_local_dev import collect_uid_sets

    app = tmp_path / "app.csv"
    behavior = tmp_path / "behavior.csv"
    credit = tmp_path / "credit.csv"
    _write_csv(app, ["uid"], [{"uid": "u1"}, {"uid": "u2"}])
    _write_csv(behavior, ["uid"], [{"uid": "u2"}, {"uid": "u3"}])
    _write_csv(credit, ["user_uuid"], [{"user_uuid": "u2"}, {"user_uuid": "u4"}])

    uid_sets = collect_uid_sets(
        app_path=app,
        behavior_path=behavior,
        credit_path=credit,
    )

    assert uid_sets["app"] == {"u1", "u2"}
    assert uid_sets["behavior"] == {"u2", "u3"}
    assert uid_sets["credit"] == {"u2", "u4"}


def test_dataframe_records_for_mysql_converts_nan_to_none():
    import pandas as pd

    from scripts.local_mysql.load_mexico_local_dev import dataframe_records_for_mysql

    df = pd.DataFrame(
        [
            {"uid": "u1", "first_install_time": 1, "gp_category": "金融"},
            {"uid": "u2", "first_install_time": float("nan"), "gp_category": None},
        ]
    )

    records = dataframe_records_for_mysql(df)

    assert records[0]["first_install_time"] == 1
    assert records[1]["first_install_time"] is None
    assert records[1]["gp_category"] is None


def test_normalize_app_chunk_fills_missing_app_package_with_sentinel():
    import pandas as pd

    from scripts.local_mysql.load_mexico_local_dev import MISSING_APP_PACKAGE, _normalize_app_chunk

    chunk = pd.DataFrame(
        [
            {
                "uid": "u1",
                "app_name": None,
                "app_package": None,
                "first_install_time": None,
                "last_update_time": None,
                "gp_category": "金融",
                "ai_category_level_1_CN": "金融服务",
                "ai_category_level_2_CN": "借贷",
                "timestamp_": "123",
                "create_at": None,
            }
        ]
    )

    normalized = _normalize_app_chunk(chunk)

    assert normalized.loc[0, "app_name"] == "unknown"
    assert normalized.loc[0, "app_package"] == MISSING_APP_PACKAGE
