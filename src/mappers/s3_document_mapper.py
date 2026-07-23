"""
Maps one Iceberg rental_property row into the target S3 document shape
(the nested Feed/Partner/Property structure). Only fields present in the
Iceberg table, or directly derivable from its policy/property_flags
JSON, are included -- fields with no source in the schema (State,
StateAbbr, FeatureSummary, PropertyDescription, LicenseNumber,
PhoneNumber, EcoFriendly, IsAllInclusive, PropertyTypeCategoryId,
RoomSize, most other Is* booleans, etc.) are intentionally left out
rather than fabricated.

RankedImage/RankedImages ARE included, via image_ranker.rank_images() --
a Hugging Face aesthetic-scoring model ranks each property's photos
best-to-worst by visual quality alone (not by description/room content).
"""
import json
import re
from src.core.image_ranker import rank_images

_POINT_RE = re.compile(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)")


def _parse_latlng(latlon_text):
    """'SRID=4326;POINT (-97.085391 27.797983)' -> ('27.797983', '-97.085391')"""
    if not latlon_text:
        return None, None
    match = _POINT_RE.search(latlon_text)
    if not match:
        return None, None
    lon, lat = match.group(1), match.group(2)
    return lat, lon


def to_s3_document(row: dict) -> dict:
    policy = json.loads(row.get("policy") or "{}")
    property_flags = json.loads(row.get("property_flags") or "{}")
    lat, lng = _parse_latlng(row.get("latlon"))
    images = row.get("images") or []

    document = {
        "Feed": row.get("feed"),
        "City": row.get("city"),
        "Country": row.get("country"),
        "CountryCode": row.get("country_code"),
        "Display": row.get("location_display"),
        "Lat": lat,
        "Lng": lng,
        "LocationID": row.get("partner_location_id"),
        "ID": row.get("external_id"),
        "Partner": {
            "Amenities": row.get("amenities") or [],
            "Policies": {
                "CancellationPolicy": "Free cancellation" if policy.get("free_cancellation") else "No free cancellation",
                "CheckinPolicy": policy.get("checkin_age_policy_text"),
                "PetPolicy": policy.get("pets_policy_text"),
            },
            "URL": row.get("feed_provider_url"),
        },
        "Property": {
            "AdultOnly": policy.get("adults_only_checkin", False),
            "Amenities": row.get("amenity_categories") or [],
            "Counts": {
                "Bathroom": row.get("bathroom_count"),
                "Bedroom": row.get("bedroom_count"),
                "Occupancy": row.get("occupancy"),
                "Reviews": row.get("number_of_review"),
            },
            "FeatureImage": row.get("feature_image"),
            "Image": {
                "Count": len(images),
                "Images": images,
            },
            "RankedImage": None,       # filled in below, after ranking
            "RankedImages": {
                "Count": 0,
                "Images": [],
            },
            "IsPetFriendly": policy.get("pets_allowed", False),
            "LongStayFriendlyHome": property_flags.get("long_stay_friendly_home", False),
            "MinStay": row.get("min_stay"),
            "Price": float(row["price"]) if row.get("price") is not None else None,
            "PropertyName": row.get("property_name"),
            "PropertySlug": row.get("property_slug"),
            "PropertyType": row.get("property_type"),
            "ReviewScore": float(row["review_score_general"]) if row.get("review_score_general") is not None else None,
            "StarRating": row.get("star_rating"),
            "UpdatedAt": row["last_synced_at"].isoformat() if row.get("last_synced_at") else None,
            "WorkFriendlyHome": property_flags.get("work_friendly_home", False),
        },
        "Published": row.get("is_published"),
    }

    if images:
        ranked = rank_images(images)
        top_ranked = ranked[:4]  
        document["Property"]["RankedImage"] = top_ranked[0] if top_ranked else None
        document["Property"]["RankedImages"] = {
            "Count": len(top_ranked),
            "Images": top_ranked,
        }

    return document

    return document