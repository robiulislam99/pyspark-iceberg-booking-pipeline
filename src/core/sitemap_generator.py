"""
URL structure: {SITE_BASE_URL}/property/{external_id}/{property_slug}
"""

import os
from datetime import datetime
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://rentbyowner.com")
MAX_URLS_PER_SITEMAP = 50000  # hard limit per the sitemap protocol spec

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def url_for_property(external_id: str, property_slug: str) -> str:
    slug_part = property_slug or "listing"
    return f"{SITE_BASE_URL}/property/{external_id}/{slug_part}"


def _format_lastmod(dt) -> str:
    """W3C datetime format required by the sitemap protocol, e.g. 2026-07-14T09:12:31+00:00."""
    if dt is None:
        return datetime.utcnow().isoformat()
    return dt.isoformat()


def build_sitemap_xml(rows: list[dict]) -> str:
    """
    rows: list of dicts with at least external_id, property_slug,
    last_synced_at. Returns one <urlset> XML document as a string.
    """
    urlset = Element("urlset", xmlns=SITEMAP_NS)

    for row in rows:
        url_el = SubElement(urlset, "url")

        loc = SubElement(url_el, "loc")
        loc.text = url_for_property(row.get("external_id"), row.get("property_slug"))

        lastmod = SubElement(url_el, "lastmod")
        lastmod.text = _format_lastmod(row.get("last_synced_at"))

        changefreq = SubElement(url_el, "changefreq")
        changefreq.text = "daily"

        priority = SubElement(url_el, "priority")
        priority.text = "0.8"

    raw_xml = tostring(urlset, encoding="unicode")
    return minidom.parseString(raw_xml).toprettyxml(indent="  ")


def build_sitemap_index_xml(sitemap_filenames: list[str]) -> str:
    """Only needed when rows exceed MAX_URLS_PER_SITEMAP and get split across multiple files."""
    sitemapindex = Element("sitemapindex", xmlns=SITEMAP_NS)

    for filename in sitemap_filenames:
        sitemap_el = SubElement(sitemapindex, "sitemap")
        loc = SubElement(sitemap_el, "loc")
        loc.text = f"{SITE_BASE_URL}/{filename}"
        lastmod = SubElement(sitemap_el, "lastmod")
        lastmod.text = datetime.utcnow().isoformat()

    raw_xml = tostring(sitemapindex, encoding="unicode")
    return minidom.parseString(raw_xml).toprettyxml(indent="  ")


def chunk_rows(rows: list[dict], chunk_size: int = MAX_URLS_PER_SITEMAP) -> list[list[dict]]:
    return [rows[i : i + chunk_size] for i in range(0, len(rows), chunk_size)]
