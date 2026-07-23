"""
Maps one Iceberg rental_property row into the target Elasticsearch
document shape. Only fields present in BOTH the Iceberg table and the
target ES shape are included -- see README for the full mapping notes.
"""

import json
import re

_POINT_RE = re.compile(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)")


def _parse_lonlat(latlon_text):
    """'SRID=4326;POINT (-97.085391 27.797983)' -> {'coordinates': [-97.085391, 27.797983]}"""
    if not latlon_text:
        return None
    match = _POINT_RE.search(latlon_text)
    if not match:
        return None
    lon, lat = float(match.group(1)), float(match.group(2))
    return [lon, lat]


def _build_property_attributes(row: dict, policy: dict) -> list:
    attributes = []
    if row.get("family_friendly"):
        attributes.append("Family Friendly")
    if row.get("group_friendly"):
        attributes.append("Group Friendly")
    if policy.get("free_cancellation"):
        attributes.append("Free Cancellation")
    return attributes


def to_es_document(row: dict) -> dict:
    property_flags = json.loads(row.get("property_flags") or "{}")
    policy = json.loads(row.get("policy") or "{}")

    return {
        "id": row.get("external_id"),
        "feed_provider_id": row.get("feed_provider_id"),
        "feed": row.get("feed"),
        "feed_provider_url": row.get("feed_provider_url"),
        "property_name": row.get("property_name"),
        "property_slug": row.get("property_slug"),
        "property_type": row.get("property_type"),
        "property_type_category": row.get("property_type_category"),
        "city": row.get("city"),
        "country": row.get("country"),
        "country_code": row.get("country_code"),
        "display": row.get("location_display"),
        "lonlat": _parse_lonlat(row.get("latlon")),
        "star_rating": row.get("star_rating"),
        "review_score_general": float(row["review_score_general"])
        if row.get("review_score_general") is not None
        else None,
        "number_of_review": row.get("number_of_review"),
        "bedroom_count": row.get("bedroom_count"),
        "bathroom_count": row.get("bathroom_count"),
        "occupancy": row.get("occupancy"),
        "usd_price": float(row["price"]) if row.get("price") is not None else None,
        "min_stay": row.get("min_stay"),
        "feature_image": row.get("feature_image"),
        "amenity_categories": row.get("amenity_categories"),
        "property_flags": property_flags,
        "property_attributes": _build_property_attributes(row, policy),
        "published": row.get("is_published"),
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
        "updated_at": row["last_synced_at"].isoformat() if row.get("last_synced_at") else None,
    }
