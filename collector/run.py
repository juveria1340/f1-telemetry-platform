"""Collector entrypoint.

Examples:
    python -m collector.run --session-key 9158
    python -m collector.run --year 2023 --session-name Race --max-sessions 1 --drivers 1,44
"""

import argparse
import logging
import os
import sys
from typing import Any

import httpx

from collector import transform, validate
from collector.openf1 import DEFAULT_BASE_URL, OpenF1Client

log = logging.getLogger("collector")

CHUNK = 2000


class BackendClient:
    """Pushes validated batches to the FastAPI backend."""

    def __init__(self, client: httpx.Client, api_key: str):
        self._c = client
        self._headers = {"X-API-Key": api_key}

    def _post(self, path: str, rows: list[dict[str, Any]], **params: Any) -> int:
        upserted = 0
        for i in range(0, len(rows), CHUNK):
            resp = self._c.post(
                path, json=rows[i : i + CHUNK], headers=self._headers, params=params or None
            )
            resp.raise_for_status()
            upserted += resp.json().get("upserted", 0)
        return upserted

    def wait_ready(self) -> None:
        self._c.get("/ready").raise_for_status()

    def sessions(self, rows):
        return self._post("/api/v1/sessions", rows)

    def drivers(self, rows):
        return self._post("/api/v1/drivers", rows)

    def laps(self, session_key: int, rows):
        return self._post(f"/api/v1/sessions/{session_key}/laps", rows)

    def telemetry(self, rows):
        return self._post("/api/v1/telemetry", rows)

    def evaluate_alerts(self, session_key: int) -> int:
        resp = self._c.post(
            "/api/v1/alerts/evaluate", params={"session_key": session_key}, headers=self._headers
        )
        resp.raise_for_status()
        return resp.json()["alerts_created"]


def collect_session(
    f1: OpenF1Client,
    backend: BackendClient,
    raw_session: dict[str, Any],
    driver_filter: set[int] | None,
    telemetry_every: int,
    skip_telemetry: bool,
) -> dict[str, int]:
    stats = {"rejected": 0}
    s = validate.sessions([transform.session(raw_session)])
    stats["rejected"] += s.rejected
    if not s.valid:
        log.warning("Skipping invalid session %s", raw_session.get("session_key"))
        return stats
    session_key = s.valid[0]["session_key"]
    backend.sessions(s.valid)
    log.info(
        "Session %s: %s %s",
        session_key,
        raw_session.get("location"),
        raw_session.get("session_name"),
    )

    d = validate.drivers(transform.driver(r) for r in f1.drivers(session_key))
    if driver_filter:
        d.valid = [x for x in d.valid if x["driver_number"] in driver_filter]
    stats["rejected"] += d.rejected
    stats["drivers"] = backend.drivers(d.valid)

    driver_numbers = [x["driver_number"] for x in d.valid]
    wanted = set(driver_numbers)
    laps_raw = [r for r in f1.laps(session_key) if r.get("driver_number") in wanted]
    lp = validate.laps(transform.lap(r) for r in laps_raw)
    stats["rejected"] += lp.rejected
    stats["laps"] = backend.laps(session_key, lp.valid)

    stats["telemetry"] = 0
    if not skip_telemetry:
        for number in driver_numbers:
            rows = transform.downsample(
                [transform.car_sample(r) for r in f1.car_data(session_key, number)],
                telemetry_every,
            )
            t = validate.telemetry(rows)
            stats["rejected"] += t.rejected
            stats["telemetry"] += backend.telemetry(t.valid)
            log.info("  driver #%s: %d telemetry samples", number, len(t.valid))

    stats["alerts"] = backend.evaluate_alerts(session_key)
    return stats


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Collect OpenF1 data into the F1 telemetry API")
    sel = p.add_mutually_exclusive_group(required=True)
    sel.add_argument("--session-key", type=int, help="A single OpenF1 session_key")
    sel.add_argument("--year", type=int, help="Collect sessions from this season")
    p.add_argument("--session-name", default="Race", help="Filter when using --year")
    p.add_argument("--max-sessions", type=int, default=1)
    p.add_argument("--drivers", help="Comma-separated driver numbers (default: all)")
    p.add_argument(
        "--telemetry-every",
        type=int,
        default=20,
        help="Keep every Nth car_data sample (default 20 ≈ one per 5s)",
    )
    p.add_argument("--skip-telemetry", action="store_true")
    p.add_argument("--api-url", default=os.getenv("API_URL", "http://localhost:8000"))
    p.add_argument("--api-key", default=os.getenv("API_KEY", "change-me"))
    p.add_argument("--openf1-url", default=os.getenv("OPENF1_URL", DEFAULT_BASE_URL))
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def main(
    argv: list[str] | None = None,
    f1: OpenF1Client | None = None,
    api_client: httpx.Client | None = None,
) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    f1 = f1 or OpenF1Client(base_url=args.openf1_url)
    backend = BackendClient(
        api_client or httpx.Client(base_url=args.api_url, timeout=120.0), args.api_key
    )
    backend.wait_ready()

    if args.session_key:
        raw_sessions = f1.sessions(session_key=args.session_key)
    else:
        raw_sessions = f1.sessions(year=args.year, session_name=args.session_name)
        raw_sessions = raw_sessions[: args.max_sessions]
    if not raw_sessions:
        log.error("No sessions found on OpenF1 for the given filters")
        return 1

    driver_filter = {int(x) for x in args.drivers.split(",")} if args.drivers else None
    totals: dict[str, int] = {}
    for raw in raw_sessions:
        stats = collect_session(
            f1, backend, raw, driver_filter, args.telemetry_every, args.skip_telemetry
        )
        for k, v in stats.items():
            totals[k] = totals.get(k, 0) + v
    log.info("Done: %s", totals)
    return 0


if __name__ == "__main__":
    sys.exit(main())
