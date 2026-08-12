"""Homelab/data-path resilience tests for serve + health."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from standing.config import resolve_root
from standing.pipeline.snapshot import run_snapshot
from standing.pipeline.store import persist_immutable
from standing.providers import build_market_provider, build_social_provider
from standing.web.app import create_app


def test_resolve_root_finds_checkout():
    root = resolve_root()
    assert (root / "config" / "scoring.yaml").is_file()


def test_resolve_root_env_override(tmp_path: Path, monkeypatch):
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "scoring.yaml").write_text("methodology_version: '9'\nscore_kind: x\nplaceholder: true\nbase: {}\nsocial_tilt: {}\nshrinkage: {}\nsocial_pipeline: {}\nuniverse: {}\n")
    monkeypatch.setenv("STANDING_ROOT", str(tmp_path))
    assert resolve_root() == tmp_path.resolve()


def test_health_exposes_data_paths(tmp_path: Path, monkeypatch):
    db = tmp_path / "p.db"
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(db))
    client = TestClient(create_app())
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["portfolio_db_ok"] is True
    assert str(db) in body["portfolio_db"] or body["portfolio_db"].endswith("p.db")
    assert "root" in body
    assert "prefer_store" in body
    assert "default_market" in body


def test_snapshot_falls_back_to_latest_store(tmp_path: Path, monkeypatch):
    snap_root = tmp_path / "snaps"
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "p.db"))
    monkeypatch.setattr("standing.pipeline.store.DEFAULT_SNAPSHOT_ROOT", snap_root)
    monkeypatch.setattr("standing.web.app._prefer_store_default", lambda: True)

    snap = run_snapshot(
        as_of=date(2026, 7, 22),
        market=build_market_provider("fixture"),
        social=build_social_provider("fixture", history_days=14),
    )
    persist_immutable(snap, root=snap_root)

    client = TestClient(create_app())
    # Request a day with no store file — should fall back to 2026-07-22
    resp = client.get(
        "/api/snapshot",
        params={
            "as_of": "2099-01-01",
            "market": "fixture",
            "social": "fixture",
            "prefer_store": True,
        },
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert payload["meta"]["as_of"] == "2026-07-22"
    assert payload["meta"]["as_of_fallback"] is True
    assert len(payload["standings"]) > 0
    assert payload["meta"]["portfolio_db_ok"] is True
    assert (payload["meta"]["portfolio_sync_n"] or 0) > 0


def test_snapshot_omitted_as_of_uses_latest_store(tmp_path: Path, monkeypatch):
    snap_root = tmp_path / "snaps"
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "p.db"))
    monkeypatch.setattr("standing.pipeline.store.DEFAULT_SNAPSHOT_ROOT", snap_root)
    monkeypatch.setattr("standing.web.app._prefer_store_default", lambda: True)

    snap = run_snapshot(
        as_of=date(2026, 7, 22),
        market=build_market_provider("fixture"),
        social=build_social_provider("fixture", history_days=14),
    )
    persist_immutable(snap, root=snap_root)

    client = TestClient(create_app())
    resp = client.get(
        "/api/snapshot",
        params={"market": "fixture", "social": "fixture", "prefer_store": True},
    )
    assert resp.status_code == 200
    assert resp.json()["meta"]["as_of"] == "2026-07-22"
    assert resp.json()["meta"]["as_of_fallback"] is True
