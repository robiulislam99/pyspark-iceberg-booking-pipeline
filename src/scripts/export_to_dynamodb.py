"""
Reads Iceberg rental_property rows that changed/opened on a given date
(per that date's changelog files) and writes each one as an item into
DynamoDB Local.

Usage: python export_to_dynamodb.py 20260714

Uses df.foreachPartition() instead of df.collect() -- each Spark worker
writes its own slice of rows directly to DynamoDB, rather than pulling
the entire result set into the driver's memory first. At small data
volumes this makes no visible difference, but it's the pattern that
scales: collect() would eventually crash the driver on a large enough
table, foreachPartition() never brings more than one partition's worth
of rows into any single process at a time.
"""
import sys

from src.clients.spark_session import get_spark
from src.core.file_locator import get_changelog_ids

TABLE = "local.booking.rental_property"


def _export_partition(rows):
    """
    Runs independently on each Spark worker -- only sees its own
    partition's rows, never the full dataset. Imports are done inside
    the function because this code runs on worker processes, which
    don't share the driver's already-imported modules.
    """
    from src.clients.dynamodb_client import batch_put_items
    from src.mappers.dynamodb_document_mapper import to_dynamodb_item

    items = [to_dynamodb_item(row.asDict()) for row in rows]
    items = [item for item in items if item["property_id"] and item["timestamp"]]

    if items:
        batch_put_items(items)


def export_date(spark, date_str: str):
    changed_ids = set(get_changelog_ids(date_str, "changed"))
    opened_ids = set(get_changelog_ids(date_str, "opened"))
    relevant_ids = changed_ids | opened_ids

    if not relevant_ids:
        print(f"No changelog IDs for {date_str}, nothing to export.")
        return

    id_list = ", ".join(f"'{fid}'" for fid in relevant_ids)
    df = spark.sql(f"SELECT * FROM {TABLE} WHERE feed_provider_id IN ({id_list})")

    row_count = df.count()
    if row_count == 0:
        print(f"No matching rows found in Iceberg for date={date_str}")
        return

    df.foreachPartition(_export_partition)
    print(f"Wrote {row_count} item(s) to DynamoDB Local table 'rental_properties' for date={date_str}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python export_to_dynamodb.py <YYYYMMDD>")
        sys.exit(1)

    date_str = sys.argv[1]
    spark = get_spark("export-dynamodb")
    export_date(spark, date_str)
    spark.stop()