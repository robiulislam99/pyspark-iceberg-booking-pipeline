"""
Maps one S3-exported property document into a Qdrant point: an
embedding vector (from a text summary of the property) + a payload
(fields used for filtering search results, e.g. published/city/price).

Qdrant point IDs must be an integer or a valid UUID -- external_id is
a string like "BC-12908249", not a UUID, so it's deterministically
converted via uuid5. The original external_id is preserved in the
payload for lookup, since the UUID itself isn't human-readable.
"""

import uuid

from qdrant_client.models import PointStruct

from clients.embedding_client import generate_embedding

# Deterministic namespace -- same external_id always produces the same
# UUID, so re-running an export overwrites the same point instead of
# creating duplicates.
_QDRANT_ID_NAMESPACE = uuid.NAMESPACE_DNS


def external_id_to_point_id(external_id: str) -> str:
    return str(uuid.uuid5(_QDRANT_ID_NAMESPACE, external_id))


def _boolean_flags_as_text(prop: dict) -> list[str]:
    """Turns boolean property flags into readable phrases so they
    contribute to the embedding's semantic meaning (e.g. a query like
    'pet friendly cabin' should match)."""
    flags = []
    if prop.get("IsPetFriendly"):
        flags.append("pet friendly")
    if prop.get("AdultOnly"):
        flags.append("adults only")
    if prop.get("LongStayFriendlyHome"):
        flags.append("long stay friendly")
    if prop.get("WorkFriendlyHome"):
        flags.append("work friendly")
    return flags


def build_embedding_text(document: dict) -> str:
    """
    Combines the fields that matter for "similar property" matching
    into one text string. Only uses fields already present in the S3
    document shape -- no fabricated fields.
    """
    prop = document.get("Property", {})
    partner = document.get("Partner", {})

    parts = [
        prop.get("PropertyName") or "",
        prop.get("PropertyType") or "",
        prop.get("PropertyTypeCategory") or "",
        document.get("City") or "",
        document.get("Country") or "",
        prop.get("PropertyDescription") or "",
    ]

    property_amenities = prop.get("Amenities") or []
    if property_amenities:
        parts.append(", ".join(property_amenities))

    partner_amenities = partner.get("Amenities") or []
    if partner_amenities:
        parts.append(", ".join(partner_amenities))

    parts.extend(_boolean_flags_as_text(prop))

    return " | ".join(p for p in parts if p)


def to_qdrant_point(document: dict) -> PointStruct | None:
    """
    Takes one S3 document (the shape produced by s3_document_mapper.py)
    and returns a PointStruct ready for bulk_upsert(). Returns None if
    there's no usable ID or embeddable text -- callers should skip Nones
    rather than crash the batch.
    """
    external_id = document.get("ID")
    if not external_id:
        return None

    text = build_embedding_text(document)
    if not text:
        return None

    prop = document.get("Property", {})
    counts = prop.get("Counts", {})

    return PointStruct(
        id=external_id_to_point_id(external_id),
        vector=generate_embedding(text),
        payload={
            "external_id": external_id,
            "property_name": prop.get("PropertyName"),
            "property_type": prop.get("PropertyType"),
            "city": document.get("City"),
            "country": document.get("Country"),
            "usd_price": prop.get("Price"),
            "published": document.get("Published"),
            "feature_image": prop.get("FeatureImage"),
            "star_rating": prop.get("StarRating"),
            "review_score": prop.get("ReviewScore"),
            "bedroom_count": counts.get("Bedroom"),
            "bathroom_count": counts.get("Bathroom"),
            "occupancy": counts.get("Occupancy"),
            "min_stay": prop.get("MinStay"),
            "is_pet_friendly": prop.get("IsPetFriendly", False),
            "adult_only": prop.get("AdultOnly", False),
            "long_stay_friendly_home": prop.get("LongStayFriendlyHome", False),
            "work_friendly_home": prop.get("WorkFriendlyHome", False),
        },
    )
