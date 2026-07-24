"""
Thin boto3 wrapper pointed at LocalStack's SQS emulation instead of real
AWS -- no AWS account or credentials needed, endpoint_url does all the work.
"""

import json
import os

import boto3

SQS_ENDPOINT_URL = os.environ.get("SQS_ENDPOINT_URL", "http://localstack:4566")
QUEUE_NAME = os.environ.get("SQS_QUEUE_NAME", "booking-property-updates")
AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")


def _client():
    kwargs = {"region_name": AWS_REGION}
    endpoint_url = SQS_ENDPOINT_URL

    if endpoint_url and endpoint_url.startswith("http://sqs-mock-only"):
        endpoint_url = None

    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url

    return boto3.client("sqs", **kwargs)


def ensure_queue() -> str:
    """create_queue is idempotent -- safe to call every time."""
    return _client().create_queue(QueueName=QUEUE_NAME)["QueueUrl"]


def publish_sync_event(feed_provider_ids: list, date_str: str):
    if not feed_provider_ids:
        return
    client = _client()
    queue_url = ensure_queue()
    payload = {"date": date_str, "feed_provider_ids": feed_provider_ids}
    client.send_message(QueueUrl=queue_url, MessageBody=json.dumps(payload))
    print(f"Published SQS event: {len(feed_provider_ids)} id(s) for date={date_str}")


def receive_messages(max_messages: int = 10, wait_time: int = 10):
    client = _client()
    queue_url = ensure_queue()
    resp = client.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_time,
    )
    return client, queue_url, resp.get("Messages", [])


def delete_message(client, queue_url, receipt_handle):
    client.delete_message(QueueUrl=queue_url, ReceiptHandle=receipt_handle)
