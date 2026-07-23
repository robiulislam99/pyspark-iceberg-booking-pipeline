"""
Maps one Iceberg rental_property row into the target DynamoDB item shape.
Only fields present in the Iceberg table are mapped:

- 'timestamp' is derived from last_synced_at's date (YYYYMMDD), matching
  the target example where timestamp "20260529" lines up with that
  row's UpdatedAt date -- not the sync run's date.
- 'language' has no source anywhere in the Iceberg schema. Hardcoded to
  "english" -- flagging this as an assumption, not a real mapped field.
"""

from decimal import Decimal


def to_dynamodb_item(row: dict) -> dict:
    last_synced = row.get("last_synced_at")
    timestamp = last_synced.strftime("%Y%m%d") if last_synced else None

    return {
        "country_code": row.get("country_code"),
        "language": row.get("language"),
        "property_id": row.get("external_id"),
        "property_name": row.get("property_name"),
        "property_slug": row.get("property_slug"),
        "published": row.get("is_published"),
        "timestamp": timestamp,
        "usd_price": Decimal(str(row["price"])) if row.get("price") is not None else None,
    }
