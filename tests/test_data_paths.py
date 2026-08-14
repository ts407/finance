from __future__ import annotations

from pathlib import Path

from standing.config import default_desk_dir, default_portfolio_db, resolve_data_root


def test_data_root_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_DATA_DIR", str(tmp_path / "data"))
    assert resolve_data_root() == (tmp_path / "data").resolve()
    assert default_portfolio_db() == (tmp_path / "data" / "portfolio" / "standing.db").resolve()
    assert default_desk_dir() == (tmp_path / "data" / "diary").resolve()


def test_explicit_portfolio_and_diary_override_data_root(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("STANDING_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("STANDING_PORTFOLIO_DB", str(tmp_path / "book.db"))
    monkeypatch.setenv("STANDING_DESK_DIR", str(tmp_path / "notes"))
    assert default_portfolio_db() == (tmp_path / "book.db").resolve()
    assert default_desk_dir() == (tmp_path / "notes").resolve()


def test_defaults_are_outside_git_checkout(monkeypatch):
    monkeypatch.delenv("STANDING_DATA_DIR", raising=False)
    monkeypatch.delenv("STANDING_PORTFOLIO_DB", raising=False)
    monkeypatch.delenv("STANDING_DESK_DIR", raising=False)
    monkeypatch.setattr("standing.config.sys.platform", "darwin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: Path("/Users/test")))
    root = resolve_data_root()
    assert root == Path("/Users/test/Library/Application Support/Standing")
    assert default_portfolio_db() == root / "portfolio" / "standing.db"
    assert default_desk_dir() == root / "diary"
