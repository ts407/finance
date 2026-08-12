"""Position attribution for ``standing review``."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from standing.portfolio.models import CloseReason, Position, PositionStatus
from standing.portfolio.repository import PortfolioRepository

PriceFn = Callable[[str, date], float | None]


@dataclass(frozen=True)
class AttributionRow:
    ticker: str
    position_id: int
    hold_days: int
    realized_return: float
    benchmark_return: float | None
    decile_return: float | None
    excess_vs_benchmark: float | None
    excess_vs_decile: float | None
    thesis_outcome: str
    status: str
    pseudo_closed: bool


def log_return(entry: float, exit_: float) -> float:
    if entry <= 0 or exit_ <= 0:
        raise ValueError("prices must be positive for log return")
    return math.log(exit_ / entry)


def thesis_outcome_from_reason(reason: CloseReason | None) -> str:
    """Self-scored heuristic from close reason (discrete layer)."""
    if reason is None:
        return "partial"
    if reason == CloseReason.TARGET:
        return "validated"
    if reason in (CloseReason.STOP, CloseReason.THESIS_BROKEN):
        return "falsified"
    return "partial"


def _as_date(ts: datetime | date) -> date:
    if isinstance(ts, datetime):
        return ts.astimezone(timezone.utc).date() if ts.tzinfo else ts.date()
    return ts


def score_decile(score: float, scores: list[float]) -> int:
    """Return 1..10 decile (10 = highest scores)."""
    if not scores:
        return 5
    ordered = sorted(scores)
    # percentile rank of score among peers
    n = len(ordered)
    # count how many are strictly below
    below = sum(1 for s in ordered if s < score)
    pct = below / max(n - 1, 1)
    decile = int(pct * 10) + 1
    return min(10, max(1, decile))


def mean_log_return(
    tickers: list[str],
    start: date,
    end: date,
    price_fn: PriceFn,
) -> float | None:
    rets: list[float] = []
    for t in tickers:
        p0 = price_fn(t, start)
        p1 = price_fn(t, end)
        if p0 is None or p1 is None or p0 <= 0 or p1 <= 0:
            continue
        rets.append(log_return(p0, p1))
    if not rets:
        return None
    return sum(rets) / len(rets)


def attribute_position(
    repo: PortfolioRepository,
    pos: Position,
    *,
    price_fn: PriceFn | None = None,
    mark_price: float | None = None,
    as_of: date | None = None,
) -> AttributionRow:
    """Attribute one closed (or pseudo-closed open) position."""
    price_fn = price_fn or (lambda t, d: repo.get_mark_on_or_before(t, d))
    entry_snap = repo.get_snapshot(pos.entry_snapshot_id)
    start = _as_date(pos.open_ts)
    pseudo = pos.status == PositionStatus.OPEN
    if pseudo:
        end = as_of or date.today()
        exit_px = mark_price
        if exit_px is None:
            exit_px = price_fn(pos.ticker, end)
        if exit_px is None:
            raise ValueError(f"No mark price for open position {pos.ticker}")
        outcome = "partial"
        reason = None
    else:
        assert pos.close_ts is not None and pos.close_price is not None
        end = _as_date(pos.close_ts)
        exit_px = pos.close_price
        reason = pos.close_reason
        outcome = thesis_outcome_from_reason(reason)

    realized = log_return(pos.entry_price, exit_px)
    hold_days = max(0, (end - start).days)

    # Universe peers on entry date / version
    peers = repo.list_snapshots_on_date(entry_snap.date, universe_version=entry_snap.universe_version)
    peer_tickers = [s.ticker for s in peers]
    peer_scores = [s.score for s in peers]
    bench = mean_log_return(peer_tickers, start, end, price_fn)

    my_decile = score_decile(entry_snap.score, peer_scores)
    decile_tickers = [
        s.ticker
        for s in peers
        if score_decile(s.score, peer_scores) == my_decile
    ]
    decile_ret = mean_log_return(decile_tickers, start, end, price_fn)

    return AttributionRow(
        ticker=pos.ticker,
        position_id=pos.position_id,
        hold_days=hold_days,
        realized_return=realized,
        benchmark_return=bench,
        decile_return=decile_ret,
        excess_vs_benchmark=(realized - bench) if bench is not None else None,
        excess_vs_decile=(realized - decile_ret) if decile_ret is not None else None,
        thesis_outcome=outcome,
        status=pos.status.value,
        pseudo_closed=pseudo,
    )


def review_closed(
    repo: PortfolioRepository,
    *,
    price_fn: PriceFn | None = None,
) -> list[AttributionRow]:
    rows = [
        attribute_position(repo, pos, price_fn=price_fn)
        for pos in repo.list_closed_positions()
    ]
    return rows
