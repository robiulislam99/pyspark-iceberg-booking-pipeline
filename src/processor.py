"""
The single processing function:

    "one function that goes through all the fields, processes them,
    and returns everything at once at the end."

`process_rental_property(raw, search_price_map)`:
  - Input:  one raw `rental_property` dict (already loaded from disk by
            file_locator.py), plus the search-feed price map
  - Output: one plain dict, fully cleaned/typed, with keys matching
            the Iceberg table's column names -- ready to hand to
            spark.createDataFrame() for the MERGE INTO.
  - Pure function: no database/Spark access, no I/O, no side effects.
    Same input always produces the same output, so it's trivial to unit-test.

Ported from the Django version. Changes forced by dropping Django:
  - django.utils.text.slugify -> python-slugify's slugify (same behavior)
  - django.contrib.gis.geos.Point -> resolve_latlon now returns an EWKT
    string, e.g. 'SRID=4326;POINT (lon lat)', matching sync_iceberg.py's
    ST_GeomFromEWKT() call that turns it into a real Iceberg GEOMETRY value.
Also dropped the unused `from curses import raw` import (it did nothing --
immediately shadowed by the `raw` parameter -- and isn't available outside
Linux, so no reason to keep it here).
"""

from datetime import datetime

from slugify import slugify

from static_data import (
    resolve_country_name,
    resolve_city_name,
    get_accommodation_type_name_map,
    get_property_type_category_map,
    get_accommodation_facility_map,
    get_facility_type_name_map,
)


def resolve_property_type(accommodation_type_code) -> tuple[str, str]:
    """
    220 -> get_accommodation_type_name_map()['220'] -> 'Vacation Home'
        -> get_property_type_category_map()['Vacation Home'] -> 'House'
    """
    if accommodation_type_code is None:
        return "", ""

    en_us_name = get_accommodation_type_name_map().get(str(accommodation_type_code), "")
    if not en_us_name:
        return "", ""

    group_name = get_property_type_category_map().get(en_us_name, "")
    return en_us_name, group_name


def resolve_latlon(raw_latitude, raw_longitude):
    """
    raw lat/lon (float or str) -> EWKT string, e.g.
    'SRID=4326;POINT (-88.001641 17.882912)', or None if missing/invalid.

    POINT order is (longitude, latitude) -- matches PostGIS/GEOS convention.
    sync_iceberg.py converts this text into a real Iceberg GEOMETRY value
    via ST_GeomFromEWKT() at merge time.
    """
    if raw_latitude is None or raw_longitude is None:
        return None
    try:
        lat = float(raw_latitude)
        lon = float(raw_longitude)
    except (TypeError, ValueError):
        return None
    return f"SRID=4326;POINT ({lon} {lat})"


def resolve_images(photos: list) -> tuple[str, list]:
    """
    photos (raw list of {main_photo, url: {standard, thumbnail}}) ->
    (feature_image, images)

    feature_image = 'standard' url of the photo with main_photo=True
                    (falls back to first photo's standard url if none marked main)
    images = list of all 'standard' urls
    """
    if not photos:
        return "", []

    images = [p.get("url", {}).get("standard", "") for p in photos if p.get("url", {}).get("standard")]

    feature_image = ""
    for photo in photos:
        if photo.get("main_photo"):
            feature_image = photo.get("url", {}).get("standard", "")
            break

    if not feature_image and images:
        feature_image = images[0]  # fallback: no photo marked main_photo

    return feature_image, images


