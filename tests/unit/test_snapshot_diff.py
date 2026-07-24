"""
Unit tests for snapshot_diff.py

Run:
    docker compose exec spark pytest tests/unit/test_snapshot_diff.py -v
"""

from unittest.mock import MagicMock

import pytest
from pyspark.sql import Row, SparkSession
from pyspark.sql.types import StringType, StructField, StructType

from core.snapshot_diff import COMPARE_COLUMNS, diff_snapshots


@pytest.fixture(scope="session")
def spark():
    session = SparkSession.builder.appName("test-snapshot-diff").master("local[1]").getOrCreate()
    yield session
    session.stop()


def _schema():
    fields = [StructField("feed_provider_id", StringType(), True)]
    fields += [StructField(col, StringType(), True) for col in COMPARE_COLUMNS]
    return StructType(fields)


def _base_row(feed_provider_id, property_name, **overrides):
    row = {"feed_provider_id": feed_provider_id}
    for col in COMPARE_COLUMNS:
        row[col] = property_name if col == "property_name" else None
    for key, value in overrides.items():
        row[key] = str(value) if value is not None else None
    return Row(**row)


def _make_df(spark, rows):
    return spark.createDataFrame(rows, schema=_schema())


def _patch_spark_read(spark, monkeypatch, old_df, new_df, old_snapshot_id, new_snapshot_id):
    def option_side_effect(key, value):
        table_mock = MagicMock()
        if value == old_snapshot_id:
            table_mock.table.return_value = old_df
        elif value == new_snapshot_id:
            table_mock.table.return_value = new_df
        else:
            raise AssertionError(f"Unexpected snapshot id: {value}")
        return table_mock

    read_mock = MagicMock()
    read_mock.option.side_effect = option_side_effect
    monkeypatch.setattr(type(spark), "read", property(lambda self: read_mock), raising=False)
    return read_mock


def test_diff_snapshots_detects_changed_column(spark, monkeypatch):
    old_df = _make_df(spark, [_base_row("p1", "Old Name", price=100, city="Dhaka")])
    new_df = _make_df(spark, [_base_row("p1", "Old Name", price=150, city="Dhaka")])
    _patch_spark_read(spark, monkeypatch, old_df, new_df, old_snapshot_id=1, new_snapshot_id=2)

    result = diff_snapshots(spark, 1, 2)

    assert len(result) == 1
    assert result[0]["feed_provider_id"] == "p1"
    assert result[0]["changed_fields"] == ["price"]


def test_diff_snapshots_no_changes_returns_empty(spark, monkeypatch):
    old_df = _make_df(spark, [_base_row("p1", "Same Name", price=100)])
    new_df = _make_df(spark, [_base_row("p1", "Same Name", price=100)])
    _patch_spark_read(spark, monkeypatch, old_df, new_df, old_snapshot_id=1, new_snapshot_id=2)

    result = diff_snapshots(spark, 1, 2)

    assert result == []


def test_diff_snapshots_detects_multiple_changed_columns(spark, monkeypatch):
    old_df = _make_df(spark, [_base_row("p1", "Name A", price=100, star_rating=4, currency="USD")])
    new_df = _make_df(spark, [_base_row("p1", "Name B", price=200, star_rating=5, currency="USD")])
    _patch_spark_read(spark, monkeypatch, old_df, new_df, old_snapshot_id=1, new_snapshot_id=2)

    result = diff_snapshots(spark, 1, 2)

    assert len(result) == 1
    changed = set(result[0]["changed_fields"])
    assert changed == {"property_name", "price", "star_rating"}


def test_diff_snapshots_only_reports_changed_rows_among_many(spark, monkeypatch):
    old_df = _make_df(spark, [_base_row("p1", "Name A", price=100), _base_row("p2", "Name B", price=200)])
    new_df = _make_df(spark, [_base_row("p1", "Name A", price=100), _base_row("p2", "Name B", price=250)])
    _patch_spark_read(spark, monkeypatch, old_df, new_df, old_snapshot_id=1, new_snapshot_id=2)

    result = diff_snapshots(spark, 1, 2)

    assert len(result) == 1
    assert result[0]["feed_provider_id"] == "p2"
    assert result[0]["changed_fields"] == ["price"]


def test_diff_snapshots_ignores_rows_only_in_one_snapshot(spark, monkeypatch):
    old_df = _make_df(spark, [_base_row("p1", "Name A", price=100)])
    new_df = _make_df(
        spark,
        [_base_row("p1", "Name A", price=100), _base_row("p2", "Brand New Property", price=999)],
    )
    _patch_spark_read(spark, monkeypatch, old_df, new_df, old_snapshot_id=1, new_snapshot_id=2)

    result = diff_snapshots(spark, 1, 2)

    assert result == []


def test_diff_snapshots_respects_limit_for_printing_but_returns_all(spark, monkeypatch, capsys):
    old_rows = [_base_row(f"p{i}", f"Name {i}", price=100) for i in range(5)]
    new_rows = [_base_row(f"p{i}", f"Name {i}", price=100 + i) for i in range(5)]
    old_df = _make_df(spark, old_rows)
    new_df = _make_df(spark, new_rows)
    _patch_spark_read(spark, monkeypatch, old_df, new_df, old_snapshot_id=1, new_snapshot_id=2)

    result = diff_snapshots(spark, 1, 2, limit=2)

    assert len(result) == 5
