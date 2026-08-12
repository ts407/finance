"""Dataclass models for portfolio, thesis, journal, and scanner snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any


class PositionStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class CloseReason(str, Enum):
    TARGET = "target"
    STOP = "stop"
    THESIS_BROKEN = "thesis_broken"
    REBALANCE = "rebalance"
    MANUAL = "manual"


class JournalEntryType(str, Enum):
    WATCHLIST_THESIS = "watchlist_thesis"
    UPDATE = "update"
    EXIT_NOTE = "exit_note"


@dataclass(frozen=True)
class ScannerSnapshot:
    snapshot_id: int
    date: date
    ticker: str
    universe_version: str
    score: float
    pillar_fundamentals: float | None
    pillar_momentum: float | None
    pillar_attention: float | None
    coverage_flags: dict[str, Any]
    provider_state: dict[str, Any]


@dataclass(frozen=True)
class Position:
    position_id: int
    ticker: str
    open_ts: datetime
    entry_price: float
    size: float
    status: PositionStatus
    entry_snapshot_id: int
    close_ts: datetime | None = None
    close_price: float | None = None
    close_reason: CloseReason | None = None


@dataclass(frozen=True)
class ThesisSnapshot:
    thesis_id: int
    position_id: int
    claim: str
    mechanism: str
    falsifier: str
    target_price: float
    stop_price: float
    horizon_days: int
    conviction: int
    reference_class: str | None = None


@dataclass(frozen=True)
class JournalEntry:
    entry_id: int
    ticker: str
    ts: datetime
    entry_type: JournalEntryType
    body: str
    position_id: int | None = None
    linked_snapshot_id: int | None = None
