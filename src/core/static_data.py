"""
Loads the static reference/lookup JSON files (`custom_static/`, `static/`)
into memory, once per process.

These files rarely change (they're not inside a dated folder), so there's
no reason to re-read them from disk on every property we process. We load
each one lazily on first use and cache it in memory for the rest of the run.

Ported from the Django version -- only change is the data dir source
(env var instead of django.conf.settings). No Spark/DB access here.
"""

import json
import os
from functools import cache, lru_cache
from pathlib import Path


def _data_dir() -> Path:
    return Path(os.environ["BOOKING_DATA_DIR"])


def _load_json(relative_path: str) -> dict:
    """Read one JSON file relative to BOOKING_DATA_DIR. Returns {} if missing."""
    file_path = _data_dir() / relative_path
    if not file_path.exists():
        return {}
    with file_path.open(encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=1)
def get_hotel_types() -> dict:
    """accommodation_type integer ID -> name, e.g. {'220': 'Holiday homes'}."""
    return _load_json("custom_static/hotel_types.json")


@lru_cache(maxsize=1)
def get_property_type_categories() -> dict:
    """sub-type -> parent group, e.g. {'Aparthotels': 'Apartment'}."""
    return _load_json("static/property_type_categories.json")


@lru_cache(maxsize=1)
def get_amenity_map() -> dict:
    """raw amenity phrase -> master category, e.g. {'elevator': 'Accessibility'}."""
    return _load_json("static/amenity_map.json")


@lru_cache(maxsize=1)
def get_chain_and_brand() -> dict:
    """brand ID -> chain name, e.g. {'marriott_id': 'Marriott'}."""
    return _load_json("static/chain_and_brand.json")


@lru_cache(maxsize=1)
def get_constants() -> dict:
    """Multi-lingual translations for UI constants/facility names."""
    return _load_json("static/constants.json")


@cache
def get_location_mapping(country_code: str, location_type: str) -> dict:
    """
    Resolve negative location IDs to names for one country.

    location_type is one of: 'city', 'district', 'landmark', 'region'.
    Example: get_location_mapping('bz', 'city') -> {'-1397214': 'Xixerella'}
    """
    country_code = country_code.lower()
    return _load_json(f"static/location_mapping/{country_code}/{location_type}.json")


@lru_cache(maxsize=1)
def get_meal_translations() -> dict:
    """Multi-lingual translations for meal plan names (e.g. breakfast, half-board)."""
    return _load_json("custom_static/meal_translations.json")


@lru_cache(maxsize=1)
def get_accommodation_type_name_map() -> dict:
    """
    Normalized: accommodation_type code -> en-us display name.
    Built from constants.json's {wrapper_key: {code: {name: {lang: ...}}}} shape.
    e.g. {'220': 'Vacation Home'}
    """
    raw = get_constants()
    accommodation_types = raw.get("accommodation_types", {})
    return {
        code: entry.get("name", {}).get("en-us", "") for code, entry in accommodation_types.items() if entry.get("name", {}).get("en-us")
    }


@lru_cache(maxsize=1)
def get_property_type_category_map() -> dict:
    """
    Normalized: property_type_name -> group_name.
    Unwraps property_type_categories.json's
    {'property_type_mapping': {'mapped': [rows]}} shape.
    e.g. {'Aparthotels': 'Apartment', 'Vacation Home': 'House'}
    """
    raw = get_property_type_categories()
    mapped = raw.get("property_type_mapping", {}).get("mapped", [])

    return {
        row["property_type_name"]: row.get("group_name", "") for row in mapped if isinstance(row, dict) and row.get("property_type_name")
    }


@lru_cache(maxsize=1)
def get_country_name_map() -> dict:
    """
    Normalized: country_code (lowercase) -> country name.
    File lives at static/location_mapping/countries.json,
    alongside the per-country city/district/landmark/region subfolders.
    e.g. {'ad': 'Andorra', 'ae': 'United Arab Emirates'}
    """
    raw = _load_json("static/location_mapping/countries.json")
    return {code.lower(): name for code, name in raw.items()}


def resolve_country_name(country_code: str) -> str:
    """country_code (any case) -> readable country name, or '' if unknown."""
    if not country_code:
        return ""
    return get_country_name_map().get(country_code.lower(), "")


@cache
def get_city_name_map(country_code: str) -> dict:
    """
    Normalized: city_code -> city name, for one country.
    Built from static/location_mapping/<country_code>/city.json.
    e.g. get_city_name_map('ae') -> {'-784605': 'Wāsiţ'}
    """
    rows = get_location_mapping(country_code, "city")
    return {str(row["city_code"]): row.get("city", "") for row in rows if row.get("city_code") is not None}


def resolve_city_name(country_code: str, city_code) -> str:
    """(country_code, city_code) -> readable city name, or '' if unknown."""
    if not country_code or city_code is None:
        return ""
    return get_city_name_map(country_code).get(str(city_code), "")


@lru_cache(maxsize=1)
def get_accommodation_facility_map() -> dict:
    """
    Normalized: facility id (str) -> {'name': en-us name, 'facility_type': type id}.
    Built from constants.json's accommodation_facilities section.
    e.g. {'2': {'name': 'Parking', 'facility_type': 16}}
    """
    raw = get_constants()
    facilities = raw.get("accommodation_facilities", {})
    return {
        facility_id: {
            "name": entry.get("name", {}).get("en-us", ""),
            "facility_type": entry.get("facility_type"),
        }
        for facility_id, entry in facilities.items()
    }


@lru_cache(maxsize=1)
def get_facility_type_name_map() -> dict:
    """
    Normalized: facility_type id (str) -> en-us category name.
    Built from constants.json's facility_types section.
    e.g. {'16': 'General', '2': 'Activities'}
    """
    raw = get_constants()
    facility_types = raw.get("facility_types", {})
    return {type_id: entry.get("name", {}).get("en-us", "") for type_id, entry in facility_types.items()}


def clear_cache():
    """
    Call this if the static files are updated and the app is still running
    (e.g. in a long-lived scheduler process) and you need fresh data
    without restarting.
    """
    get_hotel_types.cache_clear()
    get_property_type_categories.cache_clear()
    get_amenity_map.cache_clear()
    get_chain_and_brand.cache_clear()
    get_constants.cache_clear()
    get_location_mapping.cache_clear()
    get_meal_translations.cache_clear()
    get_accommodation_type_name_map.cache_clear()
    get_property_type_category_map.cache_clear()
    get_country_name_map.cache_clear()
    get_city_name_map.cache_clear()
    get_accommodation_facility_map.cache_clear()
    get_facility_type_name_map.cache_clear()
