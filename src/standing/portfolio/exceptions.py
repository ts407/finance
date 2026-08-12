"""Portfolio / journal domain errors."""

from __future__ import annotations


class PortfolioError(Exception):
    """Base error for portfolio operations."""


class FalsifierTooShortError(PortfolioError):
    """Falsifier must be non-empty and at least 20 characters."""


class SnapshotNotFoundError(PortfolioError):
    """Referenced scanner_snapshot does not exist."""


class SnapshotInUseError(PortfolioError):
    """Cannot delete a snapshot still referenced by positions or journal."""


class PositionNotFoundError(PortfolioError):
    """No matching open/closed position."""


class PositionAlreadyClosedError(PortfolioError):
    """Attempted to close a position that is already closed."""


class ThesisImmutableError(PortfolioError):
    """thesis_snapshots are immutable after insert."""


class OpenPositionExistsError(PortfolioError):
    """Ticker already has an open position."""
