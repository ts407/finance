"""FastAPI portfolio / journal / recalibrate routes for the desk UI."""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from standing.logging_config import get_logger
from standing.portfolio.cli_support import open_repository, parse_horizon
from standing.portfolio.exceptions import (
    FalsifierTooShortError,
    OpenPositionExistsError,
    PortfolioError,
    PositionAlreadyClosedError,
    PositionNotFoundError,
    SnapshotNotFoundError,
)
from standing.portfolio.models import CloseReason
from standing.portfolio.overlay import enrich_rows, position_detail
from standing.portfolio.repository import PortfolioRepository

log = get_logger("web.portfolio")

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _repo() -> PortfolioRepository:
    try:
        return open_repository(os.environ.get("STANDING_PORTFOLIO_DB") or None)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Portfolio DB unavailable: {exc}") from exc


def _http_from_portfolio(exc: Exception) -> HTTPException:
    if isinstance(exc, FalsifierTooShortError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, (OpenPositionExistsError, PositionAlreadyClosedError)):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (PositionNotFoundError, SnapshotNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PortfolioError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))


class SnapshotSeed(BaseModel):
    """Optional standing-row seed so buy works without a prior ingest."""

    as_of: str | None = None
    universe_version: str = "desk"
    score: float
    pillar_fundamentals: float | None = None
    pillar_momentum: float | None = None
    pillar_attention: float | None = None
    coverage_flags: dict[str, Any] | None = None
    provider_state: dict[str, Any] | None = None


class BuyRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    price: float = Field(gt=0)
    size: float = Field(gt=0)
    thesis: str = Field(min_length=1)
    mechanism: str = Field(min_length=1)
    falsifier: str = Field(min_length=1)
    target: float = Field(gt=0)
    stop: float = Field(gt=0)
    horizon: str = "90d"
    conviction: int = Field(default=3, ge=1, le=5)
    reference_class: str | None = None
    snapshot: SnapshotSeed | None = None
    mark: float | None = Field(default=None, gt=0)


class SellRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    price: float = Field(gt=0)
    reason: Literal["target", "stop", "thesis_broken", "rebalance", "manual"]
    note: str = Field(min_length=1)
    mark_as_of: str | None = None


class JournalRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    note: str = Field(min_length=1)
    snapshot: SnapshotSeed | None = None


class WatchlistRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    thesis: str = Field(min_length=1)
    falsifier: str = Field(min_length=1)
    snapshot: SnapshotSeed | None = None


class MarkItem(BaseModel):
    ticker: str
    price: float = Field(gt=0)


class RecalibrateRequest(BaseModel):
    window: str = "90d"
    min_hold: int = Field(default=30, ge=1)
    as_of: str | None = None


def _ensure_snapshot(
    repo: PortfolioRepository,
    ticker: str,
    seed: SnapshotSeed | None,
) -> int:
    """Return a snapshot_id for ticker; upsert from seed if provided."""
    latest = repo.get_latest_snapshot(ticker)
    if latest is not None and seed is None:
        return latest.snapshot_id
    if seed is None:
        raise SnapshotNotFoundError(
            f"No scanner_snapshot for {ticker.upper()}. "
            "Open from the desk standing row or run standing ingest."
        )
    as_of = date.fromisoformat(seed.as_of) if seed.as_of else date.today()
    snap = repo.upsert_scanner_snapshot(
        as_of=as_of,
        ticker=ticker,
        universe_version=seed.universe_version,
        score=seed.score,
        pillar_fundamentals=seed.pillar_fundamentals,
        pillar_momentum=seed.pillar_momentum,
        pillar_attention=seed.pillar_attention,
        coverage_flags=seed.coverage_flags,
        provider_state=seed.provider_state,
    )
    return snap.snapshot_id


def _seed_mark(repo: PortfolioRepository, ticker: str, price: float, as_of: date | None = None) -> None:
    repo.upsert_daily_mark(as_of=as_of or date.today(), ticker=ticker, close_price=price)


