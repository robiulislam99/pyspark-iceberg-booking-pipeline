"""
Unit tests for src/scripts/export_to_s3_local.py

Run:
    docker compose exec spark pytest tests/unit/test_export_to_s3_local.py -v
"""

import json
from unittest.mock import MagicMock, patch

# Adjust this import to match wherever this module actually lives in src/
import scripts.export_to_s3_local as export_to_s3_local


def _make_row(as_dict):
    row = MagicMock()
    row.asDict.return_value = as_dict
    return row


def test_export_date_creates_bucket():
    spark = MagicMock()
    client = MagicMock()
    df = MagicMock()
    df.collect.return_value = []
    spark.sql.return_value = df

    export_to_s3_local.export_date(spark, "20260714", client)

    client.create_bucket.assert_called_once_with(Bucket=export_to_s3_local.BUCKET_NAME)


def test_export_date_writes_one_object_per_row():
    spark = MagicMock()
    client = MagicMock()
    df = MagicMock()
    df.collect.return_value = [
        _make_row({"feed_provider_id": "p1"}),
        _make_row({"feed_provider_id": "p2"}),
    ]
    spark.sql.return_value = df

    mapped_docs = [{"ID": "p1", "name": "Villa 1"}, {"ID": "p2", "name": "Villa 2"}]

    with patch("scripts.export_to_s3_local.to_s3_document", side_effect=mapped_docs):
        export_to_s3_local.export_date(spark, "20260714", client)

    assert client.put_object.call_count == 2

    first_call = client.put_object.call_args_list[0].kwargs
    assert first_call["Bucket"] == export_to_s3_local.BUCKET_NAME
    assert first_call["Key"] == "rental-properties/date=20260714/p1.json"
    assert json.loads(first_call["Body"].decode("utf-8")) == mapped_docs[0]

    second_call = client.put_object.call_args_list[1].kwargs
    assert second_call["Key"] == "rental-properties/date=20260714/p2.json"
    assert json.loads(second_call["Body"].decode("utf-8")) == mapped_docs[1]


def test_export_date_prints_correct_count(capsys):
    spark = MagicMock()
    client = MagicMock()
    df = MagicMock()
    df.collect.return_value = [_make_row({"feed_provider_id": "p1"})]
    spark.sql.return_value = df

    with patch("scripts.export_to_s3_local.to_s3_document", return_value={"ID": "p1"}):
        export_to_s3_local.export_date(spark, "20260714", client)

    captured = capsys.readouterr()
    assert "Wrote 1 object(s)" in captured.out
    assert f"s3://{export_to_s3_local.BUCKET_NAME}/rental-properties/date=20260714/" in captured.out


def test_export_date_no_rows_writes_nothing(capsys):
    spark = MagicMock()
    client = MagicMock()
    df = MagicMock()
    df.collect.return_value = []
    spark.sql.return_value = df

    export_to_s3_local.export_date(spark, "20260714", client)

    client.put_object.assert_not_called()
    captured = capsys.readouterr()
    assert "Wrote 0 object(s)" in captured.out


def test_export_date_uses_correct_table_in_query():
    spark = MagicMock()
    client = MagicMock()
    df = MagicMock()
    df.collect.return_value = []
    spark.sql.return_value = df

    export_to_s3_local.export_date(spark, "20260714", client)

    query = spark.sql.call_args.args[0]
    assert export_to_s3_local.TABLE in query


def test_export_date_body_is_json_encoded_bytes():
    spark = MagicMock()
    client = MagicMock()
    df = MagicMock()
    df.collect.return_value = [_make_row({"feed_provider_id": "p1"})]
    spark.sql.return_value = df

    with patch("scripts.export_to_s3_local.to_s3_document", return_value={"ID": "p1", "price": 99.5}):
        export_to_s3_local.export_date(spark, "20260714", client)

    body = client.put_object.call_args.kwargs["Body"]
    assert isinstance(body, bytes)
    assert json.loads(body.decode("utf-8")) == {"ID": "p1", "price": 99.5}
