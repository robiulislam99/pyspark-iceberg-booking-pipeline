"""
Shared fixtures for all unit tests. Fixtures here are automatically
available to every test file under tests/ -- no import needed.
"""
import pytest


@pytest.fixture
def raw_accommodation_record():
    """
    A minimal but representative raw accommodation_details record,
    matching the real feed shape documented in processor.py.
    """
    return {
        "id": 12908249,
        "name": {"en-us": "Villa Palmilla"},
        "accommodation_type": "220",
        "accommodation_status": "open",
        "min_stay": 1,
        "work_friendly_home": False,
        "long_stay_friendly_home": True,
        "location": {
            "country": "us",
            "city": -784605,
            "address": {"en-us": "Port Aransas, TX, USA"},
            "coordinates": {"latitude": 27.797983, "longitude": -97.085391},
        },
        "rating": {"stars": 3, "review_score": 0, "number_of_reviews": 0},
        "rooms": [{
            "number_of_rooms": {"bedrooms": 4, "bathrooms": 4},
            "maximum_occupancy": {"total_guests": 12},
        }],
        "photos": [
            {"main_photo": True, "url": {"standard": "https://example.com/1.jpg"}},
            {"main_photo": False, "url": {"standard": "https://example.com/2.jpg"}},
        ],
        "facilities": [{"id": 2, "attributes": []}],
        "policies": {"pets": {"allowed": "no"}, "minimum_checkin_age": 18},
        "url": {"web": "https://www.booking.com/hotel/us/villa-palmilla.html"},
        "partner_location_id": "55180",
    }


@pytest.fixture
def search_price_map():
    return {
        12908249: {"currency": "USD", "price": 1301, "free_cancellation": True},
    }


@pytest.fixture
def iceberg_row():
    """
    A minimal but representative row as it comes back from Iceberg via
    row.asDict() -- the shape mappers (es/s3/dynamodb) actually consume.
    """
    import json
    from datetime import datetime

    return {
        "external_id": "BC-12908249",
        "feed": 11,
        "feed_provider_id": "12908249",
        "feed_provider_url": "https://www.booking.com/hotel/us/villa-palmilla.html",
        "property_name": "Villa Palmilla",
        "property_slug": "villa-palmilla",
        "property_type": "Vacation Home",
        "property_type_category": "House",
        "city": "Port Aransas",
        "country": "USA",
        "country_code": "us",
        "location_display": "Port Aransas, TX, USA",
        "partner_location_id": "55180",
        "latlon": "SRID=4326;POINT (-97.085391 27.797983)",
        "star_rating": 3,
        "review_score": 0.0,
        "review_score_general": 0.0,
        "number_of_review": 0,
        "bedroom_count": 4,
        "bathroom_count": 4,
        "occupancy": 12,
        "max_occupancy": 12,
        "currency": "USD",
        "price": 1301.0,
        "min_stay": 1,
        "feature_image": "villa-palmilla-0.jpg",
        "images": ["https://example.com/1.jpg", "https://example.com/2.jpg"],
        "amenities": ["Parking"],
        "amenity_categories": ["General"],
        "policy": json.dumps({
            "pets_allowed": False,
            "pets_policy_text": "Pets are not allowed",
            "adults_only_checkin": True,
            "checkin_age_policy_text": "Only adults are allowed to check in",
            "minimum_checkin_age": 18,
            "free_cancellation": True,
        }),
        "property_flags": json.dumps({
            "work_friendly_home": False,
            "long_stay_friendly_home": True,
        }),
        "is_published": True,
        "last_synced_at": datetime(2026, 5, 29, 4, 18, 51),
        "raw_data": json.dumps({}),
    }