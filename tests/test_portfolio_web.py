"""Web API tests for portfolio overlay on the scanner desk."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from standing.portfolio.db import connect, migrate
from standing.portfolio.repository import PortfolioRepository
from standing.web.app import create_app

FALSIFIER = "Breaks if gross margin compresses below 35% for two quarters."
FIXTURE_PARAMS = {"as_of": "2026-07-22", "social": "fixture", "market": "fixture"}


def _seed_db(path: Path, ticker: str = "AAPL") -> None:
    conn = connect(path)
    migrate(conn)
    repo = PortfolioRepository(conn)
    snap = repo.insert_scanner_snapshot(
        as_of=date(2026, 7, 22),
        ticker=ticker,
        universe_version="fixture-v1",
        score=72.0,
        pillar_fundamentals=60.0,
        pillar_momentum=70.0,
        pillar_attention=50.0,
    )
    repo.insert_scanner_snapshot(
        as_of=date(2026, 7, 23),
        ticker=ticker,
        universe_version="fixture-v1",
        score=60.0,
    )
    repo.open_position(
        ticker=ticker,
        entry_price=190.0,
        size=10,
        claim="Oversold bounce",
        mechanism="Attention without fund break",
        falsifier=FALSIFIER,
        target_price=220.0,
        stop_price=170.0,
        horizon_days=90,
        conviction=3,
        entry_snapshot_id=snap.snapshot_id,
    )
    conn.close()


def test_snapshot_enriches_held_position(tmp_path: Path, monkeypatch):
    db = tmp_path / "p.db"
    _seed_db(db, "AAPL")
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(db))

    client = TestClient(create_app())
    snap = client.get("/api/snapshot", params={**FIXTURE_PARAMS, "q": "AAPL"}).json()
    rows = snap["standings"]
    assert rows
    held = next(r for r in rows if r["ticker"] == "AAPL")
    assert held["portfolio"] is not None
    assert held["portfolio"]["held"] is True
    assert held["portfolio"]["score_at_entry"] == 72.0
    assert held["portfolio"]["score_now"] == 60.0
    assert held["portfolio"]["score_drift"] == -12.0
    assert held["portfolio"]["drift_bucket"] == "yellow"


def test_unheld_ticker_has_null_portfolio(tmp_path: Path, monkeypatch):
    db = tmp_path / "p.db"
    _seed_db(db, "AAPL")
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(db))
    client = TestClient(create_app())
    snap = client.get("/api/snapshot", params={**FIXTURE_PARAMS, "limit": 20}).json()
    unheld = [r for r in snap["standings"] if r["ticker"] != "AAPL"]
    assert unheld
    assert all(r.get("portfolio") is None for r in unheld)


def test_portfolio_detail_endpoint(tmp_path: Path, monkeypatch):
    db = tmp_path / "p.db"
    _seed_db(db, "AAPL")
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(db))
    client = TestClient(create_app())
    detail = client.get("/api/portfolio/position/AAPL", params={"mark": 200}).json()
    assert detail["position"]["ticker"] == "AAPL"
    assert detail["thesis"]["falsifier"].startswith("Breaks")
    assert len(detail["journal"]) >= 1
    assert len(detail["score_series"]) == 2
    assert detail["distances"]["dist_to_target_pct"] is not None
    assert detail["distances"]["dist_to_stop_pct"] is not None


def test_portfolio_detail_404(tmp_path: Path, monkeypatch):
    db = tmp_path / "p.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(db))
    client = TestClient(create_app())
    resp = client.get("/api/portfolio/position/MSFT")
    assert resp.status_code == 404


def test_sync_standing_snapshot(tmp_path: Path):
    from standing.pipeline.snapshot import run_snapshot
    from standing.portfolio.sync import sync_standing_snapshot
    from standing.providers import build_market_provider, build_social_provider

    snap = run_snapshot(
        as_of=date(2026, 7, 22),
        market=build_market_provider("fixture"),
        social=build_social_provider("fixture", history_days=14),
    )
    conn = connect(tmp_path / "sync.db")
    migrate(conn)
    repo = PortfolioRepository(conn)
    n = sync_standing_snapshot(repo, snap)
    assert n == len(snap.standings)
    latest = repo.get_latest_snapshot(str(snap.standings.iloc[0]["ticker"]))
    assert latest is not None
    assert latest.score == float(snap.standings.iloc[0]["final_standing"])
