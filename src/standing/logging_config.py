"""Central logging setup for Standing (CLI, pipeline, web)."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

DEFAULT_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
DATE_FORMAT = "%Y-%m-%dT%H:%M:%S"
ENV_LEVEL = "STANDING_LOG_LEVEL"
ROOT_LOGGER_NAME = "standing"

_CONFIGURED = False


def resolve_level(level: str | int | None = None) -> int:
    """Resolve a log level from an explicit value or STANDING_LOG_LEVEL."""
    if isinstance(level, int):
        return level
    raw = level or os.environ.get(ENV_LEVEL) or "INFO"
    if isinstance(raw, str):
        name = raw.strip().upper()
        mapped = logging.getLevelNamesMapping().get(name)
        if mapped is not None:
            return mapped
        raise ValueError(f"Unknown log level: {raw!r}")
    raise TypeError(f"Unsupported log level type: {type(level)!r}")


def configure_logging(
    level: str | int | None = None,
    *,
    stream: Any | None = None,
    force: bool = False,
) -> logging.Logger:
    """
    Configure the ``standing`` logger hierarchy once.

    Safe to call repeatedly; pass ``force=True`` to reconfigure (e.g. tests).
    """
    global _CONFIGURED
    resolved = resolve_level(level)
    root = logging.getLogger(ROOT_LOGGER_NAME)

    if _CONFIGURED and not force:
        root.setLevel(resolved)
        return root

    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(logging.Formatter(DEFAULT_FORMAT, datefmt=DATE_FORMAT))
    handler.setLevel(resolved)

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved)
    root.propagate = False

    _CONFIGURED = True
    return root


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger under ``standing`` (or the package root)."""
    if not name or name == ROOT_LOGGER_NAME:
        return logging.getLogger(ROOT_LOGGER_NAME)
    if name.startswith(f"{ROOT_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
