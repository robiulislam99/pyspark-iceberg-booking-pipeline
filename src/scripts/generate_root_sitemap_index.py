"""
The single entry-point sitemap: references every other sitemap file
under data/sitemaps/ -- the main property sitemap(s) AND the combined
nearby sitemap(s). This is the one URL that should actually be
submitted to search engines / listed in robots.txt.

Run this AFTER generate_property_sitemap.py and generate_nearby_sitemap.py have
both already produced their files.

Usage: python generate_root_sitemap_index.py
"""

import gzip
from pathlib import Path

from core.sitemap_generator import render_sitemap_index

SITEMAPS_DIR = Path("/app/data/sitemaps")


def main():
    if not SITEMAPS_DIR.exists():
        print(f"{SITEMAPS_DIR} doesn't exist -- run generate_property_sitemap.py first.")
        return

    all_filenames = sorted(f.name for f in SITEMAPS_DIR.glob("*.xml.gz") if f.name != "sitemap_index.xml.gz")

    if not all_filenames:
        print("No sitemap files found -- nothing to index.")
        return

    index_content = render_sitemap_index(all_filenames)
    index_path = SITEMAPS_DIR / "sitemap_index.xml.gz"

    with gzip.open(index_path, "wt", encoding="utf-8") as f:
        f.write(index_content)

    print(f"Wrote root sitemap index referencing {len(all_filenames)} file(s) to {index_path}")


if __name__ == "__main__":
    main()
