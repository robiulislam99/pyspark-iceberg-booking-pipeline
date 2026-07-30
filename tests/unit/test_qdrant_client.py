"""
Unit tests for src/clients/qdrant_client.py
"""

import importlib

import src.clients.qdrant_client as qdrant_client_module


class TestGetQdrantClient:
    def test_creates_client_with_configured_url(self, mocker):
        mock_client_cls = mocker.patch("src.clients.qdrant_client.QdrantClient")

        result = qdrant_client_module.get_qdrant_client()

        mock_client_cls.assert_called_once_with(url=qdrant_client_module.QDRANT_URL)
        assert result is mock_client_cls.return_value

    def test_uses_env_var_for_url(self, mocker, monkeypatch):
        monkeypatch.setenv("QDRANT_URL", "http://custom-qdrant:1234")
        importlib.reload(qdrant_client_module)
        mock_client_cls = mocker.patch("src.clients.qdrant_client.QdrantClient")

        qdrant_client_module.get_qdrant_client()

        mock_client_cls.assert_called_once_with(url="http://custom-qdrant:1234")

        # cleanup
        monkeypatch.delenv("QDRANT_URL", raising=False)
        importlib.reload(qdrant_client_module)


class TestEnsureCollection:
    def test_creates_collection_when_not_existing(self, mocker):
        mock_client = mocker.Mock()
        mock_collections_response = mocker.Mock()
        mock_collections_response.collections = []
        mock_client.get_collections.return_value = mock_collections_response

        qdrant_client_module.ensure_collection(mock_client)

        mock_client.create_collection.assert_called_once()
        call_kwargs = mock_client.create_collection.call_args.kwargs
        assert call_kwargs["collection_name"] == qdrant_client_module.COLLECTION_NAME
        assert call_kwargs["vectors_config"].size == qdrant_client_module.VECTOR_SIZE

    def test_skips_creation_when_collection_exists(self, mocker):
        mock_client = mocker.Mock()
        mock_existing_collection = mocker.Mock()
        mock_existing_collection.name = qdrant_client_module.COLLECTION_NAME
        mock_collections_response = mocker.Mock()
        mock_collections_response.collections = [mock_existing_collection]
        mock_client.get_collections.return_value = mock_collections_response

        qdrant_client_module.ensure_collection(mock_client)

        mock_client.create_collection.assert_not_called()

    def test_checks_collections_among_multiple_existing(self, mocker):
        mock_client = mocker.Mock()
        other_collection = mocker.Mock()
        other_collection.name = "some_other_collection"
        target_collection = mocker.Mock()
        target_collection.name = qdrant_client_module.COLLECTION_NAME
        mock_collections_response = mocker.Mock()
        mock_collections_response.collections = [other_collection, target_collection]
        mock_client.get_collections.return_value = mock_collections_response

        qdrant_client_module.ensure_collection(mock_client)

        mock_client.create_collection.assert_not_called()

    def test_uses_cosine_distance(self, mocker):
        mock_client = mocker.Mock()
        mock_collections_response = mocker.Mock()
        mock_collections_response.collections = []
        mock_client.get_collections.return_value = mock_collections_response

        qdrant_client_module.ensure_collection(mock_client)

        call_kwargs = mock_client.create_collection.call_args.kwargs
        assert call_kwargs["vectors_config"].distance.name == "COSINE"


class TestBulkUpsert:
    def test_upserts_points_to_collection(self, mocker):
        mock_client = mocker.Mock()
        mocker.patch(
            "src.clients.qdrant_client.get_qdrant_client",
            return_value=mock_client,
        )
        mock_ensure_collection = mocker.patch("src.clients.qdrant_client.ensure_collection")
        fake_points = [mocker.Mock(), mocker.Mock()]

        qdrant_client_module.bulk_upsert(fake_points)

        mock_ensure_collection.assert_called_once_with(mock_client)
        mock_client.upsert.assert_called_once_with(
            collection_name=qdrant_client_module.COLLECTION_NAME,
            points=fake_points,
        )

    def test_ensures_collection_before_upsert(self, mocker):
        mock_client = mocker.Mock()
        mocker.patch(
            "src.clients.qdrant_client.get_qdrant_client",
            return_value=mock_client,
        )
        call_order = []
        mocker.patch(
            "src.clients.qdrant_client.ensure_collection",
            side_effect=lambda c: call_order.append("ensure_collection"),
        )
        mock_client.upsert.side_effect = lambda **kwargs: call_order.append("upsert")

        qdrant_client_module.bulk_upsert([])

        assert call_order == ["ensure_collection", "upsert"]

    def test_handles_empty_points_list(self, mocker):
        mock_client = mocker.Mock()
        mocker.patch(
            "src.clients.qdrant_client.get_qdrant_client",
            return_value=mock_client,
        )
        mocker.patch("src.clients.qdrant_client.ensure_collection")

        qdrant_client_module.bulk_upsert([])

        mock_client.upsert.assert_called_once_with(
            collection_name=qdrant_client_module.COLLECTION_NAME,
            points=[],
        )

    def test_creates_new_client_per_call(self, mocker):
        mock_get_client = mocker.patch(
            "src.clients.qdrant_client.get_qdrant_client",
            return_value=mocker.Mock(),
        )
        mocker.patch("src.clients.qdrant_client.ensure_collection")

        qdrant_client_module.bulk_upsert([])
        qdrant_client_module.bulk_upsert([])

        assert mock_get_client.call_count == 2
