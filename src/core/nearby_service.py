"""
"Nearby properties" feature: given a center point (lat/lon), returns
published properties within a circular radius, using Elasticsearch's
geo_distance query against the already-indexed lonlat geo_point field
(same field confirmed working for the Kibana map).

Kept separate from similarity_service.py (Qdrant, semantic similarity)
on purpose -- this is pure geographic proximity, a different concern.
"""

import os

from clients.es_client import get_es_client

INDEX_NAME = os.environ.get("ES_INDEX_NAME", "rental_properties")


def get_nearby_properties(
    lat: float,
    lon: float,
    radius_km: float = 5,
    limit: int = 20,
    published_only: bool = True,
) -> list[dict]:
    """
    Returns properties within radius_km of (lat, lon), sorted nearest
    first. Each result includes distance_km alongside the source fields.
    """
    es = get_es_client()

    filters = [
        {
            "geo_distance": {
                "distance": f"{radius_km}km",
                "lonlat": {"lat": lat, "lon": lon},
            }
        }
    ]
    if published_only:
        filters.append({"term": {"published": True}})

    query = {
        "query": {"bool": {"filter": filters}},
        "sort": [
            {
                "_geo_distance": {
                    "lonlat": {"lat": lat, "lon": lon},
                    "order": "asc",
                    "unit": "km",
                }
            }
        ],
        "size": limit,
    }

    response = es.search(index=INDEX_NAME, body=query)

    results = []
    for hit in response["hits"]["hits"]:
        source = hit["_source"]
        # sort values include the computed geo distance, in the same
        # order as the "sort" clause above -- first (only) entry here
        distance_km = hit["sort"][0] if hit.get("sort") else None
        results.append(
            {
                "id": source.get("id"),
                "property_name": source.get("property_name"),
                "city": source.get("city"),
                "country": source.get("country"),
                "usd_price": source.get("usd_price"),
                "star_rating": source.get("star_rating"),
                "distance_km": round(distance_km, 2) if distance_km is not None else None,
            }
        )

    return results


def get_nearby_properties_for_id(
    property_id: str,
    radius_km: float = 5,
    limit: int = 20,
    published_only: bool = True,
) -> list[dict]:
    """
    Convenience wrapper: looks up a property's own lonlat by ID first,
    then finds what's nearby -- excludes the source property itself
    from results.
    """
    es = get_es_client()
    doc = es.get(index=INDEX_NAME, id=property_id, ignore=[404])

    if not doc or not doc.get("found"):
        return []

    lonlat = doc["_source"].get("lonlat")
    if not lonlat or len(lonlat) != 2:
        return []

    lon, lat = lonlat  # stored as [lon, lat], per es_document_mapper.py's _parse_lonlat
    results = get_nearby_properties(lat, lon, radius_km, limit + 1, published_only)

    return [r for r in results if r["id"] != property_id][:limit]
