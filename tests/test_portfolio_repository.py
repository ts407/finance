"""Repository-layer tests for portfolio / journal."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
import sqlite3

from standing.portfolio.db import connect, migrate
from standing.portfolio.exceptions import (
    FalsifierTooShortError,
    OpenPositionExistsError,
    PositionAlreadyClosedError,
    SnapshotInUseError,
    ThesisImmutableError,
)
from standing.portfolio.models import CloseReason, JournalEntryType, PositionStatus
from standing.portfolio.repository import PortfolioRepository


@pytest.fixture()
def repo(tmp_path: Path) -> PortfolioRepository:
    conn = connect(tmp_path / "portfolio.db")
    migrate(conn)
    return PortfolioRepository(conn)


def _snap(repo: PortfolioRepository, ticker: str = "AAPL", score: float = 72.5):
    return repo.insert_scanner_snapshot(
        as_of=date(2026, 7, 22),
        ticker=ticker,
        universe_version="fixture-v1",
        score=score,
        pillar_fundamentals=60.0,
        pillar_momentum=70.0,
        pillar_attention=55.0,
        coverage_flags={"ev_ebitda": "present"},
        provider_state={"market": "fixture", "social": "fixture"},
    )


FALSIFIER = "Breaks if gross margin compresses below 35% for two quarters."


def test_insert_and_get_scanner_snapshot(repo: PortfolioRepository):
    snap = _snap(repo)
    loaded = repo.get_snapshot(snap.snapshot_id)
    assert loaded.ticker == "AAPL"
    assert loaded.date == date(2026, 7, 22)
    assert loaded.score == 72.5
    assert loaded.coverage_flags["ev_ebitda"] == "present"
    assert loaded.provider_state["market"] == "fixture"


def test_duplicate_snapshot_rejected(repo: PortfolioRepository):
    _snap(repo)
    with pytest.raises(sqlite3.IntegrityError):
        _snap(repo)


def test_upsert_scanner_snapshot(repo: PortfolioRepository):
    first = repo.upsert_scanner_snapshot(
        as_of=date(2026, 7, 22),
        ticker="aapl",
        universe_version="fixture-v1",
        score=70.0,
    )
    second = repo.upsert_scanner_snapshot(
        as_of=date(2026, 7, 22),
        ticker="AAPL",
        universe_version="fixture-v1",
        score=75.0,
        pillar_momentum=80.0,
    )
    assert first.snapshot_id == second.snapshot_id
    assert second.score == 75.0
    assert second.pillar_momentum == 80.0


def test_open_position_atomic_with_thesis_and_journal(repo: PortfolioRepository):
    snap = _snap(repo)
    open_ts = datetime(2026, 7, 22, 15, 30, tzinfo=timezone.utc)
    position, thesis, entry = repo.open_position(
        ticker="aapl",
        entry_price=190.0,
        size=10,
        claim="Mean-reversion after oversold social panic",
        mechanism="Attention spike without fundamental break",
        falsifier=FALSIFIER,
        target_price=220.0,
        stop_price=170.0,
        horizon_days=90,
        conviction=3,
        entry_snapshot_id=snap.snapshot_id,
        open_ts=open_ts,
    )
    assert position.status == PositionStatus.OPEN
    assert position.ticker == "AAPL"
    assert position.open_ts == open_ts
    assert position.open_ts.tzinfo is not None
    assert position.open_ts.utcoffset().total_seconds() == 0
    assert thesis.falsifier == FALSIFIER
    assert thesis.conviction == 3
    assert entry.entry_type == JournalEntryType.UPDATE
    assert entry.position_id == position.position_id
    assert entry.linked_snapshot_id == snap.snapshot_id
    assert repo.get_thesis(position.position_id) is not None


def test_open_position_rolls_back_on_short_falsifier(repo: PortfolioRepository):
    snap = _snap(repo)
    with pytest.raises(FalsifierTooShortError):
        repo.open_position(
            ticker="AAPL",
            entry_price=190.0,
            size=10,
            claim="claim",
            mechanism="mech",
            falsifier="too short",
            target_price=200.0,
            stop_price=180.0,
            horizon_days=30,
            conviction=2,
            entry_snapshot_id=snap.snapshot_id,
        )
    assert repo.list_open_positions() == []
    assert repo.list_journal("AAPL") == []


def test_open_position_rejects_second_open(repo: PortfolioRepository):
    snap = _snap(repo)
    repo.open_position(
        ticker="AAPL",
        entry_price=190.0,
        size=10,
        claim="claim one",
        mechanism="mech",
        falsifier=FALSIFIER,
        target_price=200.0,
        stop_price=180.0,
        horizon_days=30,
        conviction=2,
        entry_snapshot_id=snap.snapshot_id,
    )
    with pytest.raises(OpenPositionExistsError):
        repo.open_position(
            ticker="AAPL",
            entry_price=191.0,
            size=5,
            claim="claim two",
            mechanism="mech",
            falsifier=FALSIFIER,
            target_price=210.0,
            stop_price=175.0,
            horizon_days=30,
            conviction=3,
            entry_snapshot_id=snap.snapshot_id,
        )


def test_thesis_immutable_via_repository(repo: PortfolioRepository):
    snap = _snap(repo)
    position, _, _ = repo.open_position(
        ticker="AAPL",
        entry_price=190.0,
        size=10,
        claim="claim",
        mechanism="mech",
        falsifier=FALSIFIER,
        target_price=200.0,
        stop_price=180.0,
        horizon_days=30,
        conviction=2,
        entry_snapshot_id=snap.snapshot_id,
    )
    with pytest.raises(ThesisImmutableError):
        repo.update_thesis(position.position_id, claim="new claim")


def test_thesis_immutable_via_db_trigger(repo: PortfolioRepository):
    snap = _snap(repo)
    position, thesis, _ = repo.open_position(
        ticker="AAPL",
        entry_price=190.0,
        size=10,
        claim="claim",
        mechanism="mech",
        falsifier=FALSIFIER,
        target_price=200.0,
        stop_price=180.0,
        horizon_days=30,
        conviction=2,
        entry_snapshot_id=snap.snapshot_id,
    )
    with pytest.raises(sqlite3.IntegrityError):
        repo.conn.execute(
            "UPDATE thesis_snapshots SET claim = 'edited' WHERE thesis_id = ?",
            (thesis.thesis_id,),
        )
    # Original unchanged
    assert repo.get_thesis(position.position_id).claim == "claim"


def test_journal_append_only(repo: PortfolioRepository):
    entry = repo.add_journal_entry(ticker="AAPL", body="watching earnings")
    assert entry.entry_type == JournalEntryType.UPDATE
    with pytest.raises(sqlite3.IntegrityError):
        repo.conn.execute(
            "UPDATE journal_entries SET body = 'edited' WHERE entry_id = ?",
            (entry.entry_id,),
        )


def test_close_position_requires_exit_note(repo: PortfolioRepository):
    snap = _snap(repo)
    repo.open_position(
        ticker="AAPL",
        entry_price=190.0,
        size=10,
        claim="claim",
        mechanism="mech",
        falsifier=FALSIFIER,
        target_price=200.0,
        stop_price=180.0,
        horizon_days=30,
        conviction=2,
        entry_snapshot_id=snap.snapshot_id,
    )
    with pytest.raises(ValueError, match="exit_note"):
        repo.close_position(
            ticker="AAPL",
            close_price=200.0,
            reason=CloseReason.TARGET,
            exit_note="  ",
        )


def test_close_position_writes_exit_note(repo: PortfolioRepository):
    snap = _snap(repo)
    opened, _, _ = repo.open_position(
        ticker="AAPL",
        entry_price=190.0,
        size=10,
        claim="claim",
        mechanism="mech",
        falsifier=FALSIFIER,
        target_price=200.0,
        stop_price=180.0,
        horizon_days=30,
        conviction=2,
        entry_snapshot_id=snap.snapshot_id,
    )
    closed, note = repo.close_position(
        ticker="AAPL",
        close_price=205.0,
        reason="target",
        exit_note="Hit target after bounce.",
    )
    assert closed.status == PositionStatus.CLOSED
    assert closed.close_reason == CloseReason.TARGET
    assert closed.close_price == 205.0
    assert note.entry_type == JournalEntryType.EXIT_NOTE
    assert note.position_id == opened.position_id
    with pytest.raises(PositionAlreadyClosedError):
        repo.close_position(
            ticker="AAPL",
            close_price=206.0,
            reason=CloseReason.MANUAL,
            exit_note="again",
        )


def test_delete_snapshot_blocked_when_position_references(repo: PortfolioRepository):
    snap = _snap(repo)
    repo.open_position(
        ticker="AAPL",
        entry_price=190.0,
        size=10,
        claim="claim",
        mechanism="mech",
        falsifier=FALSIFIER,
        target_price=200.0,
        stop_price=180.0,
        horizon_days=30,
        conviction=2,
        entry_snapshot_id=snap.snapshot_id,
    )
    with pytest.raises(SnapshotInUseError):
        repo.delete_snapshot(snap.snapshot_id)


def test_delete_snapshot_blocked_when_journal_references(repo: PortfolioRepository):
    snap = _snap(repo, ticker="MSFT")
    repo.add_journal_entry(
        ticker="MSFT",
        body="note linked to snapshot",
        linked_snapshot_id=snap.snapshot_id,
    )
    with pytest.raises(SnapshotInUseError):
        repo.delete_snapshot(snap.snapshot_id)


def test_delete_unreferenced_snapshot(repo: PortfolioRepository):
    snap = _snap(repo, ticker="GOOG")
    repo.delete_snapshot(snap.snapshot_id)
    with pytest.raises(Exception):
        repo.get_snapshot(snap.snapshot_id)


def test_list_open_positions(repo: PortfolioRepository):
    a = _snap(repo, "AAPL", 70)
    b = _snap(repo, "MSFT", 80)
    repo.open_position(
        ticker="MSFT",
        entry_price=400.0,
        size=2,
        claim="claim",
        mechanism="mech",
        falsifier=FALSIFIER,
        target_price=450.0,
        stop_price=360.0,
        horizon_days=60,
        conviction=4,
        entry_snapshot_id=b.snapshot_id,
    )
    repo.open_position(
        ticker="AAPL",
        entry_price=190.0,
        size=10,
        claim="claim",
        mechanism="mech",
        falsifier=FALSIFIER,
        target_price=200.0,
        stop_price=180.0,
        horizon_days=30,
        conviction=2,
        entry_snapshot_id=a.snapshot_id,
    )
    tickers = [p.ticker for p in repo.list_open_positions()]
    assert tickers == ["AAPL", "MSFT"]


def test_watchlist_thesis(repo: PortfolioRepository):
    entry = repo.add_watchlist_thesis(
        ticker="nvda",
        thesis="AI capex cycle continues",
        falsifier=FALSIFIER,
    )
    assert entry.entry_type == JournalEntryType.WATCHLIST_THESIS
    assert "falsifier:" in entry.body.lower()
    assert entry.ticker == "NVDA"


def test_timestamps_stored_as_utc(repo: PortfolioRepository):
    snap = _snap(repo)
    # Pass aware non-UTC; store should normalize to UTC.
    localish = datetime(2026, 7, 22, 17, 0, tzinfo=timezone.utc)
    position, _, entry = repo.open_position(
        ticker="AAPL",
        entry_price=190.0,
        size=10,
        claim="claim",
        mechanism="mech",
        falsifier=FALSIFIER,
        target_price=200.0,
        stop_price=180.0,
        horizon_days=30,
        conviction=2,
        entry_snapshot_id=snap.snapshot_id,
        open_ts=localish,
    )
    raw = repo.conn.execute(
        "SELECT open_ts FROM positions WHERE position_id = ?",
        (position.position_id,),
    ).fetchone()["open_ts"]
    assert raw.endswith("Z") or raw.endswith("+00:00")
    assert position.open_ts.utcoffset().total_seconds() == 0
    assert entry.ts.utcoffset().total_seconds() == 0


def test_get_latest_snapshot(repo: PortfolioRepository):
    repo.insert_scanner_snapshot(
        as_of=date(2026, 7, 20),
        ticker="AAPL",
        universe_version="fixture-v1",
        score=60.0,
    )
    later = repo.insert_scanner_snapshot(
        as_of=date(2026, 7, 22),
        ticker="AAPL",
        universe_version="fixture-v1",
        score=72.0,
    )
    got = repo.get_latest_snapshot("AAPL")
    assert got is not None
    assert got.snapshot_id == later.snapshot_id
    assert got.score == 72.0
