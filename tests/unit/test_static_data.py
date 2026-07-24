"""
Unit tests for the static reference-data loader module (e.g. src/core/static_data.py).

These functions use @lru_cache / @cache, so caches must be cleared before
each test to avoid state leaking between tests.

Run:
    docker compose exec spark pytest tests/unit/test_static_data.py -v
"""

import json

import pytest

# Adjust this import to match wherever this module actually lives in src/
import core.static_data as static_data


@pytest.fixture(autouse=True)
def clear_all_caches():
    """Ensure no cached values leak between tests."""
    static_data.clear_cache()
    yield
    static_data.clear_cache()


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKING_DATA_DIR", str(tmp_path))
    return tmp_path


def _write_json(base_dir, relative_path, content):
    file_path = base_dir / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(json.dumps(content), encoding="utf-8")


# ---------------------------------------------------------------------------
# _load_json / missing file behavior
# ---------------------------------------------------------------------------


def test_load_json_returns_empty_dict_when_file_missing(data_dir):
    result = static_data._load_json("does/not/exist.json")
    assert result == {}


def test_load_json_reads_existing_file(data_dir):
    _write_json(data_dir, "custom_static/hotel_types.json", {"220": "Holiday homes"})

    result = static_data._load_json("custom_static/hotel_types.json")
    assert result == {"220": "Holiday homes"}


# ---------------------------------------------------------------------------
# Simple lru_cache-wrapped loaders
# ---------------------------------------------------------------------------


def test_get_hotel_types(data_dir):
    _write_json(data_dir, "custom_static/hotel_types.json", {"220": "Holiday homes"})
    assert static_data.get_hotel_types() == {"220": "Holiday homes"}


def test_get_hotel_types_caches_result(data_dir):
    _write_json(data_dir, "custom_static/hotel_types.json", {"220": "Holiday homes"})
    first = static_data.get_hotel_types()

    # Change the file on disk -- cached call should still return old value.
    _write_json(data_dir, "custom_static/hotel_types.json", {"220": "Changed"})
    second = static_data.get_hotel_types()

    assert first == second == {"220": "Holiday homes"}


def test_get_amenity_map(data_dir):
    _write_json(data_dir, "static/amenity_map.json", {"elevator": "Accessibility"})
    assert static_data.get_amenity_map() == {"elevator": "Accessibility"}


def test_get_chain_and_brand(data_dir):
    _write_json(data_dir, "static/chain_and_brand.json", {"marriott_id": "Marriott"})
    assert static_data.get_chain_and_brand() == {"marriott_id": "Marriott"}


def test_get_meal_translations(data_dir):
    _write_json(data_dir, "custom_static/meal_translations.json", {"breakfast": {"en-us": "Breakfast"}})
    assert static_data.get_meal_translations() == {"breakfast": {"en-us": "Breakfast"}}


# ---------------------------------------------------------------------------
# get_location_mapping (parameterized @cache)
# ---------------------------------------------------------------------------


def test_get_location_mapping_lowercases_country_code(data_dir):
    _write_json(data_dir, "static/location_mapping/bz/city.json", {"-1397214": "Xixerella"})

    result = static_data.get_location_mapping("BZ", "city")
    assert result == {"-1397214": "Xixerella"}


def test_get_location_mapping_missing_returns_empty(data_dir):
    result = static_data.get_location_mapping("zz", "city")
    assert result == {}


# ---------------------------------------------------------------------------
# get_accommodation_type_name_map (derived from get_constants)
# ---------------------------------------------------------------------------


def test_get_accommodation_type_name_map(data_dir):
    _write_json(
        data_dir,
        "static/constants.json",
        {
            "accommodation_types": {
                "220": {"name": {"en-us": "Vacation Home"}},
                "999": {"name": {}},  # no en-us name -- should be excluded
            }
        },
    )

    result = static_data.get_accommodation_type_name_map()
    assert result == {"220": "Vacation Home"}


def test_get_accommodation_type_name_map_empty_constants(data_dir):
    result = static_data.get_accommodation_type_name_map()
    assert result == {}


