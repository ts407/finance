"""Diagnostic recalibration loop — report only, no weight changes."""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from standing.config import ROOT
from standing.portfolio.attribution import (
    AttributionRow,
    attribute_position,
    log_return,
    mean_log_return,
    score_decile,
)
from standing.portfolio.models import CloseReason, PositionStatus
from standing.portfolio.repository import PortfolioRepository

DEFAULT_REPORT_DIR = ROOT / "reports"


@dataclass
class RecalibrateConfig:
    window_days: int = 90
    min_hold_days: int = 30
    as_of: date | None = None


def _as_of(cfg: RecalibrateConfig) -> date:
    return cfg.as_of or date.today()


def parse_window(value: str) -> int:
    text = value.strip().lower()
    m = re.match(r"^(\d+)\s*d?$", text)
    if not m:
        raise ValueError(f"Invalid window '{value}' (use e.g. 90d)")
    days = int(m.group(1))
    if days <= 0:
        raise ValueError("window must be positive")
    return days


def select_positions(
    repo: PortfolioRepository, cfg: RecalibrateConfig
) -> list[tuple[Any, bool]]:
    """
    Positions closed within W, or open with hold_days ≥ H.

    Returns list of (position, pseudo_closed).
    """
    as_of = _as_of(cfg)
    start = as_of - timedelta(days=cfg.window_days)
    out: list[tuple[Any, bool]] = []
    for pos in repo.list_closed_positions():
        assert pos.close_ts is not None
        close_d = pos.close_ts.date()
        if start <= close_d <= as_of:
            out.append((pos, False))
    for pos in repo.list_open_positions():
        hold = (as_of - pos.open_ts.date()).days
        if hold >= cfg.min_hold_days:
            out.append((pos, True))
    return out


