"""
Reads property documents from the local S3 export (written by
export_to_s3_local.py) for a given date and upserts embeddings into
Qdrant. Follows the same pattern as export_to_dynamodb.py /
export_to_s3_local.py: read -> map -> push, in batches.

Usage: python export_to_qdrant.py 20260714
"""

import json
import sys
from pathlib import Path

from clients.qdrant_client import bulk_upsert
from mappers.qdrant_document_mapper import to_qdrant_point

S3_LOCAL_ROOT = "/app/s3_local"
BUCKET_NAME = "booking-lake-bucket"
BATCH_SIZE = 500


def export_date(date_str: str):
    prefix_dir = Path(S3_LOCAL_ROOT) / BUCKET_NAME / "rental-properties" / f"date={date_str}"
    if not prefix_dir.exists():
        print(f"No S3 export found for date={date_str} -- run export_to_s3_local.py first.")
        return

    files = sorted(prefix_dir.glob("*.json"))
    if not files:
        print(f"No documents found under {prefix_dir}")
        return

    points = []
    skipped = 0
    for file_path in files:
        document = json.loads(file_path.read_text())
        point = to_qdrant_point(document)
        if point is None:
            skipped += 1
            continue
        points.append(point)

    if not points:
        print(f"No embeddable documents found for date={date_str}")
        return

    total_upserted = 0
    for i in range(0, len(points), BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        bulk_upsert(batch)
        total_upserted += len(batch)

    print(f"Upserted {total_upserted} point(s) into Qdrant (skipped {skipped}) for date={date_str}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python export_to_qdrant.py <YYYYMMDD>")
        sys.exit(1)

    export_date(sys.argv[1])
