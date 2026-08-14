"""Deterministic investment Entwurf from a link, text, or PNG.

Personal qualitative draft for the Trade desk — not advice, not a broker,
never a score or training input.
"""

from __future__ import annotations

import base64
import html
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from standing.desk.ledger import (
    append_diary,
    attachments_dir,
    build_diary_marks,
    extract_fundamentals,
    fundamentals_display,
    new_id,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
MAX_PNG_BYTES = 5 * 1024 * 1024
MAX_URL_BYTES = 512 * 1024
MAX_TEXT = 8000
MECHANISM_HINT = "Wie der Kurs dorthin kommt — hier ausformulieren."
FALSIFIER_HINT = "Was die These bricht — hier ausformulieren (mind. 20 Zeichen)."
UNTITLED_TICKER = "ENTWURF"

_TICKER_RE = re.compile(r"\b\$?([A-Z]{1,5})\b")
_TICKER_STOP = frozenset(
    {
        "A",
        "I",
        "THE",
        "AND",
        "OR",
        "TO",
        "IN",
        "ON",
        "OF",
        "IS",
        "IT",
        "BE",
        "AT",
        "BY",
        "IF",
        "AN",
        "AS",
        "SO",
        "NO",
        "YES",
        "ALL",
        "NEW",
        "OLD",
        "FOR",
        "NOT",
        "BUT",
        "ARE",
        "WAS",
        "HAS",
        "HAD",
        "YOU",
        "WE",
        "US",
        "HTTP",
        "HTTPS",
        "WWW",
        "COM",
        "PDF",
        "HTML",
        "PNG",
        "CEO",
        "CFO",
        "IPO",
        "ETF",
        "GDP",
        "CPI",
        "YOY",
        "TTM",
        "NTM",
        "SEC",
        "KGV",
        "KBV",
        "KUV",
        "ROE",
        "EBIT",
        "EPS",
        "PE",
        "EV",
        "USA",
        "USD",
        "EUR",
        "NYSE",
        "NASDAQ",
    }
)


class _PreviewParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_title = False
        self.title_parts: list[str] = []
        self.description: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title":
            self._in_title = True
        if tag != "meta":
            return
        props = {k.lower(): (v or "") for k, v in attrs}
        name = (props.get("name") or props.get("property") or "").lower()
        if name in {"description", "og:description"} and props.get("content") and not self.description:
            self.description = props["content"].strip()

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)


def validate_http_url(url: str) -> str:
    raw = (url or "").strip()
    if len(raw) > 2000:
        raise ValueError("URL too long")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL must be http(s) with a host")
    return raw


def extract_tickers(text: str, *, universe: set[str] | None = None) -> list[str]:
    blob = (text or "").upper()
    seen: list[str] = []
    for token in _TICKER_RE.findall(blob):
        if token in seen:
            continue
        seen.append(token)
    if universe:
        hits = [t for t in seen if t in universe]
        if hits:
            return hits
    return [t for t in seen if t not in _TICKER_STOP and len(t) >= 2]


def decode_png_b64(image_b64: str, filename: str | None = None) -> tuple[bytes, str]:
    raw = (image_b64 or "").strip()
    if not raw:
        raise ValueError("PNG payload is empty")
    if raw.startswith("data:"):
        header, _, raw = raw.partition(",")
        if "image/" in header.lower() and "png" not in header.lower():
            raise ValueError("Only PNG uploads are accepted")
    try:
        data = base64.b64decode(raw, validate=False)
    except Exception as exc:
        raise ValueError("PNG payload is not valid base64") from exc
    if len(data) > MAX_PNG_BYTES:
        raise ValueError("PNG too large (max 5 MB)")
    if not data.startswith(PNG_MAGIC):
        raise ValueError("File is not a PNG")
    name = Path(filename or "entwurf.png").name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name) or "entwurf.png"
    if not name.lower().endswith(".png"):
        name = f"{name}.png"
    return data, name


def fetch_url_preview(url: str) -> dict[str, str | None]:
    """Best-effort title/snippet. Failures become empty preview, not a hard error."""
    try:
        req = Request(
            url,
            headers={"User-Agent": "StandingDesk/1.0 (personal Entwurf; not a crawler)"},
        )
        with urlopen(req, timeout=5) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            payload = resp.read(MAX_URL_BYTES)
        if "html" not in ctype and not payload.lstrip()[:32].lower().startswith((b"<!doctype", b"<html")):
            return {"title": None, "snippet": None}
        parser = _PreviewParser()
        parser.feed(payload.decode("utf-8", errors="ignore"))
        title = html.unescape(" ".join(parser.title_parts).strip()) or None
        snippet = html.unescape((parser.description or "").strip()) or None
        if snippet and len(snippet) > 400:
            snippet = snippet[:400].rstrip() + "…"
        if title and len(title) > 200:
            title = title[:200].rstrip() + "…"
        return {"title": title, "snippet": snippet}
    except (URLError, TimeoutError, ValueError, OSError):
        return {"title": None, "snippet": None}


