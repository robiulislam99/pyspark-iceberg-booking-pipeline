"""Unit tests for scripts/generate_sitemap.py

Spark and disk I/O are mocked/tempdir'd so these tests run in isolation,
fast, and without touching /app/data/sitemaps.
"""

import gzip
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET

from core.sitemap_generator import SITE_BASE_URL, SITEMAP_NS
from scripts import generate_sitemap

NS = {"sm": SITEMAP_NS}


def _make_row(external_id="1", property_slug="a"):
    data = {
        "external_id": external_id,
        "property_slug": property_slug,
        "last_synced_at": None,
        "feature_image": None,
        "images": None,
    }
    row = mock.Mock()
    row.asDict.return_value = data
    return row


def _read_gzip_xml(path: Path) -> ET.Element:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return ET.fromstring(f.read())


class TestLoadPublishedRowsIterator(unittest.TestCase):
    def test_runs_expected_query_and_returns_local_iterator(self):
        mock_df = mock.Mock()
        mock_df.toLocalIterator.return_value = iter(["row1", "row2"])

        mock_spark = mock.Mock()
        mock_spark.sql.return_value = mock_df

        result = generate_sitemap.load_published_rows_iterator(mock_spark)

        self.assertEqual(list(result), ["row1", "row2"])
        mock_df.toLocalIterator.assert_called_once()
        mock_df.collect.assert_not_called()

        query = mock_spark.sql.call_args.args[0]
        self.assertIn(generate_sitemap.TABLE, query)
        self.assertIn("is_published = true", query)

    def test_no_published_rows_returns_empty_iterator(self):
        mock_df = mock.Mock()
        mock_df.toLocalIterator.return_value = iter([])
        mock_spark = mock.Mock()
        mock_spark.sql.return_value = mock_df

        self.assertEqual(list(generate_sitemap.load_published_rows_iterator(mock_spark)), [])


