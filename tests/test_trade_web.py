from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from standing.web.app import create_app

FALSIFIER = "Breaks if gross margin compresses below 35% for two quarters."
PARAMS = {
    "as_of": "2026-07-22",
    "social": "fixture",
    "market": "fixture",
    "prefer_store": False,
}


def test_trade_buy_sell_writes_book_and_diary(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))
    client = TestClient(create_app())
    snap = client.get("/api/snapshot", params=PARAMS).json()
    ticker = snap["standings"][0]["ticker"]
    price = float(snap["standings"][0].get("last_price") or 100)

    buy = client.post(
        "/api/trade/buy",
        json={
            "ticker": ticker,
            "price": price,
            "size": 4,
            "target": price * 1.2,
            "stop": price * 0.85,
            "horizon": "90d",
            "conviction": 3,
            "buy_reason": "Grund: coverage and quality look coherent vs peers.",
            "thesis": "These: hold while Final stays descriptive.",
            "mechanism": "Peer-relative value mean-reverts without a fund break.",
            "falsifier": FALSIFIER,
            **PARAMS,
        },
    )
    assert buy.status_code == 200, buy.text
    body = buy.json()
    assert body["ticker"] == ticker.upper()
    assert body["size"] == 4
    assert body["diary_entry"]["kind"] == "buy"
    assert body["diary_entry"]["marks"]["entry_price"] == price
    assert body["diary_entry"]["marks"]["target_price"] == price * 1.2
    assert body["diary_entry"]["marks"]["stop_price"] == price * 0.85
    assert body["diary_entry"]["marks"]["upside_from_entry_pct"] == pytest.approx(0.2)
    assert body["diary_entry"]["marks"]["upside_pct"] is not None
    assert body["diary_entry"]["marks"]["reward_risk"] == pytest.approx((price * 1.2 - price) / (price - price * 0.85))
    assert body["holdings"]["position"]["ticker"] == ticker.upper()

    book = client.get("/api/portfolio").json()
    assert book["n"] == 1
    assert book["positions"][0]["ticker"] == ticker.upper()

    diary = client.get("/api/diary", params={"ticker": ticker, "kind": "buy"}).json()
    assert diary["summary"]["n_entries"] >= 1

    sell = client.post(
        "/api/trade/sell",
        json={
            "ticker": ticker,
            "price": price * 1.05,
            "reason": "manual",
            "note": "Closed from the trade interface — not a tip.",
            **PARAMS,
        },
    )
    assert sell.status_code == 200, sell.text
    closed = sell.json()
    assert closed["close_reason"] == "manual"
    assert closed["diary_entry"]["kind"] == "close"
    assert client.get("/api/portfolio").json()["n"] == 0


def test_trade_buy_rejects_short_falsifier(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))
    client = TestClient(create_app())
    resp = client.post(
        "/api/trade/buy",
        json={
            "ticker": "AAPL",
            "price": 190,
            "size": 1,
            "target": 220,
            "stop": 170,
            "thesis": "x",
            "mechanism": "y",
            "falsifier": "short",
            "buy_reason": "z",
            **PARAMS,
        },
    )
    assert resp.status_code == 400
