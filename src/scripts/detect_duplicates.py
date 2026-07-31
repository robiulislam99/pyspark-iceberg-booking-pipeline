"""
Loads our Iceberg properties and a partner's mock data (e.g.
warehouse/verbo_mock_data.json), and reports likely duplicate listings
between the two, based on geo distance + 8-field weighted similarity.

Usage: python detect_duplicates.py [path/to/partner_mock_data.json]
Defaults to /app/warehouse/verbo_mock_data.json if no path given.
"""

import json
import sys
from pathlib import Path

from clients.spark_session import get_spark
from core.duplicate_detector import find_duplicates

DEFAULT_MOCK_PATH = "/app/warehouse/verbo_mock_data.json"
FIELDS_NEEDED = [
    "external_id",
    "latlon",
    "property_name",
    "property_type",
    "location_display",
    "bedroom_count",
    "bathroom_count",
    "property_description",
    "other_policy",
]


def load_iceberg_rows():
    spark = get_spark("detect-duplicates")
    columns = ", ".join(FIELDS_NEEDED)
    df = spark.sql(f"SELECT {columns} FROM local.booking.rental_property")
    return [row.asDict() for row in df.collect()]


def load_partner_rows(path: str):
    data = json.loads(Path(path).read_text())
    # Tolerates both a flat list and a {"properties": [...]}-style wrapper,
    # same defensive pattern used elsewhere in this project for feed files.
    if isinstance(data, list):
        return data
    return data.get("properties", data.get("data", []))


def main():
    mock_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MOCK_PATH

    print("Loading our properties from Iceberg...")
    source_rows = load_iceberg_rows()
    print(f"  {len(source_rows)} properties loaded")

    print(f"Loading partner data from {mock_path}...")
    candidate_rows = load_partner_rows(mock_path)
    print(f"  {len(candidate_rows)} properties loaded")

    print("Comparing (this may take a while -- one embedding call per text field per candidate pair)...")
    matches = find_duplicates(source_rows, candidate_rows)

    print(f"\nFound {len(matches)} likely duplicate(s):\n")
    for m in matches:
        print(f"  {m['source_id']}  <->  {m['candidate_id']}  " f"(overall={m['scores']['overall_score']}, distance={m['distance_m']}m)")


if __name__ == "__main__":
    main()
