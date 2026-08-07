"""Value-pillar metric selection, EV/PE fallback ladders, and coverage."""

from __future__ import annotations

import pandas as pd

# Sectors where EV/EBITDA is structurally meaningless.
EV_INAPPLICABLE_SECTORS = frozenset({"Financials", "Real Estate"})


def resolve_ev_multiple(row: pd.Series) -> tuple[float | None, str | None]:
    """
    Fallback ladder for non-financial names: ev_ebitda → ev_ebit → ev_sales.
    Returns (value, rung_label).
    """
    for col, label in (
        ("ev_ebitda", "ev_ebitda"),
        ("ev_ebit", "ev_ebit"),
        ("ev_sales", "ev_sales"),
    ):
        if col not in row.index:
            continue
        val = row[col]
        if pd.notna(val) and float(val) > 0:
            return float(val), label
    return None, None


def resolve_pe_multiple(row: pd.Series) -> tuple[float | None, str | None]:
    """
    P/E ladder: pe_forward (consensus NTM) → pe_ttm (trailing).

    Only positive multiples count as a rung. Non-positive but present values are
    handled downstream as worst-decile (0), not as 'missing'.
    """
    for col, label in (
        ("pe_forward", "pe_forward"),
        ("pe_ttm", "pe_ttm"),
    ):
        if col not in row.index:
            continue
        val = row[col]
        if pd.notna(val) and float(val) > 0:
            return float(val), label
    # Present but non-positive: surface the preferred column so ranking can map to 0.
    for col, label in (
        ("pe_forward", "pe_forward"),
        ("pe_ttm", "pe_ttm"),
    ):
        if col in row.index and pd.notna(row[col]):
            return float(row[col]), label
    return None, None


def _book_multiple_label(row: pd.Series) -> tuple[str, bool]:
    """Prefer P/TBV for financials when present; else P/B."""
    if "ptbv" in row.index and pd.notna(row.get("ptbv")):
        return "ptbv", True
    if pd.notna(row.get("pb")):
        return "pb", True
    return "pb", False


def value_metric_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build per-row value inputs used for ranking + coverage labels.

    - Financials / Real Estate: PE-ladder + pb (or ptbv) — EV skipped as inapplicable
    - Others: PE-ladder + pb + resolved EV rung
    """
    out = df.copy()
    # Prefer tangible book when available for ranking book multiple.
    if "ptbv" in out.columns:
        out["pb"] = out["ptbv"].where(out["ptbv"].notna(), out.get("pb"))
    pe_vals: list[float | None] = []
    pe_rungs: list[str | None] = []
    ev_vals: list[float | None] = []
    ev_rungs: list[str | None] = []
    sets: list[str] = []
    for _, row in out.iterrows():
        sector = str(row.get("sector") or "")
        book_label, has_book = _book_multiple_label(row)
        pe, pe_rung = resolve_pe_multiple(row)
        pe_vals.append(pe)
        pe_rungs.append(pe_rung)
        if sector in EV_INAPPLICABLE_SECTORS:
            ev_vals.append(None)
            ev_rungs.append("inapplicable")
            used = []
            if pe_rung:
                used.append(pe_rung)
            if has_book:
                used.append(book_label)
            sets.append("|".join(used) if used else "none")
        else:
            ev, rung = resolve_ev_multiple(row)
            ev_vals.append(ev)
            ev_rungs.append(rung)
            used = []
            if pe_rung:
                used.append(pe_rung)
            if has_book:
                used.append(book_label)
            if rung:
                used.append(rung)
            sets.append("|".join(used) if used else "none")
    out["_pe_for_value"] = pd.to_numeric(pd.Series(pe_vals, index=out.index), errors="coerce")
    out["value_pe_rung"] = pe_rungs
    out["_ev_for_value"] = pd.to_numeric(pd.Series(ev_vals, index=out.index), errors="coerce")
    out["value_ev_rung"] = ev_rungs
    out["value_metric_set"] = sets
    return out