@router.get("")
def list_portfolio(
    mark: list[str] | None = Query(
        default=None,
        description="Optional TICKER=PRICE marks (repeatable)",
    ),
) -> dict[str, Any]:
    repo = _repo()
    try:
        marks: dict[str, float] = {}
        for raw in mark or []:
            if "=" not in raw:
                raise HTTPException(status_code=400, detail=f"Invalid mark '{raw}'")
            t, p = raw.split("=", 1)
            marks[t.strip().upper()] = float(p)
        positions = repo.list_open_positions()
        rows = []
        for pos in positions:
            overlay_rows = enrich_rows([{"ticker": pos.ticker}], repo)
            port = overlay_rows[0].get("portfolio") or {}
            thesis = repo.get_thesis(pos.position_id)
            now_px = marks.get(pos.ticker)
            if now_px is None:
                now_px = repo.get_mark_on_or_before(pos.ticker, date.today())
            pnl = None
            dist_t = dist_s = None
            if now_px is not None:
                pnl = (now_px / pos.entry_price - 1.0) * 100.0
                if thesis:
                    dist_t = (thesis.target_price / now_px - 1.0) * 100.0
                    dist_s = (thesis.stop_price / now_px - 1.0) * 100.0
            rows.append(
                {
                    **port,
                    "ticker": pos.ticker,
                    "entry_price": pos.entry_price,
                    "size": pos.size,
                    "now_px": now_px,
                    "pnl_pct": pnl,
                    "dist_to_target_pct": dist_t,
                    "dist_to_stop_pct": dist_s,
                    "claim": thesis.claim if thesis else None,
                    "falsifier": thesis.falsifier if thesis else None,
                }
            )
        return {"positions": rows, "n": len(rows)}
    finally:
        repo.conn.close()


@router.get("/review")
def portfolio_review() -> dict[str, Any]:
    from standing.portfolio.attribution import review_closed

    repo = _repo()
    try:
        rows = review_closed(repo)
        return {
            "rows": [
                {
                    "ticker": r.ticker,
                    "position_id": r.position_id,
                    "hold_days": r.hold_days,
                    "realized_return": r.realized_return,
                    "benchmark_return": r.benchmark_return,
                    "decile_return": r.decile_return,
                    "excess_vs_benchmark": r.excess_vs_benchmark,
                    "excess_vs_decile": r.excess_vs_decile,
                    "thesis_outcome": r.thesis_outcome,
                    "status": r.status,
                    "pseudo_closed": r.pseudo_closed,
                }
                for r in rows
            ],
            "n": len(rows),
        }
    finally:
        repo.conn.close()


@router.get("/journal")
def list_journal(
    ticker: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    repo = _repo()
    try:
        entries = repo.list_journal(ticker)
        if len(entries) > limit:
            entries = entries[-limit:]
        return {
            "entries": [
                {
                    "entry_id": e.entry_id,
                    "ticker": e.ticker,
                    "ts": e.ts.isoformat(),
                    "entry_type": e.entry_type.value,
                    "body": e.body,
                    "position_id": e.position_id,
                    "linked_snapshot_id": e.linked_snapshot_id,
                }
                for e in entries
            ],
            "n": len(entries),
        }
    finally:
        repo.conn.close()


@router.get("/reports")
def list_recal_reports() -> dict[str, Any]:
    from standing.portfolio.recalibrate import DEFAULT_REPORT_DIR

    root = Path(DEFAULT_REPORT_DIR)
    if not root.exists():
        return {"reports": []}
    files = sorted(root.glob("recal_*.md"), reverse=True)
    out = []
    for f in files[:20]:
        out.append(
            {
                "name": f.name,
                "as_of": f.stem.replace("recal_", ""),
                "path": str(f),
                "url": f"/api/portfolio/reports/{f.stem.replace('recal_', '')}",
            }
        )
    return {"reports": out}


@router.get("/reports/{as_of}")
def get_recal_report(as_of: str) -> dict[str, Any]:
    from standing.portfolio.recalibrate import DEFAULT_REPORT_DIR

    md = Path(DEFAULT_REPORT_DIR) / f"recal_{as_of}.md"
    js = Path(DEFAULT_REPORT_DIR) / f"recal_{as_of}.json"
    if not md.exists():
        raise HTTPException(status_code=404, detail=f"No report for {as_of}")
    payload = None
    if js.exists():
        import json

        payload = json.loads(js.read_text(encoding="utf-8"))
    return {"as_of": as_of, "markdown": md.read_text(encoding="utf-8"), "json": payload}


# Keep /{ticker} after static paths so "review"/"journal" are not captured.
@router.get("/position/{ticker}")
def get_position(ticker: str, mark: float | None = Query(default=None)) -> dict[str, Any]:
    repo = _repo()
    try:
        detail = position_detail(repo, ticker, mark_price=mark)
        if detail is None:
            raise HTTPException(status_code=404, detail=f"No open position for {ticker.upper()}")
        return detail
    finally:
        repo.conn.close()


@router.post("/buy")
def buy(body: BuyRequest) -> dict[str, Any]:
    repo = _repo()
    try:
        try:
            horizon_days = parse_horizon(body.horizon)
            snapshot_id = _ensure_snapshot(repo, body.ticker, body.snapshot)
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
                reference_class=body.reference_class,
            )
        except Exception as exc:
            raise _http_from_portfolio(exc) from exc
        log.info("buy ticker=%s position_id=%s", position.ticker, position.position_id)
        return {
            "position_id": position.position_id,
            "ticker": position.ticker,
            "entry_price": position.entry_price,
            "size": position.size,
            "thesis_id": thesis.thesis_id,
            "journal_entry_id": entry.entry_id,
            "entry_snapshot_id": snapshot_id,
            "horizon_days": thesis.horizon_days,
            "conviction": thesis.conviction,
        }
    finally:
        repo.conn.close()