def _parse_datetime(value: str | None):
    """Source timestamps are ISO 8601 with a UTC offset, e.g. '2026-07-08T00:01:02.265305-07:00'."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def _to_decimal_safe(value, default=None):
    """Source sometimes sends numbers as strings (e.g. review_score_general: '0.00')."""
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def get_first_room(raw: dict) -> dict:
    """Return the first room dict from raw['rooms'], or {} if none exist."""
    rooms = raw.get("rooms") or []
    return rooms[0] if rooms else {}


def resolve_amenities(facilities: list) -> tuple[list, list]:
    """
    facilities (raw list of {id, attributes}) -> (amenities, amenity_categories)

    amenities            = list of en-us facility names, e.g. ['Parking', 'Restaurant']
    amenity_categories   = list of unique en-us facility-type/category names, e.g. ['General', 'Activities']
    """
    if not facilities:
        return [], []

    facility_map = get_accommodation_facility_map()
    type_name_map = get_facility_type_name_map()

    amenities = []
    amenity_categories = []

    for facility in facilities:
        facility_id = str(facility.get("id"))
        info = facility_map.get(facility_id)
        if not info:
            continue

        name = info.get("name")
        if name:
            amenities.append(name)

        facility_type = info.get("facility_type")
        category_name = type_name_map.get(str(facility_type)) if facility_type is not None else None
        if category_name and category_name not in amenity_categories:
            amenity_categories.append(category_name)

    return amenities, amenity_categories


def resolve_pets_policy(policies: dict) -> str:
    """policies['pets']['allowed'] ('yes'/'no') -> human-readable text."""
    allowed = policies.get("pets", {}).get("allowed")
    if allowed == "no":
        return "Pets are not allowed"
    if allowed == "yes":
        return "Pets are allowed"
    return "Pet policy not specified"


def resolve_checkin_age_policy(policies: dict) -> str:
    """policies['minimum_checkin_age'] -> human-readable text."""
    min_age = policies.get("minimum_checkin_age")
    if min_age is not None and min_age >= 18:
        return "Only adults are allowed to check in"
    return "Anyone can check in"


def resolve_policy(raw: dict, search_info: dict) -> dict:
    """
    Combines pets + checkin-age (from accommodation_details raw)
    and free_cancellation (from search feed, via search_info)
    into a single dict for the policy field.
    """
    policies = raw.get("policies") or {}
    pets_allowed = policies.get("pets", {}).get("allowed")
    min_checkin_age = policies.get("minimum_checkin_age")

    return {
        "pets_allowed": pets_allowed == "yes",
        "pets_policy_text": resolve_pets_policy(policies),
        "adults_only_checkin": min_checkin_age is not None and min_checkin_age >= 18,
        "checkin_age_policy_text": resolve_checkin_age_policy(policies),
        "minimum_checkin_age": min_checkin_age,
        "free_cancellation": search_info.get("free_cancellation", False),
    }

def resolve_eco_friendly(raw: dict) -> bool:
    """
    True if 'eco friendly' or 'eco-friendly' text found in
    description.important_information['en-us']
    """
    description = raw.get("description", {}) or {}
    important_info = description.get("important_information", {}) or {}
    text = (important_info.get("en-us") or "").lower()

    return "eco friendly" in text or "eco-friendly" in text


def resolve_property_flags(raw: dict) -> dict:
    policies = raw.get("policies") or {}
    min_checkin_age = policies.get("minimum_checkin_age")

    return {
        "work_friendly_home": bool(raw.get("work_friendly_home", False)),
        "long_stay_friendly_home": bool(raw.get("long_stay_friendly_home", False)),
        "eco_friendly_home": resolve_eco_friendly(raw),
        "adult_only": min_checkin_age is not None and min_checkin_age >= 18,
    }

def resolve_family_group_flags(raw: dict) -> tuple[bool, bool]:
    """
    family_friendly = True if children value is not null
    group_friendly  = True if total_guests >= 6
    """
    first_room = get_first_room(raw)
    max_occ = first_room.get("maximum_occupancy", {})

    children = max_occ.get("children")
    total_guests = max_occ.get("total_guests") or 0

    family_friendly = children is not None
    group_friendly = total_guests >= 6

    return family_friendly, group_friendly

def resolve_other_policy(raw: dict) -> str:
    """description.important_information['en-us'] -> other_policy text"""
    description = raw.get("description", {}) or {}
    important_info = description.get("important_information", {}) or {}
    return (important_info.get("en-us") or "").strip()



def process_rental_property(raw: dict, search_price_map: dict) -> dict:
    """Transform one raw rental_property dict into a clean dict for the Iceberg table."""

    location = raw.get("location", {})
    property_type, property_type_category = resolve_property_type(raw.get("accommodation_type"))
    country_code = location.get("country") or ""
    coordinates = location.get("coordinates", {})
    city_code = location.get("city")
    rating = raw.get("rating", {})
    review_score = rating.get("review_score")
    first_room = get_first_room(raw)
    number_of_rooms = first_room.get("number_of_rooms", {})
    maximum_occupancy = first_room.get("maximum_occupancy", {})

    property_id = raw.get("id")
    search_info = search_price_map.get(property_id, {})

    photos = raw.get("photos") or []
    feature_image, images = resolve_images(photos)

    facilities = raw.get("facilities") or []
    amenities, amenity_categories = resolve_amenities(facilities)

    property_name = (raw.get("name", {}).get("en-us") or "").strip()

    latlon = resolve_latlon(coordinates.get("latitude"), coordinates.get("longitude"))

    family_friendly, group_friendly = resolve_family_group_flags(raw)

    result = {
        # --- Identity --------------------------------------------------
        "external_id": f"BC-{str(raw.get('id') or '').strip()}",
        "feed": 11,
        "feed_provider_id": (str(raw.get("id") or "").strip()),
        "feed_provider_url": (raw.get("url", {}).get("web") or "").strip(),

        # --- Basic info -----------------------------------------------------
        "property_name": property_name,
        "property_slug": slugify(property_name),
        "property_type": property_type,
        "property_type_category": property_type_category,

        # --- Location -----------------------------------------------------
        "city": resolve_city_name(country_code, city_code),
        "country": resolve_country_name(country_code),
        "country_code": country_code,
        "location_display": (location.get("address", {}).get("en-us") or "").strip(),
        "partner_location_id": raw.get("partner_location_id") or "",
        "latlon": latlon,

        # ---Language -----------------------------------------------------
        "language": "en-us",

        # --- Ratings & size -----------------------------------------------
        "star_rating": rating.get("stars"),
        "review_score": review_score,
        "review_score_general": _to_decimal_safe(review_score / 2) if review_score is not None else None,
        "number_of_review": rating.get("number_of_reviews") or 0,
        "bedroom_count": number_of_rooms.get("bedrooms"),
        "bathroom_count": number_of_rooms.get("bathrooms"),
        "occupancy": maximum_occupancy.get("total_guests"),
        "max_occupancy": maximum_occupancy.get("total_guests"),

        # --- Pricing & stay rules -----------------------------------------------
        "currency": search_info.get("currency") or "USD",
        "price": _to_decimal_safe(search_info.get("price")),
        "min_stay": raw.get("min_stay") or 1,

        # --- Media -----------------------------------------------------
        "feature_image": feature_image,
        "images": images,

        # --- Family/group flags -----------------------------------------------
        "family_friendly": family_friendly,
        "group_friendly": group_friendly,

        # --- Nested source data, stored as-is -----------------------------------------------
        "amenities": amenities,
        "amenity_categories": amenity_categories,
        "policy": resolve_policy(raw, search_info),
        "property_flags": resolve_property_flags(raw),

        "other_policy": resolve_other_policy(raw),

        # --- Status -----------------------------------------------------
        "is_published": raw.get("accommodation_status") == "open",

        # --- Safety net: keep the full original record -----------------------------------------------
        "raw_data": raw,
    }

    return result