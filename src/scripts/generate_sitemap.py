"""
Generates sitemap.xml.gz (or sitemap-1.xml.gz, sitemap-2.xml.gz, ... +
a sitemap_index.xml.gz, if the published property count exceeds the
per-file limit) from all published properties in Iceberg. Writes
output to /app/data/sitemaps/

Two per-file limits are enforced, per the sitemap protocol spec:
50,000 URLs OR 50MB uncompressed size, whichever comes first. Files
are also gzip-compressed on write (search engines accept .xml.gz
directly) -- both the byte-size tracking and the compression happen
here, since sitemap_generator.py only renders XML fragments as plain
strings and doesn't know about either concern.

Uses df.toLocalIterator() instead of df.collect() -- pulls rows one
partition at a time rather than materializing the entire result set in
the driver's memory upfront.

Usage: python generate_sitemap.py
"""

import gzip
from pathlib import Path

from clients.spark_session import get_spark
from core.sitemap_generator import (
    MAX_BYTES_PER_SITEMAP,
    MAX_URLS_PER_SITEMAP,
    SIZE_SAFETY_MARGIN_BYTES,
    render_footer,
    render_header,
    render_sitemap_index,
    render_url_block,
)

TABLE = "local.booking.rental_property"
OUTPUT_DIR = Path("/app/data/sitemaps")


def load_published_rows_iterator(spark):
    """
    Returns a lazy iterator over published rows -- toLocalIterator()
    pulls results partition-by-partition from Spark, not all at once,
    unlike collect().
    """
    df = spark.sql(f"""
        SELECT external_id, property_slug, last_synced_at, feature_image, images
        FROM {TABLE}
        WHERE is_published = true
    """)
    return df.toLocalIterator()


class SitemapFileWriter:
    """
    Wraps one open, gzip-compressed sitemap file, tracking URL count and
    UNCOMPRESSED byte size written so far (the sitemap protocol's 50MB
    limit is defined on uncompressed content, so size is tracked on the
    text before gzip does its own compression, not the compressed output).
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


def main():
    spark = get_spark("generate-sitemap")
    try:
        row_iterator = load_published_rows_iterator(spark)
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

        filenames = []
        current_writer = None
        file_index = 1
        total_written = 0

        def open_next_file():
            nonlocal current_writer, file_index
            if current_writer is not None:
                current_writer.close()

            filename = "sitemap.xml.gz" if file_index == 1 else f"sitemap-{file_index}.xml.gz"
            filenames.append(filename)
            current_writer = SitemapFileWriter(OUTPUT_DIR / filename)
            file_index += 1

        open_next_file()

        for row in row_iterator:
            row_dict = row.asDict()
            block_text = render_url_block(row_dict)

            if current_writer.would_overflow(block_text):
                open_next_file()

            current_writer.write_url_block(block_text)
            total_written += 1

        current_writer.close()

        if total_written == 0:
            print("No published properties found -- nothing to generate.")
            (OUTPUT_DIR / filenames[0]).unlink(missing_ok=True)
            return

        for filename in filenames:
            size_mb = (OUTPUT_DIR / filename).stat().st_size / (1024 * 1024)
            print(f"Wrote {filename} ({size_mb:.2f} MB compressed)")

        print(f"Wrote {total_written} URL(s) across {len(filenames)} file(s) to {OUTPUT_DIR}")

        if len(filenames) > 1:
            index_content = render_sitemap_index(filenames)
            index_path = OUTPUT_DIR / "sitemap_index.xml.gz"
            with gzip.open(index_path, "wt", encoding="utf-8") as f:
                f.write(index_content)
            print(f"Wrote sitemap index referencing {len(filenames)} file(s) to {index_path}")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
