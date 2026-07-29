"""
Given a property's Qdrant point ID (or external_id), find other
properties that are semantically similar -- based on the embedded
name/type/city/amenities text, not keyword/filter matching (that's
Elasticsearch's job, kept separate on purpose).
"""

from qdrant_client.models import FieldCondition, Filter, MatchValue

from clients.qdrant_client import COLLECTION_NAME, get_qdrant_client
from mappers.qdrant_document_mapper import external_id_to_point_id


def get_similar_properties(external_id: str, k: int = 5, published_only: bool = True) -> list[dict]:
    """
    external_id: the source property's real ID (e.g. "BC-12908249"),
    not the Qdrant UUID -- this function does that conversion internally.

    Returns a list of {external_id, property_name, city, score} dicts,
    best match first, excluding the source property itself.
    """
    client = get_qdrant_client()
    point_id = external_id_to_point_id(external_id)

    source_points = client.retrieve(collection_name=COLLECTION_NAME, ids=[point_id], with_vectors=True)
    if not source_points:
        return []

    source_vector = source_points[0].vector

    query_filter = None
    if published_only:
        query_filter = Filter(must=[FieldCondition(key="published", match=MatchValue(value=True))])

    results = client.search(
        collection_name=COLLECTION_NAME,
        query_vector=source_vector,
        query_filter=query_filter,
        limit=k + 1,  # +1 to account for the source property itself showing up
    )

    similar = [
        {
            "external_id": r.payload.get("external_id"),
            "property_name": r.payload.get("property_name"),
            "city": r.payload.get("city"),
            "score": r.score,
        }
        for r in results
        if r.payload.get("external_id") != external_id
    ]

    return similar[:k]