class TestSitemapFileWriter(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.path = Path(self._tmpdir.name) / "sitemap.xml.gz"

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_writes_header_on_construction(self):
        writer = generate_sitemap.SitemapFileWriter(self.path)
        writer.close()

        root = _read_gzip_xml(self.path)
        self.assertEqual(root.tag, f"{{{SITEMAP_NS}}}urlset")
        self.assertEqual(writer.url_count, 0)

    def test_write_url_block_increments_url_count(self):
        writer = generate_sitemap.SitemapFileWriter(self.path)
        writer.write_url_block("  <url><loc>x</loc></url>\n")
        writer.write_url_block("  <url><loc>y</loc></url>\n")
        writer.close()

        self.assertEqual(writer.url_count, 2)

    def test_close_appends_footer_and_produces_valid_xml(self):
        writer = generate_sitemap.SitemapFileWriter(self.path)
        writer.write_url_block("  <url><loc>x</loc></url>\n")
        writer.close()

        root = _read_gzip_xml(self.path)
        self.assertEqual(len(root.findall("sm:url", NS)), 1)

    def test_would_overflow_true_once_url_count_hits_max(self):
        writer = generate_sitemap.SitemapFileWriter(self.path)
        with mock.patch.object(generate_sitemap, "MAX_URLS_PER_SITEMAP", 1):
            writer.write_url_block("  <url><loc>x</loc></url>\n")
            self.assertTrue(writer.would_overflow("  <url><loc>y</loc></url>\n"))
        writer.close()

    def test_would_overflow_false_when_under_both_limits(self):
        writer = generate_sitemap.SitemapFileWriter(self.path)
        self.assertFalse(writer.would_overflow("  <url><loc>x</loc></url>\n"))
        writer.close()

    def test_would_overflow_true_when_projected_bytes_exceed_cap_minus_margin(self):
        writer = generate_sitemap.SitemapFileWriter(self.path)
        with (
            mock.patch.object(generate_sitemap, "MAX_BYTES_PER_SITEMAP", 100),
            mock.patch.object(generate_sitemap, "SIZE_SAFETY_MARGIN_BYTES", 10),
        ):
            # header already written; a further ~95-byte block should overflow
            # a 100-byte cap with a 10-byte safety margin.
            big_block = "  <url>" + ("x" * 90) + "</url>\n"
            self.assertTrue(writer.would_overflow(big_block))
        writer.close()


class TestMain(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmpdir.name) / "sitemaps"

        self.output_dir_patcher = mock.patch.object(generate_sitemap, "OUTPUT_DIR", self.output_dir)
        self.output_dir_patcher.start()

        self.get_spark_patcher = mock.patch.object(generate_sitemap, "get_spark")
        self.mock_get_spark = self.get_spark_patcher.start()
        self.mock_get_spark.return_value = mock.Mock()

        self.load_rows_patcher = mock.patch.object(generate_sitemap, "load_published_rows_iterator")
        self.mock_load_rows = self.load_rows_patcher.start()

    def tearDown(self):
        self.output_dir_patcher.stop()
        self.get_spark_patcher.stop()
        self.load_rows_patcher.stop()
        self._tmpdir.cleanup()

    def _existing_gz_files(self):
        return sorted(p.name for p in self.output_dir.glob("*.xml.gz"))

    def test_calls_get_spark_with_expected_app_name(self):
        self.mock_load_rows.return_value = iter([])
        generate_sitemap.main()
        self.mock_get_spark.assert_called_once_with("generate-sitemap")

    def test_stops_spark_session_when_done(self):
        self.mock_load_rows.return_value = iter([])
        generate_sitemap.main()
        self.mock_get_spark.return_value.stop.assert_called_once()

    def test_no_rows_creates_output_dir_but_writes_no_sitemap_file(self):
        self.mock_load_rows.return_value = iter([])

        generate_sitemap.main()

        self.assertTrue(self.output_dir.exists())
        self.assertEqual(self._existing_gz_files(), [])

    def test_small_row_count_writes_single_gzip_sitemap(self):
        rows = [_make_row(str(i), f"listing-{i}") for i in range(3)]
        self.mock_load_rows.return_value = iter(rows)

        generate_sitemap.main()

        sitemap_path = self.output_dir / "sitemap.xml.gz"
        self.assertTrue(sitemap_path.exists())
        self.assertFalse((self.output_dir / "sitemap_index.xml.gz").exists())

        root = _read_gzip_xml(sitemap_path)
        self.assertEqual(len(root.findall("sm:url", NS)), 3)

    def test_row_count_over_url_limit_writes_chunked_files_and_index(self):
        rows = [_make_row(str(i), f"listing-{i}") for i in range(5)]
        self.mock_load_rows.return_value = iter(rows)

        with mock.patch.object(generate_sitemap, "MAX_URLS_PER_SITEMAP", 2):
            generate_sitemap.main()

        # 5 rows, 2 per file => sitemap.xml.gz(2), sitemap-2.xml.gz(2), sitemap-3.xml.gz(1)
        expected_files = ["sitemap-2.xml.gz", "sitemap-3.xml.gz", "sitemap.xml.gz"]
        self.assertEqual(self._existing_gz_files(), sorted(expected_files + ["sitemap_index.xml.gz"]))

        counts = {name: len(_read_gzip_xml(self.output_dir / name).findall("sm:url", NS)) for name in expected_files}
        self.assertEqual(counts["sitemap.xml.gz"], 2)
        self.assertEqual(counts["sitemap-2.xml.gz"], 2)
        self.assertEqual(counts["sitemap-3.xml.gz"], 1)

        index_root = _read_gzip_xml(self.output_dir / "sitemap_index.xml.gz")
        locs = [entry.find("sm:loc", NS).text for entry in index_root.findall("sm:sitemap", NS)]
        self.assertEqual(sorted(locs), sorted(f"{SITE_BASE_URL}/{name}" for name in expected_files))

    def test_row_counts_split_evenly_do_not_leave_an_empty_final_file(self):
        rows = [_make_row(str(i), f"listing-{i}") for i in range(4)]
        self.mock_load_rows.return_value = iter(rows)

        with mock.patch.object(generate_sitemap, "MAX_URLS_PER_SITEMAP", 2):
            generate_sitemap.main()

        self.assertEqual(
            self._existing_gz_files(),
            sorted(["sitemap.xml.gz", "sitemap-2.xml.gz", "sitemap_index.xml.gz"]),
        )

    def test_row_count_over_byte_limit_also_triggers_new_file(self):
        rows = [_make_row(str(i), f"listing-{i}") for i in range(4)]
        self.mock_load_rows.return_value = iter(rows)

        # Force an overflow purely on size, independent of MAX_URLS_PER_SITEMAP.
        with (
            mock.patch.object(generate_sitemap, "MAX_BYTES_PER_SITEMAP", 600),
            mock.patch.object(generate_sitemap, "SIZE_SAFETY_MARGIN_BYTES", 0),
        ):
            generate_sitemap.main()

        self.assertGreater(len(self._existing_gz_files()), 1)


if __name__ == "__main__":
    unittest.main()
