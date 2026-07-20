"""
Long-running consumer: polls SQS (LocalStack) for sync events, re-fetches
FRESH rows from Iceberg for the referenced feed_provider_ids (not whatever
was passed in the message -- always re-read from the source of truth),
maps them, and bulk-upserts into Elasticsearch.

Run:  python sqs_consumer.py
Stop: Ctrl+C
"""
import json
import logging

from spark_session import get_spark
from sqs_client import receive_messages, delete_message
from es_client import get_es_client, bulk_upsert
from es_document_mapper import to_es_document

logger = logging.getLogger("booking_lake.sqs_consumer")
logging.basicConfig(level=logging.INFO)

TABLE = "local.booking.rental_property"


def fetch_rows(spark, feed_provider_ids):
    if not feed_provider_ids:
        return []
    id_list = ", ".join(f"'{fid}'" for fid in feed_provider_ids)
    df = spark.sql(f"SELECT * FROM {TABLE} WHERE feed_provider_id IN ({id_list})")
    return [row.asDict() for row in df.collect()]


def main():
    spark = get_spark("sqs-consumer")
    es = get_es_client()

    logger.info("Consumer started, polling SQS...")
    while True:
        client, queue_url, messages = receive_messages(max_messages=10, wait_time=10)
        if not messages:
            continue

        for message in messages:
            try:
                payload = json.loads(message["Body"])
                feed_provider_ids = payload.get("feed_provider_ids", [])
                date_str = payload.get("date")

                rows = fetch_rows(spark, feed_provider_ids)
                documents = [to_es_document(r) for r in rows]
                if documents:
                    bulk_upsert(es, documents)
                    logger.info(f"Indexed {len(documents)} document(s) into ES for date={date_str}")

                delete_message(client, queue_url, message["ReceiptHandle"])
            except Exception as e:
                logger.exception(f"Failed to process message: {e}")
                # message left in queue -- SQS/LocalStack redelivers after visibility timeout


if __name__ == "__main__":
    main()