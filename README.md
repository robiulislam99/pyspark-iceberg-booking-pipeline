# Booking Lake: Local Data Pipeline

Local ETL/analytics pipeline: Booking.com JSON feeds → PySpark → Iceberg →
(SQS → Elasticsearch/Kibana) + (S3-local export with image ranking/labeling)
+ (DynamoDB export) + (Qdrant export for semantic "similar properties" search).
Fully local, no AWS account, no sudo — everything runs in Docker.

## Stack

| Component | Role |
|---|---|
| Spark + Iceberg + Sedona | transform + upsert, geo support |
| LocalStack (SQS) | change-event queue |
| Elasticsearch + Kibana | search index + dashboard |
| DynamoDB Local + dynamodb-admin | key-value export + browser UI |
| Qdrant | vector store for semantic "similar properties" search |
| Local filesystem | S3-like object store |
| Hugging Face models (local, CPU) | image aesthetic scoring + room labeling + text embeddings |
| Ruff | linting and formatting checks |
| SonarQube | code quality and security analysis |
| CI/CD | automated build, test, and quality checks |

## Prerequisites

- Docker + Docker Compose
- `booking/` data folder placed at `./data/booking` (sibling of `src/`)

## Project structure

- `src/` — main application code for the ETL pipeline
- `src/scripts/` — runnable entry points such as sync, export, and consumer scripts
- `src/clients/` — wrappers for Spark, S3, DynamoDB, Elasticsearch, Qdrant, and SQS
- `src/core/` — core processing, ranking, snapshot diff, similarity, and static-data logic
- `src/mappers/` — mapping logic between source documents and target formats
- `data/` — input feeds, local exports, and local service data directories
- `notebooks/` — exploratory notebooks for data analysis
- `tests/` — unit tests covering the pipeline components
- `docker-compose.yml` and `Dockerfile` — container orchestration and image setup

## First-time setup

```bash
git clone https://github.com/robiulislam99/pyspark-iceberg-booking-pipeline.git booking-lake
cd booking-lake

mkdir -p data/warehouse data/scheduler_data notebooks .cache/ivy_cache data/s3_local \
         data/dynamodb_data data/localstack_data data/es_data data/qdrant_data .cache/hf_cache
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
| Qdrant (REST) | http://localhost:6333 |
| Qdrant (gRPC) | http://localhost:6334 |
| Qdrant Dashboard | http://localhost:6333/dashboard |

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

## 6. Export: S3 → Qdrant (semantic "similar properties" index)

Reads the S3-exported documents (step 4 must run first), builds a text
summary per property (name, type, city, amenities, description), embeds
it locally via `sentence-transformers` (`all-MiniLM-L6-v2`, CPU-only,
no external API calls), and upserts each vector + a filterable payload
into Qdrant.

```bash
docker compose exec spark python /app/src/scripts/export_to_qdrant.py 20260714
```

Verify:
```bash
curl -s http://localhost:6333/collections/rental_properties | python3 -m json.tool
```
Look for `"points_count"` — it should roughly match the number of files
exported in step 4.

### Similarity search example

```bash
docker compose exec spark python -c "
from src.core.similarity_service import get_similar_properties
results = get_similar_properties('BC-10178627', k=5)
for r in results:
    print(f\"{r['score']:.4f}  {r['property_name']} ({r['city']})\")
"
```

Returns the top-`k` properties whose embedded name/type/city/amenities
text is most semantically similar to the given property — separate
from, and complementary to, the keyword/filter search in
Elasticsearch. `score` is cosine similarity (0–1, higher = more similar).

## 7. Compare snapshots (what changed between two syncs)

```bash
docker compose exec spark python -c "
from src.clients.spark_session import get_spark
from src.core.snapshot_diff import diff_snapshots
spark = get_spark()
snaps = spark.sql('SELECT snapshot_id FROM local.booking.rental_property.snapshots ORDER BY committed_at').collect()
diff_snapshots(spark, snaps[-2]['snapshot_id'], snaps[-1]['snapshot_id'])
"
```

## 8. Reduplication
```
docker compose exec spark python /app/src/scripts/detect_duplicates.py
```

## 9. Generate sitemap

```bash
docker compose exec spark python /app/src/scripts/generate_sitemap.py
```

This writes the sitemap XML files to `data/sitemaps/` (for example `sitemap.xml` or `sitemap-1.xml` plus `sitemap_index.xml` when the dataset is large).

## 10. Explore interactively

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

**Qdrant collection not found / `points_count: 0`**
Means `export_to_qdrant.py` hasn't been run yet, or ran against a
different `date=` partition than expected in S3. Confirm the S3 export
(step 4) has files for that date first, then re-run step 6.

**`get_similar_properties()` returns `None`**
The given `external_id` hasn't been synced into Qdrant yet (it exists
in Iceberg/S3 but wasn't in the batch exported to Qdrant), or the ID
is misspelled. Check directly:
```bash
curl -s -X POST http://localhost:6333/collections/rental_properties/points/scroll \
  -H 'Content-Type: application/json' \
  -d '{"filter": {"must": [{"key": "external_id", "match": {"value": "BC-10178627"}}]}, "limit": 1}'
```

**Qdrant embedding model download slow on first run**
The Dockerfile pre-downloads `all-MiniLM-L6-v2` at build time so it's
baked into the image — if it's still downloading at runtime, the model
cache layer likely didn't get built or was invalidated; rebuild with
`docker compose build --no-cache spark`.

## Known limitations

- Room-type labeling (`ImageAnalysis[].Label`) uses CLIP in zero-shot
  mode not trained on real-estate photos specifically; treat as
  approximate, spot-check before relying on it.
- Qdrant similarity is based only on text fields present in the S3
  document (name, type, city, country, amenities, description) — it
  does not currently factor in price, image quality, or geo-distance;
  treat it as "semantically similar," not "best alternative."