"""
URL structure: {SITE_BASE_URL}/property/{property_slug}/{external_id}
"""

import os
from datetime import datetime
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://rentbyowner.com")
MAX_URLS_PER_SITEMAP = 50000  # hard limit per the sitemap protocol spec

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
IMAGE_NS = "http://www.google.com/schemas/sitemap-image/1.1"
XHTML_NS = "http://www.w3.org/1999/xhtml"

# hreflang -> base domain, for alternate-language/region versions of the
# same listing. Per the hreflang spec, EVERY <url> block should list ALL
# variants including itself (self-referencing), not just the "other" ones.
ALTERNATE_DOMAINS = {
    "en": "https://www.rentbyowner.com",
    "en-CA": "https://www.rentbyowner.ca",
    "en-NZ": "https://www.rentbyowner.nz",
}


def url_for_property(external_id: str, property_slug: str, base_url: str = SITE_BASE_URL) -> str:
    slug_part = property_slug or "listing"
    return f"{base_url}/property/{slug_part}/{external_id}"


def _format_lastmod(dt) -> str:
    """W3C datetime format required by the sitemap protocol, e.g. 2026-07-14T09:12:31+00:00."""
    if dt is None:
        return datetime.utcnow().isoformat()
    return dt.isoformat()


def _collect_image_urls(row: dict) -> list[str]:
    """Return all image URLs for a sitemap row, preferring the feature image first."""
    image_urls: list[str] = []
    for image_url in [row.get("feature_image"), *(row.get("images") or [])]:
        if not image_url or image_url in image_urls:
            continue
        image_urls.append(image_url)
    return image_urls


def build_sitemap_xml(rows: list[dict]) -> str:
    """
    rows: list of dicts with at least external_id, property_slug,
    last_synced_at, and optionally images (list[str]).
    Returns one <urlset> XML document as a string.
    """
    urlset = Element(
        "urlset",
        {
            "xmlns": SITEMAP_NS,
            "xmlns:image": IMAGE_NS,
            "xmlns:xhtml": XHTML_NS,
        },
    )

    for row in rows:
        url_el = SubElement(urlset, "url")

        loc = SubElement(url_el, "loc")
        loc.text = url_for_property(row.get("external_id"), row.get("property_slug"))

        lastmod = SubElement(url_el, "lastmod")
        lastmod.text = _format_lastmod(row.get("last_synced_at"))

        # changefreq = SubElement(url_el, "changefreq")
        # changefreq.text = "daily"

        # priority = SubElement(url_el, "priority")
        # priority.text = "0.8"

        for hreflang, base_url in ALTERNATE_DOMAINS.items():
            alt_link = SubElement(url_el, "xhtml:link")
            alt_link.set("rel", "alternate")
            alt_link.set("hreflang", hreflang)
            alt_link.set(
                "href",
                url_for_property(row.get("external_id"), row.get("property_slug"), base_url),
            )

        for image_url in _collect_image_urls(row):
            image_el = SubElement(url_el, "image:image")
            image_loc = SubElement(image_el, "image:loc")
            image_loc.text = image_url

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
