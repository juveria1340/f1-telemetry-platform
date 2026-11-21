from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.alerting import evaluate_session
from app.config import Settings, get_settings
from app.database import get_db
from app.security import require_api_key

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


@router.get("", response_model=list[schemas.AlertOut])
def list_alerts(
    session_key: int | None = None,
    driver_number: int | None = None,
    severity: str | None = None,
    acknowledged: bool | None = None,
    limit: int = Query(200, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    A = models.Alert
    stmt = select(A)
    if session_key is not None:
        stmt = stmt.where(A.session_key == session_key)
    if driver_number is not None:
        stmt = stmt.where(A.driver_number == driver_number)
    if severity:
        stmt = stmt.where(A.severity == severity)
    if acknowledged is not None:
        stmt = stmt.where(A.acknowledged.is_(acknowledged))
    return db.scalars(stmt.order_by(A.triggered_at.desc()).limit(limit)).all()


@router.post(
    "/evaluate",
    response_model=schemas.EvaluateResult,
    dependencies=[Depends(require_api_key)],
)
def evaluate(
    session_key: int,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if db.get(models.F1Session, session_key) is None:
        raise HTTPException(404, "Session not found")
    created = evaluate_session(db, session_key, settings)
    return schemas.EvaluateResult(session_key=session_key, alerts_created=created)


@router.patch(
    "/{alert_id}/ack",
    response_model=schemas.AlertOut,
    dependencies=[Depends(require_api_key)],
)
def acknowledge(alert_id: int, db: Session = Depends(get_db)):
    alert = db.get(models.Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "Alert not found")
    alert.acknowledged = True
    db.commit()
    return alert
