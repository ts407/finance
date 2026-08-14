from __future__ import annotations

import base64
from pathlib import Path

import pytest

from standing.desk.entwurf import (
    FALSIFIER_HINT,
    MECHANISM_HINT,
    PNG_MAGIC,
    decode_png_b64,
    develop_draft,
    extract_tickers,
    persist_entwurf,
    validate_http_url,
)
from standing.desk.ledger import capture_snapshot, extract_fundamentals, fundamentals_display, read_diary

PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_validate_http_url():
    assert validate_http_url("https://example.com/a") == "https://example.com/a"
    with pytest.raises(ValueError):
        validate_http_url("ftp://example.com")
    with pytest.raises(ValueError):
        validate_http_url("not-a-url")


def test_extract_tickers_prefers_universe():
    text = "Watch THE tape on AAPL and MSFT after the 10-Q."
    assert extract_tickers(text, universe={"MSFT", "NVDA"}) == ["MSFT"]
    found = extract_tickers(text)
    assert "AAPL" in found and "MSFT" in found
    assert "THE" not in found


def test_develop_text_draft_is_deterministic():
    developed = develop_draft(
        source="text",
        text="MSFT: cloud mix still compounding.\nNot a tip.",
        universe={"MSFT", "AAPL"},
    )
    assert developed["ticker"] == "MSFT"
    assert developed["draft"]["thesis"].startswith("MSFT")
    assert developed["draft"]["mechanism"] == MECHANISM_HINT
    assert developed["draft"]["falsifier"] == FALSIFIER_HINT
    assert "cloud mix" in developed["draft"]["buy_reason"]


def test_decode_png_and_persist_attachment(tmp_path: Path):
    data, name = decode_png_b64(f"data:image/png;base64,{PNG_B64}", "chart.PNG")
    assert data.startswith(PNG_MAGIC)
    assert name.lower().endswith(".png")
    snap = capture_snapshot(
        {"ticker": "AAPL", "last_price": 100, "pe_ttm": 22.5, "final_standing": 61, "value": 50, "quality": 55, "momentum": 48},
        meta={"as_of": "2026-07-22"},
    )
    developed = develop_draft(source="png", filename=name, ticker="AAPL")
    entry = persist_entwurf(developed, snapshot=snap, png_bytes=data, original_filename=name, root=tmp_path)
    assert entry["kind"] == "entwurf"
    assert entry["entwurf"]["score_input"] is False
    assert entry["entwurf"]["attachment"]["name"].endswith(".png")
    stored = tmp_path / "attachments" / entry["entwurf"]["attachment"]["name"]
    assert stored.is_file() and stored.read_bytes().startswith(PNG_MAGIC)
    assert read_diary(kind="entwurf", root=tmp_path)[0]["id"] == entry["id"]


def test_extract_fundamentals_skips_missing():
    funds = extract_fundamentals({"pe_ttm": 18.2, "pb": None, "invented_kgv": 99})
    assert funds["pe_ttm"] == 18.2
    assert "pb" not in funds
    assert "invented_kgv" not in funds
    labels = [pair[0] for pair in fundamentals_display(funds)]
    assert "KGV (TTM)" in labels
    assert "KUV" not in labels
