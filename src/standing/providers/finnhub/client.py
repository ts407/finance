"""Minimal Finnhub HTTP client with optional cassette replay and rate limiting."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class FinnhubError(RuntimeError):
    pass


class FinnhubClient:
    BASE = "https://finnhub.io/api/v1"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        cassette_dir: Path | None = None,
        allow_network: bool = True,
        min_interval_s: float = 1.05,  # ~57/min under free 60/min cap
        timeout_s: float = 30.0,
    ):
        self.api_key = api_key or os.environ.get("FINNHUB_API_KEY")
        self.cassette_dir = cassette_dir
        self.allow_network = allow_network
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self._last_call = 0.0

    def _cassette_path(self, kind: str, symbol: str) -> Path | None:
        if self.cassette_dir is None:
            return None
        return self.cassette_dir / f"{symbol.upper()}_{kind}.json"

    def _read_cassette(self, kind: str, symbol: str) -> dict[str, Any] | None:
        path = self._cassette_path(kind, symbol)
        if path is None or not path.exists():
            return None
        return json.loads(path.read_text())

    def _write_cassette(self, kind: str, symbol: str, payload: dict[str, Any]) -> None:
        path = self._cassette_path(kind, symbol)
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call = time.monotonic()

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            raise FinnhubError("FINNHUB_API_KEY not set and no cassette hit")
        if not self.allow_network:
            raise FinnhubError("Network disabled and cassette miss")
        query = dict(params)
        query["token"] = self.api_key
        url = f"{self.BASE}{path}?{urlencode(query)}"
        self._throttle()
        req = Request(url, headers={"User-Agent": "standing-research/0.1"})
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
            raise FinnhubError(f"HTTP {exc.code} for {path}: {detail}") from exc
        except URLError as exc:
            raise FinnhubError(f"Network error for {path}: {exc}") from exc
        payload = json.loads(body)
        if isinstance(payload, dict) and payload.get("error"):
            raise FinnhubError(str(payload["error"]))
        if not isinstance(payload, dict):
            raise FinnhubError(f"Unexpected payload type for {path}")
        return payload

    def company_basic_financials(self, symbol: str) -> dict[str, Any]:
        cached = self._read_cassette("metric", symbol)
        if cached is not None:
            return cached
        payload = self._get("/stock/metric", {"symbol": symbol.upper(), "metric": "all"})
        self._write_cassette("metric", symbol, payload)
        return payload

    def company_profile2(self, symbol: str) -> dict[str, Any]:
        cached = self._read_cassette("profile2", symbol)
        if cached is not None:
            return cached
        payload = self._get("/stock/profile2", {"symbol": symbol.upper()})
        self._write_cassette("profile2", symbol, payload)
        return payload
