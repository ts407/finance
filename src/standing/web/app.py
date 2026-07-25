from __future__ import annotations

import csv
import io
import os
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from standing.config import load_scoring_config
from standing.pipeline.snapshot import StandingSnapshot, run_snapshot
from standing.providers import (
    MARKET_MODES,
    SOCIAL_MODES,
    build_market_provider,
    build_social_provider,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"

PresetName = Literal[
    "balanced",
    "value_led",
    "quality_led",
    "momentum_led",
    "attention_confirmed",
]

ATTENTION_TILT_FLOOR = 1.0

CSV_COLUMNS = [
    "ticker",
    "sector",
    "value",
    "quality",
    "momentum",
    "momentum_global",
    "composite_standing",
    "attention_tilt",
    "final_standing",
    "s_obs",
    "s_used",
    "n",
    "confidence_c",
    "neg_share",
    "social_badge",
    "sector_low_confidence",
]


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
    market_mode: str | None = None
    social_mode: str | None = None


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


class MethodologyResponse(BaseModel):
    score_kind: str
    methodology_version: str
    placeholder: bool
    non_advice: str
    framing: list[str]
    formulas: dict[str, str]
    base: dict[str, Any]
    social_tilt: dict[str, Any]
    shrinkage: dict[str, Any]
    social_pipeline: dict[str, Any]
    universe: dict[str, Any]
    presets: list[str]
    source_posture: str


def _parse_as_of(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="as_of must be YYYY-MM-DD") from exc


@lru_cache(maxsize=64)
def _cached_snapshot(
    as_of_iso: str, history_days: int, social_mode: str, market_mode: str
) -> dict[str, Any]:
    as_of = date.fromisoformat(as_of_iso)
    cfg = load_scoring_config()
    snap = run_snapshot(
        as_of=as_of,
        market=build_market_provider(market_mode),
        social=build_social_provider(social_mode, history_days=history_days),
        cfg=cfg,
    )
    return _serialize(snap)


def _default_social_mode() -> str:
    mode = os.environ.get("STANDING_SOCIAL", "open").strip().lower()
    return mode if mode in SOCIAL_MODES else "open"


def _default_market_mode() -> str:
    mode = os.environ.get("STANDING_MARKET", "live").strip().lower()
    return mode if mode in MARKET_MODES else "live"


def _resolve_mode(value: str | None, allowed: tuple[str, ...], default: str) -> str:
    if value is None or value == "":
        return default
    key = value.strip().lower()
    if key not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown mode {value!r}; expected one of {list(allowed)}",
        )
    return key


def _serialize(snap: StandingSnapshot) -> dict[str, Any]:
    records = snap.standings.to_dict(orient="records")
    heat = snap.standings.sort_values("s_used", ascending=False).to_dict(orient="records")
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


