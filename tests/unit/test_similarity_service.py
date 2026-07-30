"""
Unit tests for src/core/similarity_service.py
"""

import src.core.similarity_service as similarity_service


class TestGetSimilarProperties:
    def test_returns_none_when_source_property_not_found(self, mocker):
        mock_client = mocker.Mock()
        mock_client.retrieve.return_value = []
        mocker.patch(
            "src.core.similarity_service.get_qdrant_client",
            return_value=mock_client,
        )
        mocker.patch(
            "src.core.similarity_service.external_id_to_point_id",
            return_value="fake-point-id",
        )

        result = similarity_service.get_similar_properties("BC-12908249")

        assert result is None
        mock_client.search.assert_not_called()

    def test_returns_similar_properties_excluding_source(self, mocker):
        mock_client = mocker.Mock()
        mock_source_point = mocker.Mock()
        mock_source_point.vector = [0.1, 0.2, 0.3]
        mock_client.retrieve.return_value = [mock_source_point]

        mock_result_self = mocker.Mock()
        mock_result_self.payload = {"external_id": "BC-12908249", "name": "Source"}
        mock_result_self.score = 1.0

        mock_result_other_1 = mocker.Mock()
        mock_result_other_1.payload = {"external_id": "BC-99999999", "name": "Other 1"}
        mock_result_other_1.score = 0.95

        mock_result_other_2 = mocker.Mock()
        mock_result_other_2.payload = {"external_id": "BC-88888888", "name": "Other 2"}
        mock_result_other_2.score = 0.90

        mock_client.search.return_value = [
            mock_result_self,
            mock_result_other_1,
            mock_result_other_2,
        ]

        mocker.patch(
            "src.core.similarity_service.get_qdrant_client",
            return_value=mock_client,
        )
        mocker.patch(
            "src.core.similarity_service.external_id_to_point_id",
            return_value="fake-point-id",
        )

        result = similarity_service.get_similar_properties("BC-12908249", k=5)

        assert result == [
            {"external_id": "BC-99999999", "name": "Other 1", "score": 0.95},
            {"external_id": "BC-88888888", "name": "Other 2", "score": 0.90},
        ]

    def test_respects_k_limit_after_excluding_source(self, mocker):
        mock_client = mocker.Mock()
        mock_source_point = mocker.Mock()
        mock_source_point.vector = [0.1, 0.2, 0.3]
        mock_client.retrieve.return_value = [mock_source_point]

        results = []
        for i in range(4):
            r = mocker.Mock()
            r.payload = {"external_id": f"BC-{i}", "name": f"Prop {i}"}
            r.score = 1.0 - (i * 0.01)
            results.append(r)
        mock_client.search.return_value = results

        mocker.patch(
            "src.core.similarity_service.get_qdrant_client",
            return_value=mock_client,
        )
        mocker.patch(
            "src.core.similarity_service.external_id_to_point_id",
            return_value="fake-point-id",
        )

        result = similarity_service.get_similar_properties("BC-source", k=2)

        assert len(result) == 2

    def test_calls_search_with_correct_limit(self, mocker):
        mock_client = mocker.Mock()
        mock_source_point = mocker.Mock()
        mock_source_point.vector = [0.1, 0.2, 0.3]
        mock_client.retrieve.return_value = [mock_source_point]
        mock_client.search.return_value = []

        mocker.patch(
            "src.core.similarity_service.get_qdrant_client",
            return_value=mock_client,
        )
        mocker.patch(
            "src.core.similarity_service.external_id_to_point_id",
            return_value="fake-point-id",
        )

        similarity_service.get_similar_properties("BC-12908249", k=7)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["limit"] == 8

    def test_applies_published_filter_by_default(self, mocker):
        mock_client = mocker.Mock()
        mock_source_point = mocker.Mock()
        mock_source_point.vector = [0.1, 0.2, 0.3]
        mock_client.retrieve.return_value = [mock_source_point]
        mock_client.search.return_value = []

        mocker.patch(
            "src.core.similarity_service.get_qdrant_client",
            return_value=mock_client,
        )
        mocker.patch(
            "src.core.similarity_service.external_id_to_point_id",
            return_value="fake-point-id",
        )

        similarity_service.get_similar_properties("BC-12908249")

        call_kwargs = mock_client.search.call_args.kwargs
        query_filter = call_kwargs["query_filter"]
        assert query_filter is not None
        assert query_filter.must[0].key == "published"
        assert query_filter.must[0].match.value is True

    def test_omits_filter_when_published_only_false(self, mocker):
        mock_client = mocker.Mock()
        mock_source_point = mocker.Mock()
        mock_source_point.vector = [0.1, 0.2, 0.3]
        mock_client.retrieve.return_value = [mock_source_point]
        mock_client.search.return_value = []

        mocker.patch(
            "src.core.similarity_service.get_qdrant_client",
            return_value=mock_client,
        )
        mocker.patch(
            "src.core.similarity_service.external_id_to_point_id",
            return_value="fake-point-id",
        )

        similarity_service.get_similar_properties("BC-12908249", published_only=False)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["query_filter"] is None

    def test_uses_source_vector_for_search(self, mocker):
        mock_client = mocker.Mock()
        mock_source_point = mocker.Mock()
        mock_source_point.vector = [0.5, 0.6, 0.7]
        mock_client.retrieve.return_value = [mock_source_point]
        mock_client.search.return_value = []

        mocker.patch(
            "src.core.similarity_service.get_qdrant_client",
            return_value=mock_client,
        )
        mocker.patch(
            "src.core.similarity_service.external_id_to_point_id",
            return_value="fake-point-id",
        )

        similarity_service.get_similar_properties("BC-12908249")

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs["query_vector"] == [0.5, 0.6, 0.7]

    def test_retrieves_source_point_with_correct_id(self, mocker):
        mock_client = mocker.Mock()
        mock_source_point = mocker.Mock()
        mock_source_point.vector = [0.1, 0.2, 0.3]
        mock_client.retrieve.return_value = [mock_source_point]
        mock_client.search.return_value = []

        mocker.patch(
            "src.core.similarity_service.get_qdrant_client",
            return_value=mock_client,
        )
        mock_convert = mocker.patch(
            "src.core.similarity_service.external_id_to_point_id",
            return_value="converted-point-id",
        )

        similarity_service.get_similar_properties("BC-12908249")

        mock_convert.assert_called_once_with("BC-12908249")
        mock_client.retrieve.assert_called_once_with(
            collection_name=similarity_service.COLLECTION_NAME,
            ids=["converted-point-id"],
            with_vectors=True,
        )

    def test_returns_empty_list_when_only_source_matches(self, mocker):
        mock_client = mocker.Mock()
        mock_source_point = mocker.Mock()
        mock_source_point.vector = [0.1, 0.2, 0.3]
        mock_client.retrieve.return_value = [mock_source_point]

        mock_result_self = mocker.Mock()
        mock_result_self.payload = {"external_id": "BC-12908249", "name": "Source"}
        mock_result_self.score = 1.0
        mock_client.search.return_value = [mock_result_self]

        mocker.patch(
            "src.core.similarity_service.get_qdrant_client",
            return_value=mock_client,
        )
        mocker.patch(
            "src.core.similarity_service.external_id_to_point_id",
            return_value="fake-point-id",
        )

        result = similarity_service.get_similar_properties("BC-12908249")

        assert result == []
