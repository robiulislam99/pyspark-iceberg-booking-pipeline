"""
Cross-partner duplicate property detection: compares our processed
Booking.com properties (Iceberg) against another partner's data (e.g.
Verbo), using 8 fields:
  - latlon: geo distance (structured, hard blocking filter)
  - property_type, bedroom_count, bathroom_count: exact/near match
  - property_name, location_display, property_description, other_policy:
    semantic text similarity via the same sentence-transformers model
    used for Qdrant similarity search (reused, not a new dependency)

Geo distance is used as a BLOCKING filter first (only compare pairs
within a reasonable distance of each other) since comparing every
property against every other property is O(n*m) and unnecessary --
two properties in different cities are never the same listing.
"""

import math
import re

import numpy as np

from clients.embedding_client import generate_embedding

_POINT_RE = re.compile(r"POINT\s*\(\s*([-\d.]+)\s+([-\d.]+)\s*\)")

# Per-field weights -- text fields (name, description) weighted higher
# since they carry the most distinguishing information; structured
# fields act more as confirming/disqualifying signals.
FIELD_WEIGHTS = {
    "property_name": 0.25,
    "location_display": 0.10,
    "property_description": 0.25,
    "other_policy": 0.10,
    "property_type": 0.10,
    "bedroom_count": 0.10,
    "bathroom_count": 0.10,
}

DEFAULT_DISTANCE_THRESHOLD_M = 100  # properties farther apart than this are never compared
DEFAULT_SCORE_THRESHOLD = 0.75  # overall weighted score above this = flagged duplicate


def parse_latlon(latlon_value):
    """
    Handles multiple latlon shapes across partners:
    Returns (lat, lon) as floats, or None if missing/unrecognized.
    """
    if latlon_value is None:
        return None

    if isinstance(latlon_value, str):
        match = _POINT_RE.search(latlon_value)
        if not match:
            return None
        lon, lat = float(match.group(1)), float(match.group(2))
        return lat, lon

    if isinstance(latlon_value, dict):
        if "lat" in latlon_value and "lon" in latlon_value:
            return float(latlon_value["lat"]), float(latlon_value["lon"])
        if "latitude" in latlon_value and "longitude" in latlon_value:
            return float(latlon_value["latitude"]), float(latlon_value["longitude"])
        if "coordinates" in latlon_value:
            coords = latlon_value["coordinates"]
            if len(coords) == 2:
                lon, lat = coords
                return float(lat), float(lon)

    return None


def haversine_distance_meters(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance between two lat/lon points, in meters."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _cosine_similarity(vec_a: list, vec_b: list) -> float:
    a, b = np.array(vec_a), np.array(vec_b)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def text_similarity(text_a: str, text_b: str) -> float:
    """Semantic similarity via embeddings, 0-1. Empty strings on either side score 0."""
    if not text_a or not text_b:
        return 0.0
    return _cosine_similarity(generate_embedding(text_a), generate_embedding(text_b))


def _numeric_match(a, b) -> float:
    """1.0 if equal, 0.0 if either is missing or they differ."""
    if a is None or b is None:
        return 0.0
    return 1.0 if a == b else 0.0


def _categorical_match(a, b) -> float:
    if not a or not b:
        return 0.0
    return 1.0 if str(a).strip().lower() == str(b).strip().lower() else 0.0


def compare_properties(source: dict, candidate: dict) -> dict:
    """
    Compares one property from each partner across all 8 fields.
    Returns per-field scores plus a weighted overall score (0-1).
    """
    scores = {
        "property_name": text_similarity(source.get("property_name"), candidate.get("property_name")),
        "location_display": text_similarity(source.get("location_display"), candidate.get("location_display")),
        "property_description": text_similarity(source.get("property_description"), candidate.get("property_description")),
        "other_policy": text_similarity(source.get("other_policy"), candidate.get("other_policy")),
        "property_type": text_similarity(source.get("property_type"), candidate.get("property_type")),
        "bedroom_count": _numeric_match(source.get("bedroom_count"), candidate.get("bedroom_count")),
        "bathroom_count": _numeric_match(source.get("bathroom_count"), candidate.get("bathroom_count")),
    }

    overall = sum(scores[field] * weight for field, weight in FIELD_WEIGHTS.items())
    scores["overall_score"] = round(overall, 4)
    return scores


def find_duplicates(
    source_rows: list[dict],
    candidate_rows: list[dict],
    distance_threshold_m: float = DEFAULT_DISTANCE_THRESHOLD_M,
    score_threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> list[dict]:
    """
    source_rows: our Iceberg properties (list of dicts with the 8 fields + an id field)
    candidate_rows: the other partner's properties, same field shape

    Returns a list of {source_id, candidate_id, distance_m, scores} for
    every pair whose geo distance is within threshold AND whose overall
    weighted score exceeds score_threshold, sorted best-match first.
    """
    matches = []

    # Pre-parse candidate lat/lons once, not per-source-row, to avoid re-parsing repeatedly
    parsed_candidates = [(c, parse_latlon(c.get("latlon"))) for c in candidate_rows]

    for source in source_rows:
        source_latlon = parse_latlon(source.get("latlon"))
        if source_latlon is None:
            continue

        for candidate, candidate_latlon in parsed_candidates:
            if candidate_latlon is None:
                continue

            distance_m = haversine_distance_meters(*source_latlon, *candidate_latlon)
            if distance_m > distance_threshold_m:
                continue  # too far apart to plausibly be the same property -- skip full comparison

            scores = compare_properties(source, candidate)
            if scores["overall_score"] >= score_threshold:
                matches.append(
                    {
                        "source_id": source.get("external_id") or source.get("id"),
                        "candidate_id": candidate.get("external_id") or candidate.get("id"),
                        "distance_m": round(distance_m, 1),
                        "scores": scores,
                    }
                )

    matches.sort(key=lambda m: m["scores"]["overall_score"], reverse=True)
    return matches
