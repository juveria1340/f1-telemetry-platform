from datetime import UTC, datetime

from app import models
from app.alerting import lap_rules, telemetry_rules
from app.config import Settings

SETTINGS = Settings(alert_max_rpm=12000, alert_max_speed_kph=330, alert_slow_lap_ratio=1.07)
TS = datetime(2023, 9, 3, 13, 0, tzinfo=UTC)


def _sample(**kw):
    base = {"session_key": 1, "driver_number": 1, "date": TS, "speed": 200, "rpm": 10000}
    return models.Telemetry(**{**base, **kw})


def _lap(n, duration, pit=False):
    return models.Lap(
        session_key=1,
        driver_number=1,
        lap_number=n,
        lap_duration=duration,
        is_pit_out_lap=pit,
        date_start=TS,
    )


def test_no_alerts_under_thresholds():
    assert telemetry_rules([_sample()], SETTINGS) == []


def test_rpm_and_speed_alerts():
    alerts = telemetry_rules([_sample(rpm=12000, speed=331)], SETTINGS)
    assert {a.alert_type for a in alerts} == {"high_rpm", "high_speed"}


def test_missing_values_are_ignored():
    assert telemetry_rules([_sample(rpm=None, speed=None)], SETTINGS) == []


def test_slow_lap_rule_107_percent():
    laps = [_lap(1, 80.0), _lap(2, 85.5), _lap(3, 85.7), _lap(4, None)]
    alerts = lap_rules(laps, SETTINGS)
    # 80 * 1.07 = 85.6 → only lap 3 is outside
    assert [a.value for a in alerts] == [85.7]
    assert alerts[0].severity == "critical"


def test_pit_out_laps_are_excluded():
    laps = [_lap(1, 80.0), _lap(2, 120.0, pit=True)]
    assert lap_rules(laps, SETTINGS) == []


def test_lap_rules_empty():
    assert lap_rules([], SETTINGS) == []
