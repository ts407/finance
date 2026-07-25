from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from standing.config import load_scoring_config
from standing.pipeline.report import render_html_report
from standing.pipeline.snapshot import persist_snapshot, run_snapshot
from standing.providers import MARKET_MODES, SOCIAL_MODES, build_market_provider, build_social_provider

console = Console()


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
