from __future__ import annotations

import pytest

from standing.desk.ledger import (
    append_diary,
    build_diary_marks,
    capture_snapshot,
    close_position,
    export_diary_csv,
    open_or_add_position,
    portfolio_view,
    read_diary,
    summarize_diary_for_vergleich,
    ticker_dossier,
    update_position_notes,
)


def _snap(ticker: str = "AAPL", price: float = 100.0, final: float = 62.0) -> dict:
    return capture_snapshot(
        {
            "ticker": ticker,
            "sector": "Information Technology",
            "last_price": price,
            "value": 55,
            "quality": 60,
            "momentum": 50,
            "composite_standing": 55,
            "attention_tilt": 1.2,
            "final_standing": final,
            "s_obs": 70,
            "s_used": 61,
            "n": 40,
            "confidence_c": 0.8,
            "neg_share": 0.3,
            "social_badge": "ok",
        },
        meta={
            "as_of": "2026-07-22",
            "methodology_version": "2.1.0",
            "universe_id": "fixture-gics11-v1",
            "score_kind": "editorial_descriptive",
            "market_mode": "fixture",
            "social_mode": "fixture",
        },
    )


def test_open_add_pnl_and_append_only_diary(tmp_path):
    root = tmp_path / "desk"
    first = open_or_add_position(
        ticker="aapl",
        shares=10,
        avg_cost=100,
        buy_reason="Peer-relative value vs quality looked coherent.",
        thesis="Hold while composite stays above sector median.",
        snapshot=_snap("AAPL", 100, 62),
        opened_at="2026-07-22",
        root=root,
    )
    pos = first["position"]
    assert pos["ticker"] == "AAPL"
    assert pos["buy_reason"].startswith("Peer-relative")
    assert first["diary_entry"]["kind"] == "buy"

    added = open_or_add_position(
        ticker="AAPL",
        shares=10,
        avg_cost=120,
        buy_reason="Peer-relative value vs quality looked coherent.",
        thesis="Hold while composite stays above sector median.",
        snapshot=_snap("AAPL", 120, 64),
        root=root,
    )
    assert added["position"]["shares"] == 20
    assert added["position"]["avg_cost"] == 110
    assert added["diary_entry"]["kind"] == "add"

    view = portfolio_view(
        current_by_ticker={"AAPL": {"last_price": 130, "final_standing": 70, "ticker": "AAPL"}},
        current_meta={"as_of": "2026-07-22", "methodology_version": "2.1.0"},
        root=root,
    )
    pnl = view["positions"][0]["pnl"]
    assert pnl["cost_basis"] == 2200
    assert pnl["market_value"] == 2600
    assert pnl["pnl_abs"] == 400
    assert view["held_tickers"] == ["AAPL"]

    dossier = ticker_dossier(
        "AAPL",
        current_row={"ticker": "AAPL", "last_price": 130, "final_standing": 70},
        current_meta={"as_of": "2026-07-22"},
        root=root,
    )
    assert dossier["held"] is True
    assert dossier["purchase_snapshot"]["scores"]["last_price"] == 100
    assert dossier["current_snapshot"]["scores"]["last_price"] == 130
    assert len(dossier["diary"]) == 2

    notes = update_position_notes(
        pos["id"],
        thesis="Updated: wait for quality coverage to stabilize.",
        snapshot=_snap("AAPL", 130, 70),
        root=root,
    )
    assert notes["diary_entry"]["kind"] == "thesis_update"

    closed = close_position(
        pos["id"],
        close_price=125,
        snapshot=_snap("AAPL", 125, 68),
        root=root,
    )
    assert closed["position"]["status"] == "closed"
    kinds = [e["kind"] for e in read_diary(ticker="AAPL", root=root)]
    assert kinds == ["close", "thesis_update", "add", "buy"]

    csv_text = export_diary_csv(root=root)
    assert "AAPL" in csv_text and "final_standing" in csv_text

    summary = summarize_diary_for_vergleich(root=root)
    assert summary["n_entries"] == 4
    assert summary["ticker_counts"]["AAPL"] == 4
    assert summary["kinds"]["buy"] == 1
    assert summary["kinds"]["close"] == 1
    assert summary["score_input"] is False


