"""
Unit tests for the Iceberg-row -> Elasticsearch-document mapper
(e.g. src/mappers/document_mapper.py).

Run:
    docker compose exec spark pytest tests/unit/test_document_mapper.py -v
"""

from datetime import datetime

# Adjust this import to match wherever this module actually lives in src/
from mappers.es_document_mapper import _build_property_attributes, _parse_lonlat, to_es_document

# ---------------------------------------------------------------------------
# _parse_lonlat
# ---------------------------------------------------------------------------


def test_parse_lonlat_valid_point():
    result = _parse_lonlat("SRID=4326;POINT (-97.085391 27.797983)")
    assert result == [-97.085391, 27.797983]


def test_parse_lonlat_none_input():
    assert _parse_lonlat(None) is None


def test_parse_lonlat_empty_string():
    assert _parse_lonlat("") is None


def test_parse_lonlat_malformed_string():
    assert _parse_lonlat("not a point at all") is None


def test_parse_lonlat_without_srid_prefix():
    result = _parse_lonlat("POINT (10.5 -20.25)")
    assert result == [10.5, -20.25]


def test_parse_lonlat_positive_and_negative_values():
    result = _parse_lonlat("SRID=4326;POINT (100.123456 -45.654321)")
    assert result == [100.123456, -45.654321]


# ---------------------------------------------------------------------------
# _build_property_attributes
# ---------------------------------------------------------------------------


def test_build_property_attributes_all_true():
    row = {"family_friendly": True, "group_friendly": True}
    policy = {"free_cancellation": True}

    result = _build_property_attributes(row, policy)
    assert result == ["Family Friendly", "Group Friendly", "Free Cancellation"]


def test_build_property_attributes_all_false():
    row = {"family_friendly": False, "group_friendly": False}
    policy = {"free_cancellation": False}

    result = _build_property_attributes(row, policy)
    assert result == []


def test_build_property_attributes_partial():
    row = {"family_friendly": True, "group_friendly": False}
    policy = {"free_cancellation": True}

    result = _build_property_attributes(row, policy)
    assert result == ["Family Friendly", "Free Cancellation"]


def test_build_property_attributes_missing_keys():
    result = _build_property_attributes({}, {})
    assert result == []


# ---------------------------------------------------------------------------
# to_es_document
# ---------------------------------------------------------------------------


def _base_row(**overrides):
    row = {
        "external_id": "ext-1",
        "feed_provider_id": "fp-1",
        "feed": "expedia",
        "feed_provider_url": "https://example.com/prop/1",
        "property_name": "Sea View Villa",
        "property_slug": "sea-view-villa",
        "property_type": "Villa",
        "property_type_category": "House",
        "city": "Cancun",
        "country": "Mexico",
        "country_code": "mx",
        "location_display": "Cancun, Mexico",
        "latlon": "SRID=4326;POINT (-97.085391 27.797983)",
        "star_rating": 4,
        "review_score_general": "8.5",
        "number_of_review": 120,
        "bedroom_count": 3,
        "bathroom_count": 2,
        "occupancy": 6,
        "price": "199.99",
        "min_stay": 2,
        "feature_image": "https://example.com/img.jpg",
        "amenity_categories": ["Pool", "WiFi"],
        "property_flags": '{"is_new": true}',
        "policy": '{"free_cancellation": true}',
        "family_friendly": True,
        "group_friendly": False,
        "is_published": True,
        "created_at": datetime(2026, 1, 1, 12, 0, 0),
        "last_synced_at": datetime(2026, 2, 1, 8, 30, 0),
    }
    row.update(overrides)
    return row


def test_to_es_document_full_row():
    row = _base_row()
    doc = to_es_document(row)

    assert doc["id"] == "ext-1"
    assert doc["feed_provider_id"] == "fp-1"
    assert doc["feed"] == "expedia"
    assert doc["property_name"] == "Sea View Villa"
    assert doc["city"] == "Cancun"
    assert doc["country_code"] == "mx"
    assert doc["display"] == "Cancun, Mexico"
    assert doc["lonlat"] == [-97.085391, 27.797983]
    assert doc["review_score_general"] == 8.5
    assert doc["usd_price"] == 199.99
    assert doc["property_flags"] == {"is_new": True}
    assert doc["property_attributes"] == ["Family Friendly", "Free Cancellation"]
    assert doc["published"] is True
    assert doc["created_at"] == "2026-01-01T12:00:00"
    assert doc["updated_at"] == "2026-02-01T08:30:00"


def test_to_es_document_handles_missing_optional_fields():
    row = {"external_id": "ext-2"}
    doc = to_es_document(row)

    assert doc["id"] == "ext-2"
    assert doc["lonlat"] is None
    assert doc["review_score_general"] is None
    assert doc["usd_price"] is None
    assert doc["property_flags"] == {}
    assert doc["property_attributes"] == []
    assert doc["created_at"] is None
    assert doc["updated_at"] is None


def test_to_es_document_handles_null_json_strings():
    row = _base_row(property_flags=None, policy=None)
    doc = to_es_document(row)

    assert doc["property_flags"] == {}
    assert doc["property_attributes"] == ["Family Friendly"]


def test_to_es_document_price_and_review_score_are_floats():
    row = _base_row(price="49.5", review_score_general="7")
    doc = to_es_document(row)

    assert isinstance(doc["usd_price"], float)
    assert doc["usd_price"] == 49.5
    assert isinstance(doc["review_score_general"], float)
    assert doc["review_score_general"] == 7.0


def test_to_es_document_no_created_or_updated_at():
    row = _base_row(created_at=None, last_synced_at=None)
    doc = to_es_document(row)

    assert doc["created_at"] is None
    assert doc["updated_at"] is None
