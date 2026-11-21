from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models, schemas
from app.crud import bulk_upsert
from app.database import get_db
from app.metrics import INGESTED_RECORDS
from app.security import require_api_key

router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.get("", response_model=list[schemas.SessionOut])
def list_sessions(
    year: int | None = None,
    session_type: str | None = None,
    db: Session = Depends(get_db),
):
    stmt = select(models.F1Session).order_by(models.F1Session.date_start)
    if year is not None:
        stmt = stmt.where(models.F1Session.year == year)
    if session_type:
        stmt = stmt.where(models.F1Session.session_type.ilike(session_type))
    return db.scalars(stmt).all()


@router.get("/{session_key}", response_model=schemas.SessionOut)
def get_session(session_key: int, db: Session = Depends(get_db)):
    session = db.get(models.F1Session, session_key)
    if session is None:
        raise HTTPException(404, "Session not found")
    return session


@router.get("/{session_key}/laps", response_model=list[schemas.LapOut])
def get_session_laps(
    session_key: int,
    driver_number: int | None = None,
    limit: int = Query(500, ge=1, le=5000),
    db: Session = Depends(get_db),
):
    stmt = select(models.Lap).where(models.Lap.session_key == session_key)
    if driver_number is not None:
        stmt = stmt.where(models.Lap.driver_number == driver_number)
    stmt = stmt.order_by(models.Lap.lap_number, models.Lap.driver_number).limit(limit)
    return db.scalars(stmt).all()


@router.get("/{session_key}/fastest-laps", response_model=list[schemas.LapOut])
def get_fastest_laps(session_key: int, db: Session = Depends(get_db)):
    """Each driver's fastest lap in the session, quickest first."""
    best = (
        select(models.Lap.driver_number, func.min(models.Lap.lap_duration).label("best"))
        .where(models.Lap.session_key == session_key, models.Lap.lap_duration.is_not(None))
        .group_by(models.Lap.driver_number)
        .subquery()
    )
    stmt = (
        select(models.Lap)
        .join(
            best,
            (models.Lap.driver_number == best.c.driver_number)
            & (models.Lap.lap_duration == best.c.best),
        )
        .where(models.Lap.session_key == session_key)
        .order_by(models.Lap.lap_duration)
    )
    # A driver could set the identical best time twice; keep the first.
    seen, out = set(), []
    for lap in db.scalars(stmt):
        if lap.driver_number not in seen:
            seen.add(lap.driver_number)
            out.append(lap)
    return out


@router.post("", response_model=schemas.IngestResult, dependencies=[Depends(require_api_key)])
def upsert_sessions(sessions: list[schemas.SessionIn], db: Session = Depends(get_db)):
    INGESTED_RECORDS.labels("sessions").inc(len(sessions))
    n = bulk_upsert(db, models.F1Session, [s.model_dump() for s in sessions], ["session_key"])
    return schemas.IngestResult(entity="sessions", received=len(sessions), upserted=n)


@router.post(
    "/{session_key}/laps",
    response_model=schemas.IngestResult,
    dependencies=[Depends(require_api_key)],
)
def upsert_laps(session_key: int, laps: list[schemas.LapIn], db: Session = Depends(get_db)):
    if db.get(models.F1Session, session_key) is None:
        raise HTTPException(404, "Session not found")
    INGESTED_RECORDS.labels("laps").inc(len(laps))
    rows = [{**lap.model_dump(), "session_key": session_key} for lap in laps]
    n = bulk_upsert(db, models.Lap, rows, ["session_key", "driver_number", "lap_number"])
    return schemas.IngestResult(entity="laps", received=len(laps), upserted=n)
