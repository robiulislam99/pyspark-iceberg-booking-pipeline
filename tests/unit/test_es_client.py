"""
Unit tests for src/clients/es_client.py

Run:
    docker compose exec spark pytest tests/unit/test_es_client.py -v
"""

from unittest.mock import MagicMock, patch

import pytest

import clients.es_client as es_client


@pytest.fixture
def mock_es():
    return MagicMock()


@pytest.fixture(autouse=True)
def reset_env(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
    monkeypatch.setenv("ES_INDEX_NAME", "rental_properties_test")


def test_get_es_client_returns_elasticsearch_instance():
    with patch("clients.es_client.Elasticsearch") as MockES:
        instance = MagicMock()
        MockES.return_value = instance

        client = es_client.get_es_client()

        MockES.assert_called_once_with(es_client.ES_URL)
        assert client is instance


def test_ensure_index_creates_when_missing(mock_es):
    mock_es.indices.exists.return_value = False

    es_client.ensure_index(mock_es)

    mock_es.indices.exists.assert_called_once_with(index=es_client.INDEX_NAME)
    mock_es.indices.create.assert_called_once_with(index=es_client.INDEX_NAME, body=es_client.INDEX_MAPPING)


def test_ensure_index_skips_creation_when_exists(mock_es):
    mock_es.indices.exists.return_value = True

    es_client.ensure_index(mock_es)

    mock_es.indices.exists.assert_called_once_with(index=es_client.INDEX_NAME)
    mock_es.indices.create.assert_not_called()


def test_bulk_upsert_calls_ensure_index_and_helpers_bulk(mock_es):
    documents = [
        {"id": "prop-1", "lonlat": {"lat": 1.0, "lon": 2.0}},
        {"id": "prop-2", "lonlat": {"lat": 3.0, "lon": 4.0}},
    ]

    with patch("clients.es_client.ensure_index") as mock_ensure_index, patch("clients.es_client.helpers.bulk") as mock_bulk:
        es_client.bulk_upsert(mock_es, documents)

        mock_ensure_index.assert_called_once_with(mock_es)

        expected_actions = [
            {"_op_type": "index", "_index": es_client.INDEX_NAME, "_id": "prop-1", "_source": documents[0]},
            {"_op_type": "index", "_index": es_client.INDEX_NAME, "_id": "prop-2", "_source": documents[1]},
        ]
        mock_bulk.assert_called_once_with(mock_es, expected_actions)


def test_bulk_upsert_with_empty_documents(mock_es):
    with patch("clients.es_client.ensure_index") as mock_ensure_index, patch("clients.es_client.helpers.bulk") as mock_bulk:
        es_client.bulk_upsert(mock_es, [])

        mock_ensure_index.assert_called_once_with(mock_es)
        mock_bulk.assert_called_once_with(mock_es, [])
