"""Minimal HTTP JSON helper — stdlib only, injectable for tests."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Mapping

DEFAULT_USER_AGENT = "StandingResearchBot/0.1 (+https://github.com/ts407/finance; research demo)"

JsonFetcher = Callable[[str, Mapping[str, str] | None], Any]


def get_json(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    timeout: float = 30.0,
) -> Any:
    hdrs = {"User-Agent": DEFAULT_USER_AGENT, "Accept": "application/json"}
    if headers:
        hdrs.update(dict(headers))
    req = urllib.request.Request(url, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code} for {url}: {body}") from exc


def build_url(base: str, params: Mapping[str, str | int | float | None]) -> str:
    filtered = {k: str(v) for k, v in params.items() if v is not None}
    if not filtered:
        return base
    return f"{base}?{urllib.parse.urlencode(filtered)}"
