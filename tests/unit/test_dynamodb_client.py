"""
Unit tests for src/clients/dynamodb_client.py

Uses moto (https://github.com/getmoto/moto) to mock DynamoDB entirely
in-memory -- no real AWS account, no local DynamoDB container needed
to run these tests.

Install test deps (add to requirements.txt):
    moto[dynamodb]==5.0.16

Run (from project root, inside the spark container):
    pytest tests/unit/test_dynamodb_client.py -v
"""

import importlib

import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def dynamo_client(monkeypatch):
    """
    Reload the module under test inside the moto mock context, with fake
    credentials/region set, so every boto3.resource(...) call it makes is
    intercepted by moto instead of hitting real AWS or a real endpoint.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    # Moto ignores endpoint_url in mock mode, but clear it anyway so the
    # module doesn't try to reach a real dynamodb-local host if moto
    # weren't active for some reason.
    monkeypatch.delenv("DYNAMODB_ENDPOINT_URL", raising=False)
    monkeypatch.setenv("DYNAMODB_TABLE_NAME", "rental_properties_test")

    with mock_aws():
        import clients.dynamodb_client as module

        importlib.reload(module)
        yield module


@pytest.fixture
def sample_items():
    return [
        {"property_id": "prop-1", "timestamp": "2026-01-01T00:00:00Z", "price": 1200},
        {"property_id": "prop-1", "timestamp": "2026-02-01T00:00:00Z", "price": 1250},
        {"property_id": "prop-2", "timestamp": "2026-01-01T00:00:00Z", "price": 900},
    ]


# ---------------------------------------------------------------------------
# ensure_table / get_table
# ---------------------------------------------------------------------------


def test_ensure_table_creates_table_when_missing(dynamo_client):
    table = dynamo_client.ensure_table()

    assert table.table_name == dynamo_client.TABLE_NAME
    assert table.table_status == "ACTIVE"

    key_schema = {k["AttributeName"]: k["KeyType"] for k in table.key_schema}
    assert key_schema == {"property_id": "HASH", "timestamp": "RANGE"}


def test_ensure_table_returns_existing_table_without_error(dynamo_client):
    first = dynamo_client.ensure_table()
    second = dynamo_client.ensure_table()

    assert first.table_name == second.table_name

    dynamodb = dynamo_client._resource()
    table_names = [t.name for t in dynamodb.tables.all()]
    assert dynamo_client.TABLE_NAME in table_names
    assert table_names.count(dynamo_client.TABLE_NAME) == 1


def test_get_table_works_after_table_exists(dynamo_client):
    dynamo_client.ensure_table()
    table = dynamo_client.get_table()
    assert table.table_name == dynamo_client.TABLE_NAME


# ---------------------------------------------------------------------------
# batch_put_items / get_item
# ---------------------------------------------------------------------------


def test_batch_put_items_then_get_item(dynamo_client, sample_items):
    dynamo_client.batch_put_items(sample_items)

    item = dynamo_client.get_item("prop-1", "2026-01-01T00:00:00Z")
    assert item is not None
    assert item["price"] == 1200

    item2 = dynamo_client.get_item("prop-2", "2026-01-01T00:00:00Z")
    assert item2 is not None
    assert item2["price"] == 900


def test_get_item_returns_none_when_missing(dynamo_client):
    dynamo_client.ensure_table()  # table must exist, but stays empty
    item = dynamo_client.get_item("does-not-exist", "2026-01-01T00:00:00Z")
    assert item is None


def test_batch_put_items_overwrites_on_same_composite_key(dynamo_client):
    dynamo_client.batch_put_items([{"property_id": "prop-1", "timestamp": "2026-01-01T00:00:00Z", "price": 1000}])
    dynamo_client.batch_put_items([{"property_id": "prop-1", "timestamp": "2026-01-01T00:00:00Z", "price": 1500}])

    item = dynamo_client.get_item("prop-1", "2026-01-01T00:00:00Z")
    assert item["price"] == 1500


# ---------------------------------------------------------------------------
# query_by_property
# ---------------------------------------------------------------------------


def test_query_by_property_returns_only_matching_items(dynamo_client, sample_items):
    dynamo_client.batch_put_items(sample_items)

    results = dynamo_client.query_by_property("prop-1")
    timestamps = sorted(r["timestamp"] for r in results)

    assert len(results) == 2
    assert timestamps == ["2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"]
    assert all(r["property_id"] == "prop-1" for r in results)


def test_query_by_property_returns_empty_list_for_unknown_property(dynamo_client, sample_items):
    dynamo_client.batch_put_items(sample_items)

    results = dynamo_client.query_by_property("no-such-property")
    assert results == []
