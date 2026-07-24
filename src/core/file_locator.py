"""
Finds and reads files from the dated Booking.com feed folders:

    booking/
      changelog/<date>/booking_changed_<date>.json
      accommodation_details/<date>/changed/booking_details_<date>_changed_<i>.json
      accommodation_details/<date>/opened/booking_details_<date>_opened_<i>.json
      reviews/<date>/...
      reviews_scores/<date>/...
      search/<date>/...

`<date>` is always an 8-digit string, e.g. "20260708".

This module only reads files -- it never touches Spark or a database, and
it knows nothing about what a "processed property" looks like. That keeps
it reusable for every feed type (accommodation_details, reviews,
reviews_scores, search) since they all share the same
date/changed-or-opened layout.

Ported from the Django version: the only change is where BOOKING_DATA_DIR
comes from (an env var instead of django.conf.settings), since this
container has no Django installed.
"""

import json
import os
from collections.abc import Iterator
from datetime import date as date_type
from pathlib import Path
from typing import Literal

FeedName = Literal["accommodation_details", "reviews", "reviews_scores", "search"]
Bucket = Literal["changed", "opened"]


def _data_dir() -> Path:
    return Path(os.environ["BOOKING_DATA_DIR"])


def format_date(d: date_type) -> str:
    """Convert a date object to the folder-name format, e.g. 2026-07-08 -> '20260708'."""
    return d.strftime("%Y%m%d")


def get_changelog_ids(date_str: str, kind: Literal["changed", "opened", "closed"] = "changed") -> list:
    """
    Read changelog/<date>/booking_<kind>_*.json -- a flat list of
    property IDs. `kind` is one of:
      - 'changed': properties updated that day
      - 'opened':  properties newly added/listed that day
      - 'closed':  properties removed/delisted that day

    Matches by folder (date_str) and file prefix (booking_<kind>_),
    regardless of the date embedded in the filename itself -- this
    tolerates cases where the folder date and the filename date drift
    apart (e.g. test data reused under a new date folder).

    Handles both possible JSON shapes:
      - a flat list:        [123, 456, ...]
      - a wrapped dict:      {"changed": [123, 456, ...]}

    Returns [] if no matching file exists for that date/kind.
    """
    folder = _data_dir() / "changelog" / date_str
    if not folder.exists():
        return []

    matches = sorted(folder.glob(f"booking_{kind}_*.json"))
    if not matches:
        return []

    with matches[0].open(encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        return data.get(kind, [])
    return data


# Kept as a thin wrapper for backwards compatibility with existing calls
# and tests -- get_changed_property_ids(date) is just get_changelog_ids(date, 'changed').
def get_changed_property_ids(date_str: str) -> list:
    return get_changelog_ids(date_str, "changed")


def list_feed_files(feed: FeedName, date_str: str, bucket: Bucket) -> list[Path]:
    """
    List every JSON file for a given feed/date/bucket, e.g.:
    list_feed_files('accommodation_details', '20260708', 'changed')
    -> [.../booking_details_20260708_changed_0.json, ..._1.json, ...]

    Returns [] if the folder doesn't exist (feed not yet delivered for
    that date, or that bucket is empty).
    """
    folder = _data_dir() / feed / date_str / bucket
    if not folder.exists():
        return []
    return sorted(folder.glob("*.json"))


def read_feed_records(feed: FeedName, date_str: str, bucket: Bucket) -> Iterator[dict]:
    """
    Read every JSON file for a feed/date/bucket and yield each record.

    accommodation_details files wrap a single record in {"rental_property": {...}}.
    search/reviews/reviews_scores files are a flat top-level list of
    many records per file. Handle both shapes without guessing wrong.
    """
    for file_path in list_feed_files(feed, date_str, bucket):
        with file_path.open(encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, list):
            # e.g. search feed: file is a JSON array of records
            yield from data
        else:
            # e.g. accommodation_details: single dict, wrapped in "rental_property"
            yield data.get("rental_property", data)


def build_search_price_map(date_str: str) -> dict:
    """
    Reads every search feed file for a date and builds a lookup:
    property id -> {currency, price, free_cancellation}.
    """
    price_map = {}
    for bucket in ("changed", "opened"):
        for record in read_feed_records("search", date_str, bucket):
            record_id = record.get("id")
            if record_id is None:
                continue

            products = record.get("products") or []
            free_cancellation = any(
                product.get("policies", {}).get("cancellation", {}).get("type") == "free_cancellation" for product in products
            )

            price_map[record_id] = {
                "currency": record.get("currency", {}).get("booker"),
                "price": record.get("price", {}).get("base", {}).get("booker_currency"),
                "free_cancellation": free_cancellation,
            }
    return price_map


def iter_all_accommodation_details(date_str: str) -> Iterator[dict]:
    """
    Convenience: yields every accommodation_details record for a date,
    across both the 'changed' and 'opened' buckets.
    """
    for bucket in ("changed", "opened"):
        yield from read_feed_records("accommodation_details", date_str, bucket)
