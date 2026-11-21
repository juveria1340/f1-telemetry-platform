# F1 Telemetry Monitoring Platform

```
OpenF1 API ──► F1 Data Collector ──► FastAPI Backend ──► PostgreSQL
               (fetch·transform·      Drivers / Sessions /
                validate)             Telemetry / Alerts APIs
                                            │ /metrics
                                            ▼
                                       Prometheus ──► Grafana
```

| Component  | Where                     | Notes |
|------------|---------------------------|-------|
| Collector  | `collector/`              | Pulls sessions, drivers, laps and `car_data` from [OpenF1](https://openf1.org), validates with the API's own Pydantic schemas, pushes batches to the API, then triggers alert evaluation. |
| Backend    | `app/`                    | FastAPI + SQLAlchemy. Read endpoints are public; write endpoints need `X-API-Key`. |
| Database   | PostgreSQL 16             | Tables: `drivers`, `sessions`, `laps`, `telemetry`, `alerts`. |
| Metrics    | `GET /metrics`            | HTTP rate/latency, ingested records, alerts created, DB row counts, open alerts. |
| Monitoring | `monitoring/`             | Prometheus scrape config + alert rules; Grafana datasource + dashboard provisioned automatically. |

## Run locally

```bash
cp .env.example .env
docker compose up -d --build                 # db, api, prometheus, grafana
docker compose run --rm collector --year 2023 --session-name Race --max-sessions 1 --drivers 1,44
```

- API docs: http://localhost:8000/docs
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin) → *F1 Telemetry* folder

Live reload while developing: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up`.

## API

| Method | Path | Auth |
|--------|------|------|
| GET  | `/health`, `/ready`, `/metrics` | – |
| GET  | `/api/v1/drivers` (`?team=`), `/api/v1/drivers/{n}`, `/api/v1/drivers/{n}/laps` | – |
| POST | `/api/v1/drivers` (bulk upsert) | key |
| GET  | `/api/v1/sessions` (`?year=&session_type=`), `/api/v1/sessions/{key}`, `/{key}/laps`, `/{key}/fastest-laps` | – |
| POST | `/api/v1/sessions`, `/api/v1/sessions/{key}/laps` | key |
| GET  | `/api/v1/telemetry?session_key=&driver_number=`, `/api/v1/telemetry/summary` | – |
| POST | `/api/v1/telemetry` | key |
| GET  | `/api/v1/alerts` (`?session_key=&severity=&acknowledged=`) | – |
| POST | `/api/v1/alerts/evaluate?session_key=` | key |
| PATCH| `/api/v1/alerts/{id}/ack` | key |

All ingest endpoints are idempotent (upserts), so re-running the collector is safe.

### Alert rules (`app/alerting.py`, thresholds via env)

| Type | Severity | Trigger |
|------|----------|---------|
| `high_rpm`   | warning  | `rpm >= ALERT_MAX_RPM` (12500) |
| `high_speed` | info     | `speed >= ALERT_MAX_SPEED_KPH` (340) |
| `slow_lap`   | critical | lap slower than `ALERT_SLOW_LAP_RATIO` × session fastest (107% rule), pit-out laps excluded |

## Tests

```bash
pip install -r requirements-dev.txt
pytest --cov            # in-memory SQLite by default
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/telematics pytest   # against Postgres
```

`tests/test_collector.py::test_collector_end_to_end` runs the real collector against a mocked
OpenF1 and the real API (via `TestClient`), so the full pipeline is tested with no network.

## CI (`.github/workflows/ci.yml`)

1. **lint**: `ruff check` + `ruff format --check`
2. **test**: pytest against a Postgres 16 service container, uploads JUnit + coverage XML
3. **validate-monitoring**: `promtool check config`, dashboard JSON, `docker compose config`
4. **build-and-smoke**: builds the image, Trivy scan (fails on fixable CRITICAL CVEs), brings up
   db + api + prometheus, curls the API (including the auth check), and verifies Prometheus scrapes it
5. **collector-live** (manual `workflow_dispatch` only): ingests a real race from OpenF1

Third-party OpenF1 is never hit on push/PR, so CI is deterministic.
