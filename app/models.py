from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Driver(Base):
    __tablename__ = "drivers"

    driver_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    name_acronym: Mapped[str | None] = mapped_column(String(3))
    team_name: Mapped[str | None] = mapped_column(String(120))
    team_colour: Mapped[str | None] = mapped_column(String(6))
    country_code: Mapped[str | None] = mapped_column(String(3))
    headshot_url: Mapped[str | None] = mapped_column(String(500))


class F1Session(Base):
    __tablename__ = "sessions"

    session_key: Mapped[int] = mapped_column(Integer, primary_key=True)
    meeting_key: Mapped[int | None] = mapped_column(Integer)
    session_name: Mapped[str] = mapped_column(String(60))
    session_type: Mapped[str | None] = mapped_column(String(60))
    year: Mapped[int | None] = mapped_column(Integer, index=True)
    location: Mapped[str | None] = mapped_column(String(120))
    country_name: Mapped[str | None] = mapped_column(String(120))
    circuit_short_name: Mapped[str | None] = mapped_column(String(120))
    date_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    date_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Lap(Base):
    __tablename__ = "laps"
    __table_args__ = (UniqueConstraint("session_key", "driver_number", "lap_number"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[int] = mapped_column(ForeignKey("sessions.session_key"), index=True)
    driver_number: Mapped[int] = mapped_column(ForeignKey("drivers.driver_number"), index=True)
    lap_number: Mapped[int] = mapped_column(Integer)
    lap_duration: Mapped[float | None] = mapped_column(Float)
    duration_sector_1: Mapped[float | None] = mapped_column(Float)
    duration_sector_2: Mapped[float | None] = mapped_column(Float)
    duration_sector_3: Mapped[float | None] = mapped_column(Float)
    st_speed: Mapped[float | None] = mapped_column(Float)
    is_pit_out_lap: Mapped[bool] = mapped_column(Boolean, default=False)
    date_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        UniqueConstraint("session_key", "driver_number", "date"),
        Index("ix_telemetry_session_driver_date", "session_key", "driver_number", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[int] = mapped_column(ForeignKey("sessions.session_key"))
    driver_number: Mapped[int] = mapped_column(ForeignKey("drivers.driver_number"))
    date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    speed: Mapped[int | None] = mapped_column(Integer)
    rpm: Mapped[int | None] = mapped_column(Integer)
    n_gear: Mapped[int | None] = mapped_column(Integer)
    throttle: Mapped[int | None] = mapped_column(Integer)
    brake: Mapped[int | None] = mapped_column(Integer)
    drs: Mapped[int | None] = mapped_column(Integer)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        # One alert per rule/driver/session/moment, so re-evaluating is idempotent.
        UniqueConstraint("session_key", "driver_number", "alert_type", "triggered_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_key: Mapped[int] = mapped_column(ForeignKey("sessions.session_key"), index=True)
    driver_number: Mapped[int] = mapped_column(ForeignKey("drivers.driver_number"), index=True)
    alert_type: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(20), index=True)
    message: Mapped[str] = mapped_column(String(500))
    value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    acknowledged: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
