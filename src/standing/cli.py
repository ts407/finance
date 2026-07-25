from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from standing.config import load_scoring_config
from standing.envfile import load_env
from standing.pipeline.report import render_html_report
from standing.pipeline.snapshot import persist_snapshot, run_snapshot
from standing.providers import MARKET_MODES, SOCIAL_MODES, build_market_provider, build_social_provider

console = Console()
load_env()


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def _providers(args: argparse.Namespace):
    return (
        build_market_provider(getattr(args, "market", "fixture")),
        build_social_provider(getattr(args, "social", "fixture"), history_days=args.history_days),
    )


def cmd_score(args: argparse.Namespace) -> int:
    cfg = load_scoring_config(Path(args.config) if args.config else None)
    if not cfg.placeholder:
        console.print("[yellow]Warning:[/yellow] placeholder is false — verify empirical freeze.")
    as_of = _parse_date(args.as_of)
    market, social = _providers(args)
    snap = run_snapshot(
        as_of=as_of,
        market=market,
        social=social,
        cfg=cfg,
        market_mode=getattr(args, "market", None),
        social_mode=getattr(args, "social", None),
    )
    out = Path(args.out)
    path = persist_snapshot(snap, out)
    console.print(
        f"[bold]Final Standing snapshot[/bold]  as_of={snap.as_of}  "
        f"universe={snap.universe_id}  n={len(snap.standings)}  "
        f"score_kind={snap.score_kind}  market={snap.meta.get('market_provider')}  "
        f"social={snap.meta.get('social_provider')}"
    )
    console.print(f"Wrote {path}")
    if snap.meta["low_confidence_sectors"]:
        console.print(
            "[yellow]Low-confidence sectors[/yellow] "
            f"(<{cfg.universe['min_names_per_sector']} names): "
            + ", ".join(snap.meta["low_confidence_sectors"])
        )
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    """Compute and write the immutable daily snapshot (forward-eval log)."""
    from standing.pipeline.store import SnapshotExistsError, persist_immutable

    cfg = load_scoring_config(Path(args.config) if args.config else None)
    as_of = _parse_date(args.as_of)
    market, social = _providers(args)
    snap = run_snapshot(
        as_of=as_of,
        market=market,
        social=social,
        cfg=cfg,
        market_mode=args.market,
        social_mode=args.social,
    )
    root = Path(args.out)
    try:
        path = persist_immutable(snap, root=root, force=bool(args.force))
    except SnapshotExistsError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    console.print(
        f"[bold]Immutable day log[/bold]  as_of={snap.as_of}  "
        f"universe={snap.universe_id}  n={len(snap.standings)}  "
        f"market={snap.meta.get('market_provider')}  social={snap.meta.get('social_provider')}"
    )
    console.print(f"Wrote {path}")
    return 0


def cmd_metrics_report(args: argparse.Namespace) -> int:
    """Universe consistency check: missing / non-positive share per metric."""
    cfg = load_scoring_config(Path(args.config) if args.config else None)
    as_of = _parse_date(args.as_of)
    market, _social = _providers(args)
    frame = market.fetch(as_of)
    cols = [
        "pe_ttm",
        "pb",
        "ev_ebitda",
        "ev_ebit",
        "ev_sales",
        "roe",
        "operating_margin",
        "revenue_growth_yoy",
        "ret_1m",
        "ret_3m",
        "ret_6m",
        "relative_volume",
    ]
    table = Table(title=f"Metric consistency — {as_of}  n={len(frame)}")
    table.add_column("metric")
    table.add_column("missing %", justify="right")
    table.add_column("nonpos %", justify="right")
    table.add_column("p50", justify="right")
    for col in cols:
        if col not in frame.columns:
            table.add_row(col, "—", "—", "—")
            continue
        s = frame[col]
        miss = float(s.isna().mean() * 100)
        nonpos = float(((s.notna()) & (s <= 0)).mean() * 100)
        p50 = s.median(skipna=True)
        table.add_row(
            col,
            f"{miss:.1f}",
            f"{nonpos:.1f}",
            "—" if p50 != p50 else f"{p50:.3g}",  # noqa: PLR0124 — NaN check
        )
    console.print(table)
    console.print(
        f"[dim]methodology={cfg.methodology_version}  "
        "nonpos = present but ≤0 (should rank worst, not 'missing')[/dim]"
    )
    return 0


def cmd_table(args: argparse.Namespace) -> int:
    cfg = load_scoring_config(Path(args.config) if args.config else None)
    as_of = _parse_date(args.as_of)
    market, social = _providers(args)
    snap = run_snapshot(
        as_of=as_of,
        market=market,
        social=social,
        cfg=cfg,
    )
    top = snap.standings.head(args.top)

    table = Table(
        title=(
            f"Final Standing (editorial_descriptive) — {snap.as_of} "
            f"[placeholder={snap.placeholder}] social={snap.meta.get('social_provider')}"
        )
    )
    for col in (
        "ticker",
        "sector",
        "value",
        "quality",
        "momentum",
        "composite_standing",
        "attention_tilt",
        "final_standing",
        "n",
        "confidence_c",
        "social_badge",
    ):
        table.add_column(col, justify="right" if col not in ("ticker", "sector", "social_badge") else "left")

    for _, row in top.iterrows():
        table.add_row(
            row["ticker"],
            str(row["sector"])[:18],
            f"{row['value']:.1f}",
            f"{row['quality']:.1f}",
            f"{row['momentum']:.1f}",
            f"{row['composite_standing']:.1f}",
            f"{row['attention_tilt']:+.2f}",
            f"{row['final_standing']:.1f}",
            f"{row['n']:.0f}",
            f"{row['confidence_c']:.2f}",
            row["social_badge"],
        )
    console.print(table)
    console.print(
        "[dim]Composite Standing = equal-weight V/Q/M. "
        "Attention Tilt is bounded (tanh) and secondary. Not investment advice.[/dim]"
    )
    return 0


