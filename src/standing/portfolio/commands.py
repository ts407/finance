"""CLI command handlers for portfolio / journal."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from standing.portfolio.cli_support import drift_bucket, open_repository, parse_horizon
from standing.portfolio.exceptions import (
    FalsifierTooShortError,
    OpenPositionExistsError,
    PortfolioError,
    PositionAlreadyClosedError,
    PositionNotFoundError,
    SnapshotNotFoundError,
)
from standing.portfolio.models import CloseReason

console = Console()


def _db_path(args: argparse.Namespace) -> Path | None:
    raw = getattr(args, "db", None)
    return Path(raw) if raw else None


def cmd_buy(args: argparse.Namespace) -> int:
    repo = open_repository(_db_path(args))
    ticker = args.ticker.upper()
    try:
        horizon_days = parse_horizon(args.horizon)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    snap = repo.get_latest_snapshot(ticker)
    if snap is None:
        console.print(
            f"[red]No scanner_snapshot for {ticker}.[/red] "
            "Ingest/score first so buy can bind entry_snapshot_id."
        )
        return 2

    try:
        position, thesis, entry = repo.open_position(
            ticker=ticker,
            entry_price=float(args.price),
            size=float(args.size),
            claim=args.thesis,
            mechanism=args.mechanism,
            falsifier=args.falsifier,
            target_price=float(args.target),
            stop_price=float(args.stop),
            horizon_days=horizon_days,
            conviction=int(args.conviction),
            entry_snapshot_id=snap.snapshot_id,
            reference_class=args.reference_class,
        )
    except FalsifierTooShortError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    except (OpenPositionExistsError, SnapshotNotFoundError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    except PortfolioError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    console.print(
        f"[bold green]Opened[/bold green] {position.ticker}  "
        f"position_id={position.position_id}  entry={position.entry_price}  "
        f"size={position.size}  snapshot_id={snap.snapshot_id}  "
        f"score@entry={snap.score:.1f}"
    )
    console.print(
        f"thesis_id={thesis.thesis_id}  horizon_days={thesis.horizon_days}  "
        f"conviction={thesis.conviction}  journal_entry_id={entry.entry_id}"
    )
    return 0


def cmd_sell(args: argparse.Namespace) -> int:
    repo = open_repository(_db_path(args))
    ticker = args.ticker.upper()
    note = (args.note or "").strip()
    if not note:
        console.print("[red]--note is required (exit_note in journal).[/red]")
        return 2
    try:
        reason = CloseReason(args.reason)
    except ValueError:
        console.print(f"[red]Invalid reason '{args.reason}'[/red]")
        return 2

    snap = repo.get_latest_snapshot(ticker)
    try:
        position, entry = repo.close_position(
            ticker=ticker,
            close_price=float(args.price),
            reason=reason,
            exit_note=note,
            linked_snapshot_id=snap.snapshot_id if snap else None,
        )
    except (PositionNotFoundError, PositionAlreadyClosedError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 2

    pnl = (position.close_price / position.entry_price - 1.0) * 100.0
    console.print(
        f"[bold]Closed[/bold] {position.ticker}  reason={position.close_reason.value}  "
        f"entry={position.entry_price}  close={position.close_price}  "
        f"pnl={pnl:+.2f}%  exit_note_id={entry.entry_id}"
    )
    return 0


def cmd_journal(args: argparse.Namespace) -> int:
    repo = open_repository(_db_path(args))
    ticker = args.ticker.upper()
    open_pos = repo.get_open_position(ticker)
    snap = repo.get_latest_snapshot(ticker)
    try:
        entry = repo.add_journal_entry(
            ticker=ticker,
            body=args.note,
            position_id=open_pos.position_id if open_pos else None,
            linked_snapshot_id=snap.snapshot_id if snap else None,
        )
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    console.print(
        f"[bold]Journal[/bold] {entry.ticker}  entry_id={entry.entry_id}  "
        f"type={entry.entry_type.value}  ts={entry.ts.isoformat()}"
    )
    return 0


def cmd_watchlist_add(args: argparse.Namespace) -> int:
    repo = open_repository(_db_path(args))
    ticker = args.ticker.upper()
    snap = repo.get_latest_snapshot(ticker)
    try:
        entry = repo.add_watchlist_thesis(
            ticker=ticker,
            thesis=args.thesis,
            falsifier=args.falsifier,
            linked_snapshot_id=snap.snapshot_id if snap else None,
        )
    except (FalsifierTooShortError, ValueError) as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    console.print(
        f"[bold]Watchlist[/bold] {entry.ticker}  entry_id={entry.entry_id}  "
        f"linked_snapshot={entry.linked_snapshot_id}"
    )
    return 0


def cmd_portfolio(args: argparse.Namespace) -> int:
    repo = open_repository(_db_path(args))
    positions = repo.list_open_positions()
    marks = _parse_marks(getattr(args, "mark", None) or [])

    table = Table(title="Open portfolio")
    for col in (
        "ticker",
        "entry_px",
        "now_px",
        "pnl%",
        "score@entry",
        "score_now",
        "drift",
        "dist_target",
        "dist_stop",
    ):
        table.add_column(col)

    if not positions:
        console.print("[dim]No open positions.[/dim]")
        return 0

    for pos in positions:
        thesis = repo.get_thesis(pos.position_id)
        entry_snap = repo.get_snapshot(pos.entry_snapshot_id)
        now_snap = repo.get_latest_snapshot(pos.ticker)
        score_entry = entry_snap.score
        score_now = now_snap.score if now_snap else None
        drift = (score_now - score_entry) if score_now is not None else None
        bucket = drift_bucket(drift)
        drift_style = {
            "green": "green",
            "yellow": "yellow",
            "red": "red",
            "n/a": "dim",
        }[bucket]

        now_px = marks.get(pos.ticker)
        if now_px is not None:
            pnl = (now_px / pos.entry_price - 1.0) * 100.0
            now_s = f"{now_px:.2f}"
            pnl_s = f"{pnl:+.2f}"
            if thesis:
                dist_t = (thesis.target_price / now_px - 1.0) * 100.0
                dist_s = (thesis.stop_price / now_px - 1.0) * 100.0
                dist_t_s = f"{dist_t:+.1f}%"
                dist_s_s = f"{dist_s:+.1f}%"
            else:
                dist_t_s = dist_s_s = "—"
        else:
            now_s = pnl_s = "—"
            if thesis:
                dist_t_s = f"tgt {thesis.target_price:.2f}"
                dist_s_s = f"stp {thesis.stop_price:.2f}"
            else:
                dist_t_s = dist_s_s = "—"

        drift_s = f"{drift:+.1f}" if drift is not None else "—"
        table.add_row(
            pos.ticker,
            f"{pos.entry_price:.2f}",
            now_s,
            pnl_s,
            f"{score_entry:.1f}",
            f"{score_now:.1f}" if score_now is not None else "—",
            f"[{drift_style}]{drift_s}[/{drift_style}]",
            dist_t_s,
            dist_s_s,
        )

    console.print(table)
    console.print(
        f"[dim]as_of_local_display={datetime.now().astimezone().isoformat()}  "
        f"store=UTC  db={repo.conn.execute('PRAGMA database_list').fetchone()['file']}[/dim]"
    )
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    from standing.portfolio.attribution import review_closed

    repo = open_repository(_db_path(args))
    rows = review_closed(repo)
    table = Table(title="Closed-position review (attribution)")
    table.add_column("ticker")
    table.add_column("hold_days", justify="right")
    table.add_column("realized", justify="right")
    table.add_column("benchmark", justify="right")
    table.add_column("decile", justify="right")
    table.add_column("excess_b", justify="right")
    table.add_column("excess_d", justify="right")
    table.add_column("thesis_outcome", min_width=10)
    if not rows:
        console.print("[dim]No closed positions.[/dim]")
        return 0
    for r in rows:
        table.add_row(
            r.ticker,
            str(r.hold_days),
            f"{r.realized_return:+.4f}",
            f"{r.benchmark_return:+.4f}" if r.benchmark_return is not None else "—",
            f"{r.decile_return:+.4f}" if r.decile_return is not None else "—",
            f"{r.excess_vs_benchmark:+.4f}" if r.excess_vs_benchmark is not None else "—",
            f"{r.excess_vs_decile:+.4f}" if r.excess_vs_decile is not None else "—",
            r.thesis_outcome,
        )
    console.print(table)
    return 0


def cmd_recalibrate(args: argparse.Namespace) -> int:
    from pathlib import Path

    from standing.portfolio.recalibrate import RecalibrateConfig, parse_window, run_recalibrate

    repo = open_repository(_db_path(args))
    try:
        window_days = parse_window(args.window)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 2
    cfg = RecalibrateConfig(
        window_days=window_days,
        min_hold_days=int(args.min_hold),
        as_of=None,
    )
    if args.as_of:
        from datetime import date as date_cls

        cfg.as_of = date_cls.fromisoformat(args.as_of)
    report_dir = Path(args.report_dir) if args.report_dir else None
    result = run_recalibrate(repo, cfg, report_dir=report_dir)
    console.print(
        f"[bold]Recalibrate[/bold] as_of={result['as_of']}  "
        f"n_positions={result['n_positions']}  "
        f"spearman={result['score_power']['spearman_score_fwd']}  "
        f"hit={result['score_power']['top_decile_hit_rate']}"
    )
    console.print(f"Wrote {result['report_path']}")
    for s in result["suggestions"]:
        console.print(f"  • {s}")
    return 0


def _parse_marks(values: list[str]) -> dict[str, float]:
    """Parse repeated ``--mark TICKER=PRICE`` flags."""
    out: dict[str, float] = {}
    for raw in values:
        if "=" not in raw:
            raise SystemExit(f"Invalid --mark '{raw}' (expected TICKER=PRICE)")
        ticker, price = raw.split("=", 1)
        out[ticker.strip().upper()] = float(price.strip())
    return out


def register_portfolio_commands(sub: argparse._SubParsersAction) -> None:
    """Attach buy/sell/journal/watchlist/portfolio/review/recalibrate."""

    def add_db(sp: argparse.ArgumentParser) -> None:
        sp.add_argument(
            "--db",
            default=None,
            help="SQLite path (default: $STANDING_DATA_DIR/portfolio/standing.db)",
        )

    buy = sub.add_parser("buy", help="Open position + immutable thesis + journal entry")
    add_db(buy)
    buy.add_argument("ticker")
    buy.add_argument("--price", type=float, required=True)
    buy.add_argument("--size", type=float, required=True)
    buy.add_argument("--thesis", required=True)
    buy.add_argument("--mechanism", required=True)
    buy.add_argument("--falsifier", required=True, help="Non-empty, min 20 characters")
    buy.add_argument("--target", type=float, required=True)
    buy.add_argument("--stop", type=float, required=True)
    buy.add_argument("--horizon", default="90d", help="e.g. 90, 90d, 12M")
    buy.add_argument("--conviction", type=int, default=3, choices=range(1, 6))
    buy.add_argument("--reference-class", default=None, dest="reference_class")
    buy.set_defaults(func=cmd_buy)

    sell = sub.add_parser("sell", help="Close open position (requires exit note)")
    add_db(sell)
    sell.add_argument("ticker")
    sell.add_argument("--price", type=float, required=True)
    sell.add_argument(
        "--reason",
        required=True,
        choices=[c.value for c in CloseReason],
    )
    sell.add_argument("--note", required=True, help="exit_note body (required)")
    sell.set_defaults(func=cmd_sell)

    journal = sub.add_parser("journal", help="Append a journal update (no trade)")
    add_db(journal)
    journal.add_argument("ticker")
    journal.add_argument("--note", required=True)
    journal.set_defaults(func=cmd_journal)

    watch = sub.add_parser("watchlist", help="Watchlist thesis helpers")
    watch_sub = watch.add_subparsers(dest="watch_cmd", required=True)
    wadd = watch_sub.add_parser("add", help="Add watchlist thesis (falsifier required)")
    add_db(wadd)
    wadd.add_argument("ticker")
    wadd.add_argument("--thesis", required=True)
    wadd.add_argument("--falsifier", required=True)
    wadd.set_defaults(func=cmd_watchlist_add)

    port = sub.add_parser("portfolio", help="List open positions with score drift")
    add_db(port)
    port.add_argument(
        "--mark",
        action="append",
        default=[],
        help="Mark price TICKER=PRICE (repeatable) for pnl%% / distances",
    )
    port.set_defaults(func=cmd_portfolio)

    rev = sub.add_parser("review", help="Closed positions with return attribution")
    add_db(rev)
    rev.set_defaults(func=cmd_review)

    rec = sub.add_parser(
        "recalibrate",
        help="Diagnostic recalibration report (no automatic weight changes)",
    )
    add_db(rec)
    rec.add_argument("--window", default="90d", help="Lookback window (e.g. 90d)")
    rec.add_argument("--min-hold", type=int, default=30, dest="min_hold")
    rec.add_argument("--as-of", default=None, dest="as_of", help="YYYY-MM-DD")
    rec.add_argument(
        "--report-dir",
        default=None,
        dest="report_dir",
        help="Output directory (default: reports/)",
    )
    rec.set_defaults(func=cmd_recalibrate)
