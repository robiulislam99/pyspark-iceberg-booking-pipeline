"""Unit tests for scripts/generate_nearby_sitemap.py"""

import sys
import unittest
from unittest import mock

from scripts.generate_nearby_sitemap import (
    OUTPUT_DIR,
    collect_deduplicated_nearby_rows,
    main,
)


class TestCollectDeduplicatedNearbyRows(unittest.TestCase):
    @mock.patch("scripts.generate_nearby_sitemap.get_nearby_properties_for_sitemap")
    @mock.patch("scripts.generate_nearby_sitemap.get_all_published_ids")
    def test_calls_nearby_lookup_for_each_published_id(self, mock_get_ids, mock_get_nearby):
        mock_get_ids.return_value = ["p1", "p2", "p3"]
        mock_get_nearby.return_value = []

        collect_deduplicated_nearby_rows(radius_km=5, limit_per_property=20)

        self.assertEqual(mock_get_nearby.call_count, 3)
        mock_get_nearby.assert_any_call("p1", radius_km=5, limit=20)
        mock_get_nearby.assert_any_call("p2", radius_km=5, limit=20)
        mock_get_nearby.assert_any_call("p3", radius_km=5, limit=20)

    @mock.patch("scripts.generate_nearby_sitemap.get_nearby_properties_for_sitemap")
    @mock.patch("scripts.generate_nearby_sitemap.get_all_published_ids")
    def test_deduplicates_rows_by_external_id(self, mock_get_ids, mock_get_nearby):
        mock_get_ids.return_value = ["p1", "p2"]
        row_a = {"external_id": "a", "property_slug": "listing-a"}
        row_b = {"external_id": "b", "property_slug": "listing-b"}
        mock_get_nearby.side_effect = [
            [row_a],
            [row_a, row_b],
        ]

        result = collect_deduplicated_nearby_rows(radius_km=5, limit_per_property=20)

        self.assertEqual(set(result.keys()), {"a", "b"})
        self.assertEqual(len(result), 2)

    @mock.patch("scripts.generate_nearby_sitemap.get_nearby_properties_for_sitemap")
    @mock.patch("scripts.generate_nearby_sitemap.get_all_published_ids")
    def test_last_write_wins_on_duplicate_external_id(self, mock_get_ids, mock_get_nearby):
        mock_get_ids.return_value = ["p1", "p2"]
        first_version = {"external_id": "a", "property_slug": "old-slug"}
        second_version = {"external_id": "a", "property_slug": "new-slug"}
        mock_get_nearby.side_effect = [
            [first_version],
            [second_version],
        ]

        result = collect_deduplicated_nearby_rows(radius_km=5, limit_per_property=20)

        self.assertEqual(result["a"]["property_slug"], "new-slug")

    @mock.patch("scripts.generate_nearby_sitemap.get_nearby_properties_for_sitemap")
    @mock.patch("scripts.generate_nearby_sitemap.get_all_published_ids")
    def test_no_published_ids_returns_empty_dict(self, mock_get_ids, mock_get_nearby):
        mock_get_ids.return_value = []

        result = collect_deduplicated_nearby_rows(radius_km=5, limit_per_property=20)

        self.assertEqual(result, {})
        mock_get_nearby.assert_not_called()

    @mock.patch("scripts.generate_nearby_sitemap.get_nearby_properties_for_sitemap")
    @mock.patch("scripts.generate_nearby_sitemap.get_all_published_ids")
    def test_no_nearby_matches_for_any_property_returns_empty_dict(self, mock_get_ids, mock_get_nearby):
        mock_get_ids.return_value = ["p1", "p2"]
        mock_get_nearby.return_value = []

        result = collect_deduplicated_nearby_rows(radius_km=5, limit_per_property=20)

        self.assertEqual(result, {})

    @mock.patch("scripts.generate_nearby_sitemap.get_nearby_properties_for_sitemap")
    @mock.patch("scripts.generate_nearby_sitemap.get_all_published_ids")
    def test_passes_radius_and_limit_through_to_each_call(self, mock_get_ids, mock_get_nearby):
        mock_get_ids.return_value = ["p1"]
        mock_get_nearby.return_value = []

        collect_deduplicated_nearby_rows(radius_km=12.5, limit_per_property=7)

        mock_get_nearby.assert_called_once_with("p1", radius_km=12.5, limit=7)