def test_diary_filter_and_search(tmp_path):
    root = tmp_path / "desk"
    append_diary(
        ticker="MSFT",
        comment="Quiet tape, no change to thesis.",
        snapshot=_snap("MSFT", 400, 58),
        kind="observation",
        root=root,
    )
    append_diary(
        ticker="NVDA",
        comment="Attention spike — watch tilt, not a buy.",
        snapshot=_snap("NVDA", 90, 71),
        kind="note",
        root=root,
    )
    found = read_diary(q="attention", root=root)
    assert [r["ticker"] for r in found] == ["NVDA"]
    msft = read_diary(ticker="msft", root=root)
    assert len(msft) == 1
    empty = read_diary(since="2099-01-01", root=root)
    assert empty == []
    notes = read_diary(kind="note", root=root)
    assert [r["ticker"] for r in notes] == ["NVDA"]
    csv_msft = export_diary_csv(ticker="MSFT", root=root)
    assert "MSFT" in csv_msft
    assert "NVDA" not in csv_msft


def test_diary_marks_desk_then_book_overlay(tmp_path):
    root = tmp_path / "desk"
    opened = open_or_add_position(
        ticker="AAPL",
        shares=10,
        avg_cost=100,
        buy_reason="Peer-relative value vs quality looked coherent.",
        thesis="Hold while composite stays above sector median.",
        snapshot=_snap("AAPL", 100, 62),
        opened_at="2026-07-22",
        root=root,
    )
    buy_marks = opened["diary_entry"]["marks"]
    assert buy_marks["last_price"] == 100
    assert buy_marks["entry_price"] == 100
    assert buy_marks["shares"] == 10
    assert buy_marks["target_price"] is None
    assert buy_marks["final_standing"] == 62

    book = {
        "held": True,
        "entry_price": 95.0,
        "target_price": 140.0,
        "stop_price": 80.0,
        "size": 12.0,
    }
    note = append_diary(
        ticker="AAPL",
        comment="Zielkurs vs mark — no action.",
        snapshot=_snap("AAPL", 130, 70),
        kind="observation",
        desk_position=opened["position"],
        book=book,
        root=root,
    )
    marks = note["marks"]
    assert marks["last_price"] == 130
    assert marks["entry_price"] == 95
    assert marks["target_price"] == 140
    assert marks["stop_price"] == 80
    assert marks["shares"] == 12
    assert marks["final_standing"] == 70
    assert marks["pnl_abs"] == 300
    assert marks["pnl_pct"] == pytest.approx(300 / 1000)
    assert marks["upside_pct"] == pytest.approx(140 / 130 - 1)
    assert marks["upside_from_entry_pct"] == pytest.approx(140 / 95 - 1)
    assert marks["downside_pct"] == pytest.approx(80 / 130 - 1)
    assert marks["reward_risk"] == pytest.approx((140 - 95) / (95 - 80))

    nested = build_diary_marks(
        snapshot=_snap("MSFT", 400, 58),
        book={
            "portfolio": {
                "entry_price": 350,
                "target_price": 480,
                "stop_price": 300,
                "size": 5,
            },
            "thesis": {"target_price": 480, "stop_price": 300},
        },
    )
    assert nested["last_price"] == 400
    assert nested["entry_price"] == 350
    assert nested["target_price"] == 480
    assert nested["stop_price"] == 300
    assert nested["shares"] == 5
    assert nested["pnl_abs"] == 250
    assert nested["upside_pct"] == pytest.approx(480 / 400 - 1)
    assert nested["reward_risk"] == pytest.approx((480 - 350) / (350 - 300))

    csv_text = export_diary_csv(root=root)
    assert "entry_price" in csv_text and "target_price" in csv_text
    assert "140" in csv_text

