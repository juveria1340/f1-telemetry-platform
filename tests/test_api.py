from tests.conftest import AUTH, RAW_DRIVERS, RAW_SESSION, SESSION_KEY


def _seed(client):
    from collector import transform

    assert client.post("/api/v1/sessions", json=[RAW_SESSION], headers=AUTH).status_code == 200
    drivers = [transform.driver(d) for d in RAW_DRIVERS]
    assert client.post("/api/v1/drivers", json=drivers, headers=AUTH).status_code == 200


def test_health_and_ready(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}


def test_write_endpoints_require_api_key(client):
    for path in ["/api/v1/sessions", "/api/v1/drivers", "/api/v1/telemetry"]:
        assert client.post(path, json=[]).status_code == 401
        assert client.post(path, json=[], headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post(f"/api/v1/alerts/evaluate?session_key={SESSION_KEY}").status_code == 401


def test_drivers_crud_and_upsert(client):
    _seed(client)
    resp = client.get("/api/v1/drivers")
    assert [d["driver_number"] for d in resp.json()] == [1, 55]

    # Upsert is idempotent and updates fields
    updated = [{"driver_number": 1, "full_name": "Max Verstappen", "team_name": "RBR"}]
    assert client.post("/api/v1/drivers", json=updated, headers=AUTH).status_code == 200
    assert client.get("/api/v1/drivers/1").json()["team_name"] == "RBR"
    assert len(client.get("/api/v1/drivers").json()) == 2

    assert client.get("/api/v1/drivers?team=ferrari").json()[0]["name_acronym"] == "SAI"
    assert client.get("/api/v1/drivers/99").status_code == 404


def test_sessions_filters(client):
    _seed(client)
    assert len(client.get("/api/v1/sessions?year=2023").json()) == 1
    assert client.get("/api/v1/sessions?year=2020").json() == []
    assert client.get(f"/api/v1/sessions/{SESSION_KEY}").json()["location"] == "Monza"
    assert client.get("/api/v1/sessions/1").status_code == 404


def test_laps_and_fastest_laps(client):
    _seed(client)
    laps = [
        {"driver_number": 1, "lap_number": 1, "lap_duration": 90.0},
        {"driver_number": 1, "lap_number": 2, "lap_duration": 85.5},
        {"driver_number": 55, "lap_number": 1, "lap_duration": 86.1},
    ]
    r = client.post(f"/api/v1/sessions/{SESSION_KEY}/laps", json=laps, headers=AUTH)
    assert r.status_code == 200 and r.json()["received"] == 3

    fastest = client.get(f"/api/v1/sessions/{SESSION_KEY}/fastest-laps").json()
    assert [(lap["driver_number"], lap["lap_duration"]) for lap in fastest] == [
        (1, 85.5),
        (55, 86.1),
    ]
    assert len(client.get("/api/v1/drivers/1/laps").json()) == 2
    assert client.post("/api/v1/sessions/1/laps", json=laps, headers=AUTH).status_code == 404


def test_telemetry_validation_rejects_bad_payload(client):
    _seed(client)
    bad = [
        {
            "session_key": SESSION_KEY,
            "driver_number": 1,
            "date": "2023-09-03T13:00:00Z",
            "speed": 999,
        }
    ]
    assert client.post("/api/v1/telemetry", json=bad, headers=AUTH).status_code == 422


def test_telemetry_summary(client):
    _seed(client)
    samples = [
        {
            "session_key": SESSION_KEY,
            "driver_number": 1,
            "date": f"2023-09-03T13:00:0{i}Z",
            "speed": 200 + i * 10,
            "rpm": 10000,
            "throttle": 50,
        }
        for i in range(5)
    ]
    assert client.post("/api/v1/telemetry", json=samples, headers=AUTH).status_code == 200
    # Duplicate ingest does not create duplicate rows
    client.post("/api/v1/telemetry", json=samples, headers=AUTH)

    s = client.get(f"/api/v1/telemetry/summary?session_key={SESSION_KEY}&driver_number=1").json()
    assert s["samples"] == 5
    assert s["max_speed"] == 240
    assert s["avg_speed"] == 220.0

    page = client.get(
        f"/api/v1/telemetry?session_key={SESSION_KEY}&driver_number=1&limit=2&offset=1"
    ).json()
    assert [p["speed"] for p in page] == [210, 220]


def test_metrics_endpoint(client):
    _seed(client)
    client.get("/api/v1/drivers")
    body = client.get("/metrics").text
    assert 'f1_http_requests_total{method="GET",route="/api/v1/drivers",status="200"}' in body
    assert 'f1_db_rows{table="drivers"} 2.0' in body
    assert "f1_db_up 1.0" in body
    assert 'f1_ingested_records_total{entity="drivers"}' in body
