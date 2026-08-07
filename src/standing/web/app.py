from __future__ import annotations

import csv
import io
import math
import os
import time
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from standing.config import load_scoring_config
from standing.envfile import load_env
from standing.logging_config import configure_logging, get_logger
from standing.pipeline.snapshot import StandingSnapshot, run_snapshot
from standing.providers import (
    MARKET_MODES,
    SOCIAL_MODES,
    build_market_provider,
    build_social_provider,
)

load_env()

STATIC_DIR = Path(__file__).resolve().parent / "static"

log = get_logger("web")

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
    "size_bucket",
    "value",
    "quality",
    "momentum",
    "momentum_global",
    "composite_standing",
    "attention_tilt",
    "final_standing",
    "value_coverage",
    "value_pe_rung",
    "value_ev_rung",
    "value_metric_set",
    "s_obs",
    "s_used",
    "n",
    "confidence_c",
    "neg_share",
    "social_badge",
    "sector_low_confidence",
]

CLIENT_LEVELS = {
    "debug": log.debug,
    "info": log.info,
    "warn": log.warning,
    "warning": log.warning,
    "error": log.error,
}


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
    served_from: str | None = None
    social_is_fixture: bool | None = None
    market_is_fixture: bool | None = None
    provider_staleness_utc: dict[str, str] | None = None
    created_at_utc: str | None = None
    universe_as_of: str | None = None
    tilt_max: float | None = None
    attention_mode: str | None = None
    peer_frame: str | None = None


class StandingRow(BaseModel):
    ticker: str
    sector: str
    value: float | None = None
    quality: float | None = None
    momentum: float | None = None
    momentum_global: float | None = None
    composite_standing: float | None = None
    s_obs: float
    s_used: float
    n: float
    confidence_c: float
    neg_share: float
    attention_tilt: float
    final_standing: float | None = None
    sector_low_confidence: bool
    social_badge: str
    size_bucket: str | None = None
    value_coverage: float | None = None
    value_pe_rung: str | None = None
    value_ev_rung: str | None = None
    value_metric_set: str | None = None


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


class ClientLogEntry(BaseModel):
    level: Literal["debug", "info", "warn", "warning", "error"] = "info"
    message: str = Field(min_length=1, max_length=2000)
    context: dict[str, Any] | None = None
    ts: str | None = None
    page: str | None = Field(default=None, max_length=200)


class ClientLogBatch(BaseModel):
    entries: list[ClientLogEntry] = Field(default_factory=list, max_length=50)


def _parse_as_of(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="as_of must be YYYY-MM-DD") from exc


