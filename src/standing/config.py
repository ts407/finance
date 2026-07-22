from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SCORING_PATH = ROOT / "config" / "scoring.yaml"
DEFAULT_RULES_PATH = ROOT / "config" / "rules.json"


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
    with cfg_path.open() as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Invalid scoring config at {cfg_path}")
    return ScoringConfig(raw=raw, path=cfg_path)


def load_rules(path: Path | None = None) -> dict[str, Any]:
    rules_path = path or DEFAULT_RULES_PATH
    with rules_path.open() as f:
        return json.load(f)
