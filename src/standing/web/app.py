from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from standing.config import load_scoring_config
from standing.pipeline.snapshot import StandingSnapshot, run_snapshot
from standing.providers import FixtureMarketProvider, FixtureSocialProvider

STATIC_DIR = Path(__file__).resolve().parent / "static"


class StandingMeta(BaseModel):
    as_of: str
    universe_id: str
    methodology_version: str
    score_kind: str
    placeholder: bool
    n_names: int
    low_confidence_sectors: list[str]
    sector_counts: dict[str, int]
    market_provider: str
    social_provider: str


class StandingRow(BaseModel):
    ticker: str
    sector: str
    value: float
    quality: float
    momentum: float
    momentum_global: float
    composite_standing: float
    s_obs: float
    s_used: float
    n: float
    confidence_c: float
    neg_share: float
    attention_tilt: float
    final_standing: float
    sector_low_confidence: bool
    social_badge: str


class SnapshotResponse(BaseModel):
    meta: StandingMeta
    standings: list[StandingRow]
    heat: list[StandingRow]


class HealthResponse(BaseModel):
    status: str = "ok"
    score_kind: str
    methodology_version: str
    placeholder: bool


def _parse_as_of(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="as_of must be YYYY-MM-DD") from exc


@lru_cache(maxsize=32)
def _cached_snapshot(as_of_iso: str, history_days: int) -> dict[str, Any]:
    as_of = date.fromisoformat(as_of_iso)
    cfg = load_scoring_config()
    snap = run_snapshot(
        as_of=as_of,
        market=FixtureMarketProvider(),
        social=FixtureSocialProvider(history_days=history_days),
        cfg=cfg,
    )
    return _serialize(snap)


def _serialize(snap: StandingSnapshot) -> dict[str, Any]:
    records = snap.standings.to_dict(orient="records")
    heat = (
        snap.standings.sort_values("s_used", ascending=False)
        .to_dict(orient="records")
    )
    return {
        "meta": {
            "as_of": snap.as_of.isoformat(),
            "universe_id": snap.universe_id,
            "methodology_version": snap.methodology_version,
            "score_kind": snap.score_kind,
            "placeholder": snap.placeholder,
            "n_names": int(snap.meta.get("n_names", len(records))),
            "low_confidence_sectors": list(snap.meta.get("low_confidence_sectors") or []),
            "sector_counts": dict(snap.meta.get("sector_counts") or {}),
            "market_provider": snap.meta.get("market_provider", "unknown"),
            "social_provider": snap.meta.get("social_provider", "unknown"),
        },
        "standings": records,
        "heat": heat,
    }


def create_app() -> FastAPI:
    app = FastAPI(
        title="Standing",
        description=(
            "Editorial descriptive V/Q/M equity standing with bounded social attention tilt. "
            "Not investment advice."
        ),
        version="0.1.0",
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        cfg = load_scoring_config()
        return HealthResponse(
            score_kind=cfg.score_kind,
            methodology_version=cfg.methodology_version,
            placeholder=cfg.placeholder,
        )

    @app.get("/api/snapshot", response_model=SnapshotResponse)
    def snapshot(
        as_of: str | None = Query(default=None, description="YYYY-MM-DD"),
        history_days: int = Query(default=14, ge=7, le=60),
        sort: Literal["final", "heat", "value", "quality", "momentum"] = Query(default="final"),
        q: str | None = Query(default=None, description="Ticker or sector filter"),
        limit: int | None = Query(default=None, ge=1, le=500),
    ) -> dict[str, Any]:
        day = _parse_as_of(as_of)
        payload = _cached_snapshot(day.isoformat(), history_days)
        rows = list(payload["standings"])
        if q:
            needle = q.strip().lower()
            rows = [
                r
                for r in rows
                if needle in str(r["ticker"]).lower() or needle in str(r["sector"]).lower()
            ]
        key_map = {
            "final": "final_standing",
            "heat": "s_used",
            "value": "value",
            "quality": "quality",
            "momentum": "momentum",
        }
        key = key_map[sort]
        rows = sorted(rows, key=lambda r: float(r[key]), reverse=True)
        heat = sorted(rows, key=lambda r: float(r["s_used"]), reverse=True)
        if limit is not None:
            rows = rows[:limit]
            heat = heat[:limit]
        return {"meta": payload["meta"], "standings": rows, "heat": heat}

    @app.get("/api/ticker/{ticker}")
    def ticker_detail(
        ticker: str,
        as_of: str | None = Query(default=None),
        history_days: int = Query(default=14, ge=7, le=60),
    ) -> dict[str, Any]:
        day = _parse_as_of(as_of)
        payload = _cached_snapshot(day.isoformat(), history_days)
        match = next(
            (r for r in payload["standings"] if str(r["ticker"]).upper() == ticker.upper()),
            None,
        )
        if match is None:
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not in universe")
        return {"meta": payload["meta"], "row": match}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
