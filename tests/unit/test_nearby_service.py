"""
Unit tests for src/core/nearby_service.py

Mocks the Elasticsearch client (clients.es_client.get_es_client) so no
real ES cluster is required.
"""

from unittest.mock import MagicMock, patch

import pytest

from core import nearby_service


def make_es_response(hits):
    """Helper: build an ES-shaped search response from a list of
    (source_dict, sort_list) tuples."""
    return {"hits": {"hits": [{"_source": source, "sort": sort} if sort is not None else {"_source": source} for source, sort in hits]}}


class TestGetNearbyProperties:
    @patch("core.nearby_service.get_es_client")
    def test_returns_mapped_results_sorted_by_distance(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = make_es_response(
            [
                (
                    {
                        "id": "p1",
                        "property_name": "Sea View Villa",
                        "city": "Lisbon",
                        "country": "Portugal",
                        "usd_price": 200,
                        "star_rating": 4.5,
                    },
                    [1.2345],
                ),
                (
                    {
                        "id": "p2",
                        "property_name": "City Loft",
                        "city": "Lisbon",
                        "country": "Portugal",
                        "usd_price": 150,
                        "star_rating": 4.0,
                    },
                    [3.987],
                ),
            ]
        )
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties(lat=38.7, lon=-9.1)

        assert len(results) == 2
        assert results[0]["id"] == "p1"
        assert results[0]["distance_km"] == 1.23
        assert results[1]["id"] == "p2"
        assert results[1]["distance_km"] == 3.99

    @patch("core.nearby_service.get_es_client")
    def test_query_includes_geo_distance_filter_and_sort(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = make_es_response([])
        mock_get_client.return_value = mock_es

        nearby_service.get_nearby_properties(lat=1.0, lon=2.0, radius_km=10, limit=5)

        _, kwargs = mock_es.search.call_args
        body = kwargs["body"]

        assert body["size"] == 5
        geo_filter = body["query"]["bool"]["filter"][0]
        assert geo_filter["geo_distance"]["distance"] == "10km"
        assert geo_filter["geo_distance"]["lonlat"] == {"lat": 1.0, "lon": 2.0}

        sort_clause = body["sort"][0]["_geo_distance"]
        assert sort_clause["lonlat"] == {"lat": 1.0, "lon": 2.0}
        assert sort_clause["order"] == "asc"
        assert sort_clause["unit"] == "km"

        assert mock_es.search.call_args.kwargs["index"] == nearby_service.INDEX_NAME

    @patch("core.nearby_service.get_es_client")
    def test_published_only_true_adds_term_filter(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = make_es_response([])
        mock_get_client.return_value = mock_es

        nearby_service.get_nearby_properties(lat=1.0, lon=2.0, published_only=True)

        body = mock_es.search.call_args.kwargs["body"]
        filters = body["query"]["bool"]["filter"]
        assert {"term": {"published": True}} in filters

    @patch("core.nearby_service.get_es_client")
    def test_published_only_false_omits_term_filter(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = make_es_response([])
        mock_get_client.return_value = mock_es

        nearby_service.get_nearby_properties(lat=1.0, lon=2.0, published_only=False)

        body = mock_es.search.call_args.kwargs["body"]
        filters = body["query"]["bool"]["filter"]
        assert len(filters) == 1
        assert all("term" not in f for f in filters)

    @patch("core.nearby_service.get_es_client")
    def test_no_hits_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = make_es_response([])
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties(lat=1.0, lon=2.0)

        assert results == []

    @patch("core.nearby_service.get_es_client")
    def test_missing_sort_yields_none_distance(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = make_es_response(
            [
                ({"id": "p1"}, None),
            ]
        )
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties(lat=1.0, lon=2.0)

        assert results[0]["distance_km"] is None

    @patch("core.nearby_service.get_es_client")
    def test_missing_source_fields_default_to_none(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = make_es_response(
            [
                ({}, [0.5]),
            ]
        )
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties(lat=1.0, lon=2.0)

        assert results[0]["id"] is None
        assert results[0]["property_name"] is None
        assert results[0]["distance_km"] == 0.5


class TestGetNearbyPropertiesForId:
    @patch("core.nearby_service.get_es_client")
    @patch("core.nearby_service.get_nearby_properties")
    def test_looks_up_lonlat_and_delegates(self, mock_get_nearby, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {
            "found": True,
            "_source": {"lonlat": [-9.1, 38.7]},  # [lon, lat]
        }
        mock_get_client.return_value = mock_es
        mock_get_nearby.return_value = [
            {"id": "self_id"},
            {"id": "other_id"},
        ]

        results = nearby_service.get_nearby_properties_for_id("self_id", radius_km=5, limit=20, published_only=True)

        # lat/lon unpacked correctly (stored as [lon, lat])
        mock_get_nearby.assert_called_once_with(38.7, -9.1, 5, 21, True)
        assert results == [{"id": "other_id"}]

    @patch("core.nearby_service.get_es_client")
    def test_property_not_found_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {"found": False}
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_id("missing_id")

        assert results == []

    @patch("core.nearby_service.get_es_client")
    def test_falsy_doc_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = None
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_id("missing_id")

        assert results == []

    @patch("core.nearby_service.get_es_client")
    def test_missing_lonlat_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {"found": True, "_source": {}}
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_id("p1")

        assert results == []

    @patch("core.nearby_service.get_es_client")
    def test_malformed_lonlat_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {
            "found": True,
            "_source": {"lonlat": [-9.1]},  # wrong length
        }
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_id("p1")

        assert results == []

    @patch("core.nearby_service.get_es_client")
    @patch("core.nearby_service.get_nearby_properties")
    def test_result_limit_respected_after_excluding_self(self, mock_get_nearby, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {
            "found": True,
            "_source": {"lonlat": [1.0, 2.0]},
        }
        mock_get_client.return_value = mock_es
        # limit+1 = 3 requested; self not among them, so 3 come back
        mock_get_nearby.return_value = [
            {"id": "a"},
            {"id": "b"},
            {"id": "c"},
        ]

        results = nearby_service.get_nearby_properties_for_id("self_id", limit=2)

        assert len(results) == 2
        assert results == [{"id": "a"}, {"id": "b"}]

    @patch("core.nearby_service.get_es_client")
    def test_uses_ignore_404_when_fetching_doc(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {"found": False}
        mock_get_client.return_value = mock_es

        nearby_service.get_nearby_properties_for_id("p1")

        _, kwargs = mock_es.get.call_args
        assert kwargs.get("ignore") == [404]
        assert kwargs.get("id") == "p1"
        assert kwargs.get("index") == nearby_service.INDEX_NAME


class TestGetNearbyPropertiesForSitemap:
    @patch("core.nearby_service.get_es_client")
    def test_looks_up_lonlat_and_returns_mapped_rows(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {
            "found": True,
            "_source": {"lonlat": [-9.1, 38.7]},  # [lon, lat]
        }
        mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {
                        "_source": {
                            "id": "other_id",
                            "property_slug": "sea-view-villa",
                            "updated_at": "2024-01-01",
                            "feature_image": "img.jpg",
                        }
                    },
                ]
            }
        }
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_sitemap("self_id", radius_km=5, limit=20)

        assert results == [
            {
                "external_id": "other_id",
                "property_slug": "sea-view-villa",
                "last_synced_at": "2024-01-01",
                "feature_image": "img.jpg",
                "images": [],
            }
        ]

    @patch("core.nearby_service.get_es_client")
    def test_excludes_source_property_itself(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {
            "found": True,
            "_source": {"lonlat": [1.0, 2.0]},
        }
        mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {"_source": {"id": "self_id", "property_slug": "self"}},
                    {"_source": {"id": "other_id", "property_slug": "other"}},
                ]
            }
        }
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_sitemap("self_id")

        assert len(results) == 1
        assert results[0]["external_id"] == "other_id"

    @patch("core.nearby_service.get_es_client")
    def test_property_not_found_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {"found": False}
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_sitemap("missing_id")

        assert results == []

    @patch("core.nearby_service.get_es_client")
    def test_falsy_doc_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = None
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_sitemap("missing_id")

        assert results == []

    @patch("core.nearby_service.get_es_client")
    def test_missing_lonlat_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {"found": True, "_source": {}}
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_sitemap("p1")

        assert results == []

    @patch("core.nearby_service.get_es_client")
    def test_malformed_lonlat_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {
            "found": True,
            "_source": {"lonlat": [-9.1]},  # wrong length
        }
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_sitemap("p1")

        assert results == []

    @patch("core.nearby_service.get_es_client")
    def test_query_includes_published_filter_and_size_limit_plus_one(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {
            "found": True,
            "_source": {"lonlat": [1.0, 2.0]},
        }
        mock_es.search.return_value = {"hits": {"hits": []}}
        mock_get_client.return_value = mock_es

        nearby_service.get_nearby_properties_for_sitemap("p1", radius_km=10, limit=5)

        _, kwargs = mock_es.search.call_args
        body = kwargs["body"]

        assert body["size"] == 6  # limit + 1
        filters = body["query"]["bool"]["filter"]
        assert {"geo_distance": {"distance": "10km", "lonlat": {"lat": 2.0, "lon": 1.0}}} in filters
        assert {"term": {"published": True}} in filters

        sort_clause = body["sort"][0]["_geo_distance"]
        assert sort_clause["lonlat"] == {"lat": 2.0, "lon": 1.0}
        assert sort_clause["order"] == "asc"
        assert sort_clause["unit"] == "km"

        assert mock_es.search.call_args.kwargs["index"] == nearby_service.INDEX_NAME

    @patch("core.nearby_service.get_es_client")
    def test_result_limit_respected(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {
            "found": True,
            "_source": {"lonlat": [1.0, 2.0]},
        }
        mock_es.search.return_value = {
            "hits": {
                "hits": [
                    {"_source": {"id": "a"}},
                    {"_source": {"id": "b"}},
                    {"_source": {"id": "c"}},
                ]
            }
        }
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_sitemap("self_id", limit=2)

        assert len(results) == 2

    @patch("core.nearby_service.get_es_client")
    def test_images_field_always_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {
            "found": True,
            "_source": {"lonlat": [1.0, 2.0]},
        }
        mock_es.search.return_value = {"hits": {"hits": [{"_source": {"id": "other_id"}}]}}
        mock_get_client.return_value = mock_es

        results = nearby_service.get_nearby_properties_for_sitemap("self_id")

        assert results[0]["images"] == []

    @patch("core.nearby_service.get_es_client")
    def test_uses_ignore_404_when_fetching_doc(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.get.return_value = {"found": False}
        mock_get_client.return_value = mock_es

        nearby_service.get_nearby_properties_for_sitemap("p1")

        _, kwargs = mock_es.get.call_args
        assert kwargs.get("ignore") == [404]
        assert kwargs.get("id") == "p1"
        assert kwargs.get("index") == nearby_service.INDEX_NAME


class TestGetAllPublishedIds:
    @patch("core.nearby_service.get_es_client")
    def test_returns_ids_from_hits(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = {"hits": {"hits": [{"_id": "p1"}, {"_id": "p2"}]}}
        mock_get_client.return_value = mock_es

        results = nearby_service.get_all_published_ids()

        assert results == ["p1", "p2"]

    @patch("core.nearby_service.get_es_client")
    def test_query_uses_batch_size_term_filter_and_no_source(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = {"hits": {"hits": []}}
        mock_get_client.return_value = mock_es

        nearby_service.get_all_published_ids(batch_size=500)

        _, kwargs = mock_es.search.call_args
        body = kwargs["body"]

        assert body["query"] == {"term": {"published": True}}
        assert body["_source"] is False
        assert body["size"] == 500
        assert mock_es.search.call_args.kwargs["index"] == nearby_service.INDEX_NAME

    @patch("core.nearby_service.get_es_client")
    def test_default_batch_size_is_10000(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = {"hits": {"hits": []}}
        mock_get_client.return_value = mock_es

        nearby_service.get_all_published_ids()

        body = mock_es.search.call_args.kwargs["body"]
        assert body["size"] == 10000

    @patch("core.nearby_service.get_es_client")
    def test_no_hits_returns_empty_list(self, mock_get_client):
        mock_es = MagicMock()
        mock_es.search.return_value = {"hits": {"hits": []}}
        mock_get_client.return_value = mock_es

        results = nearby_service.get_all_published_ids()

        assert results == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
