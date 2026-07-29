"""
Qdrant connection + collection management + bulk upsert, following the
same client-wrapper pattern as dynamodb_client.py / es_client.py.
"""

import os

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
COLLECTION_NAME = os.environ.get("QDRANT_COLLECTION_NAME", "rental_properties")
VECTOR_SIZE = 384  # all-MiniLM-L6-v2's output dimension


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)


def ensure_collection(client: QdrantClient):
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME in existing:
        return
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )


def bulk_upsert(points: list[PointStruct]):
    """points: list of qdrant_client.models.PointStruct, built by qdrant_document_mapper.py"""
    client = get_qdrant_client()
    ensure_collection(client)
    client.upsert(collection_name=COLLECTION_NAME, points=points)
