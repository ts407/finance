"""Repository for scanner snapshots, positions, theses, and journal entries."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from typing import Any

from standing.portfolio.exceptions import (
    FalsifierTooShortError,
    OpenPositionExistsError,
    PositionAlreadyClosedError,
    PositionNotFoundError,
    SnapshotInUseError,
    SnapshotNotFoundError,
    ThesisImmutableError,
)
from standing.portfolio.models import (
    CloseReason,
    JournalEntry,
    JournalEntryType,
    Position,
    PositionStatus,
    ScannerSnapshot,
    ThesisSnapshot,
)

MIN_FALSIFIER_LEN = 20


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _fmt_ts(ts: datetime) -> str:
    return _ensure_utc(ts).isoformat().replace("+00:00", "Z")


def _parse_ts(value: str) -> datetime:
    raw = value.replace("Z", "+00:00")
    dt = datetime.fromisoformat(raw)
    return _ensure_utc(dt)


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def _dumps(obj: dict[str, Any] | None) -> str:
    return json.dumps(obj or {}, separators=(",", ":"), sort_keys=True)


def _loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise TypeError("JSON column must be an object")
    return data


def validate_falsifier(falsifier: str) -> str:
    text = (falsifier or "").strip()
    if len(text) < MIN_FALSIFIER_LEN:
        raise FalsifierTooShortError(
            f"Falsifier must be at least {MIN_FALSIFIER_LEN} characters "
            f"(got {len(text)} after trim)."
        )
    return text


class PortfolioRepository:
    """SQLite-backed portfolio / journal store."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # --- scanner snapshots -------------------------------------------------

    def upsert_scanner_snapshot(
        self,
        *,
        as_of: date,
        ticker: str,
        universe_version: str,
        score: float,
        pillar_fundamentals: float | None = None,
        pillar_momentum: float | None = None,
        pillar_attention: float | None = None,
        coverage_flags: dict[str, Any] | None = None,
        provider_state: dict[str, Any] | None = None,
    ) -> ScannerSnapshot:
        """Insert or replace a (date, ticker, universe_version) snapshot row."""
        cur = self.conn.execute(
            """
            INSERT INTO scanner_snapshots (
              date, ticker, universe_version, score,
              pillar_fundamentals, pillar_momentum, pillar_attention,
              coverage_flags, provider_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (date, ticker, universe_version) DO UPDATE SET
              score = excluded.score,
              pillar_fundamentals = excluded.pillar_fundamentals,
              pillar_momentum = excluded.pillar_momentum,
              pillar_attention = excluded.pillar_attention,
              coverage_flags = excluded.coverage_flags,
              provider_state = excluded.provider_state
            RETURNING snapshot_id
            """,
            (
                as_of.isoformat(),
                ticker.upper(),
                universe_version,
                float(score),
                pillar_fundamentals,
                pillar_momentum,
                pillar_attention,
                _dumps(coverage_flags),
                _dumps(provider_state),
            ),
        )
        snapshot_id = int(cur.fetchone()[0])
        self.conn.commit()
        return self.get_snapshot(snapshot_id)

    def insert_scanner_snapshot(
        self,
        *,
        as_of: date,
        ticker: str,
        universe_version: str,
        score: float,
        pillar_fundamentals: float | None = None,
        pillar_momentum: float | None = None,
        pillar_attention: float | None = None,
        coverage_flags: dict[str, Any] | None = None,
        provider_state: dict[str, Any] | None = None,
    ) -> ScannerSnapshot:
        """Insert a snapshot; raises sqlite3.IntegrityError on duplicate key."""
        cur = self.conn.execute(
            """
            INSERT INTO scanner_snapshots (
              date, ticker, universe_version, score,
              pillar_fundamentals, pillar_momentum, pillar_attention,
              coverage_flags, provider_state
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                as_of.isoformat(),
                ticker.upper(),
                universe_version,
                float(score),
                pillar_fundamentals,
                pillar_momentum,
                pillar_attention,
                _dumps(coverage_flags),
                _dumps(provider_state),
            ),
        )
        self.conn.commit()
        return self.get_snapshot(int(cur.lastrowid))

    def get_snapshot(self, snapshot_id: int) -> ScannerSnapshot:
        row = self.conn.execute(
            "SELECT * FROM scanner_snapshots WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise SnapshotNotFoundError(f"snapshot_id={snapshot_id}")
        return self._row_to_snapshot(row)

    def get_latest_snapshot(
        self, ticker: str, *, universe_version: str | None = None
    ) -> ScannerSnapshot | None:
        ticker = ticker.upper()
        if universe_version is None:
            row = self.conn.execute(
                """
                SELECT * FROM scanner_snapshots
                WHERE ticker = ?
                ORDER BY date DESC, snapshot_id DESC
                LIMIT 1
                """,
                (ticker,),
            ).fetchone()
        else:
            row = self.conn.execute(
                """
                SELECT * FROM scanner_snapshots
                WHERE ticker = ? AND universe_version = ?
                ORDER BY date DESC, snapshot_id DESC
                LIMIT 1
                """,
                (ticker, universe_version),
            ).fetchone()
        return self._row_to_snapshot(row) if row else None

    def delete_snapshot(self, snapshot_id: int) -> None:
        """Delete a snapshot; blocked while positions/journal reference it."""
        try:
            cur = self.conn.execute(
                "DELETE FROM scanner_snapshots WHERE snapshot_id = ?",
                (snapshot_id,),
            )
            if cur.rowcount == 0:
                raise SnapshotNotFoundError(f"snapshot_id={snapshot_id}")
            self.conn.commit()
        except sqlite3.IntegrityError as exc:
            self.conn.rollback()
            raise SnapshotInUseError(
                f"Cannot delete snapshot_id={snapshot_id}: still referenced"
            ) from exc

    # --- positions / thesis (atomic open) ----------------------------------

    def open_position(
        self,
        *,
        ticker: str,
        entry_price: float,
        size: float,
        claim: str,
        mechanism: str,
        falsifier: str,
        target_price: float,
        stop_price: float,
        horizon_days: int,
        conviction: int,
        entry_snapshot_id: int,
        reference_class: str | None = None,
        open_ts: datetime | None = None,
        journal_body: str | None = None,
    ) -> tuple[Position, ThesisSnapshot, JournalEntry]:
        """
        Atomically create position + immutable thesis + journal entry.

        Rolls back on any validation / FK failure.
        """
        ticker = ticker.upper()
        falsifier = validate_falsifier(falsifier)
        if not (1 <= int(conviction) <= 5):
            raise ValueError("conviction must be in 1..5")
        if horizon_days <= 0:
            raise ValueError("horizon_days must be positive")
        if size <= 0:
            raise ValueError("size must be positive")
        if entry_price <= 0:
            raise ValueError("entry_price must be positive")

        # Ensure snapshot exists (FK would catch this, but clearer error).
        self.get_snapshot(entry_snapshot_id)

        existing = self.get_open_position(ticker)
        if existing is not None:
            raise OpenPositionExistsError(f"Open position already exists for {ticker}")

        ts = _ensure_utc(open_ts or _utc_now())
        body = journal_body or (
            f"Opened {ticker} @ {entry_price}: {claim.strip()[:200]}"
        )

        try:
            cur = self.conn.execute(
                """
                INSERT INTO positions (
                  ticker, open_ts, entry_price, size, status, entry_snapshot_id
                ) VALUES (?, ?, ?, ?, 'open', ?)
                """,
                (ticker, _fmt_ts(ts), float(entry_price), float(size), entry_snapshot_id),
            )
            position_id = int(cur.lastrowid)

            cur = self.conn.execute(
                """
                INSERT INTO thesis_snapshots (
                  position_id, claim, mechanism, falsifier,
                  target_price, stop_price, horizon_days, conviction, reference_class
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    position_id,
                    claim.strip(),
                    mechanism.strip(),
                    falsifier,
                    float(target_price),
                    float(stop_price),
                    int(horizon_days),
                    int(conviction),
                    reference_class,
                ),
            )
            thesis_id = int(cur.lastrowid)

            cur = self.conn.execute(
                """
                INSERT INTO journal_entries (
                  ticker, position_id, ts, entry_type, body, linked_snapshot_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker,
                    position_id,
                    _fmt_ts(ts),
                    JournalEntryType.UPDATE.value,
                    body,
                    entry_snapshot_id,
                ),
            )
            entry_id = int(cur.lastrowid)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        position = self.get_position(position_id)
        thesis = self.get_thesis(position_id)
        entry = self.get_journal_entry(entry_id)
        assert thesis is not None
        return position, thesis, entry

    def close_position(
        self,
        *,
        ticker: str,
        close_price: float,
        reason: CloseReason | str,
        exit_note: str,
        close_ts: datetime | None = None,
        linked_snapshot_id: int | None = None,
    ) -> tuple[Position, JournalEntry]:
        """Close an open position and append a mandatory exit_note."""
        ticker = ticker.upper()
        reason = CloseReason(reason)
        note = (exit_note or "").strip()
        if not note:
            raise ValueError("exit_note is required when closing a position")
        if close_price <= 0:
            raise ValueError("close_price must be positive")

        position = self.get_open_position(ticker)
        if position is None:
            # Distinguish already-closed vs never existed.
            any_pos = self.conn.execute(
                "SELECT position_id, status FROM positions WHERE ticker = ? ORDER BY position_id DESC LIMIT 1",
                (ticker,),
            ).fetchone()
            if any_pos is None:
                raise PositionNotFoundError(f"No position for {ticker}")
            if any_pos["status"] == PositionStatus.CLOSED.value:
                raise PositionAlreadyClosedError(f"{ticker} is already closed")
            raise PositionNotFoundError(f"No open position for {ticker}")

        if linked_snapshot_id is not None:
            self.get_snapshot(linked_snapshot_id)

        ts = _ensure_utc(close_ts or _utc_now())
        try:
            self.conn.execute(
                """
                UPDATE positions
                SET status = 'closed',
                    close_ts = ?,
                    close_price = ?,
                    close_reason = ?
                WHERE position_id = ? AND status = 'open'
                """,
                (_fmt_ts(ts), float(close_price), reason.value, position.position_id),
            )
            cur = self.conn.execute(
                """
                INSERT INTO journal_entries (
                  ticker, position_id, ts, entry_type, body, linked_snapshot_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    ticker,
                    position.position_id,
                    _fmt_ts(ts),
                    JournalEntryType.EXIT_NOTE.value,
                    note,
                    linked_snapshot_id,
                ),
            )
            entry_id = int(cur.lastrowid)
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

        return self.get_position(position.position_id), self.get_journal_entry(entry_id)

    def get_position(self, position_id: int) -> Position:
        row = self.conn.execute(
            "SELECT * FROM positions WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        if row is None:
            raise PositionNotFoundError(f"position_id={position_id}")
        return self._row_to_position(row)

    def get_open_position(self, ticker: str) -> Position | None:
        row = self.conn.execute(
            "SELECT * FROM positions WHERE ticker = ? AND status = 'open'",
            (ticker.upper(),),
        ).fetchone()
        return self._row_to_position(row) if row else None

    def list_open_positions(self) -> list[Position]:
        rows = self.conn.execute(
            "SELECT * FROM positions WHERE status = 'open' ORDER BY ticker"
        ).fetchall()
        return [self._row_to_position(r) for r in rows]

    def list_closed_positions(self) -> list[Position]:
        rows = self.conn.execute(
            """
            SELECT * FROM positions
            WHERE status = 'closed'
            ORDER BY close_ts DESC, position_id DESC
            """
        ).fetchall()
        return [self._row_to_position(r) for r in rows]

    def get_thesis(self, position_id: int) -> ThesisSnapshot | None:
        row = self.conn.execute(
            "SELECT * FROM thesis_snapshots WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        return self._row_to_thesis(row) if row else None

    def update_thesis(self, position_id: int, **_fields: Any) -> None:
        """Explicitly blocked — theses are immutable after open."""
        raise ThesisImmutableError(
            f"thesis_snapshots for position_id={position_id} cannot be updated; "
            "append a journal update instead."
        )

    # --- journal -----------------------------------------------------------

    def add_journal_entry(
        self,
        *,
        ticker: str,
        body: str,
        entry_type: JournalEntryType | str = JournalEntryType.UPDATE,
        position_id: int | None = None,
        linked_snapshot_id: int | None = None,
        ts: datetime | None = None,
    ) -> JournalEntry:
        ticker = ticker.upper()
        entry_type = JournalEntryType(entry_type)
        text = (body or "").strip()
        if not text:
            raise ValueError("journal body must be non-empty")
        if linked_snapshot_id is not None:
            self.get_snapshot(linked_snapshot_id)
        if position_id is not None:
            self.get_position(position_id)

        when = _ensure_utc(ts or _utc_now())
        cur = self.conn.execute(
            """
            INSERT INTO journal_entries (
              ticker, position_id, ts, entry_type, body, linked_snapshot_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                ticker,
                position_id,
                _fmt_ts(when),
                entry_type.value,
                text,
                linked_snapshot_id,
            ),
        )
        self.conn.commit()
        return self.get_journal_entry(int(cur.lastrowid))

    def add_watchlist_thesis(
        self,
        *,
        ticker: str,
        thesis: str,
        falsifier: str,
        linked_snapshot_id: int | None = None,
        ts: datetime | None = None,
    ) -> JournalEntry:
        falsifier = validate_falsifier(falsifier)
        claim = (thesis or "").strip()
        if not claim:
            raise ValueError("thesis claim must be non-empty")
        body = f"WATCHLIST\nclaim: {claim}\nfalsifier: {falsifier}"
        return self.add_journal_entry(
            ticker=ticker,
            body=body,
            entry_type=JournalEntryType.WATCHLIST_THESIS,
            linked_snapshot_id=linked_snapshot_id,
            ts=ts,
        )

    def get_journal_entry(self, entry_id: int) -> JournalEntry:
        row = self.conn.execute(
            "SELECT * FROM journal_entries WHERE entry_id = ?",
            (entry_id,),
        ).fetchone()
        if row is None:
            raise LookupError(f"entry_id={entry_id}")
        return self._row_to_journal(row)

    def list_journal(
        self, ticker: str | None = None, *, position_id: int | None = None
    ) -> list[JournalEntry]:
        if position_id is not None:
            rows = self.conn.execute(
                "SELECT * FROM journal_entries WHERE position_id = ? ORDER BY ts, entry_id",
                (position_id,),
            ).fetchall()
        elif ticker is not None:
            rows = self.conn.execute(
                "SELECT * FROM journal_entries WHERE ticker = ? ORDER BY ts, entry_id",
                (ticker.upper(),),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM journal_entries ORDER BY ts, entry_id"
            ).fetchall()
        return [self._row_to_journal(r) for r in rows]

    # --- row mappers -------------------------------------------------------

    @staticmethod
    def _row_to_snapshot(row: sqlite3.Row) -> ScannerSnapshot:
        return ScannerSnapshot(
            snapshot_id=int(row["snapshot_id"]),
            date=_parse_date(row["date"]),
            ticker=str(row["ticker"]),
            universe_version=str(row["universe_version"]),
            score=float(row["score"]),
            pillar_fundamentals=(
                float(row["pillar_fundamentals"])
                if row["pillar_fundamentals"] is not None
                else None
            ),
            pillar_momentum=(
                float(row["pillar_momentum"]) if row["pillar_momentum"] is not None else None
            ),
            pillar_attention=(
                float(row["pillar_attention"]) if row["pillar_attention"] is not None else None
            ),
            coverage_flags=_loads(row["coverage_flags"]),
            provider_state=_loads(row["provider_state"]),
        )

    @staticmethod
    def _row_to_position(row: sqlite3.Row) -> Position:
        reason = row["close_reason"]
        return Position(
            position_id=int(row["position_id"]),
            ticker=str(row["ticker"]),
            open_ts=_parse_ts(row["open_ts"]),
            entry_price=float(row["entry_price"]),
            size=float(row["size"]),
            status=PositionStatus(row["status"]),
            entry_snapshot_id=int(row["entry_snapshot_id"]),
            close_ts=_parse_ts(row["close_ts"]) if row["close_ts"] else None,
            close_price=float(row["close_price"]) if row["close_price"] is not None else None,
            close_reason=CloseReason(reason) if reason else None,
        )

    @staticmethod
    def _row_to_thesis(row: sqlite3.Row) -> ThesisSnapshot:
        return ThesisSnapshot(
            thesis_id=int(row["thesis_id"]),
            position_id=int(row["position_id"]),
            claim=str(row["claim"]),
            mechanism=str(row["mechanism"]),
            falsifier=str(row["falsifier"]),
            target_price=float(row["target_price"]),
            stop_price=float(row["stop_price"]),
            horizon_days=int(row["horizon_days"]),
            conviction=int(row["conviction"]),
            reference_class=row["reference_class"],
        )

    @staticmethod
    def _row_to_journal(row: sqlite3.Row) -> JournalEntry:
        return JournalEntry(
            entry_id=int(row["entry_id"]),
            ticker=str(row["ticker"]),
            ts=_parse_ts(row["ts"]),
            entry_type=JournalEntryType(row["entry_type"]),
            body=str(row["body"]),
            position_id=int(row["position_id"]) if row["position_id"] is not None else None,
            linked_snapshot_id=(
                int(row["linked_snapshot_id"])
                if row["linked_snapshot_id"] is not None
                else None
            ),
        )
