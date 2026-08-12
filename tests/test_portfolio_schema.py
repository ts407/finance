"""Schema migration tests for the portfolio SQLite store."""

from __future__ import annotations

from pathlib import Path

import pytest

from standing.portfolio.db import connect, current_schema_version, migrate


@pytest.fixture()
def conn(tmp_path: Path):
    c = connect(tmp_path / "test.db")
    yield c
    c.close()


def test_migrate_creates_all_tables(conn):
    version = migrate(conn)
    assert version == 1
    tables = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    }
    assert {
        "schema_migrations",
        "scanner_snapshots",
        "positions",
        "thesis_snapshots",
        "journal_entries",
    }.issubset(tables)


def test_migrate_is_idempotent(conn):
    assert migrate(conn) == 1
    assert migrate(conn) == 1
    assert current_schema_version(conn) == 1
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    assert [r["version"] for r in rows] == [1]


def test_schema_version_recorded(conn):
    migrate(conn)
    row = conn.execute(
        "SELECT version, applied_at FROM schema_migrations WHERE version = 1"
    ).fetchone()
    assert row is not None
    assert row["applied_at"]


def test_foreign_keys_enabled(conn):
    migrate(conn)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_unique_snapshot_constraint(conn):
    migrate(conn)
    conn.execute(
        """
        INSERT INTO scanner_snapshots (
          date, ticker, universe_version, score
        ) VALUES ('2026-07-22', 'AAPL', 'u1', 70.0)
        """
    )
    conn.commit()
    with pytest.raises(Exception):
        conn.execute(
            """
            INSERT INTO scanner_snapshots (
              date, ticker, universe_version, score
            ) VALUES ('2026-07-22', 'AAPL', 'u1', 71.0)
            """
        )


def test_thesis_update_trigger_blocks(conn):
    migrate(conn)
    conn.execute(
        """
        INSERT INTO scanner_snapshots (date, ticker, universe_version, score)
        VALUES ('2026-07-22', 'MSFT', 'u1', 80.0)
        """
    )
    conn.execute(
        """
        INSERT INTO positions (
          ticker, open_ts, entry_price, size, status, entry_snapshot_id
        ) VALUES ('MSFT', '2026-07-22T12:00:00Z', 100.0, 10, 'open', 1)
        """
    )
    conn.execute(
        """
        INSERT INTO thesis_snapshots (
          position_id, claim, mechanism, falsifier,
          target_price, stop_price, horizon_days, conviction
        ) VALUES (
          1, 'claim', 'mech',
          'Falsifier must be twenty+ chars',
          120.0, 90.0, 90, 3
        )
        """
    )
    conn.commit()
    with pytest.raises(Exception) as exc:
        conn.execute(
            "UPDATE thesis_snapshots SET claim = 'edited' WHERE thesis_id = 1"
        )
    assert "immutable" in str(exc.value).lower()


def test_journal_append_only_trigger(conn):
    migrate(conn)
    conn.execute(
        """
        INSERT INTO journal_entries (ticker, ts, entry_type, body)
        VALUES ('AAPL', '2026-07-22T12:00:00Z', 'update', 'hello')
        """
    )
    conn.commit()
    with pytest.raises(Exception) as exc:
        conn.execute("UPDATE journal_entries SET body = 'nope' WHERE entry_id = 1")
    assert "append-only" in str(exc.value).lower()
