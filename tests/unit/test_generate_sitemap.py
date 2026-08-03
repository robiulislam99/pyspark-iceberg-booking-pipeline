"""Unit tests for scripts/generate_sitemap.py

Spark and disk I/O are mocked so these tests run in isolation, fast, and
without touching /app/data/sitemaps.
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET

from core.sitemap_generator import SITEMAP_NS
from scripts import generate_sitemap

NS = {"sm": SITEMAP_NS}


def _make_row(external_id="1", property_slug="a"):
    return {
        "external_id": external_id,
        "property_slug": property_slug,
        "last_synced_at": None,
        "feature_image": None,
        "images": None,
    }


class TestLoadPublishedRows(unittest.TestCase):
    def test_runs_expected_query_and_returns_rows_as_dicts(self):
        mock_row_1 = mock.Mock()
        mock_row_1.asDict.return_value = _make_row("1", "listing-1")
        mock_row_2 = mock.Mock()
        mock_row_2.asDict.return_value = _make_row("2", "listing-2")

        mock_df = mock.Mock()
        mock_df.collect.return_value = [mock_row_1, mock_row_2]

        mock_spark = mock.Mock()
        mock_spark.sql.return_value = mock_df

        rows = generate_sitemap.load_published_rows(mock_spark)

        self.assertEqual(rows, [_make_row("1", "listing-1"), _make_row("2", "listing-2")])

        # Confirm the query targets the right table and filters on is_published.
        query = mock_spark.sql.call_args.args[0]
        self.assertIn(generate_sitemap.TABLE, query)
        self.assertIn("is_published = true", query)

    def test_no_published_rows_returns_empty_list(self):
        mock_df = mock.Mock()
        mock_df.collect.return_value = []
        mock_spark = mock.Mock()
        mock_spark.sql.return_value = mock_df

        self.assertEqual(generate_sitemap.load_published_rows(mock_spark), [])


class TestMain(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmpdir.name) / "sitemaps"

        # Patch the module-level OUTPUT_DIR so nothing touches /app/data/sitemaps.
        self.output_dir_patcher = mock.patch.object(generate_sitemap, "OUTPUT_DIR", self.output_dir)
        self.output_dir_patcher.start()

        self.get_spark_patcher = mock.patch.object(generate_sitemap, "get_spark")
        self.mock_get_spark = self.get_spark_patcher.start()

        self.load_rows_patcher = mock.patch.object(generate_sitemap, "load_published_rows")
        self.mock_load_rows = self.load_rows_patcher.start()

    def tearDown(self):
        self.output_dir_patcher.stop()
        self.get_spark_patcher.stop()
        self.load_rows_patcher.stop()
        self._tmpdir.cleanup()

    def test_no_rows_does_not_create_output_dir_or_write_files(self):
        self.mock_load_rows.return_value = []

        generate_sitemap.main()

        self.assertFalse(self.output_dir.exists())

    def test_calls_get_spark_with_expected_app_name(self):
        self.mock_load_rows.return_value = []
        generate_sitemap.main()
        self.mock_get_spark.assert_called_once_with("generate-sitemap")

    def test_small_row_count_writes_single_sitemap_xml(self):
        rows = [_make_row(str(i), f"listing-{i}") for i in range(3)]
        self.mock_load_rows.return_value = rows

        generate_sitemap.main()

        sitemap_path = self.output_dir / "sitemap.xml"
        self.assertTrue(sitemap_path.exists())
        self.assertFalse((self.output_dir / "sitemap_index.xml").exists())

        root = ET.fromstring(sitemap_path.read_text())
        self.assertEqual(len(root.findall("sm:url", NS)), 3)

    def test_row_count_over_limit_writes_chunked_files_and_index(self):
        # Force the "else" branch without generating 50,000+ fake rows:
        # patch MAX_URLS_PER_SITEMAP low and chunk_rows to a small, controlled chunker.
        rows = [_make_row(str(i), f"listing-{i}") for i in range(5)]
        self.mock_load_rows.return_value = rows

        with (
            mock.patch.object(generate_sitemap, "MAX_URLS_PER_SITEMAP", 2),
            mock.patch.object(
                generate_sitemap,
                "chunk_rows",
                side_effect=lambda rows, chunk_size=2: [rows[i : i + chunk_size] for i in range(0, len(rows), chunk_size)],
            ),
        ):
            generate_sitemap.main()

        # 5 rows chunked by 2 => sitemap-1.xml (2 rows), sitemap-2.xml (2 rows), sitemap-3.xml (1 row)
        expected_files = ["sitemap-1.xml", "sitemap-2.xml", "sitemap-3.xml"]
        for filename in expected_files:
            self.assertTrue((self.output_dir / filename).exists(), filename)

        self.assertFalse((self.output_dir / "sitemap.xml").exists())

        index_path = self.output_dir / "sitemap_index.xml"
        self.assertTrue(index_path.exists())

        index_root = ET.fromstring(index_path.read_text())
        locs = [entry.find("sm:loc", NS).text for entry in index_root.findall("sm:sitemap", NS)]

        from core.sitemap_generator import SITE_BASE_URL

        self.assertEqual(locs, [f"{SITE_BASE_URL}/{name}" for name in expected_files])

    def test_row_counts_split_evenly_do_not_leave_a_short_final_chunk_file(self):
        rows = [_make_row(str(i), f"listing-{i}") for i in range(4)]
        self.mock_load_rows.return_value = rows

        with (
            mock.patch.object(generate_sitemap, "MAX_URLS_PER_SITEMAP", 2),
            mock.patch.object(
                generate_sitemap,
                "chunk_rows",
                side_effect=lambda rows, chunk_size=2: [rows[i : i + chunk_size] for i in range(0, len(rows), chunk_size)],
            ),
        ):
            generate_sitemap.main()

        self.assertTrue((self.output_dir / "sitemap-1.xml").exists())
        self.assertTrue((self.output_dir / "sitemap-2.xml").exists())
        self.assertFalse((self.output_dir / "sitemap-3.xml").exists())


if __name__ == "__main__":
    unittest.main()
