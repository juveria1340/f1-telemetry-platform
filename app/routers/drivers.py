from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.crud import bulk_upsert
from app.database import get_db
from app.metrics import INGESTED_RECORDS
from app.security import require_api_key

router = APIRouter(prefix="/api/v1/drivers", tags=["drivers"])


@router.get("", response_model=list[schemas.DriverOut])
def list_drivers(team: str | None = None, db: Session = Depends(get_db)):
    stmt = select(models.Driver).order_by(models.Driver.driver_number)
    if team:
        stmt = stmt.where(models.Driver.team_name.ilike(f"%{team}%"))
    return db.scalars(stmt).all()


@router.get("/{driver_number}", response_model=schemas.DriverOut)
def get_driver(driver_number: int, db: Session = Depends(get_db)):
    driver = db.get(models.Driver, driver_number)
    if driver is None:
        raise HTTPException(404, "Driver not found")
    return driver


@router.get("/{driver_number}/laps", response_model=list[schemas.LapOut])
def get_driver_laps(
    driver_number: int,
    session_key: int | None = None,
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    stmt = select(models.Lap).where(models.Lap.driver_number == driver_number)
    if session_key is not None:
        stmt = stmt.where(models.Lap.session_key == session_key)
    return db.scalars(
        stmt.order_by(models.Lap.session_key, models.Lap.lap_number).limit(limit)
    ).all()


@router.post("", response_model=schemas.IngestResult, dependencies=[Depends(require_api_key)])
def upsert_drivers(drivers: list[schemas.DriverIn], db: Session = Depends(get_db)):
    INGESTED_RECORDS.labels("drivers").inc(len(drivers))
    n = bulk_upsert(db, models.Driver, [d.model_dump() for d in drivers], ["driver_number"])
    return schemas.IngestResult(entity="drivers", received=len(drivers), upserted=n)
