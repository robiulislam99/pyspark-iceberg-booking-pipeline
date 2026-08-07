"""
URL structure: {SITE_BASE_URL}/property/{property_slug}/{external_id}

"""

import gzip
import os
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "https://rentbyowner.com")
MAX_URLS_PER_SITEMAP = 50000
MAX_BYTES_PER_SITEMAP = 50 * 1024 * 1024  # 50MB, uncompressed size
# Safety margin below the hard limit -- stop adding new <url> blocks
# once we're within this many bytes of the cap, so the closing
# </urlset> tag never pushes a file over the real limit.
SIZE_SAFETY_MARGIN_BYTES = 64 * 1024  # 64KB

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
    if isinstance(dt, str):
        normalized = dt.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            return datetime.fromisoformat(normalized).isoformat()
        except ValueError:
            return normalized
    return dt.isoformat()


def _collect_image_urls(row: dict) -> list[str]:
    image_urls: list[str] = []
    for image_url in [row.get("feature_image"), *(row.get("images") or [])]:
        if not image_url or image_url in image_urls:
            continue
        image_urls.append(image_url)
    return image_urls


def render_header() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="{SITEMAP_NS}" '
        f'xmlns:image="{IMAGE_NS}" '
        f'xmlns:xhtml="{XHTML_NS}">\n'
    )


def render_footer() -> str:
    return "</urlset>\n"


def render_url_block(row: dict) -> str:
    """Renders one <url>...</url> block for a single row as a string."""
    external_id = row.get("external_id")
    property_slug = row.get("property_slug")

    lines = ["  <url>"]
    lines.append(f"    <loc>{escape(url_for_property(external_id, property_slug))}</loc>")
    lines.append(f"    <lastmod>{escape(_format_lastmod(row.get('last_synced_at')))}</lastmod>")

    # <changefreq>weekly</changefreq>
    # <priority>0.8</priority>

    for hreflang, base_url in ALTERNATE_DOMAINS.items():
        href = escape(url_for_property(external_id, property_slug, base_url))
        lines.append(f'    <xhtml:link rel="alternate" hreflang="{hreflang}" href="{href}"/>')

    for image_url in _collect_image_urls(row):
        lines.append("    <image:image>")
        lines.append(f"      <image:loc>{escape(image_url)}</image:loc>")
        lines.append("    </image:image>")

    lines.append("  </url>")
    return "\n".join(lines) + "\n"


def render_sitemap_index(sitemap_filenames: list[str]) -> str:
    """Only needed when rows exceed the per-file URL/size limit and get split across multiple files."""
    now = datetime.utcnow().isoformat()
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', f'<sitemapindex xmlns="{SITEMAP_NS}">']
    for filename in sitemap_filenames:
        lines.append("  <sitemap>")
        lines.append(f"    <loc>{escape(f'{SITE_BASE_URL}/{filename}')}</loc>")
        lines.append(f"    <lastmod>{now}</lastmod>")
        lines.append("  </sitemap>")
    lines.append("</sitemapindex>")
    return "\n".join(lines) + "\n"


class SitemapFileWriter:
    """
    Wraps one open, gzip-compressed sitemap file, tracking URL count and
    UNCOMPRESSED byte size written so far (the sitemap protocol's 50MB
    limit is defined on uncompressed content, so size is tracked on the
    text before gzip does its own compression, not the compressed output).

    Shared by any script that writes a sitemap with rollover -- the main
    property sitemap, the combined nearby sitemap, and any future one.
    """

    def __init__(self, path: Path):
        self.path = path
        self._file = gzip.open(path, "wt", encoding="utf-8")
        self._uncompressed_bytes = 0
        self.url_count = 0
        self._write(render_header())

    def _write(self, text: str):
        self._file.write(text)
        self._uncompressed_bytes += len(text.encode("utf-8"))

    def would_overflow(self, block_text: str) -> bool:
        if self.url_count >= MAX_URLS_PER_SITEMAP:
            return True
        projected = self._uncompressed_bytes + len(block_text.encode("utf-8"))
        return projected > (MAX_BYTES_PER_SITEMAP - SIZE_SAFETY_MARGIN_BYTES)

    def write_url_block(self, block_text: str):
        self._write(block_text)
        self.url_count += 1

    def close(self):
        self._write(render_footer())
        self._file.close()


def write_sitemap_files(rows_iterator, output_dir: Path, filename_prefix: str) -> list[str]:
    """
    Shared rollover-writing loop: takes any iterator of row dicts, writes
    them across as many gzip sitemap files as needed (respecting the
    50,000-URL / 50MB-uncompressed limits), and returns the list of
    filenames written. filename_prefix distinguishes sitemap families,
    e.g. "sitemap" -> sitemap.xml.gz, sitemap-2.xml.gz, ...
         "nearby-sitemap" -> nearby-sitemap.xml.gz, nearby-sitemap-2.xml.gz, ...
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    filenames = []
    current_writer = None
    file_index = 1
    total_written = 0

    def open_next_file():
        nonlocal current_writer, file_index
        if current_writer is not None:
            current_writer.close()

        filename = f"{filename_prefix}.xml.gz" if file_index == 1 else f"{filename_prefix}-{file_index}.xml.gz"
        filenames.append(filename)
        current_writer = SitemapFileWriter(output_dir / filename)
        file_index += 1

    open_next_file()

    for row in rows_iterator:
        block_text = render_url_block(row)

        if current_writer.would_overflow(block_text):
            open_next_file()

        current_writer.write_url_block(block_text)
        total_written += 1

    current_writer.close()

    if total_written == 0:
        (output_dir / filenames[0]).unlink(missing_ok=True)
        return []

    return filenames
