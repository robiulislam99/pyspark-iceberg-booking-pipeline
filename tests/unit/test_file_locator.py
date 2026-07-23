"""
Unit tests for core.file_locator. Uses pytest's built-in tmp_path
fixture to create real, throwaway JSON files -- this tests the actual
file-reading/parsing logic, not mocked stand-ins for it.
"""

import json

import pytest

from core import file_locator


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    """Points BOOKING_DATA_DIR at a temporary directory for this test only."""
    monkeypatch.setenv("BOOKING_DATA_DIR", str(tmp_path))
    return tmp_path


class TestGetChangelogIds:
    def test_flat_list_shape(self, data_dir):
        folder = data_dir / "changelog" / "20260714"
        folder.mkdir(parents=True)
        (folder / "booking_changed_20260708.json").write_text(json.dumps([123, 456]))

        result = file_locator.get_changelog_ids("20260714", "changed")
        assert result == [123, 456]

    def test_wrapped_dict_shape(self, data_dir):
        folder = data_dir / "changelog" / "20260714"
        folder.mkdir(parents=True)
        (folder / "booking_changed_20260708.json").write_text(json.dumps({"changed": [789]}))

        result = file_locator.get_changelog_ids("20260714", "changed")
        assert result == [789]

    def test_missing_folder_returns_empty_list(self, data_dir):
        assert file_locator.get_changelog_ids("20260714", "changed") == []

    def test_filename_date_mismatch_is_tolerated(self, data_dir):
        """
        Folder is dated 20260714 but the filename embeds 20260708 --
        this is a deliberate, documented tolerance (test data reused
        under renamed date folders), not a bug.
        """
        folder = data_dir / "changelog" / "20260714"
        folder.mkdir(parents=True)
        (folder / "booking_changed_20260708.json").write_text(json.dumps([1]))

        assert file_locator.get_changelog_ids("20260714", "changed") == [1]


class TestReadFeedRecords:
    def test_wrapped_shape_unwraps_rental_property_key(self, data_dir):
        folder = data_dir / "accommodation_details" / "20260714" / "changed"
        folder.mkdir(parents=True)
        (folder / "record_0.json").write_text(json.dumps({"rental_property": {"id": 1}}))

        records = list(
            file_locator.read_feed_records("accommodation_details", "20260714", "changed")
        )
        assert records == [{"id": 1}]

    def test_flat_array_shape_yields_each_item(self, data_dir):
        folder = data_dir / "search" / "20260714" / "changed"
        folder.mkdir(parents=True)
        (folder / "record_0.json").write_text(json.dumps([{"id": 1}, {"id": 2}]))

        records = list(file_locator.read_feed_records("search", "20260714", "changed"))
        assert records == [{"id": 1}, {"id": 2}]

    def test_missing_bucket_yields_nothing(self, data_dir):
        records = list(
            file_locator.read_feed_records("accommodation_details", "20260714", "changed")
        )
        assert records == []


class TestBuildSearchPriceMap:
    def test_detects_free_cancellation(self, data_dir):
        folder = data_dir / "search" / "20260714" / "changed"
        folder.mkdir(parents=True)
        record = {
            "id": 1,
            "currency": {"booker": "USD"},
            "price": {"base": {"booker_currency": 100}},
            "products": [{"policies": {"cancellation": {"type": "free_cancellation"}}}],
        }
        (folder / "record_0.json").write_text(json.dumps([record]))

        price_map = file_locator.build_search_price_map("20260714")
        assert price_map[1]["free_cancellation"] is True
        assert price_map[1]["currency"] == "USD"
