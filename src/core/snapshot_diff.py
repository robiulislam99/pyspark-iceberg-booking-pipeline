"""
Compares two Iceberg snapshots of the rental_property table and reports,
per row (by feed_provider_id), which specific columns changed.

Usage (inside the container or a notebook):
    from snapshot_diff import diff_snapshots
    diff_snapshots(spark, old_snapshot_id, new_snapshot_id)
"""

TABLE = "local.booking.rental_property"

# Columns to compare -- deliberately excludes bookkeeping timestamps
# (last_synced_at, source_updated_at) since those change on every sync
# by design and would drown out real data changes in the diff.
COMPARE_COLUMNS = [
    "external_id",
    "feed",
    "feed_provider_url",
    "property_name",
    "property_slug",
    "property_type",
    "property_type_category",
    "city",
    "country",
    "country_code",
    "location_display",
    "partner_location_id",
    "latlon",
    "star_rating",
    "review_score",
    "review_score_general",
    "number_of_review",
    "bedroom_count",
    "bathroom_count",
    "occupancy",
    "max_occupancy",
    "currency",
    "price",
    "min_stay",
    "feature_image",
    "images",
    "amenities",
    "amenity_categories",
    "policy",
    "property_flags",
    "is_published",
]


def diff_snapshots(spark, old_snapshot_id: int, new_snapshot_id: int, limit: int | None = None):
    old_df = spark.read.option("snapshot-id", old_snapshot_id).table(TABLE)
    new_df = spark.read.option("snapshot-id", new_snapshot_id).table(TABLE)

    old_rows = old_df.collect()
    new_rows = new_df.collect()

    def _row_map(row):
        if hasattr(row, "asDict"):
            return row.asDict()
        return dict(row)

    old_by_id = {
        _row_map(row).get("feed_provider_id"): _row_map(row) for row in old_rows if _row_map(row).get("feed_provider_id") is not None
    }
    new_by_id = {
        _row_map(row).get("feed_provider_id"): _row_map(row) for row in new_rows if _row_map(row).get("feed_provider_id") is not None
    }

    changed_rows = []
    for feed_provider_id in new_by_id:
        if feed_provider_id not in old_by_id:
            continue

        old_row = old_by_id[feed_provider_id]
        new_row = new_by_id[feed_provider_id]
        changed_fields = [col for col in COMPARE_COLUMNS if old_row.get(col) != new_row.get(col)]

        changed_rows.append(
            {
                "feed_provider_id": feed_provider_id,
                "property_name": new_row.get("property_name"),
                "changed_fields": changed_fields,
            }
        )

    if limit is None:
        changed_rows = [row for row in changed_rows if row["changed_fields"]]
        display_limit = len(changed_rows)
    else:
        display_limit = limit

    print(f"{len(changed_rows)} row(s) changed between snapshot {old_snapshot_id} and {new_snapshot_id}")
    for r in changed_rows[:display_limit]:
        print(r)

    return changed_rows
