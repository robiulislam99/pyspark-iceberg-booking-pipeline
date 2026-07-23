"""
Mirrors sync_booking_properties.py management command, then publishes
an SQS event listing which feed_provider_ids changed, for the consumer
to pick up and push into Elasticsearch.
"""

import sys

from src.clients.sqs_client import publish_sync_event
from src.scripts.sync_iceberg import sync_accommodation_details

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python run_sync.py <YYYYMMDD>")
        sys.exit(1)

    date_str = sys.argv[1]
    summary = sync_accommodation_details(date_str)
    print(summary)

    publish_sync_event(summary.get("feed_provider_ids", []), date_str)
