from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.crud import bulk_upsert
from app.database import get_db
from app.metrics import INGESTED_RECORDS
from app.security import require_api_key

router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry"])

T = models.Telemetry


@router.get("", response_model=list[schemas.TelemetryOut])
def get_telemetry(
    session_key: int,
    driver_number: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(1000, ge=1, le=10000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(T).where(T.session_key == session_key, T.driver_number == driver_number)
    if date_from:
        stmt = stmt.where(T.date >= date_from)
    if date_to:
        stmt = stmt.where(T.date <= date_to)
    return db.scalars(stmt.order_by(T.date).offset(offset).limit(limit)).all()


@router.get("/summary", response_model=schemas.TelemetrySummary)
def get_telemetry_summary(session_key: int, driver_number: int, db: Session = Depends(get_db)):
    samples, max_speed, avg_speed, max_rpm, avg_throttle = db.execute(
        select(
            func.count(T.id),
            func.max(T.speed),
            func.avg(T.speed),
            func.max(T.rpm),
            func.avg(T.throttle),
        ).where(T.session_key == session_key, T.driver_number == driver_number)
    ).one()
    return schemas.TelemetrySummary(
        session_key=session_key,
        driver_number=driver_number,
        samples=samples,
        max_speed=max_speed,
        avg_speed=round(float(avg_speed), 2) if avg_speed is not None else None,
        max_rpm=max_rpm,
        avg_throttle=round(float(avg_throttle), 2) if avg_throttle is not None else None,
    )


@router.post("", response_model=schemas.IngestResult, dependencies=[Depends(require_api_key)])
def ingest_telemetry(samples: list[schemas.TelemetryIn], db: Session = Depends(get_db)):
    INGESTED_RECORDS.labels("telemetry").inc(len(samples))
    n = bulk_upsert(
        db,
        T,
        [s.model_dump() for s in samples],
        ["session_key", "driver_number", "date"],
        update=False,
    )
    return schemas.IngestResult(entity="telemetry", received=len(samples), upserted=n)
