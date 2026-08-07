"""
Generates property-sitemap.xml.gz (or property-sitemap-1.xml.gz, property-sitemap-2.xml.gz, ... +
a property-sitemap_index.xml.gz, if the published property count exceeds the
per-file limit) from all published properties in Iceberg.

Usage: python generate_property_sitemap.py
"""

from pathlib import Path

from clients.spark_session import get_spark
from core.sitemap_generator import write_sitemap_files

TABLE = "local.booking.rental_property"
OUTPUT_DIR = Path("/app/data/sitemaps")


def load_published_rows_iterator(spark):
    df = spark.sql(f"""
        SELECT external_id, property_slug, last_synced_at, feature_image, images
        FROM {TABLE}
        WHERE is_published = true
    """)
    return (row.asDict() for row in df.toLocalIterator())


def main():
    spark = get_spark("generate-sitemap")
    try:
        row_iterator = load_published_rows_iterator(spark)
        filenames = write_sitemap_files(row_iterator, OUTPUT_DIR, "property-sitemap")

        if not filenames:
            print("No published properties found -- nothing to generate.")
            return

        for filename in filenames:
            size_mb = (OUTPUT_DIR / filename).stat().st_size / (1024 * 1024)
            print(f"Wrote {filename} ({size_mb:.2f} MB compressed)")

    finally:
        spark.stop()


if __name__ == "__main__":
    main()
