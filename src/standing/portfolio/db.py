"""SQLite connection helpers and migration runner."""

from __future__ import annotations

import sqlite3
from importlib import resources
from pathlib import Path

from standing.config import ROOT

DEFAULT_DB_PATH = ROOT / "artifacts" / "portfolio" / "standing.db"

# Ordered migration versions → SQL resource names under standing.portfolio.migrations
MIGRATIONS: list[tuple[int, str]] = [
    (1, "001_initial.sql"),
    (2, "002_daily_marks.sql"),
]


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Open a SQLite connection with foreign keys enabled."""
    path = Path(db_path) if db_path is not None else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _load_migration_sql(name: str) -> str:
    pkg = resources.files("standing.portfolio.migrations")
    text = (pkg / name).read_text(encoding="utf-8")
    return text


def current_schema_version(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
    ).fetchone()
    if row is None:
        return 0
    ver = conn.execute("SELECT COALESCE(MAX(version), 0) AS v FROM schema_migrations").fetchone()
    return int(ver["v"]) if ver else 0


def migrate(conn: sqlite3.Connection) -> int:
    """
    Apply pending migrations. Returns the schema version after migrate.

    Idempotent: already-applied versions are skipped.
    """
    applied = current_schema_version(conn)
    for version, sql_name in MIGRATIONS:
        if version <= applied:
            continue
        sql = _load_migration_sql(sql_name)
        conn.executescript(sql)
        # schema_migrations may be created by the first migration script
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (?, datetime('now'))",
            (version,),
        )
        conn.commit()
        applied = version
    return applied
