"""Test fixtures.

By default tests run on in-memory SQLite. In CI, DATABASE_URL points at a real
Postgres service so the same suite also exercises the production dialect.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("API_KEY", "test-key")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

API_KEY = os.environ["API_KEY"]
AUTH = {"X-API-Key": API_KEY}


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---- Sample data (shape of OpenF1 responses) ----
SESSION_KEY = 9158

RAW_SESSION = {
    "session_key": SESSION_KEY,
    "meeting_key": 1219,
    "session_name": "Race",
    "session_type": "Race",
    "year": 2023,
    "location": "Monza",
    "country_name": "Italy",
    "circuit_short_name": "Monza",
    "date_start": "2023-09-03T13:00:00+00:00",
    "date_end": "2023-09-03T15:00:00+00:00",
}

RAW_DRIVERS = [
    {
        "driver_number": 1,
        "full_name": "Max VERSTAPPEN",
        "name_acronym": "VER",
        "team_name": "Red Bull Racing",
        "team_colour": "3671C6",
        "country_code": "NED",
        "session_key": SESSION_KEY,
    },
    {
        "driver_number": 55,
        "full_name": "Carlos SAINZ",
        "name_acronym": "SAI",
        "team_name": "Ferrari",
        "team_colour": "F91536",
        "country_code": "ESP",
        "session_key": SESSION_KEY,
    },
]

RAW_LAPS = [
    {
        "driver_number": 1,
        "lap_number": 1,
        "lap_duration": None,
        "is_pit_out_lap": False,
        "date_start": "2023-09-03T13:03:00+00:00",
        "session_key": SESSION_KEY,
    },
    {
        "driver_number": 1,
        "lap_number": 2,
        "lap_duration": 85.0,
        "duration_sector_1": 27.0,
        "duration_sector_2": 29.0,
        "duration_sector_3": 29.0,
        "st_speed": 330,
        "is_pit_out_lap": False,
        "date_start": "2023-09-03T13:05:00+00:00",
        "session_key": SESSION_KEY,
    },
    {
        "driver_number": 55,
        "lap_number": 2,
        "lap_duration": 86.0,
        "is_pit_out_lap": False,
        "date_start": "2023-09-03T13:05:01+00:00",
        "session_key": SESSION_KEY,
    },
    # > 107% of 85.0 → slow_lap alert
    {
        "driver_number": 55,
        "lap_number": 3,
        "lap_duration": 95.0,
        "is_pit_out_lap": False,
        "date_start": "2023-09-03T13:06:30+00:00",
        "session_key": SESSION_KEY,
    },
    # invalid: lap_number 0 → rejected by validation
    {"driver_number": 55, "lap_number": 0, "lap_duration": 90.0, "session_key": SESSION_KEY},
]


def raw_car_data(driver_number: int) -> list[dict]:
    rows = []
    for i in range(10):
        rows.append(
            {
                "session_key": SESSION_KEY,
                "driver_number": driver_number,
                "date": f"2023-09-03T13:10:{i:02d}+00:00",
                "speed": 300 + i * 5,  # reaches 345 → high_speed alert
                "rpm": 11000 + i * 200,  # reaches 12800 → high_rpm alert
                "n_gear": 7,
                "throttle": 100,
                "brake": 0,
                "drs": 0,
            }
        )
    return rows
