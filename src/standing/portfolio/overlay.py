"""Build portfolio overlay payloads for the scanner API / UI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from standing.portfolio.cli_support import drift_bucket
from standing.portfolio.models import Position, ThesisSnapshot
from standing.portfolio.repository import PortfolioRepository


def position_overlay(repo: PortfolioRepository, ticker: str) -> dict[str, Any] | None:
    """Return portfolio fields for a ticker, or None if not held."""
    pos = repo.get_open_position(ticker)
    if pos is None:
        return None
    return _overlay_for_position(repo, pos)


def enrich_rows(
    rows: list[dict[str, Any]], repo: PortfolioRepository | None
) -> list[dict[str, Any]]:
    """Attach ``portfolio`` objects to standing/heat rows when held."""
    if repo is None:
        return rows
    open_map = {p.ticker: p for p in repo.list_open_positions()}
    out: list[dict[str, Any]] = []
    for row in rows:
        copy = dict(row)
        ticker = str(row.get("ticker", "")).upper()
        pos = open_map.get(ticker)
        copy["portfolio"] = _overlay_for_position(repo, pos) if pos else None
        out.append(copy)
    return out


def position_detail(
    repo: PortfolioRepository,
    ticker: str,
    *,
    mark_price: float | None = None,
) -> dict[str, Any] | None:
    """Full position detail: thesis, journal, score series, distances."""
    pos = repo.get_open_position(ticker)
    if pos is None:
        return None
    thesis = repo.get_thesis(pos.position_id)
    entry_snap = repo.get_snapshot(pos.entry_snapshot_id)
    now_snap = repo.get_latest_snapshot(pos.ticker)
    journal = repo.list_journal(position_id=pos.position_id)
    score_series = _score_series(repo, pos.ticker, entry_snap.universe_version)

    overlay = _overlay_for_position(repo, pos, thesis=thesis)
    dist = _distances(thesis, mark_price)

    return {
        "position": {
            "position_id": pos.position_id,
            "ticker": pos.ticker,
            "open_ts": pos.open_ts.isoformat(),
            "entry_price": pos.entry_price,
            "size": pos.size,
            "status": pos.status.value,
            "entry_snapshot_id": pos.entry_snapshot_id,
        },
        "thesis": None
        if thesis is None
        else {
            "thesis_id": thesis.thesis_id,
            "claim": thesis.claim,
            "mechanism": thesis.mechanism,
            "falsifier": thesis.falsifier,
            "target_price": thesis.target_price,
            "stop_price": thesis.stop_price,
            "horizon_days": thesis.horizon_days,
            "conviction": thesis.conviction,
            "reference_class": thesis.reference_class,
        },
        "portfolio": overlay,
        "distances": dist,
        "score_series": score_series,
        "journal": [
            {
                "entry_id": e.entry_id,
                "ts": e.ts.isoformat(),
                "entry_type": e.entry_type.value,
                "body": e.body,
                "linked_snapshot_id": e.linked_snapshot_id,
            }
            for e in journal
        ],
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def _overlay_for_position(
    repo: PortfolioRepository,
    pos: Position,
    *,
    thesis: ThesisSnapshot | None = None,
) -> dict[str, Any]:
    entry_snap = repo.get_snapshot(pos.entry_snapshot_id)
    now_snap = repo.get_latest_snapshot(pos.ticker)
    score_entry = entry_snap.score
    score_now = now_snap.score if now_snap else None
    drift = (score_now - score_entry) if score_now is not None else None
    if thesis is None:
        thesis = repo.get_thesis(pos.position_id)
    return {
        "held": True,
        "position_id": pos.position_id,
        "entry_price": pos.entry_price,
        "size": pos.size,
        "open_ts": pos.open_ts.isoformat(),
        "score_at_entry": score_entry,
        "score_now": score_now,
        "score_drift": drift,
        "drift_bucket": drift_bucket(drift),
        "target_price": thesis.target_price if thesis else None,
        "stop_price": thesis.stop_price if thesis else None,
        "conviction": thesis.conviction if thesis else None,
    }


def _distances(thesis: ThesisSnapshot | None, mark_price: float | None) -> dict[str, Any]:
    if thesis is None:
        return {
            "mark_price": mark_price,
            "dist_to_target_pct": None,
            "dist_to_stop_pct": None,
        }
    if mark_price is None or mark_price <= 0:
        return {
            "mark_price": None,
            "dist_to_target_pct": None,
            "dist_to_stop_pct": None,
            "target_price": thesis.target_price,
            "stop_price": thesis.stop_price,
        }
    return {
        "mark_price": mark_price,
        "target_price": thesis.target_price,
        "stop_price": thesis.stop_price,
        "dist_to_target_pct": (thesis.target_price / mark_price - 1.0) * 100.0,
        "dist_to_stop_pct": (thesis.stop_price / mark_price - 1.0) * 100.0,
    }


def _score_series(
    repo: PortfolioRepository, ticker: str, universe_version: str
) -> list[dict[str, Any]]:
    rows = repo.conn.execute(
        """
        SELECT date, score, snapshot_id
        FROM scanner_snapshots
        WHERE ticker = ? AND universe_version = ?
        ORDER BY date ASC, snapshot_id ASC
        """,
        (ticker.upper(), universe_version),
    ).fetchall()
    return [
        {
            "date": r["date"],
            "score": float(r["score"]),
            "snapshot_id": int(r["snapshot_id"]),
        }
        for r in rows
    ]
