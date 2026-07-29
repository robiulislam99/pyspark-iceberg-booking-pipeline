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


def build_embedding_text(document: dict) -> str:
    """
    Combines the fields that matter for "similar property" matching
    into one text string. Only uses fields already present in the S3
    document shape -- no fabricated fields.
    """
    prop = document.get("Property", {})
    parts = [
        prop.get("PropertyName") or "",
        prop.get("PropertyType") or "",
        prop.get("PropertyTypeCategory") or "",
        document.get("City") or "",
        document.get("Country") or "",
    ]
    amenities = prop.get("Amenities") or []
    if amenities:
        parts.append(", ".join(amenities))

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

    return PointStruct(
        id=external_id_to_point_id(external_id),
        vector=generate_embedding(text),
        payload={
            "external_id": external_id,
            "property_name": prop.get("PropertyName"),
            "city": document.get("City"),
            "country": document.get("Country"),
            "usd_price": prop.get("Price"),
            "published": document.get("Published"),
        },
    )
