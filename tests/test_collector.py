import httpx
import pytest

from collector import run, transform, validate
from collector.openf1 import OpenF1Client
from tests.conftest import (
    API_KEY,
    RAW_DRIVERS,
    RAW_LAPS,
    RAW_SESSION,
    SESSION_KEY,
    raw_car_data,
)


def fake_openf1_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path, params = request.url.path, request.url.params
        if path.endswith("/sessions"):
            return httpx.Response(200, json=[RAW_SESSION])
        if path.endswith("/drivers"):
            return httpx.Response(200, json=RAW_DRIVERS)
        if path.endswith("/laps"):
            return httpx.Response(200, json=RAW_LAPS)
        if path.endswith("/car_data"):
            return httpx.Response(200, json=raw_car_data(int(params["driver_number"])))
        return httpx.Response(404, json={"detail": "not found"})

    return httpx.MockTransport(handler)


def make_f1(handler_transport=None, **kw) -> OpenF1Client:
    client = httpx.Client(
        base_url="https://api.openf1.org/v1", transport=handler_transport or fake_openf1_transport()
    )
    return OpenF1Client(client=client, **kw)


# ---------- transform / validate ----------
def test_driver_transform_builds_name_and_strips_hash():
    out = transform.driver(
        {"driver_number": 4, "first_name": "Lando", "last_name": "Norris", "team_colour": "#FF8000"}
    )
    assert out["full_name"] == "Lando Norris"
    assert out["team_colour"] == "FF8000"


def test_validate_rejects_and_dedupes():
    rows = [transform.lap(r) for r in RAW_LAPS] + [transform.lap(RAW_LAPS[1])]
    report = validate.laps(rows)
    assert report.rejected == 1  # lap_number 0
    assert len(report.valid) == 4  # duplicate dropped


def test_downsample():
    assert len(transform.downsample(list(range(100)), 20)) == 5
    assert len(transform.downsample(list(range(10)), 1)) == 10


# ---------- OpenF1 client ----------
def test_openf1_404_means_empty():
    f1 = make_f1(httpx.MockTransport(lambda r: httpx.Response(404)))
    assert f1.sessions(year=1900) == []


def test_openf1_retries_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(503) if calls["n"] < 3 else httpx.Response(200, json=[RAW_SESSION])

    f1 = make_f1(httpx.MockTransport(handler), retries=3, backoff_seconds=0)
    assert f1.sessions(session_key=SESSION_KEY) == [RAW_SESSION]
    assert calls["n"] == 3


def test_openf1_gives_up():
    f1 = make_f1(httpx.MockTransport(lambda r: httpx.Response(500)), retries=2, backoff_seconds=0)
    with pytest.raises(httpx.HTTPStatusError):
        f1.sessions()


# ---------- End to end: OpenF1 (mocked) → collector → FastAPI → DB ----------
def test_collector_end_to_end(client):
    code = run.main(
        ["--session-key", str(SESSION_KEY), "--telemetry-every", "1", "--api-key", API_KEY],
        f1=make_f1(),
        api_client=client,
    )
    assert code == 0

    assert len(client.get("/api/v1/drivers").json()) == 2
    assert len(client.get(f"/api/v1/sessions/{SESSION_KEY}/laps").json()) == 4
    summary = client.get(
        f"/api/v1/telemetry/summary?session_key={SESSION_KEY}&driver_number=1"
    ).json()
    assert summary["samples"] == 10 and summary["max_speed"] == 345

    alerts = client.get(f"/api/v1/alerts?session_key={SESSION_KEY}").json()
    kinds = {a["alert_type"] for a in alerts}
    assert kinds == {"high_rpm", "high_speed", "slow_lap"}

    # Re-running is idempotent: no duplicate data or alerts
    run.main(
        ["--session-key", str(SESSION_KEY), "--telemetry-every", "1", "--api-key", API_KEY],
        f1=make_f1(),
        api_client=client,
    )
    assert len(client.get(f"/api/v1/alerts?session_key={SESSION_KEY}").json()) == len(alerts)

    # Acknowledge flow
    first = alerts[0]["id"]
    acked = client.patch(f"/api/v1/alerts/{first}/ack", headers={"X-API-Key": API_KEY})
    assert acked.json()["acknowledged"] is True
    open_alerts = client.get(f"/api/v1/alerts?session_key={SESSION_KEY}&acknowledged=false").json()
    assert len(open_alerts) == len(alerts) - 1


def test_collector_no_sessions_returns_error(client):
    f1 = make_f1(httpx.MockTransport(lambda r: httpx.Response(404)))
    assert run.main(["--year", "1900", "--api-key", API_KEY], f1=f1, api_client=client) == 1
