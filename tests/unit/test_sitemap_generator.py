"""Unit tests for src/core/sitemap_generator.py"""

import unittest
from datetime import UTC, datetime
from unittest import mock
from xml.etree import ElementTree as ET

from src.core.sitemap_generator import (
    IMAGE_NS,
    MAX_URLS_PER_SITEMAP,
    SITE_BASE_URL,
    SITEMAP_NS,
    _collect_image_urls,
    _format_lastmod,
    build_sitemap_index_xml,
    build_sitemap_xml,
    chunk_rows,
    url_for_property,
)

NS = {"sm": SITEMAP_NS, "image": IMAGE_NS}


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


class TestFormatLastmod(unittest.TestCase):
    def test_formats_aware_datetime_as_isoformat(self):
        dt = datetime(2026, 7, 14, 9, 12, 31, tzinfo=UTC)
        self.assertEqual(_format_lastmod(dt), "2026-07-14T09:12:31+00:00")

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


class TestBuildSitemapXml(unittest.TestCase):
    def _parse(self, xml_str: str) -> ET.Element:
        return ET.fromstring(xml_str)

    def test_declares_sitemap_namespace(self):
        xml_str = build_sitemap_xml([])
        root = self._parse(xml_str)
        self.assertEqual(root.tag, f"{{{SITEMAP_NS}}}urlset")

    def test_single_row_produces_one_url_entry_with_expected_fields(self):
        row = {
            "external_id": "1034061",
            "property_slug": "super-8-by-wyndham-crete",
            "last_synced_at": datetime(2026, 7, 14, 9, 12, 31, tzinfo=UTC),
            "images": ["https://img/a.jpg"],
        }
        xml_str = build_sitemap_xml([row])
        root = self._parse(xml_str)

        urls = root.findall("sm:url", NS)
        self.assertEqual(len(urls), 1)

        url_el = urls[0]
        self.assertEqual(
            url_el.find("sm:loc", NS).text,
            f"{SITE_BASE_URL}/property/super-8-by-wyndham-crete/1034061",
        )
        self.assertEqual(url_el.find("sm:lastmod", NS).text, "2026-07-14T09:12:31+00:00")
        self.assertEqual(url_el.find("sm:changefreq", NS).text, "daily")
        self.assertEqual(url_el.find("sm:priority", NS).text, "0.8")

    def test_multiple_rows_produce_matching_number_of_url_entries(self):
        rows = [{"external_id": str(i), "property_slug": f"listing-{i}"} for i in range(5)]
        xml_str = build_sitemap_xml(rows)
        root = self._parse(xml_str)
        self.assertEqual(len(root.findall("sm:url", NS)), 5)

    def test_empty_rows_produces_empty_urlset(self):
        xml_str = build_sitemap_xml([])
        root = self._parse(xml_str)
        self.assertEqual(root.findall("sm:url", NS), [])

    def test_row_without_images_has_no_image_elements(self):
        row = {"external_id": "1", "property_slug": "a"}
        xml_str = build_sitemap_xml([row])
        root = self._parse(xml_str)
        url_el = root.find("sm:url", NS)
        self.assertEqual(url_el.findall("image:image", NS), [])

    def test_row_with_images_emits_image_image_elements_in_order(self):
        row = {
            "external_id": "1",
            "property_slug": "a",
            "feature_image": "https://img/feature.jpg",
            "images": ["https://img/a.jpg", "https://img/b.jpg"],
        }
        xml_str = build_sitemap_xml([row])
        root = self._parse(xml_str)
        url_el = root.find("sm:url", NS)

        image_els = url_el.findall("image:image", NS)
        self.assertEqual(len(image_els), 3)

        locs = [img.find("image:loc", NS).text for img in image_els]
        self.assertEqual(
            locs,
            ["https://img/feature.jpg", "https://img/a.jpg", "https://img/b.jpg"],
        )

    def test_missing_external_id_and_slug_still_produces_valid_url(self):
        xml_str = build_sitemap_xml([{}])
        root = self._parse(xml_str)
        loc_text = root.find("sm:url", NS).find("sm:loc", NS).text
        self.assertEqual(loc_text, f"{SITE_BASE_URL}/property/listing/None")


class TestBuildSitemapIndexXml(unittest.TestCase):
    def test_one_sitemap_entry_per_filename(self):
        filenames = ["sitemap-1.xml", "sitemap-2.xml"]
        xml_str = build_sitemap_index_xml(filenames)
        root = ET.fromstring(xml_str)

        entries = root.findall("sm:sitemap", NS)
        self.assertEqual(len(entries), 2)

        locs = [entry.find("sm:loc", NS).text for entry in entries]
        self.assertEqual(locs, [f"{SITE_BASE_URL}/{f}" for f in filenames])

    def test_empty_filenames_produces_empty_index(self):
        xml_str = build_sitemap_index_xml([])
        root = ET.fromstring(xml_str)
        self.assertEqual(root.findall("sm:sitemap", NS), [])

    def test_each_entry_has_a_lastmod(self):
        xml_str = build_sitemap_index_xml(["sitemap-1.xml"])
        root = ET.fromstring(xml_str)
        entry = root.find("sm:sitemap", NS)
        self.assertIsNotNone(entry.find("sm:lastmod", NS).text)


class TestChunkRows(unittest.TestCase):
    def test_splits_rows_into_chunks_of_given_size(self):
        rows = list(range(10))
        chunks = chunk_rows(rows, chunk_size=4)
        self.assertEqual(chunks, [[0, 1, 2, 3], [4, 5, 6, 7], [8, 9]])

    def test_empty_rows_returns_empty_list(self):
        self.assertEqual(chunk_rows([], chunk_size=10), [])

    def test_rows_fewer_than_chunk_size_returns_single_chunk(self):
        rows = [1, 2, 3]
        self.assertEqual(chunk_rows(rows, chunk_size=10), [[1, 2, 3]])

    def test_default_chunk_size_matches_max_urls_per_sitemap(self):
        rows = list(range(MAX_URLS_PER_SITEMAP + 1))
        chunks = chunk_rows(rows)
        self.assertEqual(len(chunks), 2)
        self.assertEqual(len(chunks[0]), MAX_URLS_PER_SITEMAP)
        self.assertEqual(len(chunks[1]), 1)


if __name__ == "__main__":
    unittest.main()
