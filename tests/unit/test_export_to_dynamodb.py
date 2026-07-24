"""
Unit tests for src/scripts/export_to_dynamodb.py

Run:
    docker compose exec spark pytest tests/unit/test_export_to_dynamodb.py -v
"""

from unittest.mock import MagicMock, patch

# Adjust this import to match wherever this module actually lives in src/
import scripts.export_to_dynamodb as export_to_dynamodb

# ---------------------------------------------------------------------------
# export_date
# ---------------------------------------------------------------------------


def test_export_date_no_changelog_ids_skips_query(capsys):
    spark = MagicMock()

    with patch("scripts.export_to_dynamodb.get_changelog_ids", return_value=[]):
        export_to_dynamodb.export_date(spark, "20260714")

    spark.sql.assert_not_called()
    captured = capsys.readouterr()
    assert "No changelog IDs for 20260714" in captured.out


def test_export_date_no_matching_rows_skips_write(capsys):
    spark = MagicMock()
    df = MagicMock()
    df.count.return_value = 0
    spark.sql.return_value = df

    def fake_changelog_ids(date_str, kind):
        return ["p1"] if kind == "changed" else []

    with patch("scripts.export_to_dynamodb.get_changelog_ids", side_effect=fake_changelog_ids):
        export_to_dynamodb.export_date(spark, "20260714")

    spark.sql.assert_called_once()
    df.foreachPartition.assert_not_called()
    captured = capsys.readouterr()
    assert "No matching rows found in Iceberg for date=20260714" in captured.out


def test_export_date_writes_matching_rows(capsys):
    spark = MagicMock()
    df = MagicMock()
    df.count.return_value = 3
    spark.sql.return_value = df

    def fake_changelog_ids(date_str, kind):
        if kind == "changed":
            return ["p1", "p2"]
        return ["p2", "p3"]

    with patch("scripts.export_to_dynamodb.get_changelog_ids", side_effect=fake_changelog_ids):
        export_to_dynamodb.export_date(spark, "20260714")

    spark.sql.assert_called_once()
    query = spark.sql.call_args.args[0]
    assert export_to_dynamodb.TABLE in query
    assert "'p1'" in query
    assert "'p2'" in query
    assert "'p3'" in query

    df.foreachPartition.assert_called_once_with(export_to_dynamodb._export_partition)

    captured = capsys.readouterr()
    assert "Wrote 3 item(s)" in captured.out
    assert "date=20260714" in captured.out


def test_export_date_deduplicates_changed_and_opened_ids():
    spark = MagicMock()
    df = MagicMock()
    df.count.return_value = 1
    spark.sql.return_value = df

    def fake_changelog_ids(date_str, kind):
        return ["p1", "p2"]  # same ids for both kinds

    with patch("scripts.export_to_dynamodb.get_changelog_ids", side_effect=fake_changelog_ids):
        export_to_dynamodb.export_date(spark, "20260714")

    query = spark.sql.call_args.args[0]
    # p1 and p2 should each appear exactly once despite being in both sets
    assert query.count("'p1'") == 1
    assert query.count("'p2'") == 1


# ---------------------------------------------------------------------------
# _export_partition
# ---------------------------------------------------------------------------


def _make_row(as_dict):
    row = MagicMock()
    row.asDict.return_value = as_dict
    return row


def test_export_partition_maps_and_writes_valid_rows():
    rows = [
        _make_row({"feed_provider_id": "p1"}),
        _make_row({"feed_provider_id": "p2"}),
    ]

    mapped_items = [
        {"property_id": "p1", "timestamp": "2026-07-14T00:00:00Z"},
        {"property_id": "p2", "timestamp": "2026-07-14T00:00:00Z"},
    ]

    with (
        patch("src.clients.dynamodb_client.batch_put_items") as mock_batch_put,
        patch("src.mappers.dynamodb_document_mapper.to_dynamodb_item", side_effect=mapped_items),
    ):
        export_to_dynamodb._export_partition(rows)

        mock_batch_put.assert_called_once_with(mapped_items)


def test_export_partition_filters_out_items_missing_property_id_or_timestamp():
    rows = [_make_row({"feed_provider_id": "p1"}), _make_row({"feed_provider_id": "p2"})]

    mapped_items = [
        {"property_id": None, "timestamp": "2026-07-14T00:00:00Z"},  # missing property_id
        {"property_id": "p2", "timestamp": None},  # missing timestamp
    ]

    with (
        patch("src.clients.dynamodb_client.batch_put_items") as mock_batch_put,
        patch("src.mappers.dynamodb_document_mapper.to_dynamodb_item", side_effect=mapped_items),
    ):
        export_to_dynamodb._export_partition(rows)

        mock_batch_put.assert_not_called()


def test_export_partition_no_rows_does_not_call_batch_put():
    with patch("src.clients.dynamodb_client.batch_put_items") as mock_batch_put:
        export_to_dynamodb._export_partition([])

        mock_batch_put.assert_not_called()
