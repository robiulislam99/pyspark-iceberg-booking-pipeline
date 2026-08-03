"""
Generates sitemap.xml (or sitemap-1.xml, sitemap-2.xml, ... + a
sitemap_index.xml, if the published property count exceeds 50,000)
from all published properties in Iceberg. Writes output to
/app/data/sitemaps/

Usage: python generate_sitemap.py
"""

from pathlib import Path

from clients.spark_session import get_spark
from core.sitemap_generator import (
    MAX_URLS_PER_SITEMAP,
    build_sitemap_index_xml,
    build_sitemap_xml,
    chunk_rows,
)

TABLE = "local.booking.rental_property"
OUTPUT_DIR = Path("/app/data/sitemaps")


def load_published_rows(spark) -> list[dict]:
    df = spark.sql(f"""
        SELECT external_id, property_slug, last_synced_at
        FROM {TABLE}
        WHERE is_published = true
    """)
    return [row.asDict() for row in df.collect()]


def main():
    spark = get_spark("generate-sitemap")
    rows = load_published_rows(spark)

    if not rows:
        print("No published properties found -- nothing to generate.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if len(rows) <= MAX_URLS_PER_SITEMAP:
        xml_content = build_sitemap_xml(rows)
        output_path = OUTPUT_DIR / "sitemap.xml"
        output_path.write_text(xml_content)
        print(f"Wrote {len(rows)} URL(s) to {output_path}")
    else:
        chunks = chunk_rows(rows)
        filenames = []
        for i, chunk in enumerate(chunks, start=1):
            filename = f"sitemap-{i}.xml"
            xml_content = build_sitemap_xml(chunk)
            (OUTPUT_DIR / filename).write_text(xml_content)
            filenames.append(filename)
            print(f"Wrote {len(chunk)} URL(s) to {OUTPUT_DIR / filename}")

        index_xml = build_sitemap_index_xml(filenames)
        index_path = OUTPUT_DIR / "sitemap_index.xml"
        index_path.write_text(index_xml)
        print(f"Wrote sitemap index referencing {len(filenames)} file(s) to {index_path}")


if __name__ == "__main__":
    main()
