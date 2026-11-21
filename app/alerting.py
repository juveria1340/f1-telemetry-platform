"""Alert rules engine. Rules are pure functions so they are easy to unit test."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.config import Settings
from app.crud import bulk_upsert
from app.metrics import ALERTS_CREATED


@dataclass(frozen=True)
class AlertCandidate:
    session_key: int
    driver_number: int
    alert_type: str
    severity: str
    message: str
    value: float
    threshold: float
    triggered_at: datetime


def telemetry_rules(
    samples: Iterable[models.Telemetry], settings: Settings
) -> list[AlertCandidate]:
    out: list[AlertCandidate] = []
    for s in samples:
        if s.rpm is not None and s.rpm >= settings.alert_max_rpm:
            out.append(
                AlertCandidate(
                    s.session_key,
                    s.driver_number,
                    "high_rpm",
                    "warning",
                    f"Car #{s.driver_number} reached {s.rpm} RPM",
                    s.rpm,
                    settings.alert_max_rpm,
                    s.date,
                )
            )
        if s.speed is not None and s.speed >= settings.alert_max_speed_kph:
            out.append(
                AlertCandidate(
                    s.session_key,
                    s.driver_number,
                    "high_speed",
                    "info",
                    f"Car #{s.driver_number} reached {s.speed} km/h",
                    s.speed,
                    settings.alert_max_speed_kph,
                    s.date,
                )
            )
    return out


def lap_rules(laps: Iterable[models.Lap], settings: Settings) -> list[AlertCandidate]:
    timed = [lap for lap in laps if lap.lap_duration and not lap.is_pit_out_lap]
    if not timed:
        return []
    fastest = min(lap.lap_duration for lap in timed)
    limit = fastest * settings.alert_slow_lap_ratio
    return [
        AlertCandidate(
            lap.session_key,
            lap.driver_number,
            "slow_lap",
            "critical",
            f"Car #{lap.driver_number} lap {lap.lap_number} ({lap.lap_duration:.3f}s) "
            f"outside {settings.alert_slow_lap_ratio:.0%} of fastest ({fastest:.3f}s)",
            lap.lap_duration,
            round(limit, 3),
            lap.date_start,
        )
        for lap in timed
        if lap.lap_duration > limit and lap.date_start is not None
    ]


def evaluate_session(db: Session, session_key: int, settings: Settings) -> int:
    samples = db.scalars(
        select(models.Telemetry).where(models.Telemetry.session_key == session_key)
    )
    laps = db.scalars(select(models.Lap).where(models.Lap.session_key == session_key)).all()

    candidates = telemetry_rules(samples, settings) + lap_rules(laps, settings)

    # Skip alerts that already exist so re-running evaluation is idempotent and the
    # "created" count/metric is exact.
    existing = {
        (driver, alert_type, _naive(ts))
        for driver, alert_type, ts in db.execute(
            select(
                models.Alert.driver_number,
                models.Alert.alert_type,
                models.Alert.triggered_at,
            ).where(models.Alert.session_key == session_key)
        ).tuples()
    }
    new = [
        c
        for c in candidates
        if (c.driver_number, c.alert_type, _naive(c.triggered_at)) not in existing
    ]

    bulk_upsert(
        db,
        models.Alert,
        [c.__dict__ for c in new],
        conflict_cols=["session_key", "driver_number", "alert_type", "triggered_at"],
        update=False,
    )
    for c in new:
        ALERTS_CREATED.labels(c.alert_type, c.severity).inc()
    return len(new)


def _naive(ts: datetime) -> datetime:
    # SQLite drops tzinfo; normalise so comparisons work on both backends.
    return ts.replace(tzinfo=None)