# ---------------------------------------------------------------------------
# get_property_type_category_map (derived from get_property_type_categories)
# ---------------------------------------------------------------------------


def test_get_property_type_category_map(data_dir):
    _write_json(
        data_dir,
        "static/property_type_categories.json",
        {
            "property_type_mapping": {
                "mapped": [
                    {"property_type_name": "Aparthotels", "group_name": "Apartment"},
                    {"property_type_name": "Vacation Home", "group_name": "House"},
                    {"group_name": "NoName"},  # missing property_type_name -- excluded
                    "not-a-dict",  # non-dict row -- excluded
                ]
            }
        },
    )

    result = static_data.get_property_type_category_map()
    assert result == {"Aparthotels": "Apartment", "Vacation Home": "House"}


def test_get_property_type_category_map_missing_file(data_dir):
    result = static_data.get_property_type_category_map()
    assert result == {}


# ---------------------------------------------------------------------------
# get_country_name_map / resolve_country_name
# ---------------------------------------------------------------------------


def test_get_country_name_map_lowercases_keys(data_dir):
    _write_json(
        data_dir,
        "static/location_mapping/countries.json",
        {"AD": "Andorra", "ae": "United Arab Emirates"},
    )

    result = static_data.get_country_name_map()
    assert result == {"ad": "Andorra", "ae": "United Arab Emirates"}


def test_resolve_country_name_found(data_dir):
    _write_json(data_dir, "static/location_mapping/countries.json", {"ad": "Andorra"})
    assert static_data.resolve_country_name("AD") == "Andorra"


def test_resolve_country_name_not_found(data_dir):
    _write_json(data_dir, "static/location_mapping/countries.json", {"ad": "Andorra"})
    assert static_data.resolve_country_name("zz") == ""


def test_resolve_country_name_empty_input(data_dir):
    assert static_data.resolve_country_name("") == ""
    assert static_data.resolve_country_name(None) == ""


# ---------------------------------------------------------------------------
# get_city_name_map / resolve_city_name
# ---------------------------------------------------------------------------


def test_get_city_name_map(data_dir):
    _write_json(
        data_dir,
        "static/location_mapping/ae/city.json",
        [{"city_code": -784605, "city": "Wāsiţ"}, {"city": "NoCode"}],
    )

    result = static_data.get_city_name_map("ae")
    assert result == {"-784605": "Wāsiţ"}


def test_resolve_city_name_found(data_dir):
    _write_json(data_dir, "static/location_mapping/ae/city.json", [{"city_code": -784605, "city": "Wāsiţ"}])
    assert static_data.resolve_city_name("ae", -784605) == "Wāsiţ"


def test_resolve_city_name_missing_country_or_code(data_dir):
    assert static_data.resolve_city_name("", -784605) == ""
    assert static_data.resolve_city_name("ae", None) == ""


# ---------------------------------------------------------------------------
# get_accommodation_facility_map / get_facility_type_name_map
# ---------------------------------------------------------------------------


def test_get_accommodation_facility_map(data_dir):
    _write_json(
        data_dir,
        "static/constants.json",
        {
            "accommodation_facilities": {
                "2": {"name": {"en-us": "Parking"}, "facility_type": 16},
            }
        },
    )

    result = static_data.get_accommodation_facility_map()
    assert result == {"2": {"name": "Parking", "facility_type": 16}}


def test_get_facility_type_name_map(data_dir):
    _write_json(
        data_dir,
        "static/constants.json",
        {"facility_types": {"16": {"name": {"en-us": "General"}}}},
    )

    result = static_data.get_facility_type_name_map()
    assert result == {"16": "General"}


# ---------------------------------------------------------------------------
# clear_cache
# ---------------------------------------------------------------------------


def test_clear_cache_forces_reload_from_disk(data_dir):
    _write_json(data_dir, "custom_static/hotel_types.json", {"220": "Holiday homes"})
    first = static_data.get_hotel_types()

    _write_json(data_dir, "custom_static/hotel_types.json", {"220": "Updated"})
    static_data.clear_cache()
    second = static_data.get_hotel_types()

    assert first == {"220": "Holiday homes"}
    assert second == {"220": "Updated"}
