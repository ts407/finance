from __future__ import annotations

import csv
import io
import json
import os
import re
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from standing.config import default_desk_dir

DESK_DIR_ENV = "STANDING_DESK_DIR"

SNAPSHOT_SCORE_FIELDS = (
    "ticker",
    "sector",
    "last_price",
    "value",
    "quality",
    "momentum",
    "momentum_global",
    "composite_standing",
    "attention_tilt",
    "final_standing",
    "s_obs",
    "s_used",
    "n",
    "confidence_c",
    "neg_share",
    "social_badge",
    "value_coverage",
    "value_ev_rung",
)

DIARY_KINDS = frozenset(
    {"observation", "buy", "add", "close", "thesis_update", "note"}
)


def desk_dir(path: Path | None = None) -> Path:
    if path is not None:
        return path
    return default_desk_dir()


def _positions_path(root: Path) -> Path:
    return root / "positions.json"


def _diary_path(root: Path) -> Path:
    return root / "diary.jsonl"


def ensure_desk(root: Path | None = None) -> Path:
    target = desk_dir(root)
    target.mkdir(parents=True, exist_ok=True)
    pos = _positions_path(target)
    if not pos.exists():
        _atomic_write_json(pos, {"version": 1, "positions": []})
    diary = _diary_path(target)
    if not diary.exists():
        diary.touch()
    return target


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name, suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        Path(tmp).replace(path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def capture_snapshot(
    row: dict[str, Any] | None,
    *,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Freeze desk scores + config identity for a ticker at one moment (UTC)."""
    meta = meta or {}
    row = row or {}
    scores = {field: row.get(field) for field in SNAPSHOT_SCORE_FIELDS if field in row or field == "last_price"}
    scores["last_price"] = _finite(row.get("last_price") if row.get("last_price") is not None else row.get("price"))
    return {
        "captured_utc": _now_utc(),
        "as_of": meta.get("as_of") or row.get("as_of"),
        "methodology_version": meta.get("methodology_version") or row.get("methodology_version"),
        "universe_id": meta.get("universe_id"),
        "score_kind": meta.get("score_kind") or row.get("score_kind"),
        "placeholder": meta.get("placeholder"),
        "market_mode": meta.get("market_mode") or meta.get("market_provider"),
        "social_mode": meta.get("social_mode") or meta.get("social_provider"),
        "attention_mode": meta.get("attention_mode"),
        "scores": scores,
    }


def load_positions(*, root: Path | None = None) -> list[dict[str, Any]]:
    target = ensure_desk(root)
    raw = json.loads(_positions_path(target).read_text(encoding="utf-8"))
    return list(raw.get("positions") or [])


def save_positions(positions: list[dict[str, Any]], *, root: Path | None = None) -> None:
    target = ensure_desk(root)
    _atomic_write_json(_positions_path(target), {"version": 1, "positions": positions})


def get_open_position(ticker: str, *, root: Path | None = None) -> dict[str, Any] | None:
    key = ticker.strip().upper()
    for pos in load_positions(root=root):
        if pos.get("status") == "open" and str(pos.get("ticker", "")).upper() == key:
            return pos
    return None


def get_position(position_id: str, *, root: Path | None = None) -> dict[str, Any] | None:
    for pos in load_positions(root=root):
        if pos.get("id") == position_id:
            return pos
    return None


def build_diary_marks(
    *,
    snapshot: dict[str, Any] | None = None,
    desk_position: dict[str, Any] | None = None,
    book: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Price context frozen onto a diary entry.

    Prefer SQLite book overlay (entry / target / stop / size) when held;
    fall back to the desk holdings log (avg_cost, purchase snapshot, P&L).
    """
    snap = snapshot or {}
    scores = snap.get("scores") if isinstance(snap.get("scores"), dict) else {}
    last_price = _finite(scores.get("last_price"))
    purchase = (desk_position or {}).get("purchase_snapshot") or {}
    purchase_scores = purchase.get("scores") if isinstance(purchase.get("scores"), dict) else {}
    desk_entry = _finite((desk_position or {}).get("avg_cost")) or _finite(
        purchase_scores.get("last_price")
    )
    overlay = book or {}
    if overlay.get("portfolio") and isinstance(overlay["portfolio"], dict):
        overlay = overlay["portfolio"]
    thesis = (book or {}).get("thesis") if isinstance(book, dict) else None
    if not isinstance(thesis, dict):
        thesis = {}
    entry_price = (
        _finite(overlay.get("entry_price"))
        or _finite((book or {}).get("entry_price") if isinstance(book, dict) else None)
        or desk_entry
    )
    target_price = _finite(overlay.get("target_price")) or _finite(thesis.get("target_price"))
    stop_price = _finite(overlay.get("stop_price")) or _finite(thesis.get("stop_price"))
    shares = _finite(overlay.get("size")) or _finite((desk_position or {}).get("shares"))
    avg_cost = _finite((desk_position or {}).get("avg_cost")) or entry_price
    if desk_position:
        pnl = _pnl_block(desk_position, last_price)
    elif shares is not None and avg_cost is not None:
        pnl = _pnl_block({"shares": shares, "avg_cost": avg_cost}, last_price)
    else:
        pnl = None
    return {
        "last_price": last_price,
        "entry_price": entry_price,
        "avg_cost": avg_cost,
        "target_price": target_price,
        "stop_price": stop_price,
        "shares": shares,
        "pnl_abs": None if pnl is None else pnl.get("pnl_abs"),
        "pnl_pct": None if pnl is None else pnl.get("pnl_pct"),
        "final_standing": _finite(scores.get("final_standing")),
    }


def append_diary(
    *,
    ticker: str,
    comment: str,
    snapshot: dict[str, Any],
    kind: str = "observation",
    position_id: str | None = None,
    desk_position: dict[str, Any] | None = None,
    book: dict[str, Any] | None = None,
    marks: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    if kind not in DIARY_KINDS:
        raise ValueError(f"Unknown diary kind {kind!r}")
    ticker_key = ticker.strip().upper()
    if not ticker_key:
        raise ValueError("ticker is required")
    text = (comment or "").strip()
    if not text:
        raise ValueError("comment is required")
    frozen = marks if marks is not None else build_diary_marks(
        snapshot=snapshot,
        desk_position=desk_position,
        book=book,
    )
    entry = {
        "id": _new_id("D"),
        "created_utc": _now_utc(),
        "ticker": ticker_key,
        "kind": kind,
        "comment": text,
        "position_id": position_id,
        "snapshot": snapshot,
        "marks": frozen,
    }
    target = ensure_desk(root)
    with _diary_path(target).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read_diary(
    *,
    ticker: str | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    kind: str | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    target = ensure_desk(root)
    path = _diary_path(target)
    rows: list[dict[str, Any]] = []
    if path.stat().st_size == 0:
        return rows
    ticker_key = ticker.strip().upper() if ticker else None
    needle = q.strip().lower() if q else None
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            created = str(row.get("created_utc") or "")
            if ticker_key and str(row.get("ticker", "")).upper() != ticker_key:
                continue
            if kind and row.get("kind") != kind:
                continue
            if since and created[:10] < since:
                continue
            if until and created[:10] > until:
                continue
            if needle:
                blob = f"{row.get('ticker','')} {row.get('comment','')} {row.get('kind','')}".lower()
                if needle not in blob:
                    continue
            rows.append(row)
    rows.reverse()  # newest first
    return rows


def _pnl_block(position: dict[str, Any], last_price: float | None) -> dict[str, Any]:
    shares = float(position.get("shares") or 0)
    avg_cost = float(position.get("avg_cost") or 0)
    cost_basis = shares * avg_cost
    market_value = shares * last_price if last_price is not None else None
    pnl_abs = (market_value - cost_basis) if market_value is not None else None
    pnl_pct = (pnl_abs / cost_basis) if pnl_abs is not None and cost_basis else None
    return {
        "shares": shares,
        "avg_cost": avg_cost,
        "cost_basis": cost_basis,
        "last_price": last_price,
        "market_value": market_value,
        "pnl_abs": pnl_abs,
        "pnl_pct": pnl_pct,
    }


def enrich_position(
    position: dict[str, Any],
    *,
    current_row: dict[str, Any] | None = None,
    current_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    last_price = _finite((current_row or {}).get("last_price"))
    if last_price is None and position.get("status") == "closed":
        last_price = _finite(position.get("close_price"))
    out = dict(position)
    out["pnl"] = _pnl_block(position, last_price)
    out["current_snapshot"] = capture_snapshot(current_row, meta=current_meta) if current_row else None
    return out


def open_or_add_position(
    *,
    ticker: str,
    shares: float,
    avg_cost: float,
    buy_reason: str,
    thesis: str,
    snapshot: dict[str, Any],
    opened_at: str | None = None,
    comment: str | None = None,
    book: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    if shares <= 0 or avg_cost < 0:
        raise ValueError("shares must be > 0 and avg_cost must be >= 0")
    ticker_key = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", ticker_key):
        raise ValueError(f"Invalid ticker {ticker!r}")
    reason = (buy_reason or "").strip()
    thesis_text = (thesis or "").strip()
    if not reason:
        raise ValueError("buy_reason (Grund des Kaufens) is required")
    if not thesis_text:
        raise ValueError("thesis (These) is required")

    positions = load_positions(root=root)
    existing = next(
        (
            p
            for p in positions
            if p.get("status") == "open" and str(p.get("ticker", "")).upper() == ticker_key
        ),
        None,
    )
    now = _now_utc()
    day = opened_at or date.today().isoformat()

    if existing is None:
        position = {
            "id": _new_id("P"),
            "ticker": ticker_key,
            "shares": float(shares),
            "avg_cost": float(avg_cost),
            "opened_at": day,
            "status": "open",
            "closed_at": None,
            "close_price": None,
            "buy_reason": reason,
            "thesis": thesis_text,
            "purchase_snapshot": snapshot,
            "created_utc": now,
            "updated_utc": now,
        }
        positions.append(position)
        kind = "buy"
        note = comment or f"Opened {shares:g} {ticker_key} @ {avg_cost:g}. {reason}"
    else:
        old_shares = float(existing["shares"])
        old_cost = float(existing["avg_cost"])
        new_shares = old_shares + float(shares)
        existing["avg_cost"] = (old_shares * old_cost + float(shares) * float(avg_cost)) / new_shares
        existing["shares"] = new_shares
        existing["updated_utc"] = now
        if reason:
            existing["buy_reason"] = reason
        if thesis_text:
            existing["thesis"] = thesis_text
        position = existing
        kind = "add"
        note = comment or f"Added {shares:g} {ticker_key} @ {avg_cost:g} (avg now {existing['avg_cost']:.4g})."

    save_positions(positions, root=root)
    entry = append_diary(
        ticker=ticker_key,
        comment=note,
        snapshot=snapshot,
        kind=kind,
        position_id=position["id"],
        desk_position=position,
        book=book,
        root=root,
    )
    return {"position": position, "diary_entry": entry}


def update_position_notes(
    position_id: str,
    *,
    buy_reason: str | None = None,
    thesis: str | None = None,
    snapshot: dict[str, Any] | None = None,
    comment: str | None = None,
    book: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    positions = load_positions(root=root)
    position = next((p for p in positions if p.get("id") == position_id), None)
    if position is None:
        raise KeyError(position_id)
    changed: list[str] = []
    if buy_reason is not None:
        text = buy_reason.strip()
        if not text:
            raise ValueError("buy_reason cannot be empty")
        if text != position.get("buy_reason"):
            position["buy_reason"] = text
            changed.append("Grund des Kaufens")
    if thesis is not None:
        text = thesis.strip()
        if not text:
            raise ValueError("thesis cannot be empty")
        if text != position.get("thesis"):
            position["thesis"] = text
            changed.append("These")
    if not changed:
        return {"position": position, "diary_entry": None}
    position["updated_utc"] = _now_utc()
    save_positions(positions, root=root)
    note = comment or ("Updated " + " and ".join(changed) + ".")
    entry = append_diary(
        ticker=str(position["ticker"]),
        comment=note,
        snapshot=snapshot or position.get("purchase_snapshot") or {},
        kind="thesis_update",
        position_id=position_id,
        desk_position=position,
        book=book,
        root=root,
    )
    return {"position": position, "diary_entry": entry}


def close_position(
    position_id: str,
    *,
    close_price: float | None,
    snapshot: dict[str, Any],
    comment: str | None = None,
    book: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    positions = load_positions(root=root)
    position = next((p for p in positions if p.get("id") == position_id), None)
    if position is None:
        raise KeyError(position_id)
    if position.get("status") != "open":
        raise ValueError("Position is already closed")
    position["status"] = "closed"
    position["closed_at"] = date.today().isoformat()
    position["close_price"] = _finite(close_price)
    position["updated_utc"] = _now_utc()
    save_positions(positions, root=root)
    px = position["close_price"]
    px_txt = f"{px:g}" if px is not None else "n/a"
    note = comment or f"Closed {position['shares']:g} {position['ticker']} @ {px_txt}."
    entry = append_diary(
        ticker=str(position["ticker"]),
        comment=note,
        snapshot=snapshot,
        kind="close",
        position_id=position_id,
        desk_position=position,
        book=book,
        root=root,
    )
    return {"position": position, "diary_entry": entry}


def portfolio_view(
    *,
    current_by_ticker: dict[str, dict[str, Any]],
    current_meta: dict[str, Any] | None = None,
    include_closed: bool = False,
    root: Path | None = None,
) -> dict[str, Any]:
    rows = []
    totals = {
        "cost_basis": 0.0,
        "market_value": 0.0,
        "pnl_abs": 0.0,
        "priced": 0,
        "open": 0,
    }
    for pos in load_positions(root=root):
        if not include_closed and pos.get("status") != "open":
            continue
        ticker = str(pos.get("ticker", "")).upper()
        enriched = enrich_position(
            pos,
            current_row=current_by_ticker.get(ticker),
            current_meta=current_meta,
        )
        rows.append(enriched)
        pnl = enriched["pnl"]
        if pos.get("status") == "open":
            totals["open"] += 1
            totals["cost_basis"] += float(pnl["cost_basis"] or 0)
            if pnl["market_value"] is not None:
                totals["market_value"] += float(pnl["market_value"])
                totals["pnl_abs"] += float(pnl["pnl_abs"] or 0)
                totals["priced"] += 1
    totals["pnl_pct"] = (
        totals["pnl_abs"] / totals["cost_basis"] if totals["cost_basis"] else None
    )
    return {
        "positions": rows,
        "totals": totals,
        "held_tickers": [r["ticker"] for r in rows if r.get("status") == "open"],
    }


def ticker_dossier(
    ticker: str,
    *,
    current_row: dict[str, Any] | None,
    current_meta: dict[str, Any] | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    key = ticker.strip().upper()
    positions = [p for p in load_positions(root=root) if str(p.get("ticker", "")).upper() == key]
    open_pos = next((p for p in positions if p.get("status") == "open"), None)
    chosen = open_pos or (positions[-1] if positions else None)
    enriched = (
        enrich_position(chosen, current_row=current_row, current_meta=current_meta)
        if chosen
        else None
    )
    return {
        "ticker": key,
        "held": open_pos is not None,
        "position": enriched,
        "purchase_snapshot": (chosen or {}).get("purchase_snapshot") if chosen else None,
        "current_snapshot": capture_snapshot(current_row, meta=current_meta) if current_row else None,
        "diary": read_diary(ticker=key, root=root),
        "buy_reason": (chosen or {}).get("buy_reason"),
        "thesis": (chosen or {}).get("thesis"),
    }


def export_diary_csv(
    *,
    ticker: str | None = None,
    q: str | None = None,
    since: str | None = None,
    until: str | None = None,
    kind: str | None = None,
    root: Path | None = None,
) -> str:
    rows = read_diary(ticker=ticker, q=q, since=since, until=until, kind=kind, root=root)
    buf = io.StringIO()
    fields = [
        "id",
        "created_utc",
        "ticker",
        "kind",
        "comment",
        "position_id",
        "as_of",
        "methodology_version",
        "final_standing",
        "last_price",
        "entry_price",
        "target_price",
        "stop_price",
        "shares",
        "pnl_abs",
        "pnl_pct",
    ]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for row in reversed(rows):  # chronological for export
        snap = row.get("snapshot") or {}
        scores = snap.get("scores") or {}
        marks = row.get("marks") or {}
        writer.writerow(
            {
                "id": row.get("id"),
                "created_utc": row.get("created_utc"),
                "ticker": row.get("ticker"),
                "kind": row.get("kind"),
                "comment": row.get("comment"),
                "position_id": row.get("position_id"),
                "as_of": snap.get("as_of"),
                "methodology_version": snap.get("methodology_version"),
                "final_standing": marks.get("final_standing", scores.get("final_standing")),
                "last_price": marks.get("last_price", scores.get("last_price")),
                "entry_price": marks.get("entry_price"),
                "target_price": marks.get("target_price"),
                "stop_price": marks.get("stop_price"),
                "shares": marks.get("shares"),
                "pnl_abs": marks.get("pnl_abs"),
                "pnl_pct": marks.get("pnl_pct"),
            }
        )
    return buf.getvalue()


def summarize_entries(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Qualitative counts only — never a score or training input."""
    tickers = sorted({str(r.get("ticker")) for r in rows if r.get("ticker")})
    kinds: dict[str, int] = {}
    ticker_counts: dict[str, int] = {}
    for row in rows:
        k = str(row.get("kind") or "note")
        kinds[k] = kinds.get(k, 0) + 1
        ticker = str(row.get("ticker") or "").upper()
        if ticker:
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1
    latest = rows[0]["created_utc"] if rows else None
    return {
        "n_entries": len(rows),
        "n_tickers": len(tickers),
        "tickers": tickers,
        "ticker_counts": ticker_counts,
        "kinds": kinds,
        "latest_utc": latest,
        "score_input": False,
    }


def summarize_diary_for_vergleich(*, root: Path | None = None) -> dict[str, Any]:
    """Qualitative counts only — never a score or training input."""
    return summarize_entries(read_diary(root=root))
