"""
Unit tests for src/clients/embedding_client.py
"""

import importlib

import numpy as np
import pytest
import src.clients.embedding_client as embedding_client


@pytest.fixture(autouse=True)
def reset_model_singleton():
    """Ensure the lazy-loaded singleton is reset before and after each test."""
    embedding_client._model = None
    yield
    embedding_client._model = None


class TestGetModel:
    def test_loads_model_when_not_cached(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_sentence_transformer_cls = mocker.patch(
            "src.clients.embedding_client.SentenceTransformer",
            return_value=mock_model_instance,
        )

        result = embedding_client._get_model()

        mock_sentence_transformer_cls.assert_called_once_with(embedding_client.MODEL_NAME)
        assert result is mock_model_instance

    def test_returns_cached_model_without_reloading(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_sentence_transformer_cls = mocker.patch(
            "src.clients.embedding_client.SentenceTransformer",
            return_value=mock_model_instance,
        )

        first_call = embedding_client._get_model()
        second_call = embedding_client._get_model()

        mock_sentence_transformer_cls.assert_called_once_with(embedding_client.MODEL_NAME)
        assert first_call is second_call is mock_model_instance

    def test_uses_env_var_for_model_name(self, mocker, monkeypatch):
        monkeypatch.setenv("EMBEDDING_MODEL_NAME", "custom-model-name")
        importlib.reload(embedding_client)
        mock_model_instance = mocker.Mock()
        mock_sentence_transformer_cls = mocker.patch(
            "src.clients.embedding_client.SentenceTransformer",
            return_value=mock_model_instance,
        )

        embedding_client._get_model()

        mock_sentence_transformer_cls.assert_called_once_with("custom-model-name")

        # cleanup: reload module again without the env var so other tests
        # get the default MODEL_NAME back
        monkeypatch.delenv("EMBEDDING_MODEL_NAME", raising=False)
        importlib.reload(embedding_client)


class TestGenerateEmbedding:
    def test_returns_list_of_floats(self, mocker):
        mock_model_instance = mocker.Mock()
        fake_vector = np.array([0.1, 0.2, 0.3], dtype=np.float32)
        mock_model_instance.encode.return_value = fake_vector
        mocker.patch(
            "src.clients.embedding_client.SentenceTransformer",
            return_value=mock_model_instance,
        )

        result = embedding_client.generate_embedding("a cozy two-bedroom apartment")

        mock_model_instance.encode.assert_called_once_with("a cozy two-bedroom apartment", convert_to_numpy=True)
        assert isinstance(result, list)
        assert result == pytest.approx([0.1, 0.2, 0.3])

    def test_calls_get_model_only_once_across_multiple_calls(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_model_instance.encode.return_value = np.zeros(384, dtype=np.float32)
        mock_sentence_transformer_cls = mocker.patch(
            "src.clients.embedding_client.SentenceTransformer",
            return_value=mock_model_instance,
        )

        embedding_client.generate_embedding("first description")
        embedding_client.generate_embedding("second description")

        mock_sentence_transformer_cls.assert_called_once()
        assert mock_model_instance.encode.call_count == 2

    def test_handles_empty_string_input(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_model_instance.encode.return_value = np.zeros(384, dtype=np.float32)
        mocker.patch(
            "src.clients.embedding_client.SentenceTransformer",
            return_value=mock_model_instance,
        )

        result = embedding_client.generate_embedding("")

        mock_model_instance.encode.assert_called_once_with("", convert_to_numpy=True)
        assert result == pytest.approx([0.0] * 384)

    def test_output_length_matches_model_dimension(self, mocker):
        mock_model_instance = mocker.Mock()
        mock_model_instance.encode.return_value = np.random.rand(384).astype(np.float32)
        mocker.patch(
            "src.clients.embedding_client.SentenceTransformer",
            return_value=mock_model_instance,
        )

        result = embedding_client.generate_embedding("some property description")

        assert len(result) == 384
