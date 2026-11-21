"""Map raw OpenF1 payloads onto the backend's ingest schemas."""

from typing import Any


def session(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_key": raw.get("session_key"),
        "meeting_key": raw.get("meeting_key"),
        "session_name": raw.get("session_name"),
        "session_type": raw.get("session_type"),
        "year": raw.get("year"),
        "location": raw.get("location"),
        "country_name": raw.get("country_name"),
        "circuit_short_name": raw.get("circuit_short_name"),
        "date_start": raw.get("date_start"),
        "date_end": raw.get("date_end"),
    }


def driver(raw: dict[str, Any]) -> dict[str, Any]:
    full_name = (
        raw.get("full_name")
        or " ".join(p for p in (raw.get("first_name"), raw.get("last_name")) if p)
        or raw.get("broadcast_name")
    )
    colour = raw.get("team_colour")
    return {
        "driver_number": raw.get("driver_number"),
        "full_name": full_name,
        "name_acronym": raw.get("name_acronym"),
        "team_name": raw.get("team_name"),
        "team_colour": colour.lstrip("#")[:6] if colour else None,
        "country_code": raw.get("country_code"),
        "headshot_url": raw.get("headshot_url"),
    }


def lap(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "driver_number": raw.get("driver_number"),
        "lap_number": raw.get("lap_number"),
        "lap_duration": raw.get("lap_duration"),
        "duration_sector_1": raw.get("duration_sector_1"),
        "duration_sector_2": raw.get("duration_sector_2"),
        "duration_sector_3": raw.get("duration_sector_3"),
        "st_speed": raw.get("st_speed"),
        "is_pit_out_lap": bool(raw.get("is_pit_out_lap")),
        "date_start": raw.get("date_start"),
    }


def car_sample(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_key": raw.get("session_key"),
        "driver_number": raw.get("driver_number"),
        "date": raw.get("date"),
        "speed": raw.get("speed"),
        "rpm": raw.get("rpm"),
        "n_gear": raw.get("n_gear"),
        "throttle": raw.get("throttle"),
        "brake": raw.get("brake"),
        "drs": raw.get("drs"),
    }


def downsample(rows: list[dict[str, Any]], every: int) -> list[dict[str, Any]]:
    """Keep every Nth telemetry sample (car_data is ~4 Hz, i.e. tens of thousands per race)."""
    return rows if every <= 1 else rows[::every]
