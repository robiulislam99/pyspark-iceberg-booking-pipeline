"""
Ports the Django sync.py's upsert logic to an Iceberg MERGE INTO.

Key correspondence to the Django version:
- changed + opened changelog IDs are unioned, everything else is skipped
- "don't overwrite an existing non-empty value with a new empty one" is
  expressed inside the MERGE INTO's WHEN MATCHED clause: COALESCE/NULLIF
  for scalars, a size() check for array columns.
- upsert key is feed_provider_id, matching the Django model's documented
  upsert key.
- price / review_score / review_score_general use DECIMAL, matching the
  model's DecimalField precision exactly.
- integer fields are coerced via _to_int_or_none because the source
  sometimes sends whole numbers as floats (e.g. stars: 3.0), which
  Spark's strict IntegerType rejects outright.
- created_at / source_created_at set only on first insert.
  last_synced_at / source_updated_at refresh every sync run.
- latlon is stored as plain EWKT text (e.g. 'SRID=4326;POINT (lon lat)').
  Spark 3.5's SQL parser has no native GEOMETRY column type, and the only
  extension that adds one to Iceberg DDL (sedona-iceberg-extension) is an
  unmaintained third-party module last built for Spark 3.2 -- not safe
  for production. So: store as text, parse with Sedona's ST_GeomFromEWKT()
  at QUERY time instead of write time. Full spatial querying power, just
  no native geometry column type in storage.
- processed_rows is de-duplicated by feed_provider_id before the merge,
  since a duplicate key in the source would make Iceberg's MERGE INTO
  fail with "matched multiple source rows".
"""
import json
import logging
from decimal import Decimal

from pyspark.sql.types import (
    StructType, StructField, StringType, IntegerType,
    BooleanType, ArrayType, DecimalType,
)

from spark_session import get_spark
from file_locator import (
    iter_all_accommodation_details,
    build_search_price_map,
    get_changelog_ids,
)
from processor import process_rental_property

logger = logging.getLogger("booking_lake.sync")
logging.basicConfig(level=logging.INFO)

TABLE = "local.booking.rental_property"

RENTAL_PROPERTY_SCHEMA = StructType([
    StructField("external_id", StringType()),
    StructField("feed", IntegerType()),
    StructField("feed_provider_id", StringType()),
    StructField("feed_provider_url", StringType()),

    StructField("property_name", StringType()),
    StructField("property_slug", StringType()),
    StructField("property_type", StringType()),
    StructField("property_type_category", StringType()),
    
    StructField("city", StringType()),
    StructField("country", StringType()),
    StructField("country_code", StringType()),
    StructField("location_display", StringType()),
    StructField("partner_location_id", StringType()),
    StructField("latlon", StringType()),   # EWKT text, e.g. 'SRID=4326;POINT (lon lat)'

    StructField("language", StringType()),

    StructField("star_rating", IntegerType()),
    StructField("review_score", DecimalType(4, 2)),
    StructField("review_score_general", DecimalType(4, 2)),
    StructField("number_of_review", IntegerType()),
    StructField("bedroom_count", IntegerType()),
    StructField("bathroom_count", IntegerType()),
    StructField("occupancy", IntegerType()),
    StructField("max_occupancy", IntegerType()),

    StructField("currency", StringType()),
    StructField("price", DecimalType(10, 2)),
    StructField("min_stay", IntegerType()),

    StructField("feature_image", StringType()),
    StructField("images", ArrayType(StringType())),

    StructField("family_friendly", BooleanType()),
    StructField("group_friendly", BooleanType()),

    StructField("amenities", ArrayType(StringType())),
    StructField("amenity_categories", ArrayType(StringType())),
    StructField("policy", StringType()),           # JSON text
    StructField("property_flags", StringType()),   # JSON text

    StructField("other_policy", StringType()),

    StructField("feature_summary", StringType()),  # JSON text

    StructField("is_published", BooleanType()),
    StructField("raw_data", StringType()),          # JSON text
])


