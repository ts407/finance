from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from standing.config import apply_overrides, load_scoring_config
from standing.optimization.paths import CONFIGS_DIR, HYPOTHESES_DIR, ensure_layout


def write_shadow_config(
    *,
    hypothesis_id: str,
    overrides: dict[str, Any],
    timestamp: str | None = None,
) -> Path:
    """Write an isolated scoring config copy; never touches productive scoring.yaml."""
    ensure_layout()
    cfg = load_scoring_config()
    raw = apply_overrides(cfg.raw, overrides)
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = CONFIGS_DIR / f"{hypothesis_id}_{stamp}.yaml"
    with out.open("w", encoding="utf-8") as f:
        yaml.safe_dump(raw, f, sort_keys=False, allow_unicode=True)
    return out


def write_deferred_hypothesis(
    *,
    hypothesis_id: str,
    reason: str,
    overrides: dict[str, Any],
    cycle_id: str,
) -> Path:
    """Record a formulated-but-deferred hypothesis without a shadow config."""
    ensure_layout()
    payload = {
        "id": hypothesis_id,
        "cycle_id": cycle_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "basis": reason,
        "change": [{"path": k, "to": v} for k, v in overrides.items()],
        "status": "deferred",
        "handoff": None,
        "productive_config": "config/scoring.yaml",
    }
    hyp_path = HYPOTHESES_DIR / f"{hypothesis_id}.yaml"
    with hyp_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
    return hyp_path


def write_hypothesis(
    *,
    hypothesis_id: str,
    basis: str,
    overrides: dict[str, Any],
    prediction: dict[str, Any],
    cycle_id: str,
    handoff: str = "loop-live-test-shadow",
) -> tuple[Path, Path]:
    """Persist hypothesis YAML + matching shadow config; returns (hypothesis, config) paths."""
    ensure_layout()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    config_path = write_shadow_config(
        hypothesis_id=hypothesis_id,
        overrides=overrides,
        timestamp=stamp,
    )
    payload = {
        "id": hypothesis_id,
        "cycle_id": cycle_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "basis": basis,
        "change": [{"path": k, "to": v} for k, v in overrides.items()],
        "prediction": prediction,
        "shadow_config": str(config_path),
        "productive_config": "config/scoring.yaml",
        "handoff": handoff,
        "status": "ready_for_shadow",
    }
    hyp_path = HYPOTHESES_DIR / f"{hypothesis_id}.yaml"
    with hyp_path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(payload, f, sort_keys=False, allow_unicode=True)
    return hyp_path, config_path
