"""
Compares two Iceberg snapshots of the rental_property table and reports,
per row (by feed_provider_id), which specific columns changed.

Usage (inside the container or a notebook):
    from snapshot_diff import diff_snapshots
    diff_snapshots(spark, old_snapshot_id, new_snapshot_id)
"""
from src.clients.spark_session import get_spark

TABLE = "local.booking.rental_property"

# Columns to compare -- deliberately excludes bookkeeping timestamps
# (last_synced_at, source_updated_at) since those change on every sync
# by design and would drown out real data changes in the diff.
COMPARE_COLUMNS = [
    "external_id", "feed", "feed_provider_url",
    "property_name", "property_slug", "property_type", "property_type_category",
    "city", "country", "country_code", "location_display", "partner_location_id",
    "latlon",
    "star_rating", "review_score", "review_score_general", "number_of_review",
    "bedroom_count", "bathroom_count", "occupancy", "max_occupancy",
    "currency", "price", "min_stay",
    "feature_image", "images",
    "amenities", "amenity_categories", "policy", "property_flags",
    "is_published",
]


def diff_snapshots(spark, old_snapshot_id: int, new_snapshot_id: int, limit: int = 50):
    old_df = spark.read.option("snapshot-id", old_snapshot_id).table(TABLE)
    new_df = spark.read.option("snapshot-id", new_snapshot_id).table(TABLE)

    old_df.createOrReplaceTempView("_snap_old")
    new_df.createOrReplaceTempView("_snap_new")

    select_diffs = ",\n            ".join(
        f"""CASE
                WHEN o.{col} IS DISTINCT FROM n.{col}
                THEN '{col}'
            END AS diff_{col}"""
        for col in COMPARE_COLUMNS
    )

    result = spark.sql(f"""
        SELECT
            n.feed_provider_id,
            n.property_name,
            {select_diffs}
        FROM _snap_new n
        JOIN _snap_old o ON n.feed_provider_id = o.feed_provider_id
    """)

    # Collapse the per-column flag fields into one readable "changed_fields" list per row
    diff_col_names = [f"diff_{col}" for col in COMPARE_COLUMNS]
    rows = result.collect()

    changed_rows = []
    for row in rows:
        changed = [row[c] for c in diff_col_names if row[c] is not None]
        if changed:
            changed_rows.append({
                "feed_provider_id": row["feed_provider_id"],
                "property_name": row["property_name"],
                "changed_fields": changed,
            })

    print(f"{len(changed_rows)} row(s) changed between snapshot {old_snapshot_id} and {new_snapshot_id}")
    for r in changed_rows[:limit]:
        print(r)

    return changed_rows