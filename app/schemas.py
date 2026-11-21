from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Drivers ----------
class DriverIn(BaseModel):
    driver_number: int = Field(ge=1, le=99)
    full_name: str = Field(min_length=1)
    name_acronym: str | None = Field(default=None, max_length=3)
    team_name: str | None = None
    team_colour: str | None = Field(default=None, max_length=6)
    country_code: str | None = Field(default=None, max_length=3)
    headshot_url: str | None = None


class DriverOut(DriverIn, ORMModel):
    pass


# ---------- Sessions ----------
class SessionIn(BaseModel):
    session_key: int
    meeting_key: int | None = None
    session_name: str
    session_type: str | None = None
    year: int | None = Field(default=None, ge=1950, le=2100)
    location: str | None = None
    country_name: str | None = None
    circuit_short_name: str | None = None
    date_start: datetime | None = None
    date_end: datetime | None = None


class SessionOut(SessionIn, ORMModel):
    pass


# ---------- Laps ----------
class LapIn(BaseModel):
    driver_number: int = Field(ge=1, le=99)
    lap_number: int = Field(ge=1)
    lap_duration: float | None = Field(default=None, gt=0)
    duration_sector_1: float | None = Field(default=None, gt=0)
    duration_sector_2: float | None = Field(default=None, gt=0)
    duration_sector_3: float | None = Field(default=None, gt=0)
    st_speed: float | None = Field(default=None, ge=0)
    is_pit_out_lap: bool = False
    date_start: datetime | None = None


class LapOut(LapIn, ORMModel):
    session_key: int


# ---------- Telemetry ----------
class TelemetryIn(BaseModel):
    session_key: int
    driver_number: int = Field(ge=1, le=99)
    date: datetime
    speed: int | None = Field(default=None, ge=0, le=400)
    rpm: int | None = Field(default=None, ge=0, le=20000)
    n_gear: int | None = Field(default=None, ge=0, le=8)
    throttle: int | None = Field(default=None, ge=0, le=104)
    brake: int | None = Field(default=None, ge=0, le=100)
    drs: int | None = Field(default=None, ge=0)


class TelemetryOut(TelemetryIn, ORMModel):
    pass


class TelemetrySummary(BaseModel):
    session_key: int
    driver_number: int
    samples: int
    max_speed: int | None
    avg_speed: float | None
    max_rpm: int | None
    avg_throttle: float | None


# ---------- Alerts ----------
class AlertOut(ORMModel):
    id: int
    session_key: int
    driver_number: int
    alert_type: str
    severity: str
    message: str
    value: float | None
    threshold: float | None
    triggered_at: datetime
    acknowledged: bool
    created_at: datetime


class EvaluateResult(BaseModel):
    session_key: int
    alerts_created: int


class IngestResult(BaseModel):
    entity: str
    received: int
    upserted: int
