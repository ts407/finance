-- Optional daily marks for attribution / recalibrate (v2)

CREATE TABLE IF NOT EXISTS daily_marks (
  date TEXT NOT NULL,
  ticker TEXT NOT NULL,
  close_price REAL NOT NULL CHECK (close_price > 0),
  UNIQUE (date, ticker)
);

CREATE INDEX IF NOT EXISTS idx_daily_marks_date ON daily_marks (date);
CREATE INDEX IF NOT EXISTS idx_daily_marks_ticker ON daily_marks (ticker, date);
