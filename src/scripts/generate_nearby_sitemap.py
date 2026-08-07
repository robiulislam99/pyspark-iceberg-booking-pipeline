"""
Generates a COMBINED nearby-properties sitemap across ALL published
properties -- for every property, finds what's within radius_km, then
writes the union of all those results as one set of gzip sitemap files
(nearby-sitemap.xml.gz, nearby-sitemap-2.xml.gz, ... if the 50,000-URL/
50MB limit is exceeded), same rollover rules as the main sitemap.

Deduplicated by external_id: the same property commonly shows up as
"nearby" for multiple source properties, but each URL should only
appear once in a sitemap.

Usage: python generate_nearby_sitemap.py [radius_km] [limit_per_property]
"""

import sys
from pathlib import Path

from core.nearby_service import get_all_published_ids, get_nearby_properties_for_sitemap
from core.sitemap_generator import write_sitemap_files

OUTPUT_DIR = Path("/app/data/sitemaps")


def collect_deduplicated_nearby_rows(radius_km: float, limit_per_property: int) -> dict:
    """Returns {external_id: row} -- last write wins on duplicates,
    harmless since the row content is the same regardless of which source property triggered its inclusion."""
    property_ids = get_all_published_ids()
    print(f"Found {len(property_ids)} published properties. Collecting nearby matches...")

    unique_rows = {}
    for i, property_id in enumerate(property_ids, start=1):
        rows = get_nearby_properties_for_sitemap(property_id, radius_km=radius_km, limit=limit_per_property)
        for row in rows:
            unique_rows[row["external_id"]] = row

        if i % 100 == 0:
            print(f"  ...{i}/{len(property_ids)} processed, {len(unique_rows)} unique nearby properties so far")

    return unique_rows


def main():
    radius_km = float(sys.argv[1]) if len(sys.argv) > 1 else 5
    limit_per_property = int(sys.argv[2]) if len(sys.argv) > 2 else 20

    unique_rows = collect_deduplicated_nearby_rows(radius_km, limit_per_property)

    if not unique_rows:
        print("No nearby matches found across any property -- nothing to generate.")
        return

    filenames = write_sitemap_files(iter(unique_rows.values()), OUTPUT_DIR, "nearby-sitemap")

    for filename in filenames:
        size_mb = (OUTPUT_DIR / filename).stat().st_size / (1024 * 1024)
        print(f"Wrote {filename} ({size_mb:.2f} MB compressed)")

    print(f"\nDone: {len(unique_rows)} unique nearby URL(s) across {len(filenames)} file(s)")


if __name__ == "__main__":
    main()
