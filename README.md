# Booking Lake — PySpark + Iceberg + Sedona + SQS + Elasticsearch/Kibana Pipeline

Local ETL pipeline: reads Booking.com JSON feed files, transforms them,
upserts into a local Iceberg table via Spark, publishes change events to
SQS (emulated locally via LocalStack), and a consumer indexes the changed
records into Elasticsearch for querying and Kibana dashboards.
No AWS account, no cloud services, no sudo required — everything runs
inside Docker.

## Prerequisites

- Docker + Docker Compose installed on the host
- Your `booking/` data folder placed at `./booking` (sibling of `src/`)

## First-time setup

```bash
mkdir -p warehouse scheduler_data notebooks ivy_cache localstack_data es_data
touch warehouse/.gitkeep

docker compose build
docker compose up -d
```

Services and ports once running:

| Service | URL | Purpose |
|---|---|---|
| Spark container | — | runs all `src/*.py` scripts |
| Spark UI | http://localhost:4040 | while a job is running |
| Jupyter | http://localhost:8888 | interactive exploration |
| LocalStack (SQS) | http://localhost:4566 | emulated SQS queue |
| Elasticsearch | http://localhost:9200 | indexed, queryable data |
| Kibana | http://localhost:5601 | dashboards |

## Run a manual sync

```bash
docker compose exec spark python /app/src/run_sync.py 20260714
```

(replace `20260714` with the date folder you want to process)

This upserts into Iceberg **and** publishes an SQS event listing the
changed `feed_provider_id`s, for the consumer to pick up.

## Run the SQS → Elasticsearch consumer

Keep this running in its own terminal — it polls SQS continuously and
indexes changed records into Elasticsearch as sync events arrive:

```bash
docker compose exec spark python /app/src/sqs_consumer.py
```

## Verify Elasticsearch has data

```bash
curl http://localhost:9200/rental_properties/_count
curl http://localhost:9200/rental_properties/_mapping/field/lonlat
```

## Inspect the Iceberg data directly

```bash
docker compose exec spark python -c "
from spark_session import get_spark
spark = get_spark()
spark.sql('SELECT COUNT(*) FROM local.booking.rental_property').show()
spark.sql('''
    SELECT external_id, property_name, city, country, is_published, latlon
    FROM local.booking.rental_property
    LIMIT 10
''').show(truncate=False)
"
```

## Explore interactively with Jupyter

```bash
docker compose exec spark jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root
```

Copy the printed `http://127.0.0.1:8888/lab?token=...` URL, open
`notebooks/explore_data.ipynb` in VS Code, select it as an
**Existing Jupyter Server** kernel, then run cells.

## Kibana dashboard

1. Open http://localhost:5601
2. Stack Management → Data Views → create one named `rental_properties`,
   index pattern `rental_properties*`
3. Confirm `lonlat` shows type `geo_point` in the field list (if not,
   see Troubleshooting below)
4. Maps app → Create map → Add layer → Documents → data view
   `rental_properties` → geospatial field `lonlat`
5. Dashboard → Create dashboard → Add from library (the saved map) +
   Create visualization (Lens) for bar charts / metrics / tables
6. **Time range matters** — Kibana filters by the data view's time
   field (`created_at`) by default. If panels show no data, widen the
   time range (e.g. "Last 5 years") rather than assuming the data is
   missing.

## Scheduler (manual trigger for now — cron not yet wired up)

```bash
# add a schedule
docker compose exec spark python /app/src/manage_schedule.py add --frequency daily --run-time 03:00

# list schedules
docker compose exec spark python /app/src/manage_schedule.py list

# manually simulate a scheduler tick
docker compose exec spark python /app/src/run_due_schedules.py

# view run history
docker compose exec spark python /app/src/manage_schedule.py jobs
```

## Compare what changed between two syncs

```bash
docker compose exec spark python -c "
from spark_session import get_spark
from snapshot_diff import diff_snapshots

spark = get_spark()
snaps = spark.sql('SELECT snapshot_id FROM local.booking.rental_property.snapshots ORDER BY committed_at').collect()
diff_snapshots(spark, snaps[-2]['snapshot_id'], snaps[-1]['snapshot_id'])
"
```

## Shell into the container (for debugging)

```bash
docker compose exec spark bash
```

## Troubleshooting

**Sedona jar download corrupted / `ClassNotFoundException: SedonaSqlExtensions`**
The Ivy jar cache had a partial/corrupted download. Clear it and retry:
```bash
docker compose exec spark rm -rf /root/.ivy2
docker compose exec spark python /app/src/run_sync.py 20260714
```
The `ivy_cache/` volume mount persists successful downloads across
container restarts so this should only need doing once.

**Elasticsearch field `lonlat` shows as `float` instead of `geo_point`**
ES only infers `geo_point` automatically for specific shapes — this
happens if the index was created before the explicit mapping in
`es_client.py` existed. Fix:
```bash
curl -X DELETE http://localhost:9200/rental_properties
# then re-run the consumer + a sync to recreate the index with the correct mapping
```

**Kibana Maps / dashboard panels show no data**
Check the time range picker (top right) — it defaults to "Last 15
minutes" and filters against `created_at`. Widen it (e.g. "Last 5
years") and click Update/Refresh.

**`docker compose exec spark ...` fails with `service "spark" is not running`**
The container itself stopped. Start it first:
```bash
docker compose up -d
docker compose ps   # confirm it shows "running"
```

## Stop everything

```bash
docker compose down
```