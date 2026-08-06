"""
Standalone script: given a property ID, prints the properties within a
radius of it (default 5km), nearest first.

Usage: python find_nearby.py <property_id> [radius_km] [limit]

Examples:
  python find_nearby.py BC-10178627
  python find_nearby.py BC-10178627 10
  python find_nearby.py BC-10178627 10 15
"""

import sys

from core.nearby_service import get_nearby_properties_for_id


def main():
    if len(sys.argv) < 2:
        print("Usage: python find_nearby.py <property_id> [radius_km] [limit]")
        sys.exit(1)

    property_id = sys.argv[1]
    radius_km = float(sys.argv[2]) if len(sys.argv) > 2 else 5
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 20

    results = get_nearby_properties_for_id(property_id, radius_km=radius_km, limit=limit)

    if not results:
        print(f"No nearby properties found for {property_id} within {radius_km}km " f"(or {property_id} doesn't exist / has no lonlat).")
        return

    print(f"Properties within {radius_km}km of {property_id}:\n")
    for r in results:
        print(
            f"  {r['distance_km']:5.2f} km  "
            f"{r['id']:<15} "
            f"{r['property_name']:<35} "
            f"{r['city']}, {r['country']}  (${r['usd_price']})"
        )


if __name__ == "__main__":
    main()
