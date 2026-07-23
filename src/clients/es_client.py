import os

from elasticsearch import Elasticsearch, helpers

ES_URL = os.environ.get("ELASTICSEARCH_URL", "http://elasticsearch:9200")
INDEX_NAME = os.environ.get("ES_INDEX_NAME", "rental_properties")

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "lonlat": {"type": "geo_point"},
        }
    }
}


def get_es_client() -> Elasticsearch:
    return Elasticsearch(ES_URL)


def ensure_index(es: Elasticsearch):
    if not es.indices.exists(index=INDEX_NAME):
        es.indices.create(index=INDEX_NAME, body=INDEX_MAPPING)


def bulk_upsert(es: Elasticsearch, documents: list):
    """documents: list of dicts, each must have an 'id' key used as _id."""
    ensure_index(es)
    actions = [
        {"_op_type": "index", "_index": INDEX_NAME, "_id": doc["id"], "_source": doc}
        for doc in documents
    ]
    helpers.bulk(es, actions)
