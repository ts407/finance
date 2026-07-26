"""Immutable daily snapshot store for forward-evaluation logging.

Layout:
  artifacts/snapshots/{as_of}/standings.csv
  artifacts/snapshots/{as_of}/meta.json

First successful write for an as_of wins. Later writes raise SnapshotExistsError
unless force=True (then the prior day folder is copied to runs/ before overwrite).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from standing.config import ROOT
from standing.pipeline.snapshot import StandingSnapshot

DEFAULT_SNAPSHOT_ROOT = ROOT / "artifacts" / "snapshots"


class SnapshotExistsError(RuntimeError):
    pass


class SnapshotMissingError(RuntimeError):
    pass


def day_dir(root: Path, as_of: date) -> Path:
    return Path(root) / as_of.isoformat()


def persist_immutable(
    snapshot: StandingSnapshot,
    *,
    root: Path | None = None,
    force: bool = False,
    extra_meta: dict[str, Any] | None = None,
) -> Path:
    """
    Persist a day snapshot immutably.

    Returns path to standings.csv.
    """
    root = Path(root) if root else DEFAULT_SNAPSHOT_ROOT
    ddir = day_dir(root, snapshot.as_of)
    csv_path = ddir / "standings.csv"
    meta_path = ddir / "meta.json"

    if csv_path.exists() and meta_path.exists() and not force:
        raise SnapshotExistsError(
            f"Immutable snapshot already exists for {snapshot.as_of.isoformat()} at {ddir}. "
            "Refuse overwrite (forward-eval log). Use force=True only for recovery."
        )

    if csv_path.exists() and force:
        runs = ddir / "runs"
        runs.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(csv_path, runs / f"standings_{stamp}.csv")
        if meta_path.exists():
            shutil.copy2(meta_path, runs / f"meta_{stamp}.json")

    ddir.mkdir(parents=True, exist_ok=True)
    snapshot.standings.to_csv(csv_path, index=False)

    created = datetime.now(timezone.utc).isoformat()
    meta: dict[str, Any] = {
        "as_of": snapshot.as_of.isoformat(),
        "universe_id": snapshot.universe_id,
        "methodology_version": snapshot.methodology_version,
        "score_kind": snapshot.score_kind,
        "placeholder": snapshot.placeholder,
        "created_at_utc": created,
        "immutable": True,
        "n_names": int(len(snapshot.standings)),
        "meta": snapshot.meta,
    }
    if extra_meta:
        meta.update(extra_meta)
    meta_path.write_text(json.dumps(meta, indent=2, default=str))
    return csv_path


@dataclass(frozen=True)
class LoadedSnapshot:
    as_of: date
    universe_id: str
    methodology_version: str
    score_kind: str
    placeholder: bool
    standings: pd.DataFrame
    meta: dict[str, Any]
    path: Path

    def to_standing_snapshot(self) -> StandingSnapshot:
        return StandingSnapshot(
            as_of=self.as_of,
            universe_id=self.universe_id,
            methodology_version=self.methodology_version,
            score_kind=self.score_kind,
            placeholder=self.placeholder,
            standings=self.standings,
            meta=dict(self.meta.get("meta") or self.meta),
        )


def load_immutable(as_of: date, *, root: Path | None = None) -> LoadedSnapshot:
    root = Path(root) if root else DEFAULT_SNAPSHOT_ROOT
    ddir = day_dir(root, as_of)
    csv_path = ddir / "standings.csv"
    meta_path = ddir / "meta.json"
    if not csv_path.exists() or not meta_path.exists():
        raise SnapshotMissingError(f"No immutable snapshot for {as_of.isoformat()} under {root}")
    payload = json.loads(meta_path.read_text())
    # Do not treat the literal "nan" in string columns as missing (value_ev_rung).
    standings = pd.read_csv(csv_path, keep_default_na=False, na_values=[""])
    return LoadedSnapshot(
        as_of=date.fromisoformat(str(payload["as_of"])),
        universe_id=str(payload["universe_id"]),
        methodology_version=str(payload["methodology_version"]),
        score_kind=str(payload["score_kind"]),
        placeholder=bool(payload.get("placeholder", False)),
        standings=standings,
        meta=payload,
        path=ddir,
    )


def list_snapshot_days(*, root: Path | None = None) -> list[date]:
    root = Path(root) if root else DEFAULT_SNAPSHOT_ROOT
    if not root.exists():
        return []
    days: list[date] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "meta.json").exists():
            try:
                days.append(date.fromisoformat(child.name))
            except ValueError:
                continue
    return days