@router.post("/sell")
def sell(body: SellRequest) -> dict[str, Any]:
    repo = _repo()
    try:
        try:
            snap = repo.get_latest_snapshot(body.ticker)
            position, entry = repo.close_position(
                ticker=body.ticker,
                close_price=body.price,
                reason=CloseReason(body.reason),
                exit_note=body.note,
                linked_snapshot_id=snap.snapshot_id if snap else None,
            )
            as_of = date.fromisoformat(body.mark_as_of) if body.mark_as_of else date.today()
            _seed_mark(repo, body.ticker, body.price, as_of=as_of)
        except Exception as exc:
            raise _http_from_portfolio(exc) from exc
        pnl = (position.close_price / position.entry_price - 1.0) * 100.0
        log.info("sell ticker=%s reason=%s", position.ticker, body.reason)
        return {
            "position_id": position.position_id,
            "ticker": position.ticker,
            "close_price": position.close_price,
            "close_reason": position.close_reason.value if position.close_reason else None,
            "pnl_pct": pnl,
            "exit_note_id": entry.entry_id,
        }
    finally:
        repo.conn.close()


@router.post("/journal")
def add_journal(body: JournalRequest) -> dict[str, Any]:
    repo = _repo()
    try:
        try:
            linked = None
            if body.snapshot is not None:
                linked = _ensure_snapshot(repo, body.ticker, body.snapshot)
            else:
                snap = repo.get_latest_snapshot(body.ticker)
                linked = snap.snapshot_id if snap else None
            open_pos = repo.get_open_position(body.ticker)
            entry = repo.add_journal_entry(
                ticker=body.ticker,
                body=body.note,
                position_id=open_pos.position_id if open_pos else None,
                linked_snapshot_id=linked,
            )
        except Exception as exc:
            raise _http_from_portfolio(exc) from exc
        return {
            "entry_id": entry.entry_id,
            "ticker": entry.ticker,
            "entry_type": entry.entry_type.value,
            "ts": entry.ts.isoformat(),
        }
    finally:
        repo.conn.close()


@router.post("/watchlist")
def add_watchlist(body: WatchlistRequest) -> dict[str, Any]:
    repo = _repo()
    try:
        try:
            linked = None
            if body.snapshot is not None:
                linked = _ensure_snapshot(repo, body.ticker, body.snapshot)
            else:
                snap = repo.get_latest_snapshot(body.ticker)
                linked = snap.snapshot_id if snap else None
            entry = repo.add_watchlist_thesis(
                ticker=body.ticker,
                thesis=body.thesis,
                falsifier=body.falsifier,
                linked_snapshot_id=linked,
            )
        except Exception as exc:
            raise _http_from_portfolio(exc) from exc
        return {
            "entry_id": entry.entry_id,
            "ticker": entry.ticker,
            "entry_type": entry.entry_type.value,
            "linked_snapshot_id": entry.linked_snapshot_id,
        }
    finally:
        repo.conn.close()


@router.post("/marks")
def upsert_marks(items: list[MarkItem]) -> dict[str, Any]:
    repo = _repo()
    try:
        today = date.today()
        for item in items:
            repo.upsert_daily_mark(as_of=today, ticker=item.ticker, close_price=item.price)
        return {"n": len(items)}
    finally:
        repo.conn.close()


@router.post("/recalibrate")
def recalibrate(body: RecalibrateRequest) -> dict[str, Any]:
    from standing.portfolio.recalibrate import RecalibrateConfig, parse_window, run_recalibrate

    repo = _repo()
    try:
        try:
            window_days = parse_window(body.window)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        cfg = RecalibrateConfig(
            window_days=window_days,
            min_hold_days=body.min_hold,
            as_of=date.fromisoformat(body.as_of) if body.as_of else None,
        )
        result = run_recalibrate(repo, cfg)
        # Don't dump full positions into API if huge — keep summary + suggestions + paths
        return {
            "as_of": result["as_of"],
            "n_positions": result["n_positions"],
            "score_power": result["score_power"],
            "pillars": result["pillars"],
            "thesis_discipline": result["thesis_discipline"],
            "coverage_bias": result["coverage_bias"],
            "suggestions": result["suggestions"],
            "delta_vs_previous": result.get("delta_vs_previous"),
            "report_path": result.get("report_path"),
            "markdown_url": f"/api/portfolio/reports/{result['as_of']}",
            "generated_at_utc": result.get("generated_at_utc"),
        }
    finally:
        repo.conn.close()
