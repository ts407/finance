"""Attribution + recalibrate tests with ≥5 fixture positions."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from standing.cli import main
from standing.portfolio.attribution import (
    attribute_position,
    log_return,
    review_closed,
    thesis_outcome_from_reason,
)
from standing.portfolio.db import connect, migrate
from standing.portfolio.models import CloseReason
from standing.portfolio.recalibrate import RecalibrateConfig, run_recalibrate
from standing.portfolio.repository import PortfolioRepository

FALSIFIER = "Breaks if gross margin compresses below 35% for two quarters."
UNIVERSE = "fixture-v1"
AS_OF = date(2026, 7, 22)
CLOSE_AS_OF = date(2026, 8, 20)

TICKERS = ["AAPL", "MSFT", "GOOG", "AMZN", "META", "NVDA"]


@pytest.fixture()
def fixture_book(tmp_path: Path) -> Path:
    """Seed 6 tickers with snapshots, marks, 5 closed + 1 open long-hold."""
    path = tmp_path / "book.db"
    conn = connect(path)
    migrate(conn)
    repo = PortfolioRepository(conn)

    # Cross-section scores on entry day
    scores = {
        "AAPL": 70.0,
        "MSFT": 80.0,
        "GOOG": 55.0,
        "AMZN": 65.0,
        "META": 90.0,
        "NVDA": 40.0,
    }
    for t, sc in scores.items():
        repo.insert_scanner_snapshot(
            as_of=AS_OF,
            ticker=t,
            universe_version=UNIVERSE,
            score=sc,
            pillar_fundamentals=sc - 5,
            pillar_momentum=sc,
            pillar_attention=sc - 10,
            coverage_flags={"value_coverage": 1.0, "value_ev_rung": "ev_ebitda"},
        )
        # later snapshot for score series / forward pairs
        repo.insert_scanner_snapshot(
            as_of=CLOSE_AS_OF,
            ticker=t,
            universe_version=UNIVERSE,
            score=sc + 2,
            pillar_fundamentals=sc - 4,
            pillar_momentum=sc + 1,
            pillar_attention=sc - 8,
            coverage_flags={"value_coverage": 1.0, "value_ev_rung": "ev_ebitda"},
        )

    # Prices: entry and exit (+ intermediate for marks)
    entry_px = {t: 100.0 + i * 10 for i, t in enumerate(TICKERS)}
    # Differentiated forward moves so deciles/benchmark differ
    exit_px = {
        "AAPL": 110.0,
        "MSFT": 120.0,
        "GOOG": 95.0,
        "AMZN": 108.0,
        "META": 130.0,
        "NVDA": 90.0,
    }
    for t in TICKERS:
        repo.upsert_daily_mark(as_of=AS_OF, ticker=t, close_price=entry_px[t])
        repo.upsert_daily_mark(as_of=CLOSE_AS_OF, ticker=t, close_price=exit_px[t])

    open_ts = datetime(2026, 7, 22, 15, 0, tzinfo=timezone.utc)
    close_ts = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)
    reasons = [
        ("AAPL", CloseReason.TARGET, exit_px["AAPL"]),
        ("MSFT", CloseReason.TARGET, exit_px["MSFT"]),
        ("GOOG", CloseReason.STOP, exit_px["GOOG"]),
        ("AMZN", CloseReason.MANUAL, exit_px["AMZN"]),
        ("META", CloseReason.THESIS_BROKEN, exit_px["META"]),
    ]
    for ticker, reason, px in reasons:
        snap = repo.get_latest_snapshot(ticker, universe_version=UNIVERSE)
        # entry snapshot should be AS_OF one — get by listing
        snaps = repo.list_snapshots_on_date(AS_OF, universe_version=UNIVERSE)
        entry = next(s for s in snaps if s.ticker == ticker)
        pos, _, _ = repo.open_position(
            ticker=ticker,
            entry_price=entry_px[ticker],
            size=10,
            claim=f"Thesis {ticker}",
            mechanism="fixture mechanism",
            falsifier=FALSIFIER,
            target_price=entry_px[ticker] * 1.2,
            stop_price=entry_px[ticker] * 0.9,
            horizon_days=60,
            conviction=3 if ticker != "META" else 5,
            entry_snapshot_id=entry.snapshot_id,
            open_ts=open_ts,
        )
        repo.close_position(
            ticker=ticker,
            close_price=px,
            reason=reason,
            exit_note=f"Closed {ticker} for test ({reason.value})",
            close_ts=close_ts,
        )

    # One open long-hold (≥30d by as_of 2026-09-01)
    snaps = repo.list_snapshots_on_date(AS_OF, universe_version=UNIVERSE)
    entry = next(s for s in snaps if s.ticker == "NVDA")
    repo.open_position(
        ticker="NVDA",
        entry_price=entry_px["NVDA"],
        size=5,
        claim="Thesis NVDA",
        mechanism="fixture mechanism",
        falsifier=FALSIFIER,
        target_price=entry_px["NVDA"] * 1.3,
        stop_price=entry_px["NVDA"] * 0.85,
        horizon_days=90,
        conviction=4,
        entry_snapshot_id=entry.snapshot_id,
        open_ts=open_ts,
    )

    conn.close()
    return path


def test_log_return_and_thesis_outcome():
    assert abs(log_return(100, 110) - math.log(1.1)) < 1e-12
    assert thesis_outcome_from_reason(CloseReason.TARGET) == "validated"
    assert thesis_outcome_from_reason(CloseReason.STOP) == "falsified"
    assert thesis_outcome_from_reason(CloseReason.THESIS_BROKEN) == "falsified"
    assert thesis_outcome_from_reason(CloseReason.MANUAL) == "partial"


def test_review_five_closed_positions(fixture_book: Path):
    repo = PortfolioRepository(connect(fixture_book))
    rows = review_closed(repo)
    assert len(rows) >= 5
    by_ticker = {r.ticker: r for r in rows}
    assert by_ticker["AAPL"].thesis_outcome == "validated"
    assert by_ticker["GOOG"].thesis_outcome == "falsified"
    assert by_ticker["META"].thesis_outcome == "falsified"
    assert by_ticker["AMZN"].thesis_outcome == "partial"
    assert by_ticker["AAPL"].hold_days == (CLOSE_AS_OF - AS_OF).days
    assert by_ticker["AAPL"].benchmark_return is not None
    assert by_ticker["AAPL"].decile_return is not None
    assert abs(by_ticker["AAPL"].realized_return - math.log(110 / 100)) < 1e-9


def test_review_cli(fixture_book: Path, capsys):
    code = main(["review", "--db", str(fixture_book)])
    assert code == 0
    out = capsys.readouterr().out
    assert "AAPL" in out
    assert "valida" in out or "falsif" in out or "partial" in out


def test_recalibrate_report(fixture_book: Path, tmp_path: Path):
    repo = PortfolioRepository(connect(fixture_book))
    report_dir = tmp_path / "reports"
    # Prior report for delta
    prior = run_recalibrate(
        repo,
        RecalibrateConfig(window_days=90, min_hold_days=30, as_of=date(2026, 8, 15)),
        report_dir=report_dir,
    )
    assert prior["report_path"]
    result = run_recalibrate(
        repo,
        RecalibrateConfig(window_days=90, min_hold_days=30, as_of=date(2026, 9, 1)),
        report_dir=report_dir,
    )
    assert result["n_positions"] >= 5
    assert Path(result["report_path"]).exists()
    md = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "Recalibration report" in md
    assert "Vorgeschlagene Prüfungen" in md
    assert result["delta_vs_previous"] is not None
    assert "score_power" in result
    assert "pillars" in result


def test_recalibrate_cli(fixture_book: Path, tmp_path: Path, capsys):
    code = main(
        [
            "recalibrate",
            "--db",
            str(fixture_book),
            "--window",
            "90d",
            "--min-hold",
            "30",
            "--as-of",
            "2026-09-01",
            "--report-dir",
            str(tmp_path / "reports"),
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "Recalibrate" in out
    assert (tmp_path / "reports" / "recal_2026-09-01.md").exists()


def test_attribute_open_pseudo_close(fixture_book: Path):
    repo = PortfolioRepository(connect(fixture_book))
    pos = repo.get_open_position("NVDA")
    assert pos is not None
    row = attribute_position(repo, pos, as_of=date(2026, 9, 1))
    assert row.pseudo_closed is True
    assert row.thesis_outcome == "partial"
    assert row.hold_days >= 30
