"""Unit tests for scripts/generate_root_sitemap_index.py"""

import gzip
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.generate_root_sitemap_index import main


def _read_gzip_text(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return f.read()


class TestMain(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_missing_sitemaps_dir_returns_without_writing(self):
        missing_dir = self.tmp_path / "does-not-exist"

        with mock.patch("scripts.generate_root_sitemap_index.SITEMAPS_DIR", missing_dir):
            main()

        self.assertFalse(missing_dir.exists())

    def test_no_sitemap_files_returns_without_writing_index(self):
        with mock.patch("scripts.generate_root_sitemap_index.SITEMAPS_DIR", self.tmp_path):
            main()

        self.assertFalse((self.tmp_path / "sitemap_index.xml.gz").exists())

    def test_writes_index_referencing_all_xml_gz_files(self):
        (self.tmp_path / "property-sitemap.xml.gz").touch()
        (self.tmp_path / "nearby-sitemap.xml.gz").touch()

        with mock.patch("scripts.generate_root_sitemap_index.SITEMAPS_DIR", self.tmp_path):
            main()

        index_path = self.tmp_path / "sitemap_index.xml.gz"
        self.assertTrue(index_path.exists())

        content = _read_gzip_text(index_path)
        self.assertIn("property-sitemap.xml.gz", content)
        self.assertIn("nearby-sitemap.xml.gz", content)

    def test_excludes_existing_sitemap_index_file_from_the_list(self):
        (self.tmp_path / "property-sitemap.xml.gz").touch()
        (self.tmp_path / "sitemap_index.xml.gz").touch()

        with (
            mock.patch("scripts.generate_root_sitemap_index.SITEMAPS_DIR", self.tmp_path),
            mock.patch("scripts.generate_root_sitemap_index.render_sitemap_index") as mock_render,
        ):
            mock_render.return_value = "<sitemapindex></sitemapindex>"
            main()

        args, _ = mock_render.call_args
        filenames_passed = args[0]
        self.assertNotIn("sitemap_index.xml.gz", filenames_passed)
        self.assertIn("property-sitemap.xml.gz", filenames_passed)

    def test_ignores_non_xml_gz_files(self):
        (self.tmp_path / "property-sitemap.xml.gz").touch()
        (self.tmp_path / "readme.txt").touch()
        (self.tmp_path / "notes.xml").touch()

        with (
            mock.patch("scripts.generate_root_sitemap_index.SITEMAPS_DIR", self.tmp_path),
            mock.patch("scripts.generate_root_sitemap_index.render_sitemap_index") as mock_render,
        ):
            mock_render.return_value = "<sitemapindex></sitemapindex>"
            main()

        args, _ = mock_render.call_args
        filenames_passed = args[0]
        self.assertEqual(filenames_passed, ["property-sitemap.xml.gz"])

    def test_filenames_passed_to_render_are_sorted(self):
        (self.tmp_path / "sitemap-2.xml.gz").touch()
        (self.tmp_path / "sitemap-1.xml.gz").touch()
        (self.tmp_path / "nearby-sitemap.xml.gz").touch()

        with (
            mock.patch("scripts.generate_root_sitemap_index.SITEMAPS_DIR", self.tmp_path),
            mock.patch("scripts.generate_root_sitemap_index.render_sitemap_index") as mock_render,
        ):
            mock_render.return_value = "<sitemapindex></sitemapindex>"
            main()

        args, _ = mock_render.call_args
        filenames_passed = args[0]
        self.assertEqual(filenames_passed, sorted(filenames_passed))

    def test_index_file_content_matches_render_sitemap_index_output(self):
        (self.tmp_path / "property-sitemap.xml.gz").touch()

        with (
            mock.patch("scripts.generate_root_sitemap_index.SITEMAPS_DIR", self.tmp_path),
            mock.patch("scripts.generate_root_sitemap_index.render_sitemap_index") as mock_render,
        ):
            mock_render.return_value = "<sitemapindex><sitemap>fake</sitemap></sitemapindex>"
            main()

        content = _read_gzip_text(self.tmp_path / "sitemap_index.xml.gz")
        self.assertEqual(content, "<sitemapindex><sitemap>fake</sitemap></sitemapindex>")

    def test_index_written_as_gzip_compressed_file(self):
        (self.tmp_path / "property-sitemap.xml.gz").touch()

        with mock.patch("scripts.generate_root_sitemap_index.SITEMAPS_DIR", self.tmp_path):
            main()

        index_path = self.tmp_path / "sitemap_index.xml.gz"
        # Reading via gzip.open succeeding (done in _read_gzip_text) confirms
        # it's valid gzip; also sanity-check the magic bytes directly.
        with open(index_path, "rb") as f:
            magic = f.read(2)
        self.assertEqual(magic, b"\x1f\x8b")


if __name__ == "__main__":
    unittest.main()
