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

    snap = client.get("/api/snapshot", params={"as_of": "2026-07-22"})
    assert snap.status_code == 200
    payload = snap.json()
    assert payload["meta"]["universe_id"]
    assert len(payload["standings"]) > 0
    assert "final_standing" in payload["standings"][0]
    assert len(payload["heat"]) > 0

    ticker = payload["standings"][0]["ticker"]
    detail = client.get(f"/api/ticker/{ticker}", params={"as_of": "2026-07-22"})
    assert detail.status_code == 200
    assert detail.json()["row"]["ticker"] == ticker

    index = client.get("/")
    assert index.status_code == 200
    assert b"Standing" in index.content
    assert b"Export CSV" in index.content
    assert b'id="preset"' in index.content
    assert b"/static/app.js" in index.content


def test_web_filter_and_sort():
    client = TestClient(create_app())
    snap = client.get(
        "/api/snapshot",
        params={"as_of": "2026-07-22", "q": "tech", "sort": "value", "limit": 5},
    )
    assert snap.status_code == 200
    rows = snap.json()["standings"]
    assert len(rows) <= 5
    if len(rows) >= 2:
        assert rows[0]["value"] >= rows[1]["value"]


def test_web_sector_and_presets():
    client = TestClient(create_app())
    base = client.get("/api/snapshot", params={"as_of": "2026-07-22"}).json()
    sector = next(iter(base["meta"]["sector_counts"]))

    by_sector = client.get(
        "/api/snapshot",
        params={"as_of": "2026-07-22", "sector": sector},
    ).json()
    assert by_sector["standings"]
    assert all(r["sector"] == sector for r in by_sector["standings"])

    value_led = client.get(
        "/api/snapshot",
        params={"as_of": "2026-07-22", "preset": "value_led", "limit": 5},
    ).json()["standings"]
    assert value_led
    if len(value_led) >= 2:
        assert value_led[0]["value"] >= value_led[1]["value"]

    attention = client.get(
        "/api/snapshot",
        params={"as_of": "2026-07-22", "preset": "attention_confirmed"},
    ).json()["standings"]
    for row in attention:
        assert row["social_badge"] == "ok"
        assert abs(row["attention_tilt"]) >= 1.0


def test_web_snapshot_csv():
    client = TestClient(create_app())
    res = client.get(
        "/api/snapshot.csv",
        params={"as_of": "2026-07-22", "preset": "balanced", "limit": 3},
    )
    assert res.status_code == 200
    assert "text/csv" in res.headers["content-type"]
    text = res.text
    assert "ticker,sector,value" in text.splitlines()[0]
    assert len(text.strip().splitlines()) == 4  # header + 3 rows


def test_web_methodology():
    client = TestClient(create_app())
    api = client.get("/api/methodology")
    assert api.status_code == 200
    body = api.json()
    assert body["score_kind"] == "editorial_descriptive"
    assert body["placeholder"] is True
    assert "tilt" in body["formulas"]
    assert body["social_tilt"]["tilt_max"] == 10
    assert "balanced" in body["presets"]

    page = client.get("/methodology")
    assert page.status_code == 200
    assert b"Methodology" in page.content
    assert b"/api/methodology" in page.content
