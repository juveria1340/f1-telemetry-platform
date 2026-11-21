"""Prometheus instrumentation: HTTP metrics, ingest counters and DB-backed gauges."""

import logging
import time

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from prometheus_client.registry import Collector
from sqlalchemy import func, select
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app import models
from app.database import SessionLocal

log = logging.getLogger(__name__)

REGISTRY = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "f1_http_requests_total",
    "HTTP requests handled",
    ["method", "route", "status"],
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "f1_http_request_duration_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
    registry=REGISTRY,
)
INGESTED_RECORDS = Counter(
    "f1_ingested_records_total",
    "Records received through ingest endpoints",
    ["entity"],
    registry=REGISTRY,
)
ALERTS_CREATED = Counter(
    "f1_alerts_created_total",
    "Alerts created by the rules engine",
    ["alert_type", "severity"],
    registry=REGISTRY,
)


class DatabaseCollector(Collector):
    """Queries table sizes and open alerts at scrape time."""

    TABLES = {
        "drivers": models.Driver,
        "sessions": models.F1Session,
        "laps": models.Lap,
        "telemetry": models.Telemetry,
        "alerts": models.Alert,
    }

    def collect(self):
        rows = GaugeMetricFamily("f1_db_rows", "Row count per table", labels=["table"])
        open_alerts = GaugeMetricFamily(
            "f1_open_alerts", "Unacknowledged alerts", labels=["severity"]
        )
        up = GaugeMetricFamily("f1_db_up", "1 if the database answered the scrape query")
        try:
            with SessionLocal() as db:
                for name, model in self.TABLES.items():
                    count = db.scalar(select(func.count()).select_from(model))
                    rows.add_metric([name], count or 0)
                stmt = (
                    select(models.Alert.severity, func.count())
                    .where(models.Alert.acknowledged.is_(False))
                    .group_by(models.Alert.severity)
                )
                for severity, count in db.execute(stmt):
                    open_alerts.add_metric([severity], count)
            up.add_metric([], 1)
        except Exception:  # never fail a scrape because the DB is down
            log.exception("DB metrics collection failed")
            up.add_metric([], 0)
        yield rows
        yield open_alerts
        yield up


REGISTRY.register(DatabaseCollector())


class PrometheusMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = request.scope.get("route")
            # Use the route template (e.g. /drivers/{driver_number}) to keep cardinality low.
            path = getattr(route, "path", "unmatched")
            if path != "/metrics":
                HTTP_REQUESTS.labels(request.method, path, str(status_code)).inc()
                HTTP_LATENCY.labels(request.method, path).observe(time.perf_counter() - start)


def metrics_response() -> Response:
    return Response(generate_latest(REGISTRY), media_type="text/plain; version=0.0.4")
