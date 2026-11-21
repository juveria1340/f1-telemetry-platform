"""Thin client for the public OpenF1 API (https://openf1.org)."""

import logging
import time
from typing import Any

import httpx

log = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openf1.org/v1"


class OpenF1Client:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        client: httpx.Client | None = None,
        retries: int = 3,
        backoff_seconds: float = 2.0,
    ):
        self._client = client or httpx.Client(base_url=base_url, timeout=60.0)
        self._retries = retries
        self._backoff = backoff_seconds

    def _get(self, path: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        for attempt in range(1, self._retries + 1):
            try:
                resp = self._client.get(path, params=params)
                if resp.status_code == 404:  # OpenF1 returns 404 for "no results"
                    return []
                if resp.status_code == 429 or resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"retryable status {resp.status_code}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, list) else []
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if attempt == self._retries:
                    raise
                wait = self._backoff * attempt
                log.warning("OpenF1 %s failed (%s); retry %d in %.1fs", path, exc, attempt, wait)
                time.sleep(wait)
        return []

    def sessions(self, **filters: Any) -> list[dict[str, Any]]:
        return self._get("/sessions", filters)

    def drivers(self, session_key: int) -> list[dict[str, Any]]:
        return self._get("/drivers", {"session_key": session_key})

    def laps(self, session_key: int, driver_number: int | None = None) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"session_key": session_key}
        if driver_number is not None:
            params["driver_number"] = driver_number
        return self._get("/laps", params)

    def car_data(self, session_key: int, driver_number: int) -> list[dict[str, Any]]:
        return self._get("/car_data", {"session_key": session_key, "driver_number": driver_number})
