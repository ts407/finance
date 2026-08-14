"""Isolate personal data dirs so tests never write into the git checkout or home."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolate_standing_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "standing-data"
    monkeypatch.setenv("STANDING_DATA_DIR", str(root))
    return root