def spearman(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None

    def ranks(vals: list[float]) -> list[float]:
        order = sorted(range(n), key=lambda i: vals[i])
        r = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r

    rx, ry = ranks(xs), ranks(ys)
    mx = sum(rx) / n
    my = sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    denx = math.sqrt(sum((a - mx) ** 2 for a in rx))
    deny = math.sqrt(sum((b - my) ** 2 for b in ry))
    if denx == 0 or deny == 0:
        return None
    return num / (denx * deny)


def partial_corr(x: list[float], y: list[float], controls: list[list[float]]) -> float | None:
    """Partial correlation of x,y controlling for columns in controls (via residuals)."""
    n = len(x)
    if n < 5:
        return None
    # Simple successive residualization via univariate OLS against each control.
    def resid(dep: list[float], preds: list[list[float]]) -> list[float]:
        r = list(dep)
        for p in preds:
            mp = sum(p) / n
            mr = sum(r) / n
            var = sum((v - mp) ** 2 for v in p)
            if var == 0:
                continue
            cov = sum((p[i] - mp) * (r[i] - mr) for i in range(n))
            beta = cov / var
            r = [r[i] - beta * (p[i] - mp) for i in range(n)]
        return r

    rx = resid(x, controls)
    ry = resid(y, controls)
    return spearman(rx, ry)


def _forward_pairs(
    repo: PortfolioRepository,
    *,
    as_of: date,
    window_days: int,
    universe_version: str | None = None,
) -> list[dict[str, Any]]:
    """Build (score_t, forward_return_t→t+W) pairs from snapshots + marks."""
    rows = repo.conn.execute(
        """
        SELECT snapshot_id, date, ticker, universe_version, score,
               pillar_fundamentals, pillar_momentum, pillar_attention,
               coverage_flags
        FROM scanner_snapshots
        WHERE date <= ?
        ORDER BY date, ticker
        """,
        (as_of.isoformat(),),
    ).fetchall()
    pairs: list[dict[str, Any]] = []
    for row in rows:
        if universe_version and row["universe_version"] != universe_version:
            continue
        t0 = date.fromisoformat(row["date"])
        t1 = t0 + timedelta(days=window_days)
        if t1 > as_of:
            continue
        p0 = repo.get_mark_on_or_before(row["ticker"], t0)
        p1 = repo.get_mark_on_or_before(row["ticker"], t1)
        if p0 is None or p1 is None:
            continue
        pairs.append(
            {
                "date": t0,
                "ticker": row["ticker"],
                "universe_version": row["universe_version"],
                "score": float(row["score"]),
                "forward_return": log_return(p0, p1),
                "fundamentals": row["pillar_fundamentals"],
                "momentum": row["pillar_momentum"],
                "attention": row["pillar_attention"],
                "coverage_flags": json.loads(row["coverage_flags"] or "{}"),
            }
        )
    return pairs


def _top_decile_hit_rate(pairs: list[dict[str, Any]]) -> float | None:
    if len(pairs) < 10:
        return None
    by_date: dict[date, list[dict[str, Any]]] = {}
    for p in pairs:
        by_date.setdefault(p["date"], []).append(p)
    hits = 0
    total = 0
    for day_rows in by_date.values():
        if len(day_rows) < 10:
            continue
        scores = [r["score"] for r in day_rows]
        rets = [r["forward_return"] for r in day_rows]
        med = sorted(rets)[len(rets) // 2]
        for r in day_rows:
            if score_decile(r["score"], scores) == 10:
                total += 1
                if r["forward_return"] > med:
                    hits += 1
    if total == 0:
        return None
    return hits / total


def run_recalibrate(
    repo: PortfolioRepository,
    cfg: RecalibrateConfig | None = None,
    *,
    report_dir: Path | None = None,
    previous_report: Path | None = None,
) -> dict[str, Any]:
    cfg = cfg or RecalibrateConfig()
    as_of = _as_of(cfg)
    report_dir = Path(report_dir) if report_dir else DEFAULT_REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    selected = select_positions(repo, cfg)
    attributions: list[AttributionRow] = []
    for pos, pseudo in selected:
        try:
            attributions.append(
                attribute_position(
                    repo,
                    pos,
                    as_of=as_of if pseudo else None,
                )
            )
        except ValueError:
            continue

    pairs = _forward_pairs(repo, as_of=as_of, window_days=cfg.window_days)
    scores = [p["score"] for p in pairs]
    fwds = [p["forward_return"] for p in pairs]
    rho = spearman(scores, fwds)
    hit = _top_decile_hit_rate(pairs)

    # Pillar partial correlations
    pillar_stats: dict[str, Any] = {}
    for name, key in (
        ("fundamentals", "fundamentals"),
        ("momentum", "momentum"),
        ("attention", "attention"),
    ):
        xs = [p[key] for p in pairs if p[key] is not None]
        ys = [p["forward_return"] for p in pairs if p[key] is not None]
        others = [
            [float(p[k]) for p in pairs if p[key] is not None and p[k] is not None]
            for k in ("fundamentals", "momentum", "attention")
            if k != key
        ]
        # Align rows where all three pillars present
        aligned_x: list[float] = []
        aligned_y: list[float] = []
        aligned_c: list[list[float]] = [[], []]
        for p in pairs:
            vals = [p["fundamentals"], p["momentum"], p["attention"]]
            if any(v is None for v in vals):
                continue
            aligned_y.append(p["forward_return"])
            if key == "fundamentals":
                aligned_x.append(float(p["fundamentals"]))
                aligned_c[0].append(float(p["momentum"]))
                aligned_c[1].append(float(p["attention"]))
            elif key == "momentum":
                aligned_x.append(float(p["momentum"]))
                aligned_c[0].append(float(p["fundamentals"]))
                aligned_c[1].append(float(p["attention"]))
            else:
                aligned_x.append(float(p["attention"]))
                aligned_c[0].append(float(p["fundamentals"]))
                aligned_c[1].append(float(p["momentum"]))
        pc = partial_corr(aligned_x, aligned_y, aligned_c) if aligned_x else None
        pillar_stats[name] = {
            "partial_corr": pc,
            "n": len(aligned_x),
            "flag_weak": pc is not None and abs(pc) < 0.03,
        }

    # Thesis discipline
    closed_attrs = [a for a in attributions if not a.pseudo_closed]
    falsifier_triggered = 0
    falsifier_closed = 0
    for pos, _pseudo in selected:
        if pos.status != PositionStatus.CLOSED:
            continue
        if pos.close_reason == CloseReason.THESIS_BROKEN:
            falsifier_triggered += 1
            falsifier_closed += 1
    conviction_pairs: list[tuple[float, float]] = []
    for pos, pseudo in selected:
        thesis = repo.get_thesis(pos.position_id)
        if thesis is None:
            continue
        try:
            row = attribute_position(repo, pos, as_of=as_of if pseudo else None)
        except ValueError:
            continue
        if row.excess_vs_decile is None:
            continue
        conviction_pairs.append((float(thesis.conviction), row.excess_vs_decile))
    conv_corr = None
    if len(conviction_pairs) >= 3:
        conv_corr = spearman(
            [c for c, _ in conviction_pairs],
            [e for _, e in conviction_pairs],
        )

    # Coverage bias: share missing EV/EBITDA in top decile vs universe
    coverage = _coverage_bias(pairs)

    suggestions = _suggestions(pillar_stats, rho, hit, conv_corr, coverage)

    payload: dict[str, Any] = {
        "as_of": as_of.isoformat(),
        "window_days": cfg.window_days,
        "min_hold_days": cfg.min_hold_days,
        "n_positions": len(attributions),
        "positions": [asdict(a) for a in attributions],
        "score_power": {
            "spearman_score_fwd": rho,
            "top_decile_hit_rate": hit,
            "n_pairs": len(pairs),
        },
        "pillars": pillar_stats,
        "thesis_discipline": {
            "falsifier_triggered_and_closed": falsifier_closed,
            "conviction_vs_excess_decile_corr": conv_corr,
            "n_conviction_pairs": len(conviction_pairs),
        },
        "coverage_bias": coverage,
        "suggestions": suggestions,
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }

    prev = previous_report or _latest_report(report_dir, before=as_of)
    delta = _delta(payload, prev) if prev else None
    payload["delta_vs_previous"] = delta
    payload["previous_report"] = str(prev) if prev else None

    md_path = report_dir / f"recal_{as_of.isoformat()}.md"
    json_path = report_dir / f"recal_{as_of.isoformat()}.json"
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    payload["report_path"] = str(md_path)
    payload["json_path"] = str(json_path)
    return payload


def _coverage_bias(pairs: list[dict[str, Any]]) -> dict[str, Any]:
    if not pairs:
        return {"top_decile_missing_ev_share": None, "universe_missing_ev_share": None, "flag": False}

    def missing_ev(p: dict[str, Any]) -> bool:
        flags = p.get("coverage_flags") or {}
        # Treat absent value_ev_rung / explicit missing as coverage gap.
        if flags.get("ev_ebitda") in ("missing", "absent", False):
            return True
        if flags.get("value_ev_rung") in (None, "", "missing"):
            # only count when coverage_flags explicitly tracked value_coverage low
            vc = flags.get("value_coverage")
            if vc is not None and float(vc) < 1.0:
                return True
        return False

    by_date: dict[date, list[dict[str, Any]]] = {}
    for p in pairs:
        by_date.setdefault(p["date"], []).append(p)

    top_miss = 0
    top_n = 0
    uni_miss = 0
    uni_n = 0
    for day_rows in by_date.values():
        scores = [r["score"] for r in day_rows]
        for r in day_rows:
            uni_n += 1
            if missing_ev(r):
                uni_miss += 1
            if score_decile(r["score"], scores) == 10:
                top_n += 1
                if missing_ev(r):
                    top_miss += 1
    top_share = (top_miss / top_n) if top_n else None
    uni_share = (uni_miss / uni_n) if uni_n else None
    flag = (
        top_share is not None
        and uni_share is not None
        and abs(top_share - uni_share) >= 0.10
    )
    return {
        "top_decile_missing_ev_share": top_share,
        "universe_missing_ev_share": uni_share,
        "flag": flag,
    }


def _suggestions(
    pillars: dict[str, Any],
    rho: float | None,
    hit: float | None,
    conv_corr: float | None,
    coverage: dict[str, Any],
) -> list[str]:
    out: list[str] = []
    for name, st in pillars.items():
        if st.get("flag_weak"):
            out.append(
                f"{name.capitalize()}-Säule: partielle Korrelation "
                f"{st['partial_corr']:.3f} (|ρ|<0.03) — Gewichtung zur Überprüfung erwägen "
                "bis das Signal kalibriert ist."
            )
    if rho is not None and abs(rho) < 0.02:
        out.append(
            f"Score-Prognosekraft schwach (Spearman ρ={rho:.3f}) — "
            "keine automatische Gewichtungsänderung; manueller Review der Basis-Säulen."
        )
    if hit is not None and hit < 0.50:
        out.append(
            f"Top-Dezil-Trefferquote {hit:.1%} unter 50% — "
            "Ranking trennt Forward-Returns derzeit schlecht."
        )
    if conv_corr is not None and abs(conv_corr) < 0.05:
        out.append(
            "Conviction vs. Excess-Dezil ≈ 0 — diskretionäre Selektion wirkt wie Rauschen; "
            "Score allein kann ausreichen."
        )
    elif conv_corr is not None and conv_corr > 0.2:
        out.append(
            f"Conviction korreliert mit Excess (ρ={conv_corr:.2f}) — "
            "Thesenarbeit trägt messbares Alpha."
        )
    if coverage.get("flag"):
        out.append(
            "Coverage-Bias: fehlende EV/EBITDA-Anteile im Top-Dezil weichen vom Universum ab "
            f"(top={coverage['top_decile_missing_ev_share']}, "
            f"univ={coverage['universe_missing_ev_share']})."
        )
    if not out:
        out.append("Keine kritischen Flags in diesem Fenster — Konfiguration belassen.")
    return out


def _latest_report(report_dir: Path, *, before: date) -> Path | None:
    files = sorted(report_dir.glob("recal_*.json"))
    prev = None
    for f in files:
        try:
            d = date.fromisoformat(f.stem.replace("recal_", ""))
        except ValueError:
            continue
        if d < before:
            prev = f
    return prev


def _delta(current: dict[str, Any], prev_path: Path) -> dict[str, Any]:
    try:
        prev = json.loads(prev_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    cur_sp = current.get("score_power") or {}
    prev_sp = prev.get("score_power") or {}

    def d(a, b):
        if a is None or b is None:
            return None
        return a - b

    return {
        "previous_as_of": prev.get("as_of"),
        "spearman_delta": d(cur_sp.get("spearman_score_fwd"), prev_sp.get("spearman_score_fwd")),
        "hit_rate_delta": d(cur_sp.get("top_decile_hit_rate"), prev_sp.get("top_decile_hit_rate")),
        "n_positions_delta": d(current.get("n_positions"), prev.get("n_positions")),
    }


def _fmt(v: Any, digits: int = 4) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{digits}f}"
    return str(v)


def _render_markdown(payload: dict[str, Any]) -> str:
    sp = payload["score_power"]
    lines = [
        f"# Recalibration report — {payload['as_of']}",
        "",
        f"- Window: **{payload['window_days']}d** · min hold: **{payload['min_hold_days']}d**",
        f"- Positions in sample: **{payload['n_positions']}**",
        f"- Generated (UTC): `{payload['generated_at_utc']}`",
        "",
        "## Score predictive power",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Spearman ρ(score, fwd return) | {_fmt(sp.get('spearman_score_fwd'))} |",
        f"| Top-decile hit rate | {_fmt(sp.get('top_decile_hit_rate'), 3)} |",
        f"| n pairs | {sp.get('n_pairs')} |",
        "",
        "## Pillar partial correlations",
        "",
        "| Pillar | partial ρ | n | weak flag |",
        "| --- | ---: | ---: | --- |",
    ]
    for name, st in payload["pillars"].items():
        lines.append(
            f"| {name} | {_fmt(st.get('partial_corr'))} | {st.get('n')} | "
            f"{'yes' if st.get('flag_weak') else 'no'} |"
        )
    lines += [
        "",
        "## Thesis discipline",
        "",
        f"- Falsifier triggered & closed: "
        f"**{payload['thesis_discipline']['falsifier_triggered_and_closed']}**",
        f"- Conviction vs excess-decile ρ: "
        f"**{_fmt(payload['thesis_discipline']['conviction_vs_excess_decile_corr'])}**",
        "",
        "## Coverage bias",
        "",
        f"- Top-decile missing EV share: "
        f"**{_fmt(payload['coverage_bias'].get('top_decile_missing_ev_share'), 3)}**",
        f"- Universe missing EV share: "
        f"**{_fmt(payload['coverage_bias'].get('universe_missing_ev_share'), 3)}**",
        f"- Flag: **{payload['coverage_bias'].get('flag')}**",
        "",
        "## Positions",
        "",
        "| ticker | hold_days | realized | benchmark | decile | excess_b | outcome |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for p in payload["positions"]:
        lines.append(
            f"| {p['ticker']} | {p['hold_days']} | {_fmt(p['realized_return'])} | "
            f"{_fmt(p['benchmark_return'])} | {_fmt(p['decile_return'])} | "
            f"{_fmt(p['excess_vs_benchmark'])} | {p['thesis_outcome']} |"
        )
    if payload.get("delta_vs_previous"):
        d = payload["delta_vs_previous"]
        lines += [
            "",
            f"## Delta vs previous ({d.get('previous_as_of')})",
            "",
            f"- Spearman Δ: {_fmt(d.get('spearman_delta'))}",
            f"- Hit-rate Δ: {_fmt(d.get('hit_rate_delta'), 3)}",
            f"- n positions Δ: {_fmt(d.get('n_positions_delta'), 0)}",
        ]
    lines += ["", "## Vorgeschlagene Prüfungen", ""]
    for s in payload["suggestions"]:
        lines.append(f"- {s}")
    lines += [
        "",
        "---",
        "",
        "_Diagnostic only — no automatic weight changes._",
        "",
    ]
    return "\n".join(lines)
