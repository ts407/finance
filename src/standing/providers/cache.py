"""Simple disk cache for live HTTP payloads / provider frames."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd

from standing.config import ROOT

DEFAULT_CACHE_DIR = ROOT / "artifacts" / "cache"


def _key_hash(parts: tuple[Any, ...]) -> str:
    blob = json.dumps(parts, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:24]


class DiskCache:
    def __init__(self, root: Path | None = None, *, ttl_seconds: float = 6 * 3600):
        self.root = Path(root) if root else DEFAULT_CACHE_DIR
        self.ttl_seconds = ttl_seconds
        self.root.mkdir(parents=True, exist_ok=True)

    def path_for(self, namespace: str, *parts: Any) -> Path:
        return self.root / namespace / f"{_key_hash(parts)}.json"

    def get_json(self, namespace: str, *parts: Any) -> Any | None:
        path = self.path_for(namespace, *parts)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return None
        ts = float(payload.get("_cached_at", 0))
        if self.ttl_seconds > 0 and (time.time() - ts) > self.ttl_seconds:
            return None
        return payload.get("data")

    def set_json(self, namespace: str, *parts: Any, data: Any) -> None:
        path = self.path_for(namespace, *parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"_cached_at": time.time(), "data": data}, default=str))

    def get_frame(self, namespace: str, *parts: Any) -> pd.DataFrame | None:
        data = self.get_json(namespace, *parts)
        if data is None:
            return None
        return pd.DataFrame(data)

    def set_frame(self, namespace: str, *parts: Any, frame: pd.DataFrame) -> None:
        self.set_json(namespace, *parts, data=frame.to_dict(orient="records"))

    def wrap_frame(
        self,
        namespace: str,
        parts: tuple[Any, ...],
        producer: Callable[[], pd.DataFrame],
    ) -> pd.DataFrame:
        cached = self.get_frame(namespace, *parts)
        if cached is not None:
            return cached
        frame = producer()
        self.set_frame(namespace, *parts, frame=frame)
        return frame
