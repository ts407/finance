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


def test_trade_snap_freezes_score_and_buy_keeps_it(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))
    client = TestClient(create_app())
    snap = client.get("/api/snapshot", params=PARAMS).json()
    ticker = snap["standings"][0]["ticker"]
    price = float(snap["standings"][0].get("last_price") or 100)

    freeze = client.post("/api/trade/snap", json={"ticker": ticker, **PARAMS})
    assert freeze.status_code == 200, freeze.text
    frozen = freeze.json()
    assert frozen["ticker"] == ticker.upper()
    assert frozen["snapshot_id"]
    assert frozen["snapshot"]["captured_utc"]
    assert frozen["snapshot"]["scores"]["final_standing"] is not None
    assert frozen["snapshot"]["as_of"] == PARAMS["as_of"]

    locked = dict(frozen["snapshot"])
    locked["methodology_version"] = "frozen-test-v1"

    buy = client.post(
        "/api/trade/buy",
        json={
            "ticker": ticker,
            "price": price,
            "size": 2,
            "target": price * 1.15,
            "stop": price * 0.9,
            "horizon": "90d",
            "conviction": 3,
            "buy_reason": "Grund: freeze the desk score at this as-of.",
            "thesis": "These: the booked score is the snapped one.",
            "mechanism": "Trade submit must not recapture live scores.",
            "falsifier": FALSIFIER,
            "score_snap": locked,
            **PARAMS,
        },
    )
    assert buy.status_code == 200, buy.text
    diary_snap = buy.json()["diary_entry"]["snapshot"]
    assert diary_snap["methodology_version"] == "frozen-test-v1"
    assert diary_snap["captured_utc"] == locked["captured_utc"]
    assert diary_snap["scores"]["final_standing"] == locked["scores"]["final_standing"]
    assert buy.json()["snapshot"]["methodology_version"] == "frozen-test-v1"

    locked_exit = dict(locked)
    locked_exit["methodology_version"] = "exit-freeze-v1"
    sell = client.post(
        "/api/trade/sell",
        json={
            "ticker": ticker,
            "price": price * 1.02,
            "reason": "manual",
            "note": "Exit attached to the frozen score, not a later recapture.",
            "score_snap": locked_exit,
            **PARAMS,
        },
    )
    assert sell.status_code == 200, sell.text
    assert sell.json()["diary_entry"]["snapshot"]["methodology_version"] == "exit-freeze-v1"


def test_trade_snap_unknown_ticker_404(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))
    client = TestClient(create_app())
    resp = client.post("/api/trade/snap", json={"ticker": "ZZZZNOTATICKER", **PARAMS})
    assert resp.status_code == 404


def test_trade_entwurf_text_includes_fundamentals_and_diary(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))
    client = TestClient(create_app())
    snap = client.get("/api/snapshot", params=PARAMS).json()
    row = snap["standings"][0]
    ticker = row["ticker"]

    resp = client.post(
        "/api/trade/entwurf",
        json={
            "source": "text",
            "text": f"{ticker}: coverage looks coherent vs peers. Personal sketch only.",
            "ticker": ticker,
            **PARAMS,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["kind"] == "entwurf"
    assert body["source"] == "text"
    assert body["ticker"] == ticker.upper()
    assert body["score_input"] is False
    assert body["draft"]["thesis"]
    assert body["draft"]["buy_reason"]
    assert body["apply"]["thesis"] == body["draft"]["thesis"]
    assert body["apply"]["falsifier"] is None
    assert "KGV (TTM)" in [pair[0] for pair in body["fundamentals_display"]]
    assert body["fundamentals"]["pe_ttm"] == row["pe_ttm"]
    assert body["fundamentals"]["final_standing"] == row["final_standing"]
    assert body["diary_entry"]["kind"] == "entwurf"
    assert body["diary_entry"]["marks"]["fundamentals"]["pe_ttm"] == row["pe_ttm"]

    diary = client.get("/api/diary", params={"ticker": ticker, "kind": "entwurf"}).json()
    assert diary["summary"]["n_entries"] >= 1
    assert diary["entries"][0]["entwurf"]["score_input"] is False


def test_trade_entwurf_url_rejects_non_http(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))
    client = TestClient(create_app())
    resp = client.post(
        "/api/trade/entwurf",
        json={"source": "url", "url": "ftp://example.com/x", **PARAMS},
    )
    assert resp.status_code == 400


def test_trade_entwurf_url_uses_preview(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))

    def fake_preview(url: str):
        return {"title": "MSFT 10-Q excerpt", "snippet": "Cloud mix, not a recommendation."}

    monkeypatch.setattr("standing.desk.entwurf.fetch_url_preview", fake_preview)
    client = TestClient(create_app())
    resp = client.post(
        "/api/trade/entwurf",
        json={
            "source": "url",
            "url": "https://example.com/filing",
            "ticker": "MSFT",
            **PARAMS,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source"] == "url"
    assert body["url"] == "https://example.com/filing"
    assert "MSFT 10-Q" in body["draft"]["thesis"]
    assert body["apply"]["buy_reason"]


def test_trade_entwurf_png_stores_and_serves(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))
    client = TestClient(create_app())
    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    snap = client.get("/api/snapshot", params=PARAMS).json()
    ticker = snap["standings"][0]["ticker"]
    resp = client.post(
        "/api/trade/entwurf",
        json={
            "source": "png",
            "image_b64": png_b64,
            "filename": "tape.png",
            "ticker": ticker,
            **PARAMS,
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["attachment_url"]
    assert body["filename"] == "tape.png"
    file_resp = client.get(body["attachment_url"])
    assert file_resp.status_code == 200
    assert file_resp.content.startswith(b"\x89PNG")


def test_trade_entwurf_empty_text_400(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))
    client = TestClient(create_app())
    resp = client.post("/api/trade/entwurf", json={"source": "text", "text": "  ", **PARAMS})
    assert resp.status_code == 400