class TestMain(unittest.TestCase):
    def setUp(self):
        self._argv_patcher = mock.patch.object(sys, "argv", ["generate_nearby_sitemap.py"])
        self._argv_patcher.start()

    def tearDown(self):
        self._argv_patcher.stop()

    @mock.patch("scripts.generate_nearby_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_nearby_sitemap.collect_deduplicated_nearby_rows")
    def test_no_unique_rows_skips_writing(self, mock_collect, mock_write):
        mock_collect.return_value = {}

        main()

        mock_write.assert_not_called()

    @mock.patch("scripts.generate_nearby_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_nearby_sitemap.collect_deduplicated_nearby_rows")
    def test_default_radius_and_limit_used_when_no_args(self, mock_collect, mock_write):
        mock_collect.return_value = {}

        main()

        mock_collect.assert_called_once_with(5.0, 20)

    @mock.patch.object(sys, "argv", ["generate_nearby_sitemap.py", "10", "50"])
    @mock.patch("scripts.generate_nearby_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_nearby_sitemap.collect_deduplicated_nearby_rows")
    def test_cli_args_override_radius_and_limit(self, mock_collect, mock_write):
        mock_collect.return_value = {}

        main()

        mock_collect.assert_called_once_with(10.0, 50)

    @mock.patch.object(sys, "argv", ["generate_nearby_sitemap.py", "7.5"])
    @mock.patch("scripts.generate_nearby_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_nearby_sitemap.collect_deduplicated_nearby_rows")
    def test_only_radius_arg_uses_default_limit(self, mock_collect, mock_write):
        mock_collect.return_value = {}

        main()

        mock_collect.assert_called_once_with(7.5, 20)

    @mock.patch("scripts.generate_nearby_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_nearby_sitemap.collect_deduplicated_nearby_rows")
    def test_passes_deduplicated_row_values_to_writer(self, mock_collect, mock_write):
        row_a = {"external_id": "a"}
        row_b = {"external_id": "b"}
        mock_collect.return_value = {"a": row_a, "b": row_b}
        mock_write.return_value = []

        main()

        args, kwargs = mock_write.call_args
        rows_arg = list(args[0])
        self.assertEqual(sorted(rows_arg, key=lambda r: r["external_id"]), [row_a, row_b])
        self.assertEqual(args[1], OUTPUT_DIR)
        self.assertEqual(args[2], "nearby-sitemap")

    @mock.patch("scripts.generate_nearby_sitemap.Path.stat")
    @mock.patch("scripts.generate_nearby_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_nearby_sitemap.collect_deduplicated_nearby_rows")
    def test_reports_file_sizes_for_each_written_filename(self, mock_collect, mock_write, mock_stat):
        mock_collect.return_value = {"a": {"external_id": "a"}}
        mock_write.return_value = ["nearby-sitemap.xml.gz", "nearby-sitemap-2.xml.gz"]
        mock_stat.return_value = mock.Mock(st_size=1024 * 1024)

        main()

        self.assertEqual(mock_stat.call_count, 2)

    @mock.patch("scripts.generate_nearby_sitemap.Path.stat")
    @mock.patch("scripts.generate_nearby_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_nearby_sitemap.collect_deduplicated_nearby_rows")
    def test_returns_early_without_stat_calls_when_no_rows(self, mock_collect, mock_write, mock_stat):
        mock_collect.return_value = {}

        main()

        mock_stat.assert_not_called()
        mock_write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
