"""Unit tests for src/core/sitemap_generator.py"""

import gzip
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock
from xml.etree import ElementTree as ET

from src.core.sitemap_generator import (
    ALTERNATE_DOMAINS,
    IMAGE_NS,
    SITE_BASE_URL,
    SITEMAP_NS,
    XHTML_NS,
    SitemapFileWriter,
    _collect_image_urls,
    _format_lastmod,
    render_footer,
    render_header,
    render_sitemap_index,
    render_url_block,
    url_for_property,
    write_sitemap_files,
)

NS = {"sm": SITEMAP_NS, "image": IMAGE_NS, "xhtml": XHTML_NS}


def _build_doc(rows: list[dict]) -> str:
    """Assemble a full urlset document out of the header/url/footer fragments."""
    body = "".join(render_url_block(row) for row in rows)
    return render_header() + body + render_footer()


def _read_gzip_text(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return f.read()


class TestUrlForProperty(unittest.TestCase):
    def test_builds_url_with_slug(self):
        url = url_for_property("1034061", "super-8-by-wyndham-crete")
        self.assertEqual(url, f"{SITE_BASE_URL}/property/super-8-by-wyndham-crete/1034061")

    def test_falls_back_to_listing_when_slug_missing(self):
        url = url_for_property("1034061", None)
        self.assertEqual(url, f"{SITE_BASE_URL}/property/listing/1034061")

    def test_falls_back_to_listing_when_slug_empty_string(self):
        url = url_for_property("1034061", "")
        self.assertEqual(url, f"{SITE_BASE_URL}/property/listing/1034061")

    def test_respects_custom_base_url(self):
        url = url_for_property("1034061", "a-listing", base_url="https://www.rentbyowner.ca")
        self.assertEqual(url, "https://www.rentbyowner.ca/property/a-listing/1034061")


class TestFormatLastmod(unittest.TestCase):
    def test_formats_aware_datetime_as_isoformat(self):
        dt = datetime(2026, 7, 14, 9, 12, 31, tzinfo=UTC)
        self.assertEqual(_format_lastmod(dt), "2026-07-14T09:12:31+00:00")

    def test_formats_iso_string_as_isoformat(self):
        self.assertEqual(_format_lastmod("2026-07-14T09:12:31+00:00"), "2026-07-14T09:12:31+00:00")

    def test_formats_naive_datetime_as_isoformat(self):
        dt = datetime(2026, 7, 14, 9, 12, 31)
        self.assertEqual(_format_lastmod(dt), "2026-07-14T09:12:31")

    def test_none_falls_back_to_utcnow(self):
        fixed_now = datetime(2026, 1, 1, 0, 0, 0)
        with mock.patch("src.core.sitemap_generator.datetime") as mock_datetime:
            mock_datetime.utcnow.return_value = fixed_now
            self.assertEqual(_format_lastmod(None), fixed_now.isoformat())


class TestCollectImageUrls(unittest.TestCase):
    def test_feature_image_comes_first(self):
        row = {
            "feature_image": "https://img/feature.jpg",
            "images": ["https://img/a.jpg", "https://img/b.jpg"],
        }
        self.assertEqual(
            _collect_image_urls(row),
            ["https://img/feature.jpg", "https://img/a.jpg", "https://img/b.jpg"],
        )

    def test_deduplicates_feature_image_repeated_in_images(self):
        row = {
            "feature_image": "https://img/a.jpg",
            "images": ["https://img/a.jpg", "https://img/b.jpg"],
        }
        self.assertEqual(_collect_image_urls(row), ["https://img/a.jpg", "https://img/b.jpg"])

    def test_no_images_and_no_feature_image_returns_empty(self):
        self.assertEqual(_collect_image_urls({}), [])

    def test_images_missing_key_defaults_to_empty_list(self):
        row = {"feature_image": "https://img/a.jpg"}
        self.assertEqual(_collect_image_urls(row), ["https://img/a.jpg"])

    def test_filters_out_falsy_urls(self):
        row = {"feature_image": None, "images": ["", None, "https://img/a.jpg"]}
        self.assertEqual(_collect_image_urls(row), ["https://img/a.jpg"])


class TestRenderHeaderFooter(unittest.TestCase):
    def test_header_declares_expected_namespaces(self):
        xml_str = render_header() + render_footer()
        root = ET.fromstring(xml_str)
        self.assertEqual(root.tag, f"{{{SITEMAP_NS}}}urlset")

    def test_empty_document_has_no_url_entries(self):
        root = ET.fromstring(_build_doc([]))
        self.assertEqual(root.findall("sm:url", NS), [])


class TestRenderUrlBlock(unittest.TestCase):
    def test_single_row_produces_one_url_entry_with_expected_fields(self):
        row = {
            "external_id": "1034061",
            "property_slug": "super-8-by-wyndham-crete",
            "last_synced_at": datetime(2026, 7, 14, 9, 12, 31, tzinfo=UTC),
            "images": ["https://img/a.jpg"],
        }
        root = ET.fromstring(_build_doc([row]))

        urls = root.findall("sm:url", NS)
        self.assertEqual(len(urls), 1)

        url_el = urls[0]
        self.assertEqual(
            url_el.find("sm:loc", NS).text,
            f"{SITE_BASE_URL}/property/super-8-by-wyndham-crete/1034061",
        )
        self.assertEqual(url_el.find("sm:lastmod", NS).text, "2026-07-14T09:12:31+00:00")

    def test_multiple_rows_produce_matching_number_of_url_entries(self):
        rows = [{"external_id": str(i), "property_slug": f"listing-{i}"} for i in range(5)]
        root = ET.fromstring(_build_doc(rows))
        self.assertEqual(len(root.findall("sm:url", NS)), 5)

    def test_row_without_images_has_no_image_elements(self):
        row = {"external_id": "1", "property_slug": "a"}
        root = ET.fromstring(_build_doc([row]))
        url_el = root.find("sm:url", NS)
        self.assertEqual(url_el.findall("image:image", NS), [])

    def test_row_with_images_emits_image_image_elements_in_order(self):
        row = {
            "external_id": "1",
            "property_slug": "a",
            "feature_image": "https://img/feature.jpg",
            "images": ["https://img/a.jpg", "https://img/b.jpg"],
        }
        root = ET.fromstring(_build_doc([row]))
        url_el = root.find("sm:url", NS)

        image_els = url_el.findall("image:image", NS)
        self.assertEqual(len(image_els), 3)

        locs = [img.find("image:loc", NS).text for img in image_els]
        self.assertEqual(
            locs,
            ["https://img/feature.jpg", "https://img/a.jpg", "https://img/b.jpg"],
        )

    def test_missing_external_id_and_slug_still_produces_valid_url(self):
        root = ET.fromstring(_build_doc([{}]))
        loc_text = root.find("sm:url", NS).find("sm:loc", NS).text
        self.assertEqual(loc_text, f"{SITE_BASE_URL}/property/listing/None")

    def test_emits_self_referencing_and_alternate_hreflang_links(self):
        row = {"external_id": "1", "property_slug": "a"}
        root = ET.fromstring(_build_doc([row]))
        url_el = root.find("sm:url", NS)

        alt_links = url_el.findall("xhtml:link", NS)
        self.assertEqual(len(alt_links), len(ALTERNATE_DOMAINS))

        hreflangs = {link.get("hreflang") for link in alt_links}
        self.assertEqual(hreflangs, set(ALTERNATE_DOMAINS.keys()))

        hrefs_by_lang = {link.get("hreflang"): link.get("href") for link in alt_links}
        for hreflang, base_url in ALTERNATE_DOMAINS.items():
            self.assertEqual(hrefs_by_lang[hreflang], f"{base_url}/property/a/1")


class TestRenderSitemapIndex(unittest.TestCase):
    def test_one_sitemap_entry_per_filename(self):
        filenames = ["sitemap-1.xml", "sitemap-2.xml"]
        xml_str = render_sitemap_index(filenames)
        root = ET.fromstring(xml_str)

        entries = root.findall("sm:sitemap", NS)
        self.assertEqual(len(entries), 2)

        locs = [entry.find("sm:loc", NS).text for entry in entries]
        self.assertEqual(locs, [f"{SITE_BASE_URL}/{f}" for f in filenames])

    def test_empty_filenames_produces_empty_index(self):
        xml_str = render_sitemap_index([])
        root = ET.fromstring(xml_str)
        self.assertEqual(root.findall("sm:sitemap", NS), [])

    def test_each_entry_has_a_lastmod(self):
        xml_str = render_sitemap_index(["sitemap-1.xml"])
        root = ET.fromstring(xml_str)
        entry = root.find("sm:sitemap", NS)
        self.assertIsNotNone(entry.find("sm:lastmod", NS).text)


class TestSitemapFileWriter(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_close_writes_valid_header_and_footer_when_empty(self):
        path = self.tmp_path / "empty.xml.gz"
        writer = SitemapFileWriter(path)
        writer.close()

        content = _read_gzip_text(path)
        root = ET.fromstring(content)
        self.assertEqual(root.tag, f"{{{SITEMAP_NS}}}urlset")
        self.assertEqual(root.findall("sm:url", NS), [])

    def test_write_url_block_increments_count_and_appears_in_output(self):
        path = self.tmp_path / "one.xml.gz"
        writer = SitemapFileWriter(path)
        block = render_url_block({"external_id": "1", "property_slug": "a"})

        writer.write_url_block(block)
        writer.write_url_block(block)
        self.assertEqual(writer.url_count, 2)
        writer.close()

        content = _read_gzip_text(path)
        root = ET.fromstring(content)
        self.assertEqual(len(root.findall("sm:url", NS)), 2)

    def test_would_overflow_false_when_under_limits(self):
        path = self.tmp_path / "under.xml.gz"
        writer = SitemapFileWriter(path)
        block = render_url_block({"external_id": "1", "property_slug": "a"})

        self.assertFalse(writer.would_overflow(block))
        writer.close()

    @mock.patch("src.core.sitemap_generator.MAX_URLS_PER_SITEMAP", 2)
    def test_would_overflow_true_when_url_count_reaches_max(self):
        path = self.tmp_path / "maxcount.xml.gz"
        writer = SitemapFileWriter(path)
        block = render_url_block({"external_id": "1", "property_slug": "a"})

        writer.write_url_block(block)
        writer.write_url_block(block)
        self.assertTrue(writer.would_overflow(block))
        writer.close()

    @mock.patch("src.core.sitemap_generator.SIZE_SAFETY_MARGIN_BYTES", 100)
    @mock.patch("src.core.sitemap_generator.MAX_BYTES_PER_SITEMAP", 200)
    def test_would_overflow_true_when_projected_bytes_exceed_margin(self):
        path = self.tmp_path / "maxbytes.xml.gz"
        writer = SitemapFileWriter(path)
        big_block = "x" * 500

        self.assertTrue(writer.would_overflow(big_block))
        writer.close()

    def test_uncompressed_bytes_tracked_on_raw_text_not_compressed(self):
        path = self.tmp_path / "bytes.xml.gz"
        writer = SitemapFileWriter(path)
        before = writer._uncompressed_bytes
        block = render_url_block({"external_id": "1", "property_slug": "a"})

        writer.write_url_block(block)
        self.assertEqual(writer._uncompressed_bytes, before + len(block.encode("utf-8")))
        writer.close()


class TestWriteSitemapFiles(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_writes_all_rows_to_single_file_when_under_limits(self):
        rows = [{"external_id": str(i), "property_slug": f"listing-{i}"} for i in range(3)]
        output_dir = self.tmp_path / "out"

        filenames = write_sitemap_files(iter(rows), output_dir, "sitemap")

        self.assertEqual(filenames, ["sitemap.xml.gz"])
        content = _read_gzip_text(output_dir / "sitemap.xml.gz")
        root = ET.fromstring(content)
        self.assertEqual(len(root.findall("sm:url", NS)), 3)

    def test_creates_output_dir_if_missing(self):
        rows = [{"external_id": "1", "property_slug": "a"}]
        output_dir = self.tmp_path / "nested" / "out"

        self.assertFalse(output_dir.exists())
        write_sitemap_files(iter(rows), output_dir, "sitemap")
        self.assertTrue(output_dir.exists())

    def test_no_rows_returns_empty_list_and_removes_file(self):
        output_dir = self.tmp_path / "out"

        filenames = write_sitemap_files(iter([]), output_dir, "sitemap")

        self.assertEqual(filenames, [])
        self.assertFalse((output_dir / "sitemap.xml.gz").exists())

    @mock.patch("src.core.sitemap_generator.MAX_URLS_PER_SITEMAP", 2)
    def test_rolls_over_to_new_file_when_url_count_limit_exceeded(self):
        rows = [{"external_id": str(i), "property_slug": f"listing-{i}"} for i in range(5)]
        output_dir = self.tmp_path / "out"

        filenames = write_sitemap_files(iter(rows), output_dir, "sitemap")

        self.assertEqual(filenames, ["sitemap.xml.gz", "sitemap-2.xml.gz", "sitemap-3.xml.gz"])

        total_urls = 0
        for filename in filenames:
            content = _read_gzip_text(output_dir / filename)
            root = ET.fromstring(content)
            urls = root.findall("sm:url", NS)
            self.assertLessEqual(len(urls), 2)
            total_urls += len(urls)
        self.assertEqual(total_urls, 5)

    def test_filename_prefix_used_for_naming(self):
        rows = [{"external_id": "1", "property_slug": "a"}]
        output_dir = self.tmp_path / "out"

        filenames = write_sitemap_files(iter(rows), output_dir, "nearby-sitemap")

        self.assertEqual(filenames, ["nearby-sitemap.xml.gz"])

    @mock.patch("src.core.sitemap_generator.MAX_URLS_PER_SITEMAP", 1)
    def test_second_and_later_filenames_include_numeric_suffix(self):
        rows = [{"external_id": str(i), "property_slug": f"l{i}"} for i in range(3)]
        output_dir = self.tmp_path / "out"

        filenames = write_sitemap_files(iter(rows), output_dir, "nearby-sitemap")

        self.assertEqual(
            filenames,
            ["nearby-sitemap.xml.gz", "nearby-sitemap-2.xml.gz", "nearby-sitemap-3.xml.gz"],
        )

    def test_all_written_files_are_well_formed_xml(self):
        rows = [{"external_id": str(i), "property_slug": f"listing-{i}"} for i in range(3)]
        output_dir = self.tmp_path / "out"

        filenames = write_sitemap_files(iter(rows), output_dir, "sitemap")

        for filename in filenames:
            content = _read_gzip_text(output_dir / filename)
            root = ET.fromstring(content)  # raises if malformed
            self.assertEqual(root.tag, f"{{{SITEMAP_NS}}}urlset")


if __name__ == "__main__":
    unittest.main()
