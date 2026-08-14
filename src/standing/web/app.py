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
    "last_price",
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
    as_of_fallback: bool | None = None
    requested_as_of: str | None = None
    portfolio_sync_n: int | None = None
    portfolio_db: str | None = None
    portfolio_db_ok: bool | None = None
    portfolio_db_error: str | None = None


class StandingRow(BaseModel):
    ticker: str
    sector: str
    last_price: float | None = None
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
    portfolio: dict[str, Any] | None = None


class SnapshotResponse(BaseModel):
    meta: StandingMeta
    standings: list[StandingRow]
    heat: list[StandingRow]


class HealthResponse(BaseModel):
    status: str = "ok"
    score_kind: str
    methodology_version: str
    placeholder: bool
    root: str | None = None
    data_root: str | None = None
    diary_dir: str | None = None
    portfolio_db: str | None = None
    portfolio_db_ok: bool | None = None
    portfolio_db_error: str | None = None
    open_positions: int | None = None
    snapshot_root: str | None = None
    latest_snapshot_as_of: str | None = None
    snapshot_days: int | None = None
    default_market: str | None = None
    default_social: str | None = None
    prefer_store: bool | None = None


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


class DiaryCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    comment: str = Field(min_length=1, max_length=8000)
    kind: Literal["observation", "note", "thesis_update"] = "observation"
    as_of: str | None = None
    history_days: int = Field(default=14, ge=7, le=60)
    social: str | None = None
    market: str | None = None
    prefer_store: bool | None = None


class PositionCreate(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    shares: float = Field(gt=0)
    avg_cost: float = Field(ge=0)
    buy_reason: str = Field(min_length=1, max_length=4000)
    thesis: str = Field(min_length=1, max_length=8000)
    comment: str | None = Field(default=None, max_length=8000)
    opened_at: str | None = None
    as_of: str | None = None
    history_days: int = Field(default=14, ge=7, le=60)
    social: str | None = None
    market: str | None = None
    prefer_store: bool | None = None


class PositionNotesUpdate(BaseModel):
    buy_reason: str | None = Field(default=None, max_length=4000)
    thesis: str | None = Field(default=None, max_length=8000)
    comment: str | None = Field(default=None, max_length=8000)
    as_of: str | None = None
    history_days: int = Field(default=14, ge=7, le=60)
    social: str | None = None
    market: str | None = None
    prefer_store: bool | None = None


class PositionClose(BaseModel):
    close_price: float | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=8000)
    as_of: str | None = None
    history_days: int = Field(default=14, ge=7, le=60)
    social: str | None = None
    market: str | None = None
    prefer_store: bool | None = None