def _apply_filters(
    rows: list[dict[str, Any]],
    *,
    q: str | None,
    sector: str | None,
    preset: PresetName,
    sort: Literal["final", "heat", "value", "quality", "momentum"],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    """Return (standings, heat, effective_sort_key)."""
    filtered = list(rows)
    if q:
        needle = q.strip().lower()
        filtered = [
            r
            for r in filtered
            if needle in str(r["ticker"]).lower() or needle in str(r["sector"]).lower()
        ]
    if sector:
        sector_l = sector.strip().lower()
        filtered = [r for r in filtered if str(r["sector"]).lower() == sector_l]

    effective_sort = sort
    if preset == "balanced":
        effective_sort = "final"
    elif preset == "value_led":
        effective_sort = "value"
    elif preset == "quality_led":
        effective_sort = "quality"
    elif preset == "momentum_led":
        effective_sort = "momentum"
    elif preset == "attention_confirmed":
        filtered = [
            r
            for r in filtered
            if str(r.get("social_badge")) == "ok"
            and abs(float(r.get("attention_tilt", 0.0))) >= ATTENTION_TILT_FLOOR
        ]
        effective_sort = "heat"

    key_map = {
        "final": "final_standing",
        "heat": "s_used",
        "value": "value",
        "quality": "quality",
        "momentum": "momentum",
    }
    key = key_map[effective_sort]
    standings = sorted(filtered, key=lambda r: float(r[key]), reverse=True)
    heat = sorted(filtered, key=lambda r: float(r["s_used"]), reverse=True)
    return standings, heat, key


def _methodology_payload() -> dict[str, Any]:
    cfg = load_scoring_config()
    return {
        "score_kind": cfg.score_kind,
        "methodology_version": cfg.methodology_version,
        "placeholder": cfg.placeholder,
        "non_advice": (
            "Not investment advice. Outputs are editorial descriptive peer context "
            "(Composite Standing and Attention Tilt), not buy/sell recommendations."
        ),
        "framing": [
            "score_kind = editorial_descriptive",
            "No Buyworthiness / Buy-Rank on the product surface",
            "Composite Standing = equal-weight sector-relative V/Q/M",
            "Attention Tilt is bounded (tanh) and secondary to the base",
            "Loud attention ≠ good",
            "Single score process: Final = clip(Base + Tilt, 0, 100)",
        ],
        "formulas": {
            "base": "Base = (V + Q + M) / 3",
            "shrinkage": "S_used = c · S_obs + (1 − c) · prior,  c = n / (n + k)",
            "tilt": "Tilt = tilt_max · tanh(β · (S_used − 50) / 50)",
            "final": "Final Standing = clip(Base + Tilt, 0, 100)",
            "hype_dampener": "d = 1 − 2 · max(0, neg_share − pivot); applied to positive tilt only",
        },
        "base": cfg.base,
        "social_tilt": cfg.social_tilt,
        "shrinkage": cfg.shrinkage,
        "social_pipeline": cfg.social_pipeline,
        "universe": cfg.universe,
        "presets": [
            "balanced",
            "value_led",
            "quality_led",
            "momentum_led",
            "attention_confirmed",
        ],
        "source_posture": (
            "Desk defaults: market=live (EDGAR fundamentals + Yahoo OHLCV; Finnhub if key) · "
            "social=open (Wikipedia + Bluesky). "
            f"Modes market={list(MARKET_MODES)} social={list(SOCIAL_MODES)}."
        ),
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

    @app.get("/api/methodology", response_model=MethodologyResponse)
    def methodology() -> dict[str, Any]:
        return _methodology_payload()

    @app.get("/api/snapshot", response_model=SnapshotResponse)
    def snapshot(
        as_of: str | None = Query(default=None, description="YYYY-MM-DD"),
        history_days: int = Query(default=14, ge=7, le=60),
        social: str | None = Query(default=None, description="fixture|wikipedia|bluesky|open|all"),
        market: str | None = Query(default=None, description="fixture|stooq|finnhub|live"),
        sort: Literal["final", "heat", "value", "quality", "momentum"] = Query(default="final"),
        preset: PresetName = Query(default="balanced"),
        sector: str | None = Query(default=None, description="Exact GICS-11 sector"),
        q: str | None = Query(default=None, description="Ticker or sector filter"),
        limit: int | None = Query(default=None, ge=1, le=500),
    ) -> dict[str, Any]:
        day = _parse_as_of(as_of)
        social_mode = _resolve_mode(social, SOCIAL_MODES, _default_social_mode())
        market_mode = _resolve_mode(market, MARKET_MODES, _default_market_mode())
        try:
            payload = _cached_snapshot(day.isoformat(), history_days, social_mode, market_mode)
        except Exception as exc:  # surface provider errors cleanly
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        payload = {
            **payload,
            "meta": {
                **payload["meta"],
                "social_mode": social_mode,
                "market_mode": market_mode,
            },
        }
        standings, heat, _key = _apply_filters(
            list(payload["standings"]),
            q=q,
            sector=sector,
            preset=preset,
            sort=sort,
        )
        if limit is not None:
            standings = standings[:limit]
            heat = heat[:limit]
        return {"meta": payload["meta"], "standings": standings, "heat": heat}

    @app.get("/api/snapshot.csv")
    def snapshot_csv(
        as_of: str | None = Query(default=None),
        history_days: int = Query(default=14, ge=7, le=60),
        social: str | None = Query(default=None),
        market: str | None = Query(default=None),
        sort: Literal["final", "heat", "value", "quality", "momentum"] = Query(default="final"),
        preset: PresetName = Query(default="balanced"),
        sector: str | None = Query(default=None),
        q: str | None = Query(default=None),
        limit: int | None = Query(default=None, ge=1, le=500),
    ) -> StreamingResponse:
        day = _parse_as_of(as_of)
        social_mode = _resolve_mode(social, SOCIAL_MODES, _default_social_mode())
        market_mode = _resolve_mode(market, MARKET_MODES, _default_market_mode())
        payload = _cached_snapshot(day.isoformat(), history_days, social_mode, market_mode)
        standings, _heat, _key = _apply_filters(
            list(payload["standings"]),
            q=q,
            sector=sector,
            preset=preset,
            sort=sort,
        )
        if limit is not None:
            standings = standings[:limit]

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in standings:
            writer.writerow({col: row.get(col) for col in CSV_COLUMNS})
        buf.seek(0)
        filename = f"standing_{day.isoformat()}_{preset}.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    @app.get("/api/ticker/{ticker}")
    def ticker_detail(
        ticker: str,
        as_of: str | None = Query(default=None),
        history_days: int = Query(default=14, ge=7, le=60),
        social: str | None = Query(default=None),
        market: str | None = Query(default=None),
    ) -> dict[str, Any]:
        day = _parse_as_of(as_of)
        social_mode = _resolve_mode(social, SOCIAL_MODES, _default_social_mode())
        market_mode = _resolve_mode(market, MARKET_MODES, _default_market_mode())
        payload = _cached_snapshot(day.isoformat(), history_days, social_mode, market_mode)
        match = next(
            (r for r in payload["standings"] if str(r["ticker"]).upper() == ticker.upper()),
            None,
        )
        if match is None:
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not in universe")
        return {"meta": {**payload["meta"], "social_mode": social_mode, "market_mode": market_mode}, "row": match}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/methodology")
    def methodology_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "methodology.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
