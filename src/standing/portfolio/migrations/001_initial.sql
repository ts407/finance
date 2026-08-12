-- Portfolio / journal / scanner snapshot schema (v1)
-- All timestamps stored as UTC ISO-8601 text (…Z or +00:00).

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scanner_snapshots (
  snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
  date TEXT NOT NULL,
  ticker TEXT NOT NULL,
  universe_version TEXT NOT NULL,
  score REAL NOT NULL,
  pillar_fundamentals REAL,
  pillar_momentum REAL,
  pillar_attention REAL,
  coverage_flags TEXT NOT NULL DEFAULT '{}',
  provider_state TEXT NOT NULL DEFAULT '{}',
  UNIQUE (date, ticker, universe_version)
);

CREATE INDEX IF NOT EXISTS idx_scanner_snapshots_date
  ON scanner_snapshots (date);
CREATE INDEX IF NOT EXISTS idx_scanner_snapshots_ticker_date
  ON scanner_snapshots (ticker, date);

CREATE TABLE IF NOT EXISTS positions (
  position_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  open_ts TEXT NOT NULL,
  entry_price REAL NOT NULL,
  size REAL NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('open', 'closed')),
  close_ts TEXT,
  close_price REAL,
  close_reason TEXT CHECK (
    close_reason IS NULL
    OR close_reason IN ('target', 'stop', 'thesis_broken', 'rebalance', 'manual')
  ),
  entry_snapshot_id INTEGER NOT NULL
    REFERENCES scanner_snapshots (snapshot_id) ON DELETE RESTRICT,
  CHECK (
    (status = 'open' AND close_ts IS NULL AND close_price IS NULL AND close_reason IS NULL)
    OR (status = 'closed' AND close_ts IS NOT NULL AND close_price IS NOT NULL AND close_reason IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_positions_status ON positions (status);
CREATE INDEX IF NOT EXISTS idx_positions_ticker_status ON positions (ticker, status);

-- At most one open position per ticker.
CREATE UNIQUE INDEX IF NOT EXISTS idx_positions_one_open_per_ticker
  ON positions (ticker)
  WHERE status = 'open';

CREATE TABLE IF NOT EXISTS thesis_snapshots (
  thesis_id INTEGER PRIMARY KEY AUTOINCREMENT,
  position_id INTEGER NOT NULL UNIQUE
    REFERENCES positions (position_id) ON DELETE RESTRICT,
  claim TEXT NOT NULL,
  mechanism TEXT NOT NULL,
  falsifier TEXT NOT NULL,
  target_price REAL NOT NULL,
  stop_price REAL NOT NULL,
  horizon_days INTEGER NOT NULL,
  conviction INTEGER NOT NULL CHECK (conviction BETWEEN 1 AND 5),
  reference_class TEXT,
  CHECK (length(trim(falsifier)) >= 20)
);

CREATE TABLE IF NOT EXISTS journal_entries (
  entry_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticker TEXT NOT NULL,
  position_id INTEGER
    REFERENCES positions (position_id) ON DELETE RESTRICT,
  ts TEXT NOT NULL,
  entry_type TEXT NOT NULL CHECK (
    entry_type IN ('watchlist_thesis', 'update', 'exit_note')
  ),
  body TEXT NOT NULL,
  linked_snapshot_id INTEGER
    REFERENCES scanner_snapshots (snapshot_id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_journal_ticker_ts ON journal_entries (ticker, ts);
CREATE INDEX IF NOT EXISTS idx_journal_position ON journal_entries (position_id);

-- thesis_snapshots are immutable after insert.
CREATE TRIGGER IF NOT EXISTS thesis_snapshots_no_update
BEFORE UPDATE ON thesis_snapshots
BEGIN
  SELECT RAISE(ABORT, 'thesis_snapshots are immutable');
END;

CREATE TRIGGER IF NOT EXISTS thesis_snapshots_no_delete
BEFORE DELETE ON thesis_snapshots
BEGIN
  SELECT RAISE(ABORT, 'thesis_snapshots are immutable');
END;

-- journal_entries are append-only (no UPDATE/DELETE).
CREATE TRIGGER IF NOT EXISTS journal_entries_no_update
BEFORE UPDATE ON journal_entries
BEGIN
  SELECT RAISE(ABORT, 'journal_entries are append-only');
END;

CREATE TRIGGER IF NOT EXISTS journal_entries_no_delete
BEFORE DELETE ON journal_entries
BEGIN
  SELECT RAISE(ABORT, 'journal_entries are append-only');
END;