class TradeBuy(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    price: float = Field(gt=0)
    size: float = Field(gt=0)
    thesis: str = Field(min_length=1, max_length=8000)
    mechanism: str = Field(min_length=1, max_length=4000)
    falsifier: str = Field(min_length=1)
    target: float = Field(gt=0)
    stop: float = Field(gt=0)
    horizon: str = "90d"
    conviction: int = Field(default=3, ge=1, le=5)
    buy_reason: str | None = Field(default=None, max_length=4000)
    as_of: str | None = None
    history_days: int = Field(default=14, ge=7, le=60)
    social: str | None = None
    market: str | None = None
    prefer_store: bool | None = None


class TradeSell(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    price: float = Field(gt=0)
    reason: Literal["target", "stop", "thesis_broken", "rebalance", "manual"]
    note: str = Field(min_length=1, max_length=8000)
    as_of: str | None = None
    history_days: int = Field(default=14, ge=7, le=60)
    social: str | None = None
    market: str | None = None
    prefer_store: bool | None = None


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


def _portfolio_repo():
    """Open portfolio DB if present/usable; return None on failure."""
    try:
        from standing.portfolio.cli_support import open_repository

        return open_repository(os.environ.get("STANDING_PORTFOLIO_DB") or None)
    except Exception as exc:
        log.warning("portfolio DB unavailable: %s", exc)
        return None


def _book_overlay_for(ticker: str) -> dict[str, Any] | None:
    """SQLite book overlay (entry / target / stop / size) when the ticker is held."""
    repo = _portfolio_repo()
    if repo is None:
        return None
    try:
        from standing.portfolio.overlay import position_overlay

        return position_overlay(repo, ticker)
    except Exception as exc:
        log.warning("portfolio overlay unavailable ticker=%s: %s", ticker, exc)
        return None
    finally:
        repo.conn.close()


def _portfolio_status() -> dict[str, Any]:
    from standing.config import default_desk_dir, default_portfolio_db, resolve_data_root

    path = default_portfolio_db()
    out: dict[str, Any] = {
        "data_root": str(resolve_data_root()),
        "diary_dir": str(default_desk_dir()),
        "portfolio_db": str(path),
        "portfolio_db_ok": False,
        "portfolio_db_error": None,
        "open_positions": None,
    }
    repo = _portfolio_repo()
    if repo is None:
        out["portfolio_db_error"] = "open/migrate failed — check STANDING_ROOT / write perms"
        return out
    try:
        out["portfolio_db_ok"] = True
        out["open_positions"] = len(repo.list_open_positions())
        out["portfolio_db"] = str(Path(repo.conn.execute("PRAGMA database_list").fetchone()["file"]))
    except Exception as exc:
        out["portfolio_db_error"] = str(exc)
    finally:
        repo.conn.close()
    return out


def _sync_payload_to_portfolio(payload: dict[str, Any]) -> tuple[int | None, str | None]:
    """Best-effort upsert of served standings into scanner_snapshots."""
    repo = _portfolio_repo()
    if repo is None:
        return None, "portfolio DB unavailable"
    try:
        from standing.portfolio.sync import sync_standing_rows

        meta = payload.get("meta") or {}
        n = sync_standing_rows(
            repo,
            as_of=date.fromisoformat(str(meta["as_of"])),
            universe_version=str(meta.get("universe_id") or "desk"),
            rows=list(payload.get("standings") or []),
            provider_state={
                "market_provider": meta.get("market_provider"),
                "social_provider": meta.get("social_provider"),
                "market_mode": meta.get("market_mode"),
                "social_mode": meta.get("social_mode"),
                "served_from": meta.get("served_from"),
            },
        )
        return n, None
    except Exception as exc:
        log.warning("portfolio sync failed: %s", exc)
        return None, str(exc)
    finally:
        repo.conn.close()


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
    def health() -> dict[str, Any]:
        from standing.config import ROOT
        from standing.pipeline.store import DEFAULT_SNAPSHOT_ROOT, list_snapshot_days

        cfg = load_scoring_config()
        days = list_snapshot_days()
        port = _portfolio_status()
        return {
            "status": "ok",
            "score_kind": cfg.score_kind,
            "methodology_version": cfg.methodology_version,
            "placeholder": cfg.placeholder,
            "root": str(ROOT),
            "data_root": port["data_root"],
            "diary_dir": port["diary_dir"],
            "portfolio_db": port["portfolio_db"],
            "portfolio_db_ok": port["portfolio_db_ok"],
            "portfolio_db_error": port["portfolio_db_error"],
            "open_positions": port["open_positions"],
            "snapshot_root": str(DEFAULT_SNAPSHOT_ROOT),
            "latest_snapshot_as_of": days[-1].isoformat() if days else None,
            "snapshot_days": len(days),
            "default_market": _default_market_mode(),
            "default_social": _default_social_mode(),
            "prefer_store": _prefer_store_default(),
        }

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
        from standing.pipeline.store import list_snapshot_days

        social_mode = _resolve_mode(social, SOCIAL_MODES, _default_social_mode())
        market_mode = _resolve_mode(market, MARKET_MODES, _default_market_mode())
        use_store = _prefer_store_default() if prefer_store is None else prefer_store

        requested = as_of
        fallback = False
        day = _parse_as_of(as_of) if as_of else date.today()

        if use_store:
            days = list_snapshot_days()
            if days and day not in days:
                alt = days[-1]
                log.warning(
                    "No store snapshot for %s — using latest ingested day %s "
                    "(homelab cold-start / as_of mismatch)",
                    day.isoformat(),
                    alt.isoformat(),
                )
                day = alt
                fallback = True
            elif not as_of and days:
                day = days[-1]
                fallback = True
                log.info("as_of omitted — using latest store day %s", day.isoformat())

        try:
            payload = _cached_snapshot(
                day.isoformat(), history_days, social_mode, market_mode, use_store
            )
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        payload["meta"]["as_of_fallback"] = fallback
        payload["meta"]["requested_as_of"] = requested
        return day, social_mode, market_mode, payload

    def _row_and_snapshot(
        *,
        ticker: str,
        as_of: str | None,
        history_days: int,
        social: str | None,
        market: str | None,
        prefer_store: bool | None,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        from standing.desk.ledger import capture_snapshot

        _day, social_mode, market_mode, payload = _load_payload(
            as_of=as_of,
            history_days=history_days,
            social=social,
            market=market,
            prefer_store=prefer_store,
        )
        meta = {**payload["meta"], "social_mode": social_mode, "market_mode": market_mode}
        match = next(
            (r for r in payload["standings"] if str(r["ticker"]).upper() == ticker.strip().upper()),
            None,
        )
        snap = capture_snapshot(match, meta=meta)
        return meta, match or {}, snap

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

        sync_n, sync_err = _sync_payload_to_portfolio(payload)
        port = _portfolio_status()
        payload["meta"]["portfolio_sync_n"] = sync_n
        payload["meta"]["portfolio_db"] = port.get("portfolio_db")
        payload["meta"]["portfolio_db_ok"] = port.get("portfolio_db_ok")
        payload["meta"]["portfolio_db_error"] = sync_err or port.get("portfolio_db_error")

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
        repo = _portfolio_repo()
        try:
            from standing.portfolio.overlay import enrich_rows

            standings = enrich_rows(standings, repo)
            heat = enrich_rows(heat, repo)
        finally:
            if repo is not None:
                repo.conn.close()
        log.info(
            "snapshot response as_of=%s preset=%s sort_key=%s sector=%s q=%s n=%s portfolio_ok=%s",
            _day.isoformat(),
            preset,
            key,
            sector or "-",
            q or "-",
            len(standings),
            port.get("portfolio_db_ok"),
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
        repo = _portfolio_repo()
        try:
            from standing.portfolio.overlay import enrich_rows, position_detail

            enriched = enrich_rows([match], repo)[0]
            detail = position_detail(repo, ticker) if repo is not None else None
        finally:
            if repo is not None:
                repo.conn.close()
        log.info("ticker detail ticker=%s as_of=%s", match["ticker"], _day.isoformat())
        from standing.desk.ledger import ticker_dossier

        dossier = ticker_dossier(
            match["ticker"],
            current_row=match,
            current_meta={**payload["meta"], "social_mode": social_mode, "market_mode": market_mode},
        )
        return {
            "meta": {**payload["meta"], "social_mode": social_mode, "market_mode": market_mode},
            "row": enriched,
            "held": dossier["held"],
            "position": dossier["position"],
            "diary": dossier["diary"][:8],
            "book": detail,
        }

    @app.get("/api/holdings")
    def holdings(
        as_of: str | None = Query(default=None),
        history_days: int = Query(default=14, ge=7, le=60),
        social: str | None = Query(default=None),
        market: str | None = Query(default=None),
        prefer_store: bool | None = Query(default=None),
        include_closed: bool = Query(default=False),
    ) -> dict[str, Any]:
        from standing.desk.ledger import portfolio_view

        _day, social_mode, market_mode, payload = _load_payload(
            as_of=as_of,
            history_days=history_days,
            social=social,
            market=market,
            prefer_store=prefer_store,
        )
        meta = {**payload["meta"], "social_mode": social_mode, "market_mode": market_mode}
        by_ticker = {str(r["ticker"]).upper(): r for r in payload["standings"]}
        view = portfolio_view(
            current_by_ticker=by_ticker,
            current_meta=meta,
            include_closed=include_closed,
        )
        return {"meta": meta, **view}

    @app.get("/api/holdings/{ticker}")
    def holdings_ticker(
        ticker: str,
        as_of: str | None = Query(default=None),
        history_days: int = Query(default=14, ge=7, le=60),
        social: str | None = Query(default=None),
        market: str | None = Query(default=None),
        prefer_store: bool | None = Query(default=None),
    ) -> dict[str, Any]:
        from standing.desk.ledger import ticker_dossier

        meta, match, _snap = _row_and_snapshot(
            ticker=ticker,
            as_of=as_of,
            history_days=history_days,
            social=social,
            market=market,
            prefer_store=prefer_store,
        )
        dossier = ticker_dossier(ticker, current_row=match or None, current_meta=meta)
        return {"meta": meta, **dossier}

    @app.post("/api/holdings")
    def holdings_open(body: PositionCreate) -> dict[str, Any]:
        from standing.desk.ledger import open_or_add_position

        _meta, _match, snap = _row_and_snapshot(
            ticker=body.ticker,
            as_of=body.as_of,
            history_days=body.history_days,
            social=body.social,
            market=body.market,
            prefer_store=body.prefer_store,
        )
        try:
            result = open_or_add_position(
                ticker=body.ticker,
                shares=body.shares,
                avg_cost=body.avg_cost,
                buy_reason=body.buy_reason,
                thesis=body.thesis,
                snapshot=snap,
                opened_at=body.opened_at,
                comment=body.comment,
                book=_book_overlay_for(body.ticker),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        log.info(
            "holdings open ticker=%s shares=%s avg_cost=%s",
            body.ticker.upper(),
            body.shares,
            body.avg_cost,
        )
        return result

    @app.patch("/api/holdings/{position_id}")
    def holdings_notes(position_id: str, body: PositionNotesUpdate) -> dict[str, Any]:
        from standing.desk.ledger import get_position, update_position_notes

        pos = get_position(position_id)
        if pos is None:
            raise HTTPException(status_code=404, detail="Position not found")
        _meta, _match, snap = _row_and_snapshot(
            ticker=str(pos["ticker"]),
            as_of=body.as_of,
            history_days=body.history_days,
            social=body.social,
            market=body.market,
            prefer_store=body.prefer_store,
        )
        try:
            result = update_position_notes(
                position_id,
                buy_reason=body.buy_reason,
                thesis=body.thesis,
                snapshot=snap,
                comment=body.comment,
                book=_book_overlay_for(str(pos["ticker"])),
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return result

    @app.post("/api/holdings/{position_id}/close")
    def holdings_close(position_id: str, body: PositionClose) -> dict[str, Any]:
        from standing.desk.ledger import close_position, get_position

        pos = get_position(position_id)
        if pos is None:
            raise HTTPException(status_code=404, detail="Position not found")
        _meta, match, snap = _row_and_snapshot(
            ticker=str(pos["ticker"]),
            as_of=body.as_of,
            history_days=body.history_days,
            social=body.social,
            market=body.market,
            prefer_store=body.prefer_store,
        )
        close_px = body.close_price
        if close_px is None:
            close_px = match.get("last_price")
        try:
            result = close_position(
                position_id,
                close_price=close_px,
                snapshot=snap,
                comment=body.comment,
                book=_book_overlay_for(str(pos["ticker"])),
            )
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        log.info("holdings close id=%s ticker=%s", position_id, pos["ticker"])
        return result

    def _desk_snapshot_seed(match: dict[str, Any], meta: dict[str, Any]):
        from standing.web.portfolio_api import SnapshotSeed

        if not match or match.get("final_standing") is None:
            return None
        return SnapshotSeed(
            as_of=str(meta.get("as_of") or date.today().isoformat()),
            universe_version=str(meta.get("universe_id") or "desk"),
            score=float(match["final_standing"]),
            pillar_fundamentals=None if match.get("value") is None else float(match["value"]),
            pillar_momentum=None if match.get("momentum") is None else float(match["momentum"]),
            pillar_attention=None if match.get("s_used") is None else float(match["s_used"]),
            coverage_flags={
                "value_coverage": match.get("value_coverage"),
                "value_ev_rung": match.get("value_ev_rung"),
                "sector_low_confidence": match.get("sector_low_confidence"),
            },
            provider_state={
                "market_mode": meta.get("market_mode"),
                "social_mode": meta.get("social_mode"),
                "market_provider": meta.get("market_provider"),
                "social_provider": meta.get("social_provider"),
            },
        )

    @app.post("/api/trade/buy")
    def trade_buy(body: TradeBuy) -> dict[str, Any]:
        from standing.desk.ledger import open_or_add_position
        from standing.portfolio.cli_support import parse_horizon
        from standing.web.portfolio_api import (
            _ensure_snapshot,
            _http_from_portfolio,
            _repo,
            _seed_mark,
        )

        meta, match, snap = _row_and_snapshot(
            ticker=body.ticker,
            as_of=body.as_of,
            history_days=body.history_days,
            social=body.social,
            market=body.market,
            prefer_store=body.prefer_store,
        )
        seed = _desk_snapshot_seed(match, meta)
        if seed is None:
            from standing.web.portfolio_api import SnapshotSeed

            seed = SnapshotSeed(
                as_of=str(meta.get("as_of") or date.today().isoformat()),
                universe_version=str(meta.get("universe_id") or "desk"),
                score=0.0,
            )
        repo = _repo()
        try:
            try:
                horizon_days = parse_horizon(body.horizon)
                snapshot_id = _ensure_snapshot(repo, body.ticker, seed)
                _seed_mark(repo, body.ticker, body.price)
                position, thesis, entry = repo.open_position(
                    ticker=body.ticker,
                    entry_price=body.price,
                    size=body.size,
                    claim=body.thesis,
                    mechanism=body.mechanism,
                    falsifier=body.falsifier,
                    target_price=body.target,
                    stop_price=body.stop,
                    horizon_days=horizon_days,
                    conviction=body.conviction,
                    entry_snapshot_id=snapshot_id,
                )
            except Exception as exc:
                raise _http_from_portfolio(exc) from exc
        finally:
            repo.conn.close()

        reason = (body.buy_reason or body.thesis).strip()
        holdings = None
        holdings_error = None
        try:
            holdings = open_or_add_position(
                ticker=body.ticker,
                shares=body.size,
                avg_cost=body.price,
                buy_reason=reason,
                thesis=body.thesis,
                snapshot=snap,
                comment=f"Kauf {body.size:g} {body.ticker.upper()} @ {body.price:g}. {reason}",
                book=_book_overlay_for(body.ticker),
            )
        except Exception as exc:
            holdings_error = str(exc)
            log.warning("trade buy desk ledger failed ticker=%s: %s", body.ticker.upper(), exc)
        log.info("trade buy ticker=%s position_id=%s", position.ticker, position.position_id)
        return {
            "ticker": position.ticker,
            "position_id": position.position_id,
            "entry_price": position.entry_price,
            "size": position.size,
            "thesis_id": thesis.thesis_id,
            "journal_entry_id": entry.entry_id,
            "holdings": holdings,
            "diary_entry": None if holdings is None else holdings.get("diary_entry"),
            "holdings_error": holdings_error,
        }

    @app.post("/api/trade/sell")
    def trade_sell(body: TradeSell) -> dict[str, Any]:
        from standing.desk.ledger import close_position, get_open_position
        from standing.portfolio.models import CloseReason
        from standing.web.portfolio_api import _http_from_portfolio, _repo, _seed_mark

        meta, match, snap = _row_and_snapshot(
            ticker=body.ticker,
            as_of=body.as_of,
            history_days=body.history_days,
            social=body.social,
            market=body.market,
            prefer_store=body.prefer_store,
        )
        repo = _repo()
        try:
            try:
                snap_row = repo.get_latest_snapshot(body.ticker)
                position, entry = repo.close_position(
                    ticker=body.ticker,
                    close_price=body.price,
                    reason=CloseReason(body.reason),
                    exit_note=body.note,
                    linked_snapshot_id=snap_row.snapshot_id if snap_row else None,
                )
                as_of = date.fromisoformat(body.as_of) if body.as_of else date.today()
                _seed_mark(repo, body.ticker, body.price, as_of=as_of)
            except Exception as exc:
                raise _http_from_portfolio(exc) from exc
        finally:
            repo.conn.close()

        holdings = None
        holdings_error = None
        held = get_open_position(body.ticker)
        if held is not None:
            try:
                holdings = close_position(
                    held["id"],
                    close_price=body.price,
                    snapshot=snap,
                    comment=body.note,
                    book=_book_overlay_for(body.ticker),
                )
            except Exception as exc:
                holdings_error = str(exc)
                log.warning("trade sell desk ledger failed ticker=%s: %s", body.ticker.upper(), exc)
        pnl = (position.close_price / position.entry_price - 1.0) * 100.0
        log.info("trade sell ticker=%s reason=%s", position.ticker, body.reason)
        return {
            "ticker": position.ticker,
            "position_id": position.position_id,
            "close_price": position.close_price,
            "close_reason": position.close_reason.value if position.close_reason else None,
            "pnl_pct": pnl,
            "exit_note_id": entry.entry_id,
            "holdings": holdings,
            "diary_entry": None if holdings is None else holdings.get("diary_entry"),
            "holdings_error": holdings_error,
        }

    @app.get("/api/diary")
    def diary_list(
        ticker: str | None = Query(default=None),
        q: str | None = Query(default=None),
        since: str | None = Query(default=None),
        until: str | None = Query(default=None),
        kind: str | None = Query(default=None),
    ) -> dict[str, Any]:
        from standing.desk.ledger import read_diary, summarize_diary_for_vergleich, summarize_entries

        entries = read_diary(ticker=ticker, q=q, since=since, until=until, kind=kind)
        return {
            "entries": entries,
            "summary": summarize_entries(entries),
            "corpus": summarize_diary_for_vergleich(),
        }

    @app.post("/api/diary")
    def diary_create(body: DiaryCreate) -> dict[str, Any]:
        from standing.desk.ledger import append_diary, get_open_position

        _meta, _match, snap = _row_and_snapshot(
            ticker=body.ticker,
            as_of=body.as_of,
            history_days=body.history_days,
            social=body.social,
            market=body.market,
            prefer_store=body.prefer_store,
        )
        held = get_open_position(body.ticker)
        try:
            entry = append_diary(
                ticker=body.ticker,
                comment=body.comment,
                snapshot=snap,
                kind=body.kind,
                position_id=held["id"] if held else None,
                desk_position=held,
                book=_book_overlay_for(body.ticker),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        log.info("diary append ticker=%s kind=%s", body.ticker.upper(), body.kind)
        return {"entry": entry}

    @app.get("/api/diary.csv")
    def diary_csv(
        ticker: str | None = Query(default=None),
        q: str | None = Query(default=None),
        since: str | None = Query(default=None),
        until: str | None = Query(default=None),
        kind: str | None = Query(default=None),
    ) -> StreamingResponse:
        from standing.desk.ledger import export_diary_csv

        text = export_diary_csv(ticker=ticker, q=q, since=since, until=until, kind=kind)
        return StreamingResponse(
            iter([text]),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="standing_diary.csv"'},
        )

    @app.get("/api/diary.json")
    def diary_json(
        ticker: str | None = Query(default=None),
        q: str | None = Query(default=None),
        since: str | None = Query(default=None),
        until: str | None = Query(default=None),
        kind: str | None = Query(default=None),
    ) -> JSONResponse:
        from standing.desk.ledger import read_diary

        return JSONResponse(
            {"entries": read_diary(ticker=ticker, q=q, since=since, until=until, kind=kind)}
        )

    from standing.web.portfolio_api import router as portfolio_router

    app.include_router(portfolio_router)

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

    @app.get("/portfolio")
    def portfolio_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "portfolio.html")

    @app.get("/diary")
    def diary_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "diary.html")

    @app.get("/trade")
    def trade_page() -> FileResponse:
        return FileResponse(STATIC_DIR / "trade.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    log.info("Standing web app created")
    return app


app = create_app()
