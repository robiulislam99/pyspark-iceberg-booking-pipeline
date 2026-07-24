"""
Unit tests for src/scripts/run_sync.py

This module has no functions to import -- it's a `__main__`-guarded
script, so we execute it with runpy while mocking its two dependencies.

Run:
    docker compose exec spark pytest tests/unit/test_run_sync.py -v
"""

import runpy
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Adjust this path if run_sync.py lives somewhere else in your repo.
SCRIPT_PATH = str(Path(__file__).resolve().parents[2] / "src" / "scripts" / "run_sync.py")


def test_run_sync_missing_argument_exits(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_sync.py"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(SCRIPT_PATH, run_name="__main__")

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Usage: python run_sync.py <YYYYMMDD>" in captured.out


def test_run_sync_too_many_arguments_exits(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_sync.py", "20260714", "extra"])

    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(SCRIPT_PATH, run_name="__main__")

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Usage: python run_sync.py <YYYYMMDD>" in captured.out


def test_run_sync_calls_sync_and_publishes_event(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["run_sync.py", "20260714"])
    summary = {"feed_provider_ids": ["p1", "p2"], "changed": 2}

    with (
        patch("src.scripts.sync_iceberg.sync_accommodation_details", return_value=summary) as mock_sync,
        patch("src.clients.sqs_client.publish_sync_event") as mock_publish,
    ):
        runpy.run_path(SCRIPT_PATH, run_name="__main__")

    mock_sync.assert_called_once_with("20260714")
    mock_publish.assert_called_once_with(["p1", "p2"], "20260714")

    captured = capsys.readouterr()
    assert str(summary) in captured.out


def test_run_sync_no_feed_provider_ids_publishes_empty_list(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["run_sync.py", "20260714"])
    summary = {"changed": 0}  # no "feed_provider_ids" key at all

    with (
        patch("src.scripts.sync_iceberg.sync_accommodation_details", return_value=summary),
        patch("src.clients.sqs_client.publish_sync_event") as mock_publish,
    ):
        runpy.run_path(SCRIPT_PATH, run_name="__main__")

    mock_publish.assert_called_once_with([], "20260714")
