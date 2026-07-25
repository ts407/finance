"""SEC EDGAR helpers — ticker→CIK and point-in-time companyconcept pulls.

No API key. Requires a descriptive User-Agent (SEC fair-access policy).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from standing.providers.cache import DiskCache

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_CONCEPT_TMPL = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
)
SEC_DEI_CONCEPT_TMPL = (
    "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/dei/{tag}.json"
)

DEFAULT_UA = "StandingResearchBot/0.1 (tomerik_steinkopf@icloud.com; research demo)"


@dataclass(frozen=True)
class FactPoint:
    end: date
    filed: date
    val: float
    form: str
    fp: str | None
    frame: str | None


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


class EdgarClient:
    def __init__(
        self,
        *,
        cache: DiskCache | None = None,
        user_agent: str = DEFAULT_UA,
        min_interval_s: float = 0.12,  # ~8 req/s under SEC 10/s guidance
        timeout_s: float = 45.0,
        allow_network: bool = True,
    ):
        self.cache = cache
        self.user_agent = user_agent
        self.min_interval_s = min_interval_s
        self.timeout_s = timeout_s
        self.allow_network = allow_network
        self._last_call = 0.0
        self._ticker_to_cik: dict[str, str] | None = None

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < self.min_interval_s:
            time.sleep(self.min_interval_s - elapsed)
        self._last_call = time.monotonic()

    def _get_json(self, url: str, cache_ns: str, *cache_parts: Any) -> dict[str, Any] | None:
        if self.cache is not None:
            cached = self.cache.get_json(cache_ns, *cache_parts)
            if isinstance(cached, dict):
                return cached
        if not self.allow_network:
            return None
        self._throttle()
        req = Request(url, headers={"User-Agent": self.user_agent, "Accept": "application/json"})
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
            return None
        if self.cache is not None and isinstance(payload, dict):
            self.cache.set_json(cache_ns, *cache_parts, data=payload)
        return payload if isinstance(payload, dict) else None

    def ticker_to_cik(self) -> dict[str, str]:
        if self._ticker_to_cik is not None:
            return self._ticker_to_cik
        payload = self._get_json(SEC_TICKERS_URL, "edgar_tickers", "company_tickers")
        mapping: dict[str, str] = {}
        if payload:
            for row in payload.values():
                ticker = str(row.get("ticker") or "").upper().strip()
                cik_str = row.get("cik_str")
                if ticker and cik_str is not None:
                    mapping[ticker] = f"{int(cik_str):010d}"
        self._ticker_to_cik = mapping
        return mapping

    def cik_for(self, ticker: str) -> str | None:
        return self.ticker_to_cik().get(ticker.upper())

    def concept_points(
        self,
        cik: str,
        tag: str,
        *,
        taxonomy: str = "us-gaap",
        unit_keys: Iterable[str] = ("USD", "USD/shares", "shares"),
    ) -> list[FactPoint]:
        tmpl = SEC_DEI_CONCEPT_TMPL if taxonomy == "dei" else SEC_CONCEPT_TMPL
        url = tmpl.format(cik=cik, tag=tag)
        payload = self._get_json(url, "edgar_concept", cik, taxonomy, tag)
        if not payload:
            return []
        units = payload.get("units") or {}
        raw: list[dict[str, Any]] = []
        for key in unit_keys:
            if key in units and isinstance(units[key], list):
                raw.extend(units[key])
        if not raw:
            # take first unit list
            for vals in units.values():
                if isinstance(vals, list):
                    raw.extend(vals)
                    break
        out: list[FactPoint] = []
        for row in raw:
            end = _parse_day(row.get("end"))
            filed = _parse_day(row.get("filed"))
            if end is None or filed is None:
                continue
            try:
                val = float(row.get("val"))
            except (TypeError, ValueError):
                continue
            out.append(
                FactPoint(
                    end=end,
                    filed=filed,
                    val=val,
                    form=str(row.get("form") or ""),
                    fp=row.get("fp"),
                    frame=row.get("frame"),
                )
            )
        out.sort(key=lambda p: (p.filed, p.end))
        return out


def latest_as_of(
    points: list[FactPoint],
    as_of: date,
    *,
    forms: tuple[str, ...] | None = ("10-K", "10-Q"),
    prefer_frames: bool = True,
) -> FactPoint | None:
    """Latest point with filed <= as_of (and preferably a CY frame to avoid restatement noise)."""
    candidates = [p for p in points if p.filed <= as_of]
    if forms:
        filtered = [p for p in candidates if p.form in forms]
        if filtered:
            candidates = filtered
    if not candidates:
        return None
    if prefer_frames:
        framed = [p for p in candidates if p.frame]
        if framed:
            candidates = framed
    return candidates[-1]


def ttm_sum_quarters(points: list[FactPoint], as_of: date, *, n: int = 4) -> float | None:
    """Sum the last n quarterly framed values with filed <= as_of."""
    q = [
        p
        for p in points
        if p.filed <= as_of
        and p.form in ("10-Q", "10-K")
        and p.frame
        and ("Q" in (p.frame or "") or p.fp in ("Q1", "Q2", "Q3", "Q4"))
    ]
    # Prefer pure quarter frames (CY####Q#)
    quarters = [p for p in q if p.frame and "Q" in p.frame and not p.frame.endswith("Q4YTD")]
    if len(quarters) < n:
        # fallback: any framed points
        quarters = [p for p in q if p.frame]
    if len(quarters) < n:
        return None
    # unique by frame, keep latest filed per frame
    by_frame: dict[str, FactPoint] = {}
    for p in quarters:
        if p.frame:
            by_frame[p.frame] = p
    ordered = sorted(by_frame.values(), key=lambda p: p.end)
    if len(ordered) < n:
        return None
    return float(sum(p.val for p in ordered[-n:]))


def yoy_growth(points: list[FactPoint], as_of: date) -> float | None:
    """YoY growth from the two latest annual (FY / CY####) revenue-like points."""
    annual = [
        p
        for p in points
        if p.filed <= as_of
        and p.form == "10-K"
        and p.frame
        and "Q" not in p.frame
    ]
    if len(annual) < 2:
        # try FY fp without requiring frame
        annual = [p for p in points if p.filed <= as_of and p.fp == "FY"]
    if len(annual) < 2:
        return None
    # unique by end year
    by_end: dict[date, FactPoint] = {}
    for p in annual:
        by_end[p.end] = p
    ordered = sorted(by_end.values(), key=lambda p: p.end)
    if len(ordered) < 2:
        return None
    prev, cur = ordered[-2], ordered[-1]
    if prev.val == 0:
        return None
    return float(cur.val / prev.val - 1.0)
