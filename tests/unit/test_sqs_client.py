"""
Unit tests for src/clients/sqs_client.py

Uses moto to mock SQS entirely in-memory -- no LocalStack container
needed to run these tests.

Run:
    docker compose exec spark pytest tests/unit/test_sqs_client.py -v
"""

import importlib
import json

import pytest
from moto import mock_aws


@pytest.fixture
def sqs_client(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("SQS_ENDPOINT_URL", "http://sqs-mock-only:4566")
    monkeypatch.setenv("SQS_QUEUE_NAME", "booking-property-updates-test")

    with mock_aws():
        import clients.sqs_client as module

        importlib.reload(module)
        yield module


def test_ensure_queue_creates_queue(sqs_client):
    queue_url = sqs_client.ensure_queue()
    assert sqs_client.QUEUE_NAME in queue_url


def test_ensure_queue_is_idempotent(sqs_client):
    first_url = sqs_client.ensure_queue()
    second_url = sqs_client.ensure_queue()
    assert first_url == second_url


def test_publish_sync_event_sends_message(sqs_client):
    sqs_client.publish_sync_event(["p1", "p2"], "2026-07-24")

    client, queue_url, messages = sqs_client.receive_messages(max_messages=10, wait_time=0)
    assert len(messages) == 1

    body = json.loads(messages[0]["Body"])
    assert body == {"date": "2026-07-24", "feed_provider_ids": ["p1", "p2"]}


def test_publish_sync_event_with_empty_ids_does_not_send(sqs_client):
    sqs_client.ensure_queue()
    sqs_client.publish_sync_event([], "2026-07-24")

    client, queue_url, messages = sqs_client.receive_messages(max_messages=10, wait_time=0)
    assert messages == []


def test_receive_messages_returns_client_queue_url_and_messages(sqs_client):
    sqs_client.publish_sync_event(["p1"], "2026-07-24")

    client, queue_url, messages = sqs_client.receive_messages(max_messages=5, wait_time=0)

    assert sqs_client.QUEUE_NAME in queue_url
    assert len(messages) == 1
    assert "ReceiptHandle" in messages[0]


def test_delete_message_removes_message_from_queue(sqs_client):
    sqs_client.publish_sync_event(["p1"], "2026-07-24")

    client, queue_url, messages = sqs_client.receive_messages(max_messages=10, wait_time=0)
    receipt_handle = messages[0]["ReceiptHandle"]

    sqs_client.delete_message(client, queue_url, receipt_handle)

    _, _, remaining = sqs_client.receive_messages(max_messages=10, wait_time=0)
    assert remaining == []
