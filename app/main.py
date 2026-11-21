from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db, init_db
from app.metrics import PrometheusMiddleware, metrics_response
from app.routers import alerts, drivers, sessions, telemetry


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=get_settings().app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(PrometheusMiddleware)

app.include_router(drivers.router)
app.include_router(sessions.router)
app.include_router(telemetry.router)
app.include_router(alerts.router)


@app.get("/health", tags=["ops"])
def health():
    """Liveness: the process is up."""
    return {"status": "ok"}


@app.get("/ready", tags=["ops"])
def ready(db: Session = Depends(get_db)):
    """Readiness: the database is reachable."""
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "database unavailable") from exc
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metrics():
    return metrics_response()
