"""
Creates a SparkSession wired up to:
  - a local Iceberg catalog (table metadata + data as plain files under
    /app/warehouse -- no S3, no AWS account, no external metastore)
  - Apache Sedona, which provides the actual GEOMETRY type and spatial
    functions (ST_GeomFromEWKT, ST_Contains, etc.) used against Iceberg's
    native v3 geometry column type.

Why Sedona instead of Spark's own built-in GEOMETRY type: Spark's native
geospatial types only exist in a preview release (4.2.0-preview) as of
this writing -- not something to depend on for production. Sedona is a
mature, widely deployed project with its own documented pattern for
writing GEOMETRY columns straight into Iceberg v3 tables, which is what
we use here.
"""
from pyspark.sql import SparkSession
from sedona.spark import SedonaContext

ICEBERG_VERSION = "1.9.1"          # first widely-used release with solid v3/geometry table support
SEDONA_VERSION = "1.6.1"           # documented, stable pairing with Spark 3.5

ICEBERG_PACKAGE = f"org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:{ICEBERG_VERSION}"
SEDONA_PACKAGE = f"org.apache.sedona:sedona-spark-shaded-3.5_2.12:{SEDONA_VERSION}"

WAREHOUSE_PATH = "file:///app/warehouse"


def get_spark(app_name: str = "booking-etl") -> SparkSession:
    config = (
        SparkSession.builder
        .appName(app_name)
        .config("spark.jars.packages", f"{ICEBERG_PACKAGE},{SEDONA_PACKAGE}")
        .config(
            "spark.sql.extensions",
            "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions,"
            "org.apache.sedona.sql.SedonaSqlExtensions",
        )
        .config("spark.sql.catalog.local", "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.local.type", "hadoop")
        .config("spark.sql.catalog.local.warehouse", WAREHOUSE_PATH)
        # Sedona-recommended serializer settings -- without these, spatial
        # joins/functions still work but are noticeably slower and use more memory.
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .config("spark.kryo.registrator", "org.apache.sedona.core.serde.SedonaKryoRegistrator")
        .master("local[*]")
        .getOrCreate()
    )
    #SedonaContext.create() registers Sedona's UDTs/functions on top of
    # the session above; it returns the same session, just Sedona-aware.
    return SedonaContext.create(config)