# Booking Lake — PySpark + Iceberg + Sedona Pipeline

Local ETL pipeline: reads Booking.com JSON feed files, transforms them,
upserts into a local Iceberg table via Spark. No AWS, no cloud account,
no sudo required — everything runs inside Docker.

## Prerequisites

- Docker + Docker Compose installed on the host
- Your `booking/` data folder placed at `./booking` (sibling of `src/`)

## First-time setup

```bash
mkdir -p warehouse scheduler_data notebooks
touch warehouse/.gitkeep

docker compose build
docker compose up -d
```

## Run a manual sync

```bash
docker compose exec spark python /app/src/run_sync.py 20260714
```

(replace `20260714` with the date folder you want to process)

## Inspect the data

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

## Stop everything

```bash
docker compose down
```