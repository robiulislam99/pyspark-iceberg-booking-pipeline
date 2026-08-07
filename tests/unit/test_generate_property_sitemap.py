"""Unit tests for scripts/generate_property_sitemap.py"""

import unittest
from unittest import mock

from scripts.generate_property_sitemap import (
    OUTPUT_DIR,
    TABLE,
    load_published_rows_iterator,
    main,
)


class TestLoadPublishedRowsIterator(unittest.TestCase):
    def test_runs_expected_sql_query(self):
        mock_spark = mock.MagicMock()
        mock_df = mock.MagicMock()
        mock_df.toLocalIterator.return_value = iter([])
        mock_spark.sql.return_value = mock_df

        list(load_published_rows_iterator(mock_spark))

        args, _ = mock_spark.sql.call_args
        query = args[0]
        self.assertIn(TABLE, query)
        self.assertIn("is_published = true", query)
        self.assertIn("external_id", query)
        self.assertIn("property_slug", query)
        self.assertIn("last_synced_at", query)
        self.assertIn("feature_image", query)
        self.assertIn("images", query)

    def test_converts_each_row_to_dict(self):
        mock_spark = mock.MagicMock()
        mock_df = mock.MagicMock()
        row1 = mock.MagicMock()
        row1.asDict.return_value = {"external_id": "1"}
        row2 = mock.MagicMock()
        row2.asDict.return_value = {"external_id": "2"}
        mock_df.toLocalIterator.return_value = iter([row1, row2])
        mock_spark.sql.return_value = mock_df

        results = list(load_published_rows_iterator(mock_spark))

        self.assertEqual(results, [{"external_id": "1"}, {"external_id": "2"}])

    def test_returns_lazy_generator_not_a_list(self):
        mock_spark = mock.MagicMock()
        mock_df = mock.MagicMock()
        mock_df.toLocalIterator.return_value = iter([])
        mock_spark.sql.return_value = mock_df

        result = load_published_rows_iterator(mock_spark)

        self.assertTrue(hasattr(result, "__next__"))

    def test_empty_table_yields_no_rows(self):
        mock_spark = mock.MagicMock()
        mock_df = mock.MagicMock()
        mock_df.toLocalIterator.return_value = iter([])
        mock_spark.sql.return_value = mock_df

        results = list(load_published_rows_iterator(mock_spark))

        self.assertEqual(results, [])


class TestMain(unittest.TestCase):
    @mock.patch("scripts.generate_property_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_property_sitemap.load_published_rows_iterator")
    @mock.patch("scripts.generate_property_sitemap.get_spark")
    def test_creates_spark_session_with_expected_app_name(self, mock_get_spark, mock_load_rows, mock_write):
        mock_spark = mock.MagicMock()
        mock_get_spark.return_value = mock_spark
        mock_load_rows.return_value = iter([])
        mock_write.return_value = []

        main()

        mock_get_spark.assert_called_once_with("generate-sitemap")

    @mock.patch("scripts.generate_property_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_property_sitemap.load_published_rows_iterator")
    @mock.patch("scripts.generate_property_sitemap.get_spark")
    def test_stops_spark_session_on_success(self, mock_get_spark, mock_load_rows, mock_write):
        mock_spark = mock.MagicMock()
        mock_get_spark.return_value = mock_spark
        mock_load_rows.return_value = iter([])
        mock_write.return_value = []

        main()

        mock_spark.stop.assert_called_once()

    @mock.patch("scripts.generate_property_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_property_sitemap.load_published_rows_iterator")
    @mock.patch("scripts.generate_property_sitemap.get_spark")
    def test_stops_spark_session_even_when_write_raises(self, mock_get_spark, mock_load_rows, mock_write):
        mock_spark = mock.MagicMock()
        mock_get_spark.return_value = mock_spark
        mock_load_rows.return_value = iter([])
        mock_write.side_effect = RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            main()

        mock_spark.stop.assert_called_once()

    @mock.patch("scripts.generate_property_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_property_sitemap.load_published_rows_iterator")
    @mock.patch("scripts.generate_property_sitemap.get_spark")
    def test_passes_row_iterator_and_output_settings_to_writer(self, mock_get_spark, mock_load_rows, mock_write):
        mock_spark = mock.MagicMock()
        mock_get_spark.return_value = mock_spark
        sentinel_iterator = iter([{"external_id": "1"}])
        mock_load_rows.return_value = sentinel_iterator
        mock_write.return_value = ["property-sitemap.xml.gz"]

        with mock.patch("scripts.generate_property_sitemap.Path.stat") as mock_stat:
            mock_stat.return_value = mock.Mock(st_size=1024)
            main()

        args, _ = mock_write.call_args
        self.assertIs(args[0], sentinel_iterator)
        self.assertEqual(args[1], OUTPUT_DIR)
        self.assertEqual(args[2], "property-sitemap")

    @mock.patch("scripts.generate_property_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_property_sitemap.load_published_rows_iterator")
    @mock.patch("scripts.generate_property_sitemap.get_spark")
    def test_no_filenames_returns_without_stat_calls(self, mock_get_spark, mock_load_rows, mock_write):
        mock_spark = mock.MagicMock()
        mock_get_spark.return_value = mock_spark
        mock_load_rows.return_value = iter([])
        mock_write.return_value = []

        with mock.patch("scripts.generate_property_sitemap.Path.stat") as mock_stat:
            main()
            mock_stat.assert_not_called()

    @mock.patch("scripts.generate_property_sitemap.Path.stat")
    @mock.patch("scripts.generate_property_sitemap.write_sitemap_files")
    @mock.patch("scripts.generate_property_sitemap.load_published_rows_iterator")
    @mock.patch("scripts.generate_property_sitemap.get_spark")
    def test_reports_file_sizes_for_each_written_filename(self, mock_get_spark, mock_load_rows, mock_write, mock_stat):
        mock_spark = mock.MagicMock()
        mock_get_spark.return_value = mock_spark
        mock_load_rows.return_value = iter([])
        mock_write.return_value = ["property-sitemap.xml.gz", "property-sitemap-2.xml.gz"]
        mock_stat.return_value = mock.Mock(st_size=2 * 1024 * 1024)

        main()

        self.assertEqual(mock_stat.call_count, 2)


if __name__ == "__main__":
    unittest.main()
