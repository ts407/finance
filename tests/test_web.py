from __future__ import annotations

from fastapi.testclient import TestClient

from standing.web.app import create_app


def test_web_health_and_snapshot():
    client = TestClient(create_app())
    health = client.get("/api/health")
    assert health.status_code == 200
    body = health.json()
    assert body["score_kind"] == "editorial_descriptive"
    assert body["placeholder"] is True

    snap = client.get(
        "/api/snapshot",
        params={"as_of": "2026-07-22", "social": "fixture", "market": "fixture", "prefer_store": False},
    )
    assert snap.status_code == 200
    payload = snap.json()
    assert payload["meta"]["universe_id"]
    assert payload["meta"]["social_mode"] == "fixture"
    assert payload["meta"]["market_mode"] == "fixture"
    assert payload["meta"]["social_is_fixture"] is True
    assert payload["meta"]["served_from"] in ("live", "store")
    assert len(payload["standings"]) > 0
    assert "last_price" in payload["standings"][0]
    assert "value_coverage" in payload["standings"][0]
    assert len(payload["heat"]) > 0

    ticker = payload["standings"][0]["ticker"]
    detail = client.get(
        f"/api/ticker/{ticker}",
        params={"as_of": "2026-07-22", "social": "fixture", "market": "fixture", "prefer_store": False},
    )
    assert detail.status_code == 200
    assert detail.json()["row"]["ticker"] == ticker

    index = client.get("/")
    assert index.status_code == 200
    assert b"Standing" in index.content
    assert b"Export CSV" in index.content
    assert b'id="preset"' in index.content
    assert b'id="market"' in index.content
    assert b'id="social"' in index.content
    assert b'id="fixture-banner"' in index.content
    assert b'id="foot-staleness"' in index.content
    assert b"/static/app.js" in index.content
    assert b'href="/portfolio"' in index.content
    assert b'href="/diary"' in index.content
    assert b"Grund des Kaufens" in index.content


FIXTURE_PARAMS = {
    "as_of": "2026-07-22",
    "social": "fixture",
    "market": "fixture",
    "prefer_store": False,
}


def test_web_filter_and_sort():
    client = TestClient(create_app())
    snap = client.get(
        "/api/snapshot",
        params={**FIXTURE_PARAMS, "q": "tech", "preset": "value_led", "limit": 5},
    )
    assert snap.status_code == 200
    rows = snap.json()["standings"]
    assert len(rows) <= 5
    if len(rows) >= 2:
        assert rows[0]["value"] >= rows[1]["value"]


def test_web_sector_and_presets():
    client = TestClient(create_app())
    base = client.get("/api/snapshot", params=FIXTURE_PARAMS).json()
    sector = next(iter(base["meta"]["sector_counts"]))

    by_sector = client.get(
        "/api/snapshot",
        params={**FIXTURE_PARAMS, "sector": sector},
    ).json()
    assert by_sector["standings"]
    assert all(r["sector"] == sector for r in by_sector["standings"])

    value_led = client.get(
        "/api/snapshot",
        params={**FIXTURE_PARAMS, "preset": "value_led", "limit": 5},
    ).json()["standings"]
    assert value_led
    if len(value_led) >= 2:
        assert value_led[0]["value"] >= value_led[1]["value"]

    attention = client.get(
        "/api/snapshot",
        params={**FIXTURE_PARAMS, "preset": "attention_confirmed"},
    ).json()["standings"]
    for row in attention:
        assert row["social_badge"] == "ok"
        assert abs(row["attention_tilt"]) >= 1.0


def test_web_snapshot_csv():
    client = TestClient(create_app())
    res = client.get(
        "/api/snapshot.csv",
        params={**FIXTURE_PARAMS, "preset": "balanced", "limit": 3},
    )
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    text = res.text
    header = text.splitlines()[0]
    assert "ticker" in header and "sector" in header and "value" in header
    assert "size_bucket" in header
    assert "last_price" in header
    assert len(text.strip().splitlines()) == 4  # header + 3 rows


def test_web_methodology():
    client = TestClient(create_app())
    api = client.get("/api/methodology")
    assert api.status_code == 200
    body = api.json()
    assert body["score_kind"] == "editorial_descriptive"
    assert body["placeholder"] is True
    assert "tilt" in body["formulas"]
    assert body["social_tilt"]["tilt_max"] == 5
    assert "balanced" in body["presets"]

    page = client.get("/methodology")
    assert page.status_code == 200
    assert b"Methodology" in page.content
    assert b"/api/methodology" in page.content
    assert b'href="/portfolio"' in page.content


def test_web_portfolio_diary_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "desk"))
    client = TestClient(create_app())
    params = {**FIXTURE_PARAMS, "prefer_store": False}

    snap = client.get("/api/snapshot", params=params).json()
    ticker = snap["standings"][0]["ticker"]
    raw_px = snap["standings"][0].get("last_price")
    price = float(raw_px if raw_px is not None else 100.0)

    opened = client.post(
        "/api/holdings",
        json={
            "ticker": ticker,
            "shares": 5,
            "avg_cost": price * 0.9,
            "buy_reason": "Grund: coverage and quality look coherent vs peers.",
            "thesis": "These: hold while Final stays descriptive, not a tip.",
            **params,
        },
    )
    assert opened.status_code == 200, opened.text
    body = opened.json()
    assert body["position"]["ticker"] == ticker
    assert body["diary_entry"]["kind"] == "buy"
    position_id = body["position"]["id"]

    book = client.get("/api/holdings", params=params).json()
    assert ticker in book["held_tickers"]
    assert book["positions"][0]["pnl"]["shares"] == 5
    assert book["positions"][0]["buy_reason"].startswith("Grund")

    dossier = client.get(f"/api/holdings/{ticker}", params=params).json()
    assert dossier["held"] is True
    assert dossier["purchase_snapshot"]["scores"]["final_standing"] is not None
    assert dossier["current_snapshot"]["scores"]["last_price"] is not None

    note = client.post(
        "/api/diary",
        json={"ticker": ticker, "comment": "Beobachtung: tilt still bounded.", **params},
    )
    assert note.status_code == 200
    diary = client.get("/api/diary", params={"ticker": ticker}).json()
    assert diary["summary"]["score_input"] is False
    assert diary["summary"]["n_entries"] >= 2
    assert any("Beobachtung" in e["comment"] for e in diary["entries"])

    csv = client.get("/api/diary.csv")
    assert csv.status_code == 200
    assert ticker in csv.text

    closed = client.post(
        f"/api/holdings/{position_id}/close",
        json={"close_price": price, **params},
    )
    assert closed.status_code == 200
    assert closed.json()["position"]["status"] == "closed"

    pages = client.get("/portfolio")
    assert pages.status_code == 200
    assert b"Grund des Kaufens" in pages.content
    diary_page = client.get("/diary")
    assert diary_page.status_code == 200
    assert b"Tagebuch" in diary_page.content
