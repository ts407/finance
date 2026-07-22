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
