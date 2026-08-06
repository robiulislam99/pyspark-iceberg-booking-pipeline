"""
Generates a sitemap.xml.gz scoped to one property's nearby listings
(within a radius), rather than the full site sitemap. Reuses the same
XML rendering + gzip approach as generate_sitemap.py, but queries
Elasticsearch (no Spark session needed) and doesn't need the 50MB/
50,000-URL rollover logic, since nearby results are inherently small
(bounded by the limit argument).

Usage: python generate_nearby_sitemap.py <property_id> [radius_km] [limit]

Examples:
  python generate_nearby_sitemap.py BC-10178627
  python generate_nearby_sitemap.py BC-10178627 10 30
"""

import gzip
import sys
from pathlib import Path

from core.nearby_service import get_nearby_properties_for_sitemap
from core.sitemap_generator import render_footer, render_header, render_url_block

OUTPUT_DIR = Path("/app/data/sitemaps")


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_nearby_sitemap.py <property_id> [radius_km] [limit]")
        sys.exit(1)

    property_id = sys.argv[1]
    radius_km = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    rows = get_nearby_properties_for_sitemap(property_id, radius_km=radius_km, limit=limit)

    if not rows:
        print(f"No nearby published properties found for {property_id} within {radius_km}km " f"-- nothing to generate.")
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_id = property_id.replace("/", "_")
    output_path = OUTPUT_DIR / f"sitemap-nearby-{safe_id}.xml.gz"

    with gzip.open(output_path, "wt", encoding="utf-8") as f:
        f.write(render_header())
        for row in rows:
            f.write(render_url_block(row))
        f.write(render_footer())

    print(f"Wrote {len(rows)} nearby URL(s) to {output_path}")


if __name__ == "__main__":
    main()