def _prefer_store_default() -> bool:
    """Try immutable day log first (cold-start). Override with STANDING_PREFER_STORE=0."""
    raw = os.environ.get("STANDING_PREFER_STORE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _store_only() -> bool:
    raw = os.environ.get("STANDING_SERVE_STORE_ONLY", "0").strip().lower()
    return raw in ("1", "true", "yes", "on")


@lru_cache(maxsize=64)
def _cached_snapshot(
    as_of_iso: str, history_days: int, social_mode: str, market_mode: str, prefer_store: bool
) -> dict[str, Any]:
    log.info(
        "Snapshot cache miss as_of=%s history_days=%s market=%s social=%s prefer_store=%s",
        as_of_iso,
        history_days,
        market_mode,
        social_mode,
        prefer_store,
    )
    as_of = date.fromisoformat(as_of_iso)
    # Prefer immutable day log when present (cold-start / serve-from-snapshot).
    if prefer_store:
        try:
            from standing.pipeline.store import load_immutable

            loaded = load_immutable(as_of)
            snap = loaded.to_standing_snapshot()
            inner = loaded.meta.get("meta") or {}
            payload = _serialize(snap)
            payload["meta"] = {
                **payload["meta"],
                "served_from": "store",
                "created_at_utc": loaded.meta.get("created_at_utc"),
                "market_mode": inner.get("market_mode") or market_mode,
                "social_mode": inner.get("social_mode") or social_mode,
                "social_is_fixture": inner.get("social_is_fixture"),
                "market_is_fixture": inner.get("market_is_fixture"),
                "provider_staleness_utc": inner.get("provider_staleness_utc"),
                "universe_as_of": inner.get("universe_as_of"),
                "tilt_max": inner.get("tilt_max"),
                "attention_mode": inner.get("attention_mode"),
                "peer_frame": inner.get("peer_frame"),
            }
            return payload
        except Exception:
            if _store_only():
                raise RuntimeError(f"No immutable snapshot for {as_of_iso}; run standing ingest")
            # Fall through to live compute.

    cfg = load_scoring_config()
    snap = run_snapshot(
        as_of=as_of,
        market=build_market_provider(market_mode),
        social=build_social_provider(social_mode, history_days=history_days),
        cfg=cfg,
        market_mode=market_mode,
        social_mode=social_mode,
    )
    payload = _serialize(snap)
    payload["meta"] = {
        **payload["meta"],
        "served_from": "live",
        "market_mode": market_mode,
        "social_mode": social_mode,
        "social_is_fixture": snap.meta.get("social_is_fixture"),
        "market_is_fixture": snap.meta.get("market_is_fixture"),
        "provider_staleness_utc": snap.meta.get("provider_staleness_utc"),
        "universe_as_of": snap.meta.get("universe_as_of"),
        "tilt_max": snap.meta.get("tilt_max"),
        "attention_mode": snap.meta.get("attention_mode"),
        "peer_frame": snap.meta.get("peer_frame"),
    }
    return payload


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


_OPTIONAL_STRING_FIELDS = frozenset({"value_pe_rung", "value_ev_rung", "value_metric_set", "size_bucket"})


def _json_safe(value: Any, *, key: str | None = None) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "nan" or (key in _OPTIONAL_STRING_FIELDS and lowered == ""):
            return None
    return value


def _json_safe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: _json_safe(val, key=key) for key, val in row.items()} for row in records]


def _serialize(snap: StandingSnapshot) -> dict[str, Any]:
    records = _json_safe_records(snap.standings.to_dict(orient="records"))
    heat = _json_safe_records(
        snap.standings.sort_values("s_used", ascending=False).to_dict(orient="records")
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

    def _sort_key(row: dict[str, Any], field: str) -> float:
        # Missing pillars (None after JSON-safe serialization) sort last.
        raw = row.get(field)
        if raw is None:
            return float("-inf")
        try:
            val = float(raw)
        except (TypeError, ValueError):
            return float("-inf")
        return float("-inf") if math.isnan(val) else val

    standings = sorted(filtered, key=lambda r: _sort_key(r, key), reverse=True)
    heat = sorted(filtered, key=lambda r: _sort_key(r, "s_used"), reverse=True)
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
            "Volume-only attention until sentiment is calibrated (tilt_max dampened)",
            "Loud attention ≠ good",
            "Single score process: Final = clip(Base + Tilt, 0, 100)",
            "Serve prefers immutable day snapshots (standing ingest)",
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
            f"Modes market={list(MARKET_MODES)} social={list(SOCIAL_MODES)}. "
            "Fixture social is labelled in the UI — do not treat as live signal."
        ),
    }


