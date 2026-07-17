## Since warehouse/ needs to exist as a folder but its contents shouldn't be tracked:
```
touch ~/booking-lake/warehouse/.gitkeep
```


# Commands to run and see output
```
cd ~/booking-lake
```
# 1. Build the image (installs Java 17 + PySpark + Sedona inside the container)
```docker compose build

# 2. Start the container in the background
docker compose up -d
```
```
# 3. Get a shell inside it
docker compose exec spark bash


# Now inside the container:
cd /app/src
```
```
# 4. Sanity check Java
java -version
```
```
# 5. Run the smoke test for geometry writes (first run downloads Iceberg + Sedona jars, needs internet)
python -c "
from spark_session import get_spark

spark = get_spark('smoke-test-geometry')
spark.sql('CREATE NAMESPACE IF NOT EXISTS local.smoketest')
spark.sql(\"\"\"
    CREATE TABLE IF NOT EXISTS local.smoketest.geo_check (id STRING, latlon GEOMETRY)
    USING iceberg TBLPROPERTIES ('format-version'='3')
\"\"\")
spark.createDataFrame(
    [('a', 'SRID=4326;POINT (-88.001641 17.882912)')],
    ['id', 'latlon_text'],
).createOrReplaceTempView('staged')
spark.sql(\"\"\"
    MERGE INTO local.smoketest.geo_check t
    USING staged s
    ON t.id = s.id
    WHEN NOT MATCHED THEN INSERT (id, latlon) VALUES (s.id, ST_GeomFromEWKT(s.latlon_text))
\"\"\")
spark.sql('SELECT id, ST_AsText(latlon) FROM local.smoketest.geo_check').show(truncate=False)
spark.sql('DROP TABLE local.smoketest.geo_check')
spark.stop()
"
```
Expect to see a table print showing POINT (-88.001641 17.882912). If that shows up, continue:
# 6. Run the real sync for a date that has data on disk
```
python run_sync.py 20260716
```
Expect output like:
{'date': '20260716', 'created': X, 'updated': Y, 'errors': 0, 'skipped': Z}

# 7. Inspect the resulting table
```
python -c "
from spark_session import get_spark
spark = get_spark()
spark.sql('''
    SELECT external_id, property_name, city, is_published, ST_AsText(latlon) AS latlon
    FROM local.booking.rental_property
    LIMIT 10
''').show(truncate=False)
"
```
# 8. Exit the container shell when done
```
exit
```
# 9. Stop the container (from your host, outside the container)
```
docker compose down
```