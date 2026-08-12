"""CLI tests for portfolio / journal commands."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from standing.cli import main
from standing.portfolio.cli_support import drift_bucket, parse_horizon
from standing.portfolio.db import connect, migrate
from standing.portfolio.models import PositionStatus
from standing.portfolio.repository import PortfolioRepository


FALSIFIER = "Breaks if gross margin compresses below 35% for two quarters."


def test_parse_horizon_variants():
    assert parse_horizon(90) == 90
    assert parse_horizon("90") == 90
    assert parse_horizon("90d") == 90
    assert parse_horizon("4w") == 28
    assert parse_horizon("12M") == 360
    assert parse_horizon("1y") == 365
    with pytest.raises(ValueError):
        parse_horizon("nope")
    with pytest.raises(ValueError):
        parse_horizon(0)


def test_drift_bucket():
    assert drift_bucket(1.0) == "green"
    assert drift_bucket(-4.9) == "green"
    assert drift_bucket(-5.0) == "yellow"
    assert drift_bucket(-15.0) == "yellow"
    assert drift_bucket(-15.1) == "red"
    assert drift_bucket(None) == "n/a"


@pytest.fixture()
def db(tmp_path: Path) -> Path:
    path = tmp_path / "p.db"
    conn = connect(path)
    migrate(conn)
    repo = PortfolioRepository(conn)
    repo.insert_scanner_snapshot(
        as_of=date(2026, 7, 22),
        ticker="AAPL",
        universe_version="fixture-v1",
        score=72.0,
        pillar_fundamentals=60.0,
        pillar_momentum=70.0,
        pillar_attention=50.0,
    )
    repo.insert_scanner_snapshot(
        as_of=date(2026, 7, 22),
        ticker="MSFT",
        universe_version="fixture-v1",
        score=80.0,
    )
    conn.close()
    return path


def test_buy_creates_position(db: Path):
    code = main(
        [
            "buy",
            "AAPL",
            "--db",
            str(db),
            "--price",
            "190",
            "--size",
            "10",
            "--thesis",
            "Oversold bounce",
            "--mechanism",
            "Attention without fund break",
            "--falsifier",
            FALSIFIER,
            "--target",
            "220",
            "--stop",
            "170",
            "--horizon",
            "12M",
            "--conviction",
            "3",
        ]
    )
    assert code == 0
    repo = PortfolioRepository(connect(db))
    pos = repo.get_open_position("AAPL")
    assert pos is not None
    assert pos.status == PositionStatus.OPEN
    thesis = repo.get_thesis(pos.position_id)
    assert thesis is not None
    assert thesis.horizon_days == 360
    journal = repo.list_journal("AAPL")
    assert len(journal) == 1


def test_buy_rejects_short_falsifier(db: Path):
    code = main(
        [
            "buy",
            "AAPL",
            "--db",
            str(db),
            "--price",
            "190",
            "--size",
            "10",
            "--thesis",
            "x",
            "--mechanism",
            "y",
            "--falsifier",
            "short",
            "--target",
            "200",
            "--stop",
            "180",
        ]
    )
    assert code == 2
    repo = PortfolioRepository(connect(db))
    assert repo.get_open_position("AAPL") is None


def test_buy_requires_snapshot(tmp_path: Path):
    db = tmp_path / "empty.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    code = main(
        [
            "buy",
            "ZZZZ",
            "--db",
            str(db),
            "--price",
            "10",
            "--size",
            "1",
            "--thesis",
            "x",
            "--mechanism",
            "y",
            "--falsifier",
            FALSIFIER,
            "--target",
            "12",
            "--stop",
            "8",
        ]
    )
    assert code == 2


def test_sell_closes_with_exit_note(db: Path):
    assert (
        main(
            [
                "buy",
                "AAPL",
                "--db",
                str(db),
                "--price",
                "190",
                "--size",
                "10",
                "--thesis",
                "claim",
                "--mechanism",
                "mech",
                "--falsifier",
                FALSIFIER,
                "--target",
                "220",
                "--stop",
                "170",
            ]
        )
        == 0
    )
    code = main(
        [
            "sell",
            "AAPL",
            "--db",
            str(db),
            "--price",
            "205",
            "--reason",
            "target",
            "--note",
            "Hit target after bounce.",
        ]
    )
    assert code == 0
    repo = PortfolioRepository(connect(db))
    assert repo.get_open_position("AAPL") is None
    closed = repo.list_closed_positions()
    assert len(closed) == 1
    notes = [e for e in repo.list_journal("AAPL") if e.entry_type.value == "exit_note"]
    assert len(notes) == 1


def test_journal_update(db: Path):
    code = main(["journal", "AAPL", "--db", str(db), "--note", "Watching CPI print"])
    assert code == 0
    repo = PortfolioRepository(connect(db))
    entries = repo.list_journal("AAPL")
    assert len(entries) == 1
    assert "CPI" in entries[0].body


def test_watchlist_add(db: Path):
    code = main(
        [
            "watchlist",
            "add",
            "MSFT",
            "--db",
            str(db),
            "--thesis",
            "Cloud growth re-accelerates",
            "--falsifier",
            FALSIFIER,
        ]
    )
    assert code == 0
    repo = PortfolioRepository(connect(db))
    entries = repo.list_journal("MSFT")
    assert entries[0].entry_type.value == "watchlist_thesis"


def test_portfolio_shows_score_drift(db: Path, capsys):
    assert (
        main(
            [
                "buy",
                "AAPL",
                "--db",
                str(db),
                "--price",
                "190",
                "--size",
                "10",
                "--thesis",
                "claim",
                "--mechanism",
                "mech",
                "--falsifier",
                FALSIFIER,
                "--target",
                "220",
                "--stop",
                "170",
            ]
        )
        == 0
    )
    repo = PortfolioRepository(connect(db))
    repo.insert_scanner_snapshot(
        as_of=date(2026, 7, 23),
        ticker="AAPL",
        universe_version="fixture-v1",
        score=60.0,
    )
    repo.conn.close()

    code = main(
        [
            "portfolio",
            "--db",
            str(db),
            "--mark",
            "AAPL=200",
        ]
    )
    assert code == 0
    out = capsys.readouterr().out
    assert "AAPL" in out
    assert "72.0" in out or "72" in out
    assert "60.0" in out or "60" in out
