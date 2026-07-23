"""
Unit tests for mappers.dynamodb_document_mapper.
"""
from decimal import Decimal

from mappers.dynamodb_document_mapper import to_dynamodb_item


def test_price_is_converted_to_decimal_not_float(iceberg_row):
    item = to_dynamodb_item(iceberg_row)
    assert isinstance(item["usd_price"], Decimal)
    assert item["usd_price"] == Decimal("1301.0")


def test_timestamp_derived_from_last_synced_at_date(iceberg_row):
    item = to_dynamodb_item(iceberg_row)
    assert item["timestamp"] == "20260529"


def test_missing_last_synced_at_gives_none_timestamp(iceberg_row):
    iceberg_row["last_synced_at"] = None
    item = to_dynamodb_item(iceberg_row)
    assert item["timestamp"] is None


def test_missing_price_gives_none_not_zero(iceberg_row):
    iceberg_row["price"] = None
    item = to_dynamodb_item(iceberg_row)
    assert item["usd_price"] is None