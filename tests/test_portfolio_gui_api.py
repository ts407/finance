"""API tests for portfolio desk mutations (buy/sell/journal/review/recal)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from standing.portfolio.db import connect, migrate
from standing.portfolio.repository import PortfolioRepository
from standing.web.app import create_app

FALSIFIER = "Breaks if gross margin compresses below 35% for two quarters."


def test_gui_buy_sell_journal_watchlist_flow(tmp_path: Path, monkeypatch):
    db = tmp_path / "gui.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(db))
    client = TestClient(create_app())

    seed = {
        "as_of": "2026-07-22",
        "universe_version": "fixture-v1",
        "score": 72.0,
        "pillar_fundamentals": 60.0,
        "pillar_momentum": 70.0,
        "pillar_attention": 50.0,
    }

    buy = client.post(
        "/api/portfolio/buy",
        json={
            "ticker": "AAPL",
            "price": 190,
            "size": 10,
            "thesis": "Oversold bounce",
            "mechanism": "Attention without fund break",
            "falsifier": FALSIFIER,
            "target": 220,
            "stop": 170,
            "horizon": "12M",
            "conviction": 3,
            "snapshot": seed,
        },
    )
    assert buy.status_code == 200, buy.text
    assert buy.json()["ticker"] == "AAPL"

    book = client.get("/api/portfolio")
    assert book.status_code == 200
    assert book.json()["n"] == 1
    assert book.json()["positions"][0]["score_at_entry"] == 72.0

    note = client.post(
        "/api/portfolio/journal",
        json={"ticker": "AAPL", "note": "Watching CPI", "snapshot": seed},
    )
    assert note.status_code == 200

    wl = client.post(
        "/api/portfolio/watchlist",
        json={
            "ticker": "MSFT",
            "thesis": "Cloud re-accel",
            "falsifier": FALSIFIER,
            "snapshot": {**seed, "score": 80.0},
        },
    )
    assert wl.status_code == 200

    sell = client.post(
        "/api/portfolio/sell",
        json={
            "ticker": "AAPL",
            "price": 205,
            "reason": "target",
            "note": "Hit target after bounce.",
        },
    )
    assert sell.status_code == 200
    assert sell.json()["close_reason"] == "target"

    review = client.get("/api/portfolio/review")
    assert review.status_code == 200
    assert review.json()["n"] >= 1
    assert review.json()["rows"][0]["thesis_outcome"] == "validated"

    journal = client.get("/api/portfolio/journal")
    assert journal.status_code == 200
    types = {e["entry_type"] for e in journal.json()["entries"]}
    assert "exit_note" in types
    assert "watchlist_thesis" in types


def test_gui_buy_rejects_short_falsifier(tmp_path: Path, monkeypatch):
    db = tmp_path / "gui.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(db))
    client = TestClient(create_app())
    resp = client.post(
        "/api/portfolio/buy",
        json={
            "ticker": "AAPL",
            "price": 190,
            "size": 1,
            "thesis": "x",
            "mechanism": "y",
            "falsifier": "short",
            "target": 200,
            "stop": 180,
            "snapshot": {
                "as_of": "2026-07-22",
                "universe_version": "u",
                "score": 70,
            },
        },
    )
    assert resp.status_code == 400


def test_gui_recalibrate_endpoint(tmp_path: Path, monkeypatch):
    db = tmp_path / "gui.db"
    reports = tmp_path / "reports"
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(db))
    monkeypatch.setattr("standing.portfolio.recalibrate.DEFAULT_REPORT_DIR", reports)

    conn = connect(db)
    migrate(conn)
    repo = PortfolioRepository(conn)
    for i, t in enumerate(["AAPL", "MSFT", "GOOG", "AMZN", "META"]):
        snap = repo.insert_scanner_snapshot(
            as_of=date(2026, 7, 22),
            ticker=t,
            universe_version="u1",
            score=50 + i * 5,
        )
        repo.upsert_daily_mark(as_of=date(2026, 7, 22), ticker=t, close_price=100 + i)
        repo.upsert_daily_mark(as_of=date(2026, 8, 20), ticker=t, close_price=105 + i)
        repo.open_position(
            ticker=t,
            entry_price=100 + i,
            size=1,
            claim=f"claim {t}",
            mechanism="mech",
            falsifier=FALSIFIER,
            target_price=120,
            stop_price=90,
            horizon_days=60,
            conviction=3,
            entry_snapshot_id=snap.snapshot_id,
            open_ts=datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
        )
        repo.close_position(
            ticker=t,
            close_price=105 + i,
            reason="manual",
            exit_note=f"exit {t}",
            close_ts=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        )
    conn.close()

    client = TestClient(create_app())
    resp = client.post(
        "/api/portfolio/recalibrate",
        json={"window": "90d", "min_hold": 30, "as_of": "2026-09-01"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["n_positions"] >= 5
    assert "suggestions" in body
    report = client.get(body["markdown_url"])
    assert report.status_code == 200
    assert "Recalibration report" in report.json()["markdown"]


def test_index_exposes_book_tabs():
    client = TestClient(create_app())
    page = client.get("/")
    assert page.status_code == 200
    assert b'data-view="book"' in page.content
    assert b'data-view="review"' in page.content
    assert b'data-view="recal"' in page.content
    assert b'id="modal"' in page.content
    assert b'id="drawer-actions"' in page.content
