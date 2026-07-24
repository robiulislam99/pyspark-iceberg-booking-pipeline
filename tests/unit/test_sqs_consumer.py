"""
Unit tests for src/scripts/sqs_consumer.py

`main()` runs an infinite polling loop, so tests break out of it by
making receive_messages raise a sentinel exception after the desired
number of iterations.

Run:
    docker compose exec spark pytest tests/unit/test_sqs_consumer.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

# Adjust this import to match wherever this module actually lives in src/
import scripts.sqs_consumer as sqs_consumer


class _StopLoop(Exception):
    """Sentinel used to break out of main()'s infinite while loop in tests."""


# ---------------------------------------------------------------------------
# fetch_rows
# ---------------------------------------------------------------------------


def test_fetch_rows_empty_ids_returns_empty_without_querying():
    spark = MagicMock()

    result = sqs_consumer.fetch_rows(spark, [])

    assert result == []
    spark.sql.assert_not_called()


def test_fetch_rows_queries_and_converts_rows():
    spark = MagicMock()
    row1 = MagicMock()
    row1.asDict.return_value = {"feed_provider_id": "p1"}
    row2 = MagicMock()
    row2.asDict.return_value = {"feed_provider_id": "p2"}
    df = MagicMock()
    df.collect.return_value = [row1, row2]
    spark.sql.return_value = df

    result = sqs_consumer.fetch_rows(spark, ["p1", "p2"])

    query = spark.sql.call_args.args[0]
    assert sqs_consumer.TABLE in query
    assert "'p1'" in query
    assert "'p2'" in query
    assert result == [{"feed_provider_id": "p1"}, {"feed_provider_id": "p2"}]


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_no_messages_skips_processing_and_continues():
    with (
        patch("scripts.sqs_consumer.get_spark"),
        patch("scripts.sqs_consumer.get_es_client"),
        patch("scripts.sqs_consumer.receive_messages") as mock_receive,
        patch("scripts.sqs_consumer.fetch_rows") as mock_fetch,
        patch("scripts.sqs_consumer.bulk_upsert") as mock_bulk,
        patch("scripts.sqs_consumer.delete_message") as mock_delete,
    ):
        mock_receive.side_effect = [
            (MagicMock(), "queue-url", []),  # no messages
            _StopLoop(),
        ]

        with pytest.raises(_StopLoop):
            sqs_consumer.main()

    mock_fetch.assert_not_called()
    mock_bulk.assert_not_called()
    mock_delete.assert_not_called()


def test_main_processes_message_and_indexes_documents():
    message = {
        "Body": '{"feed_provider_ids": ["p1"], "date": "20260714"}',
        "ReceiptHandle": "receipt-1",
    }
    client_mock = MagicMock()

    with (
        patch("scripts.sqs_consumer.get_spark") as mock_get_spark,
        patch("scripts.sqs_consumer.get_es_client") as mock_get_es,
        patch("scripts.sqs_consumer.receive_messages") as mock_receive,
        patch("scripts.sqs_consumer.fetch_rows", return_value=[{"feed_provider_id": "p1"}]) as mock_fetch,
        patch("scripts.sqs_consumer.to_es_document", return_value={"id": "p1"}) as mock_to_doc,
        patch("scripts.sqs_consumer.bulk_upsert") as mock_bulk,
        patch("scripts.sqs_consumer.delete_message") as mock_delete,
    ):
        mock_receive.side_effect = [
            (client_mock, "queue-url", [message]),
            _StopLoop(),
        ]

        with pytest.raises(_StopLoop):
            sqs_consumer.main()

    mock_fetch.assert_called_once_with(mock_get_spark.return_value, ["p1"])
    mock_to_doc.assert_called_once_with({"feed_provider_id": "p1"})
    mock_bulk.assert_called_once_with(mock_get_es.return_value, [{"id": "p1"}])
    mock_delete.assert_called_once_with(client_mock, "queue-url", "receipt-1")


