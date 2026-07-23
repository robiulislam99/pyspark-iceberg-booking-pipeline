"""
Unit tests for core.processor -- all pure functions, no I/O, so no
mocking is needed here at all.
"""

import pytest

from core.processor import (
    get_first_room,
    process_rental_property,
    resolve_checkin_age_policy,
    resolve_images,
    resolve_latlon,
    resolve_pets_policy,
)


class TestResolveLatlon:
    def test_valid_coordinates_produce_ewkt_point(self):
        result = resolve_latlon(27.797983, -97.085391)
        assert result == "SRID=4326;POINT (-97.085391 27.797983)"

    def test_missing_latitude_returns_none(self):
        assert resolve_latlon(None, -97.085391) is None

    def test_missing_longitude_returns_none(self):
        assert resolve_latlon(27.797983, None) is None

    def test_non_numeric_input_returns_none(self):
        assert resolve_latlon("not-a-number", -97.085391) is None


class TestResolveImages:
    def test_main_photo_becomes_feature_image(self):
        photos = [
            {"main_photo": False, "url": {"standard": "https://example.com/a.jpg"}},
            {"main_photo": True, "url": {"standard": "https://example.com/b.jpg"}},
        ]
        feature_image, images = resolve_images(photos)
        assert feature_image == "https://example.com/b.jpg"
        assert images == ["https://example.com/a.jpg", "https://example.com/b.jpg"]

    def test_no_main_photo_falls_back_to_first(self):
        photos = [
            {"main_photo": False, "url": {"standard": "https://example.com/a.jpg"}},
            {"main_photo": False, "url": {"standard": "https://example.com/b.jpg"}},
        ]
        feature_image, _ = resolve_images(photos)
        assert feature_image == "https://example.com/a.jpg"

    def test_empty_photos_returns_empty(self):
        assert resolve_images([]) == ("", [])
        assert resolve_images(None) == ("", [])


class TestResolvePoliciesText:
    @pytest.mark.parametrize(
        "allowed,expected",
        [
            ("yes", "Pets are allowed"),
            ("no", "Pets are not allowed"),
            (None, "Pet policy not specified"),
        ],
    )
    def test_pets_policy_text(self, allowed, expected):
        assert resolve_pets_policy({"pets": {"allowed": allowed}}) == expected

    @pytest.mark.parametrize(
        "min_age,expected",
        [
            (18, "Only adults are allowed to check in"),
            (25, "Only adults are allowed to check in"),
            (0, "Anyone can check in"),
            (None, "Anyone can check in"),
        ],
    )
    def test_checkin_age_policy_text(self, min_age, expected):
        assert resolve_checkin_age_policy({"minimum_checkin_age": min_age}) == expected


class TestGetFirstRoom:
    def test_returns_first_room(self):
        rooms = [{"bedrooms": 1}, {"bedrooms": 2}]
        assert get_first_room({"rooms": rooms}) == {"bedrooms": 1}

    def test_no_rooms_returns_empty_dict(self):
        assert get_first_room({}) == {}
        assert get_first_room({"rooms": []}) == {}


class TestProcessRentalProperty:
    """Integration-within-a-unit-test: the full pure transformation, one record."""

    def test_maps_identity_fields(self, raw_accommodation_record, search_price_map):
        result = process_rental_property(raw_accommodation_record, search_price_map)
        assert result["external_id"] == "BC-12908249"
        assert result["feed_provider_id"] == "12908249"

    def test_maps_location_fields(self, raw_accommodation_record, search_price_map):
        result = process_rental_property(raw_accommodation_record, search_price_map)
        assert result["country_code"] == "us"
        assert result["latlon"] == "SRID=4326;POINT (-97.085391 27.797983)"

    def test_maps_pricing_from_search_price_map(self, raw_accommodation_record, search_price_map):
        result = process_rental_property(raw_accommodation_record, search_price_map)
        assert result["price"] == 1301
        assert result["currency"] == "USD"

    def test_property_name_is_slugified(self, raw_accommodation_record, search_price_map):
        result = process_rental_property(raw_accommodation_record, search_price_map)
        assert result["property_slug"] == "villa-palmilla"

    def test_is_published_reflects_accommodation_status(
        self, raw_accommodation_record, search_price_map
    ):
        raw_accommodation_record["accommodation_status"] = "closed_temporarily"
        result = process_rental_property(raw_accommodation_record, search_price_map)
        assert result["is_published"] is False

    def test_raw_data_is_preserved(self, raw_accommodation_record, search_price_map):
        result = process_rental_property(raw_accommodation_record, search_price_map)
        assert result["raw_data"] == raw_accommodation_record