def ensure_table_exists(spark):
    spark.sql("CREATE NAMESPACE IF NOT EXISTS local.booking")
    spark.sql(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            external_id STRING,
            feed INT,
            feed_provider_id STRING,
            feed_provider_url STRING,

            property_name STRING,
            property_slug STRING,
            property_type STRING,
            property_type_category STRING,

            city STRING,
            country STRING,
            country_code STRING,
            location_display STRING,
            partner_location_id STRING,
            latlon STRING,

            language STRING,

            star_rating INT,
            review_score DECIMAL(4,2),
            review_score_general DECIMAL(4,2),
            number_of_review INT,
            bedroom_count INT,
            bathroom_count INT,
            occupancy INT,
            max_occupancy INT,

            currency STRING,
            price DECIMAL(10,2),
            min_stay INT,

            feature_image STRING,
            images ARRAY<STRING>,

            family_friendly BOOLEAN,
            group_friendly BOOLEAN,

            amenities ARRAY<STRING>,
            amenity_categories ARRAY<STRING>,
            policy STRING,
            property_flags STRING,

            other_policy STRING,

            feature_summary STRING,

            is_published BOOLEAN,

            source_created_at TIMESTAMP,
            source_updated_at TIMESTAMP,
            raw_data STRING,
            last_synced_at TIMESTAMP,
            created_at TIMESTAMP
        ) USING iceberg
    """)
    _sync_schema(spark)

def _sync_schema(spark):
    """
    Auto-migrate: add any column present in RENTAL_PROPERTY_SCHEMA but
    missing from the live Iceberg table. Runs on every sync, every date --
    no manual ALTER TABLE ever needed again.
    """
    existing_columns = {f.name for f in spark.table(TABLE).schema.fields}
    for field in RENTAL_PROPERTY_SCHEMA.fields:
        if field.name not in existing_columns:
            ddl_type = field.dataType.simpleString().upper()  # e.g. 'STRING', 'ARRAY<STRING>'
            logger.info(f"Adding missing column '{field.name}' ({ddl_type}) to {TABLE}")
            spark.sql(f"ALTER TABLE {TABLE} ADD COLUMN {field.name} {ddl_type}")


def _to_decimal_or_none(value):
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _to_int_or_none(value):
    """
    Source sometimes sends whole numbers as floats (e.g. stars: 3.0)
    or numeric strings. Spark's IntegerType is strict and rejects a
    Python float outright, even one with no fractional part -- so
    coerce explicitly rather than let PySpark's schema check reject it.
    """
    if value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def sync_accommodation_details(date_str: str) -> dict:
    """
    date_str: e.g. "20260716". BOOKING_DATA_DIR must already be set as an
    env var (docker-compose.yml sets this) -- file_locator/static_data
    read it internally.
    """
    spark = get_spark(f"sync-{date_str}")
    ensure_table_exists(spark)

    changed_ids = set(get_changelog_ids(date_str, "changed"))
    opened_ids = set(get_changelog_ids(date_str, "opened"))
    relevant_ids = changed_ids | opened_ids

    summary = {"date": date_str, "created": 0, "updated": 0, "errors": 0, "skipped": 0}

    if not relevant_ids:
        logger.info(f"No changelog IDs for {date_str}, nothing to do.")
        spark.stop()
        return summary

    logger.info(f"Starting sync for date={date_str}, relevant_ids={len(relevant_ids)}")

    search_price_map = build_search_price_map(date_str)

    processed_rows = []
    for raw in iter_all_accommodation_details(date_str):
        feed_id = raw.get("id")
        if feed_id not in relevant_ids:
            summary["skipped"] += 1
            continue
        try:
            row = process_rental_property(raw, search_price_map)
            row["review_score"] = _to_decimal_or_none(row["review_score"])
            row["review_score_general"] = _to_decimal_or_none(row["review_score_general"])
            row["price"] = _to_decimal_or_none(row["price"])

            row["feed"] = _to_int_or_none(row["feed"])
            row["star_rating"] = _to_int_or_none(row["star_rating"])
            row["number_of_review"] = _to_int_or_none(row["number_of_review"])
            row["bedroom_count"] = _to_int_or_none(row["bedroom_count"])
            row["bathroom_count"] = _to_int_or_none(row["bathroom_count"])
            row["occupancy"] = _to_int_or_none(row["occupancy"])
            row["max_occupancy"] = _to_int_or_none(row["max_occupancy"])
            row["min_stay"] = _to_int_or_none(row["min_stay"])

            row["policy"] = json.dumps(row["policy"])
            row["property_flags"] = json.dumps(row["property_flags"])
            row["feature_summary"] = json.dumps(row["feature_summary"])
            row["raw_data"] = json.dumps(row["raw_data"])
            processed_rows.append(row)
        except Exception as e:
            logger.exception(f"Failed to process feed_id={feed_id}: {e}")
            summary["errors"] += 1

    if not processed_rows:
        logger.info(f"Finished sync for date={date_str}: {summary}")
        spark.stop()
        return summary

    # De-duplicate by feed_provider_id -- avoids Iceberg's MERGE INTO
    # failing with "matched multiple source rows" if a property appears
    # in both the 'changed' and 'opened' buckets on the same day.
    # Keeps the LAST occurrence seen (opened overrides changed here).
    deduped = {}
    for row in processed_rows:
        deduped[row["feed_provider_id"]] = row
    if len(deduped) != len(processed_rows):
        logger.warning(
            f"Deduped {len(processed_rows) - len(deduped)} duplicate "
            f"feed_provider_id row(s) before merge for date={date_str}"
        )
    processed_rows = list(deduped.values())

    staged_df = spark.createDataFrame(processed_rows, schema=RENTAL_PROPERTY_SCHEMA)
    staged_df.createOrReplaceTempView("staged_updates")

    before_count = spark.sql(f"SELECT COUNT(*) c FROM {TABLE}").collect()[0]["c"]

    merge_sql = f"""
        MERGE INTO {TABLE} t
        USING staged_updates s
        ON t.feed_provider_id = s.feed_provider_id
        WHEN MATCHED THEN UPDATE SET
            t.external_id = COALESCE(NULLIF(s.external_id, ''), t.external_id),
            t.feed = COALESCE(s.feed, t.feed),
            t.feed_provider_url = COALESCE(NULLIF(s.feed_provider_url, ''), t.feed_provider_url),

            t.property_name = COALESCE(NULLIF(s.property_name, ''), t.property_name),
            t.property_slug = COALESCE(NULLIF(s.property_slug, ''), t.property_slug),
            t.property_type = COALESCE(NULLIF(s.property_type, ''), t.property_type),
            t.property_type_category = COALESCE(NULLIF(s.property_type_category, ''), t.property_type_category),

            t.city = COALESCE(NULLIF(s.city, ''), t.city),
            t.country = COALESCE(NULLIF(s.country, ''), t.country),
            t.country_code = COALESCE(NULLIF(s.country_code, ''), t.country_code),
            t.location_display = COALESCE(NULLIF(s.location_display, ''), t.location_display),
            t.partner_location_id = COALESCE(NULLIF(s.partner_location_id, ''), t.partner_location_id),
            t.latlon = COALESCE(NULLIF(s.latlon, ''), t.latlon),

            t.language = COALESCE(NULLIF(s.language, ''), t.language),

            t.star_rating = COALESCE(s.star_rating, t.star_rating),
            t.review_score = COALESCE(s.review_score, t.review_score),
            t.review_score_general = COALESCE(s.review_score_general, t.review_score_general),
            t.number_of_review = COALESCE(s.number_of_review, t.number_of_review, 0),
            t.bedroom_count = COALESCE(s.bedroom_count, t.bedroom_count),
            t.bathroom_count = COALESCE(s.bathroom_count, t.bathroom_count),
            t.occupancy = COALESCE(s.occupancy, t.occupancy),
            t.max_occupancy = COALESCE(s.max_occupancy, t.max_occupancy),

            t.currency = COALESCE(NULLIF(s.currency, ''), t.currency, 'USD'),
            t.price = COALESCE(s.price, t.price),
            t.min_stay = COALESCE(s.min_stay, t.min_stay, 1),

            t.feature_image = COALESCE(NULLIF(s.feature_image, ''), t.feature_image),
            t.images = CASE WHEN size(s.images) = 0 THEN t.images ELSE s.images END,

            t.family_friendly = COALESCE(s.family_friendly, t.family_friendly),
            t.group_friendly = COALESCE(s.group_friendly, t.group_friendly),

            t.amenities = CASE WHEN size(s.amenities) = 0 THEN t.amenities ELSE s.amenities END,
            t.amenity_categories = CASE WHEN size(s.amenity_categories) = 0 THEN t.amenity_categories ELSE s.amenity_categories END,
            t.policy = COALESCE(NULLIF(s.policy, '{{}}'), t.policy),
            t.property_flags = COALESCE(NULLIF(s.property_flags, '{{}}'), t.property_flags),

            t.other_policy = COALESCE(NULLIF(s.other_policy, ''), t.other_policy),
            
            t.feature_summary = COALESCE(NULLIF(s.feature_summary, '[]'), t.feature_summary),

            t.is_published = COALESCE(s.is_published, t.is_published),

            t.source_updated_at = current_timestamp(),
            t.last_synced_at = current_timestamp()
        WHEN NOT MATCHED THEN INSERT (
            external_id, feed, feed_provider_id, feed_provider_url,
            property_name, property_slug, property_type, property_type_category,
            city, country, country_code, location_display, partner_location_id,
            latlon, language,
            star_rating, review_score, review_score_general, number_of_review,
            bedroom_count, bathroom_count, occupancy, max_occupancy,
            currency, price, min_stay,
            feature_image, images, family_friendly, group_friendly, amenities, amenity_categories, policy, property_flags,
            other_policy,feature_summary, is_published,
            source_created_at, source_updated_at, raw_data, last_synced_at, created_at
        ) VALUES (
            s.external_id, s.feed, s.feed_provider_id, s.feed_provider_url,
            s.property_name, s.property_slug, s.property_type, s.property_type_category,
            s.city, s.country, s.country_code, s.location_display, s.partner_location_id,
            s.latlon, s.language,
            s.star_rating, s.review_score, s.review_score_general, COALESCE(s.number_of_review, 0),
            s.bedroom_count, s.bathroom_count, s.occupancy, s.max_occupancy,
            COALESCE(s.currency, 'USD'), s.price, COALESCE(s.min_stay, 1),
            s.feature_image, s.images, s.family_friendly, s.group_friendly, s.amenities, s.amenity_categories, s.policy, s.property_flags,
            s.other_policy, s.feature_summary,
            COALESCE(s.is_published, true),
            current_timestamp(), current_timestamp(), s.raw_data, current_timestamp(), current_timestamp()
        )
    """
    spark.sql(merge_sql)

    after_count = spark.sql(f"SELECT COUNT(*) c FROM {TABLE}").collect()[0]["c"]
    summary["created"] = after_count - before_count
    summary["updated"] = len(processed_rows) - summary["created"]

    summary["feed_provider_ids"] = [row["feed_provider_id"] for row in processed_rows]

    logger.info(f"Finished sync for date={date_str}: {summary}")
    spark.stop()
    return summary