def _ingest_client_logs(entries: list[ClientLogEntry], *, client: str | None) -> int:
    for entry in entries:
        emit = CLIENT_LEVELS.get(entry.level, log.info)
        ctx = entry.context or {}
        emit(
            "ui page=%s client=%s msg=%s ctx=%s ts=%s",
            entry.page or "unknown",
            client or "-",
            entry.message,
            ctx,
            entry.ts or "-",
        )
    return len(entries)


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(
        title="Standing",
        description=(
            "Editorial descriptive V/Q/M equity standing with bounded social attention tilt. "
            "Not investment advice."
        ),
        version="0.1.0",
    )

    @app.middleware("http")
    async def request_logging(request: Request, call_next):  # type: ignore[no-untyped-def]
        started = time.perf_counter()
        path = request.url.path
        # Keep static noise quieter at debug
        quiet = path.startswith("/static/")
        if not quiet:
            log.info(
                "request start method=%s path=%s query=%s",
                request.method,
                path,
                str(request.url.query) or "-",
            )
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (time.perf_counter() - started) * 1000
            log.exception(
                "request failed method=%s path=%s elapsed_ms=%.1f",
                request.method,
                path,
                elapsed_ms,
            )
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        level = log.debug if quiet else log.info
        level(
            "request done method=%s path=%s status=%s elapsed_ms=%.1f",
            request.method,
            path,
            response.status_code,
            elapsed_ms,
        )
        return response

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
        log.debug("Serving methodology payload")
        return _methodology_payload()

    def _load_payload(
        *,
        as_of: str | None,
        history_days: int,
        social: str | None,
        market: str | None,
        prefer_store: bool | None,
    ) -> tuple[date, str, str, dict[str, Any]]:
        day = _parse_as_of(as_of)
        social_mode = _resolve_mode(social, SOCIAL_MODES, _default_social_mode())
        market_mode = _resolve_mode(market, MARKET_MODES, _default_market_mode())
        use_store = _prefer_store_default() if prefer_store is None else prefer_store
        try:
            payload = _cached_snapshot(
                day.isoformat(), history_days, social_mode, market_mode, use_store
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return day, social_mode, market_mode, payload

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
        prefer_store: bool | None = Query(
            default=None,
            description="Prefer immutable day log (default from STANDING_PREFER_STORE)",
        ),
    ) -> dict[str, Any]:
        _day, social_mode, market_mode, payload = _load_payload(
            as_of=as_of,
            history_days=history_days,
            social=social,
            market=market,
            prefer_store=prefer_store,
        )
        payload["meta"]["social_mode"] = social_mode
        payload["meta"]["market_mode"] = market_mode
        standings, heat, key = _apply_filters(
            list(payload["standings"]),
            q=q,
            sector=sector,
            preset=preset,
            sort=sort,
        )
        if limit is not None:
            standings = standings[:limit]
            heat = heat[:limit]
        log.info(
            "snapshot response as_of=%s preset=%s sort_key=%s sector=%s q=%s n=%s",
            _day.isoformat(),
            preset,
            key,
            sector or "-",
            q or "-",
            len(standings),
        )
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
        prefer_store: bool | None = Query(default=None),
    ) -> StreamingResponse:
        day, social_mode, market_mode, payload = _load_payload(
            as_of=as_of,
            history_days=history_days,
            social=social,
            market=market,
            prefer_store=prefer_store,
        )
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
        log.info(
            "csv export as_of=%s preset=%s rows=%s filename=%s",
            day.isoformat(),
            preset,
            len(standings),
            filename,
        )
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
        prefer_store: bool | None = Query(default=None),
    ) -> dict[str, Any]:
        _day, social_mode, market_mode, payload = _load_payload(
            as_of=as_of,
            history_days=history_days,
            social=social,
            market=market,
            prefer_store=prefer_store,
        )
        match = next(
            (r for r in payload["standings"] if str(r["ticker"]).upper() == ticker.upper()),
            None,
        )
        if match is None:
            log.warning("ticker not found ticker=%s as_of=%s", ticker.upper(), _day.isoformat())
            raise HTTPException(status_code=404, detail=f"Ticker {ticker} not in universe")
        log.info("ticker detail ticker=%s as_of=%s", match["ticker"], _day.isoformat())
        return {
            "meta": {**payload["meta"], "social_mode": social_mode, "market_mode": market_mode},
            "row": match,
        }

    @app.post("/api/client-logs")
    def client_logs(batch: ClientLogBatch, request: Request) -> JSONResponse:
        client = request.client.host if request.client else None
        accepted = _ingest_client_logs(batch.entries, client=client)
        return JSONResponse({"accepted": accepted})

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/methodology")
    def methodology_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "methodology.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    log.info("Standing web app created")
    return app


app = create_app()