def cmd_heat(args: argparse.Namespace) -> int:
    """Attention board — primary heat surface, separate from composite."""
    cfg = load_scoring_config(Path(args.config) if args.config else None)
    as_of = _parse_date(args.as_of)
    market, social = _providers(args)
    snap = run_snapshot(
        as_of=as_of,
        market=market,
        social=social,
        cfg=cfg,
    )
    heat = snap.standings.sort_values("s_used", ascending=False).head(args.top)

    table = Table(
        title=(
            f"Attention Heat Board — {snap.as_of}  (loud ≠ good)  "
            f"social={snap.meta.get('social_provider')}"
        )
    )
    for col in ("ticker", "s_obs", "s_used", "n", "confidence_c", "neg_share", "attention_tilt", "final_standing", "social_badge"):
        table.add_column(col, justify="right" if col != "ticker" and col != "social_badge" else "left")
    for _, row in heat.iterrows():
        table.add_row(
            row["ticker"],
            f"{row['s_obs']:.1f}",
            f"{row['s_used']:.1f}",
            f"{row['n']:.0f}",
            f"{row['confidence_c']:.2f}",
            f"{row['neg_share']:.2f}",
            f"{row['attention_tilt']:+.2f}",
            f"{row['final_standing']:.1f}",
            row["social_badge"],
        )
    console.print(table)
    console.print("[dim]Heat is attention context, not a recommendation.[/dim]")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    cfg = load_scoring_config(Path(args.config) if args.config else None)
    as_of = _parse_date(args.as_of)
    market, social = _providers(args)
    snap = run_snapshot(
        as_of=as_of,
        market=market,
        social=social,
        cfg=cfg,
    )
    out = Path(args.out)
    path = render_html_report(snap, out)
    persist_snapshot(snap, out.parent / "snapshots")
    console.print(f"Wrote HTML report {path}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Web extras required. Install with: pip install -e '.[web]'"
        ) from exc
    from standing.web.app import app

    console.print(
        f"[bold]Standing[/bold] web desk → http://{args.host}:{args.port}  "
        "(editorial_descriptive · not investment advice)"
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="standing",
        description="Descriptive V/Q/M standing screener with bounded social attention tilt",
    )
    p.add_argument("--config", default=None, help="Path to scoring.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--as-of", default=None, help="YYYY-MM-DD (default: today)")
        sp.add_argument("--history-days", type=int, default=14)
        sp.add_argument(
            "--market",
            default="fixture",
            choices=list(MARKET_MODES),
            help="Market provider: fixture | stooq (real OHLCV overlay) | finnhub | live",
        )
        sp.add_argument(
            "--social",
            default="fixture",
            choices=list(SOCIAL_MODES),
            help=(
                "Social/attention provider: fixture (CI default), wikipedia, bluesky, "
                "open (wiki+bluesky), all (fixture+open)"
            ),
        )

    s = sub.add_parser("score", help="Compute and persist a standing snapshot")
    add_common(s)
    s.add_argument("--out", default="artifacts/snapshots")
    s.set_defaults(func=cmd_score)

    ing = sub.add_parser(
        "ingest",
        help="Write immutable daily snapshot for forward-eval (first write wins)",
    )
    add_common(ing)
    ing.add_argument("--out", default="artifacts/snapshots")
    ing.add_argument("--force", action="store_true", help="Archive prior day file then overwrite")
    ing.set_defaults(func=cmd_ingest)

    mr = sub.add_parser("metrics-report", help="Missing/non-positive metric consistency over universe")
    add_common(mr)
    mr.set_defaults(func=cmd_metrics_report)

    t = sub.add_parser("table", help="Print top Final Standing rows")
    add_common(t)
    t.add_argument("--top", type=int, default=20)
    t.set_defaults(func=cmd_table)

    h = sub.add_parser("heat", help="Print Attention Heat board (loud ≠ good)")
    add_common(h)
    h.add_argument("--top", type=int, default=20)
    h.set_defaults(func=cmd_heat)

    r = sub.add_parser("report", help="Write Standing + Heat HTML report")
    add_common(r)
    r.add_argument("--out", default="artifacts/reports/standing.html")
    r.set_defaults(func=cmd_report)

    w = sub.add_parser("serve", help="Run the Standing web interface")
    w.add_argument("--host", default="127.0.0.1")
    w.add_argument("--port", type=int, default=8000)
    w.add_argument("--log-level", default="info")
    w.set_defaults(func=cmd_serve)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
