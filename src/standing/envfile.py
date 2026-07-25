"""Load local .env without overriding existing process env."""

from __future__ import annotations

from pathlib import Path

from standing.config import ROOT


def load_env(dotenv_path: Path | None = None) -> bool:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    path = dotenv_path or (ROOT / ".env")
    if not path.exists():
        return False
    load_dotenv(path, override=False)
    return True
