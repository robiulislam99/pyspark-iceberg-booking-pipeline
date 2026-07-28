# Booking Lake — Local Data Pipeline

Local ETL/analytics pipeline: Booking.com JSON feeds → PySpark → Iceberg →
(SQS → Elasticsearch/Kibana) + (S3-local export with image ranking/labeling)
+ (DynamoDB export). Fully local, no AWS account, no sudo — everything runs
in Docker.

## Stack

| Component | Role |
|---|---|
| Spark + Iceberg + Sedona | transform + upsert, geo support |
| LocalStack (SQS) | change-event queue |
| Elasticsearch + Kibana | search index + dashboard |
| DynamoDB Local + dynamodb-admin | key-value export + browser UI |
| Local filesystem | S3-like object store |
| Hugging Face models (local, CPU) | image aesthetic scoring + room labeling |
| Ruff | linting and formatting checks |
| SonarQube | code quality and security analysis |
| CI/CD | automated build, test, and quality checks |

## Prerequisites

- Docker + Docker Compose
- `booking/` data folder placed at `./data/booking` (sibling of `src/`)

## Project structure

- `src/` — main application code for the ETL pipeline
- `src/scripts/` — runnable entry points such as sync, export, and consumer scripts
- `src/clients/` — wrappers for Spark, S3, DynamoDB, Elasticsearch, and SQS
- `src/core/` — core processing, ranking, snapshot diff, and static-data logic
- `src/mappers/` — mapping logic between source documents and target formats
- `data/` — input feeds, local exports, and local service data directories
- `notebooks/` — exploratory notebooks for data analysis
- `tests/` — unit tests covering the pipeline components
- `docker-compose.yml` and `Dockerfile` — container orchestration and image setup

## First-time setup

```bash
git clone <repo-url>
cd booking-lake

mkdir -p data/warehouse data/scheduler_data notebooks .cache/ivy_cache data/s3_local \
         data/dynamodb_data data/localstack_data data/es_data .cache/hf_cache
touch data/warehouse/.gitkeep

docker compose build
docker compose up -d
docker compose ps    # confirm all services show "running"
```

Ports:

| Service | URL |
|---|---|
| Spark UI | http://localhost:4040 |
| Jupyter | http://localhost:8888 |
| LocalStack | http://localhost:4566 |
| Elasticsearch | http://localhost:9200 |
| Kibana | http://localhost:5601 |
| DynamoDB Local | http://localhost:8001 |
| dynamodb-admin | http://localhost:8002 |

## 1. Sync: JSON feed → Iceberg

```bash
docker compose exec spark python /app/src/scripts/run_sync.py 20260714
```

Publishes an SQS event with changed `feed_provider_id`s on success.

Verify:
```bash
docker compose exec spark python -c "
from src.clients.spark_session import get_spark
spark = get_spark()
spark.sql('SELECT COUNT(*) FROM local.booking.rental_property').show()
"
```

## 2. Consumer: SQS → Elasticsearch

Run in its own terminal, keep running:
```bash
docker compose exec spark python /app/src/scripts/sqs_consumer.py
```

Verify:
```bash
curl http://localhost:9200/rental_properties/_count
curl http://localhost:9200/rental_properties/_mapping/field/lonlat
```

## 3. Kibana dashboard

1. http://localhost:5601 → **Explore on my own**
2. Stack Management → Data Views → create `rental_properties`, pattern `rental_properties*`
3. Maps app → Create map → Add layer → Documents → data view `rental_properties` → geospatial field `lonlat`
4. Dashboard → Add from library (map) + Create visualization (Lens) for charts/tables
5. If panels show no data: widen the time range (default is "Last 15 minutes")

## 4. Export: Iceberg → local S3 (May take time, as used two models for RankImage)

```bash
docker compose exec spark python /app/src/scripts/export_to_s3_local.py 20260714
```

Includes `RankedImage`/`RankedImages` (top 4 by aesthetic score) and
`ImageAnalysis` (per-image aesthetic score 0–10 + room-type label:
bedroom/balcony/bathroom/swimming pool/house), computed via local
Hugging Face models — slow, one download + two model passes per photo.

Verify:
```bash
ls data/s3_local/booking-lake-bucket/rental-properties/date=20260714/ | wc -l
cat data/s3_local/booking-lake-bucket/rental-properties/date=20260714/BC-<id>.json
```

## 5. Export: Iceberg → DynamoDB

```bash
docker compose exec spark python /app/src/scripts/export_to_dynamodb.py 20260714
```

Verify: open http://localhost:8002, or:
```bash
docker compose exec spark python -c "
from src.clients.dynamodb_client import get_table
print(get_table().scan()['Count'], 'items')
"
```

## 6. Compare snapshots (what changed between two syncs)

```bash
docker compose exec spark python -c "
from src.clients.spark_session import get_spark
from src.core.snapshot_diff import diff_snapshots
spark = get_spark()
snaps = spark.sql('SELECT snapshot_id FROM local.booking.rental_property.snapshots ORDER BY committed_at').collect()
diff_snapshots(spark, snaps[-2]['snapshot_id'], snaps[-1]['snapshot_id'])
"
```

## 7. Explore interactively

```bash
docker compose exec spark jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --allow-root
```
Copy the printed token URL, open `notebooks/explore_data.ipynb` in VS Code,
select **Existing Jupyter Server** as the kernel.

## Shell into the container

```bash
docker compose exec spark bash
```

## Stop everything

```bash
docker compose down
```

## Troubleshooting

**Sedona jar corrupted / `ClassNotFoundException`**
```bash
docker compose exec spark rm -rf /root/.ivy2
docker compose exec spark python /app/src/scripts/run_sync.py 20260714
```

**ES `lonlat` mapped as `float` instead of `geo_point`**
```bash
curl -X DELETE http://localhost:9200/rental_properties
# re-run consumer + a sync to recreate with the correct mapping
```

**Kibana panels show no data**
Widen the time range picker (top right), then Update/Refresh.

**`service "spark" is not running`**
```bash
docker compose up -d
docker compose ps
```

**Port already allocated (e.g. DynamoDB on 8000)**
Change the host-side port in `docker-compose.yml` (`"8001:8000"`), leave
the container-internal port unchanged.

**`Float types are not supported` (DynamoDB)**
Numeric fields must be `Decimal`, not `float`, before writing to
DynamoDB — see `dynamodb_document_mapper.py`.

**Image ranking: `Skipping <url>: 404`**
Booking.com photo URLs are signed and expire — expected on older test
data, not a code fault. Confirm with:
```bash
docker compose exec spark python -c "
import requests
print(requests.head('<url>', timeout=5).status_code)
"
```

## Known limitations

- Iceberg's `rental_property` table holds only the latest merged state
  per property — no historical snapshots per sync date beyond Iceberg's
  own snapshot metadata (see step 7).
- `export_to_s3_local.py` and `export_to_dynamodb.py` filter by that
  date's changelog IDs, not by any stored "as of" state.
- Room-type labeling (`ImageAnalysis[].Label`) uses CLIP in zero-shot
  mode — not trained on real-estate photos specifically; treat as
  approximate, spot-check before relying on it.
