from __future__ import annotations

from pathlib import Path

from standing.config import ROOT

OPTIMIZATION_ROOT = ROOT / "artifacts" / "optimization"
HYPOTHESES_DIR = OPTIMIZATION_ROOT / "hypotheses"
CONFIGS_DIR = OPTIMIZATION_ROOT / "configs"
BASELINE_DIR = OPTIMIZATION_ROOT / "baseline"
LOOP_LOG_PATH = OPTIMIZATION_ROOT / "loop_log.jsonl"


def ensure_layout() -> Path:
    """Create the durable optimization artifact directories."""
    for path in (OPTIMIZATION_ROOT, HYPOTHESES_DIR, CONFIGS_DIR, BASELINE_DIR):
        path.mkdir(parents=True, exist_ok=True)
    if not LOOP_LOG_PATH.exists():
        LOOP_LOG_PATH.touch()
    return OPTIMIZATION_ROOT
