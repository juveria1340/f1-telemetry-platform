"""Validate transformed rows against the backend's own Pydantic schemas.

Invalid rows are dropped and counted, never sent. Reusing app.schemas keeps the
collector and API contract in lock-step (a schema change breaks CI, not prod).
"""

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from app.schemas import DriverIn, LapIn, SessionIn, TelemetryIn

log = logging.getLogger(__name__)


@dataclass
class ValidationReport:
    valid: list[dict[str, Any]] = field(default_factory=list)
    rejected: int = 0


def _validate(
    rows: Iterable[dict[str, Any]],
    schema: type[BaseModel],
    key: Callable[[BaseModel], Any],
) -> ValidationReport:
    report = ValidationReport()
    seen: set[Any] = set()
    for row in rows:
        try:
            model = schema.model_validate(row)
        except ValidationError as exc:
            report.rejected += 1
            log.debug("Rejected %s row %s: %s", schema.__name__, row, exc.errors())
            continue
        k = key(model)
        if k in seen:  # de-duplicate within a batch (Postgres upsert can't touch a row twice)
            continue
        seen.add(k)
        report.valid.append(model.model_dump(mode="json"))
    if report.rejected:
        log.warning("%s: rejected %d invalid rows", schema.__name__, report.rejected)
    return report


def sessions(rows: Iterable[dict[str, Any]]) -> ValidationReport:
    return _validate(rows, SessionIn, lambda m: m.session_key)


def drivers(rows: Iterable[dict[str, Any]]) -> ValidationReport:
    return _validate(rows, DriverIn, lambda m: m.driver_number)


def laps(rows: Iterable[dict[str, Any]]) -> ValidationReport:
    return _validate(rows, LapIn, lambda m: (m.driver_number, m.lap_number))


def telemetry(rows: Iterable[dict[str, Any]]) -> ValidationReport:
    return _validate(rows, TelemetryIn, lambda m: (m.driver_number, m.date))
