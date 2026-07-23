from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from standing.optimization.paths import LOOP_LOG_PATH, ensure_layout


def append_log(entry: dict[str, Any], *, path: Path | None = None) -> Path:
    """Append one JSON line to the optimization log (append-only)."""
    ensure_layout()
    log_path = path or LOOP_LOG_PATH
    payload = dict(entry)
    payload.setdefault("timestamp_utc", datetime.now(timezone.utc).isoformat())
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")
    return log_path


def read_log(*, path: Path | None = None, tail: int | None = None) -> list[dict[str, Any]]:
    """Read optimization log entries; optionally only the last ``tail`` rows."""
    log_path = path or LOOP_LOG_PATH
    if not log_path.exists() or log_path.stat().st_size == 0:
        return []
    rows: list[dict[str, Any]] = []
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    if tail is not None and tail >= 0:
        return rows[-tail:]
    return rows


def latest_entry(*, path: Path | None = None) -> dict[str, Any] | None:
    rows = read_log(path=path, tail=1)
    return rows[-1] if rows else None
