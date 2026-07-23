"""
Reads processed rows from the Iceberg rental_property table and writes
each one as a JSON "object" into the local S3-like store, using
LocalS3Client -- the same put_object/list_objects_v2 calls you'd make
against real boto3 S3, just backed by the filesystem.

Usage: python export_to_s3_local.py 20260714
"""

import json
import sys

from src.clients.s3_local_client import LocalS3Client
from src.clients.spark_session import get_spark
from src.mappers.s3_document_mapper import to_s3_document

TABLE = "local.booking.rental_property"
BUCKET_NAME = "booking-lake-bucket"


def export_date(spark, date_str: str, client: LocalS3Client):
    client.create_bucket(Bucket=BUCKET_NAME)

    df = spark.sql(f"SELECT * FROM {TABLE}")
    rows = [row.asDict() for row in df.collect()]

    written = 0
    for row in rows:
        document = to_s3_document(row)
        key = f"rental-properties/date={date_str}/{document['ID']}.json"
        body = json.dumps(document, indent=2).encode("utf-8")
        client.put_object(Bucket=BUCKET_NAME, Key=key, Body=body)
        written += 1

    print(f"Wrote {written} object(s) to s3://{BUCKET_NAME}/rental-properties/date={date_str}/")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python export_to_s3_local.py <YYYYMMDD>")
        sys.exit(1)

    date_str = sys.argv[1]
    spark = get_spark("export-s3-local")
    client = LocalS3Client()
    export_date(spark, date_str, client)
    spark.stop()
