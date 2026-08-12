from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from standing.logging_config import get_logger

log = get_logger("config")


def resolve_root() -> Path:
    """
    Locate the Standing checkout (directory that contains ``config/scoring.yaml``).

    Order:
    1. ``STANDING_ROOT`` env
    2. Walk up from this file (editable ``src/standing`` layout)
    3. Walk up from process cwd
    """
    env = (os.environ.get("STANDING_ROOT") or "").strip()
    if env:
        candidate = Path(env).expanduser().resolve()
        if (candidate / "config" / "scoring.yaml").is_file():
            return candidate
        # Still honour an explicit override even if scoring.yaml is missing —
        # operators may mount config elsewhere, but artifacts should land here.
        return candidate

    here = Path(__file__).resolve()
    candidates: list[Path] = []
    # src/standing/config.py → repo root is parents[2]
    if len(here.parents) >= 3:
        candidates.append(here.parents[2])
    if len(here.parents) >= 2:
        candidates.append(here.parents[1])
    cur = Path.cwd().resolve()
    for _ in range(8):
        candidates.append(cur)
        if cur.parent == cur:
            break
        cur = cur.parent

    seen: set[Path] = set()
    for c in candidates:
        c = c.resolve()
        if c in seen:
            continue
        seen.add(c)
        if (c / "config" / "scoring.yaml").is_file():
            return c

    # Fallback for broken installs: keep historical parents[2] behaviour.
    return here.parents[2]


ROOT = resolve_root()
DEFAULT_SCORING_PATH = ROOT / "config" / "scoring.yaml"
DEFAULT_RULES_PATH = ROOT / "config" / "rules.json"


def set_dotted(raw: dict[str, Any], dotted: str, value: Any) -> None:
    """
    Set ``raw[a][b][c] = value`` from a dotted path ``"a.b.c"`` in place.

    Nested dicts along the path are copy-on-write (replaced with shallow copies)
    so shared sub-dicts from the source config are never mutated.
    """
    node: Any = raw
    parts = dotted.split(".")
    for part in parts[:-1]:
        child = node[part]
        if not isinstance(child, dict):
            raise TypeError(f"Cannot override non-dict path segment '{part}' in {dotted}")
        node[part] = dict(child)
        node = node[part]
    node[parts[-1]] = value


def apply_overrides(raw: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``raw`` with every dotted-path override applied."""
    out = copy.deepcopy(raw)
    for dotted, value in overrides.items():
        set_dotted(out, dotted, value)
    return out


@dataclass(frozen=True)
class ScoringConfig:
    raw: dict[str, Any]
    path: Path

    @property
    def methodology_version(self) -> str:
        return str(self.raw["methodology_version"])

    @property
    def score_kind(self) -> str:
        return str(self.raw["score_kind"])

    @property
    def placeholder(self) -> bool:
        return bool(self.raw.get("placeholder", False))

    @property
    def base(self) -> dict[str, Any]:
        return self.raw["base"]

    @property
    def social_tilt(self) -> dict[str, Any]:
        return self.raw["social_tilt"]

    @property
    def shrinkage(self) -> dict[str, Any]:
        return self.raw["shrinkage"]

    @property
    def social_pipeline(self) -> dict[str, Any]:
        return self.raw["social_pipeline"]

    @property
    def universe(self) -> dict[str, Any]:
        return self.raw["universe"]


def load_scoring_config(path: Path | None = None) -> ScoringConfig:
    cfg_path = path or DEFAULT_SCORING_PATH
    log.debug("Loading scoring config from %s (ROOT=%s)", cfg_path, ROOT)
    if not cfg_path.is_file():
        raise FileNotFoundError(
            f"scoring.yaml not found at {cfg_path}. "
            f"Set STANDING_ROOT to the Standing checkout (current ROOT={ROOT})."
        )
    with cfg_path.open() as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        log.error("Invalid scoring config at %s", cfg_path)
        raise ValueError(f"Invalid scoring config at {cfg_path}")
    cfg = ScoringConfig(raw=raw, path=cfg_path)
    log.info(
        "Loaded scoring config methodology=%s score_kind=%s placeholder=%s",
        cfg.methodology_version,
        cfg.score_kind,
        cfg.placeholder,
    )
    return cfg


def load_rules(path: Path | None = None) -> dict[str, Any]:
    rules_path = path or DEFAULT_RULES_PATH
    log.debug("Loading universe rules from %s", rules_path)
    with rules_path.open() as f:
        rules = json.load(f)
    log.info(
        "Loaded universe rules universe_id=%s",
        rules.get("universe_id", "unknown"),
    )
    return rules