def test_main_skips_bulk_upsert_when_no_documents_but_still_deletes_message():
    message = {
        "Body": '{"feed_provider_ids": [], "date": "20260714"}',
        "ReceiptHandle": "receipt-2",
    }
    client_mock = MagicMock()

    with (
        patch("scripts.sqs_consumer.get_spark"),
        patch("scripts.sqs_consumer.get_es_client"),
        patch("scripts.sqs_consumer.receive_messages") as mock_receive,
        patch("scripts.sqs_consumer.fetch_rows", return_value=[]),
        patch("scripts.sqs_consumer.bulk_upsert") as mock_bulk,
        patch("scripts.sqs_consumer.delete_message") as mock_delete,
    ):
        mock_receive.side_effect = [
            (client_mock, "queue-url", [message]),
            _StopLoop(),
        ]

        with pytest.raises(_StopLoop):
            sqs_consumer.main()

    mock_bulk.assert_not_called()
    mock_delete.assert_called_once_with(client_mock, "queue-url", "receipt-2")


def test_main_exception_during_processing_does_not_delete_message():
    message = {
        "Body": '{"feed_provider_ids": ["p1"], "date": "20260714"}',
        "ReceiptHandle": "receipt-3",
    }
    client_mock = MagicMock()

    with (
        patch("scripts.sqs_consumer.get_spark"),
        patch("scripts.sqs_consumer.get_es_client"),
        patch("scripts.sqs_consumer.receive_messages") as mock_receive,
        patch("scripts.sqs_consumer.fetch_rows", side_effect=RuntimeError("boom")),
        patch("scripts.sqs_consumer.delete_message") as mock_delete,
    ):
        mock_receive.side_effect = [
            (client_mock, "queue-url", [message]),
            _StopLoop(),
        ]

        with pytest.raises(_StopLoop):
            sqs_consumer.main()

    mock_delete.assert_not_called()


def test_main_malformed_json_body_does_not_crash_or_delete():
    message = {"Body": "not valid json", "ReceiptHandle": "receipt-4"}
    client_mock = MagicMock()

    with (
        patch("scripts.sqs_consumer.get_spark"),
        patch("scripts.sqs_consumer.get_es_client"),
        patch("scripts.sqs_consumer.receive_messages") as mock_receive,
        patch("scripts.sqs_consumer.delete_message") as mock_delete,
    ):
        mock_receive.side_effect = [
            (client_mock, "queue-url", [message]),
            _StopLoop(),
        ]

        with pytest.raises(_StopLoop):
            sqs_consumer.main()

    mock_delete.assert_not_called()


def test_main_continues_processing_remaining_messages_after_one_fails():
    good_message = {
        "Body": '{"feed_provider_ids": ["p1"], "date": "20260714"}',
        "ReceiptHandle": "receipt-good",
    }
    bad_message = {"Body": "broken json", "ReceiptHandle": "receipt-bad"}
    client_mock = MagicMock()

    with (
        patch("scripts.sqs_consumer.get_spark"),
        patch("scripts.sqs_consumer.get_es_client") as mock_get_es_client,
        patch("scripts.sqs_consumer.receive_messages") as mock_receive,
        patch("scripts.sqs_consumer.fetch_rows", return_value=[{"feed_provider_id": "p1"}]),
        patch("scripts.sqs_consumer.to_es_document", return_value={"id": "p1"}),
        patch("scripts.sqs_consumer.bulk_upsert") as mock_bulk,
        patch("scripts.sqs_consumer.delete_message") as mock_delete,
    ):
        mock_receive.side_effect = [
            (client_mock, "queue-url", [bad_message, good_message]),
            _StopLoop(),
        ]

        with pytest.raises(_StopLoop):
            sqs_consumer.main()

        mock_bulk.assert_called_once_with(mock_get_es_client.return_value, [{"id": "p1"}])
        mock_delete.assert_called_once_with(client_mock, "queue-url", "receipt-good")