def _clip(text: str, limit: int) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def develop_draft(
    *,
    source: str,
    url: str | None = None,
    text: str | None = None,
    filename: str | None = None,
    title: str | None = None,
    snippet: str | None = None,
    ticker: str | None = None,
    universe: set[str] | None = None,
) -> dict[str, Any]:
    if source not in {"url", "text", "png"}:
        raise ValueError("source must be url, text, or png")
    raw = (text or "").strip()
    if source == "url":
        href = validate_http_url(url or "")
        preview_title = (title or "").strip() or href
        thesis = _clip(preview_title, 500)
        grund = _clip(" ".join(part for part in (snippet, href) if part), 800) or href
        haystack = " ".join(part for part in (ticker, preview_title, snippet, href, raw) if part)
    elif source == "text":
        if not raw:
            raise ValueError("Text is empty")
        if len(raw) > MAX_TEXT:
            raw = raw[:MAX_TEXT]
        first = raw.split("\n", 1)[0].strip() or raw
        thesis = _clip(first, 500)
        grund = _clip(raw, 800)
        haystack = " ".join(part for part in (ticker, raw) if part)
        href = None
    else:
        label = (filename or "screenshot.png").strip() or "screenshot.png"
        thesis = f"PNG-Beobachtung: {label}"
        grund = "Screenshot als qualitative Beobachtung — keine Handlungsempfehlung."
        haystack = " ".join(part for part in (ticker, label, raw) if part)
        href = None
    detected = extract_tickers(haystack, universe=universe)
    resolved = (ticker or "").strip().upper() or (detected[0] if detected else UNTITLED_TICKER)
    return {
        "source": source,
        "url": href,
        "title": (title or thesis)[:200],
        "snippet": (snippet or "")[:400] or None,
        "raw": raw[:MAX_TEXT] if raw else None,
        "filename": filename,
        "ticker": resolved,
        "detected_tickers": detected,
        "draft": {
            "ticker": resolved,
            "thesis": thesis,
            "buy_reason": grund,
            "mechanism": MECHANISM_HINT,
            "falsifier": FALSIFIER_HINT,
        },
    }


def save_png_attachment(
    entry_id: str,
    data: bytes,
    original_filename: str,
    *,
    root: Path | None = None,
) -> dict[str, str]:
    name = f"{entry_id}.png"
    path = attachments_dir(root) / name
    path.write_bytes(data)
    return {
        "name": name,
        "original_filename": original_filename,
        "content_type": "image/png",
    }


def format_entwurf_comment(developed: dict[str, Any]) -> str:
    source = developed.get("source") or "text"
    draft = developed.get("draft") or {}
    lines = [f"Entwurf ({source})"]
    title = developed.get("title")
    if title:
        lines.append(str(title))
    if developed.get("url"):
        lines.append(str(developed["url"]))
    lines.append("")
    lines.append(f"These: {draft.get('thesis') or ''}".strip())
    if draft.get("buy_reason"):
        lines.append(f"Grund: {draft['buy_reason']}")
    text = "\n".join(lines).strip()
    return text[:8000]


def persist_entwurf(
    developed: dict[str, Any],
    *,
    snapshot: dict[str, Any],
    png_bytes: bytes | None = None,
    original_filename: str | None = None,
    desk_position: dict[str, Any] | None = None,
    book: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    entry_id = new_id("D")
    attachment = None
    if png_bytes:
        attachment = save_png_attachment(
            entry_id,
            png_bytes,
            original_filename or developed.get("filename") or "entwurf.png",
            root=root,
        )
    scores = snapshot.get("scores") if isinstance(snapshot.get("scores"), dict) else {}
    funds = extract_fundamentals(scores)
    marks = build_diary_marks(
        snapshot=snapshot,
        desk_position=desk_position,
        book=book,
    )
    payload = {
        "source": developed["source"],
        "url": developed.get("url"),
        "title": developed.get("title"),
        "snippet": developed.get("snippet"),
        "raw": developed.get("raw"),
        "filename": developed.get("filename"),
        "detected_tickers": developed.get("detected_tickers") or [],
        "draft": developed.get("draft") or {},
        "attachment": attachment,
        "fundamentals": funds,
        "score_input": False,
    }
    entry = append_diary(
        ticker=str((developed.get("draft") or {}).get("ticker") or UNTITLED_TICKER),
        comment=format_entwurf_comment(developed),
        snapshot=snapshot,
        kind="entwurf",
        desk_position=desk_position,
        book=book,
        marks=marks,
        extra={"entwurf": payload},
        entry_id=entry_id,
        root=root,
    )
    return entry


def entwurf_response(entry: dict[str, Any]) -> dict[str, Any]:
    payload = dict(entry.get("entwurf") or {})
    draft = dict(payload.get("draft") or {})
    funds = payload.get("fundamentals") or (entry.get("marks") or {}).get("fundamentals") or {}
    attachment = payload.get("attachment")
    falsifier = draft.get("falsifier")
    apply_falsifier = None if falsifier == FALSIFIER_HINT else falsifier
    attachment_url = None
    if attachment and attachment.get("name"):
        attachment_url = f"/api/trade/entwurf/file/{attachment['name']}"
    return {
        "id": entry.get("id"),
        "ticker": entry.get("ticker"),
        "kind": "entwurf",
        "source": payload.get("source"),
        "url": payload.get("url"),
        "title": payload.get("title"),
        "snippet": payload.get("snippet"),
        "filename": payload.get("filename") or (attachment or {}).get("original_filename"),
        "detected_tickers": payload.get("detected_tickers") or [],
        "draft": draft,
        "fundamentals": funds,
        "fundamentals_display": fundamentals_display(funds),
        "attachment_url": attachment_url,
        "diary_entry": entry,
        "score_input": False,
        "apply": {
            "ticker": draft.get("ticker"),
            "thesis": draft.get("thesis") or "",
            "buy_reason": draft.get("buy_reason") or "",
            "mechanism": draft.get("mechanism") or "",
            "falsifier": apply_falsifier,
        },
    }
