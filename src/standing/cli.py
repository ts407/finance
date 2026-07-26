from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from standing.config import load_scoring_config
from standing.envfile import load_env
from standing.logging_config import configure_logging, get_logger
from standing.pipeline.report import render_html_report
from standing.pipeline.snapshot import persist_snapshot, run_snapshot
from standing.providers import MARKET_MODES, SOCIAL_MODES, build_market_provider, build_social_provider

console = Console()
load_env()
log = get_logger("cli")


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
        log.warning("placeholder=false — verify empirical freeze before production use")
    as_of = _parse_date(args.as_of)
    market, social = _providers(args)
    log.info("CLI score as_of=%s out=%s", as_of.isoformat(), args.out)
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
    log.info("CLI table as_of=%s top=%s", as_of.isoformat(), args.top)
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
    log.info("CLI heat as_of=%s top=%s", as_of.isoformat(), args.top)
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
    log.info("CLI report as_of=%s out=%s", as_of.isoformat(), args.out)
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
    log.info("Wrote HTML report path=%s", path)
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
    log.info(
        "Starting web desk host=%s port=%s log_level=%s",
        args.host,
        args.port,
        args.log_level,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level=args.log_level)
    return 0


def cmd_loop_analyse(args: argparse.Namespace) -> int:
    """Baseline diagnostics + hypothesis artifacts for the next optimization cycle."""
    from standing.optimization.analyse import write_baseline_report
    from standing.optimization.cycle import formulate_hypotheses, next_cycle_id, prior_reject_summary
    from standing.optimization.hypotheses import write_deferred_hypothesis, write_hypothesis
    from standing.optimization.log import append_log, latest_entry
    from standing.optimization.paths import ensure_layout

    ensure_layout()
    as_of = _parse_date(args.as_of)
    prior = latest_entry()
    rejects = prior_reject_summary()
    cycle_id = next_cycle_id(as_of)
    fine = bool(rejects) or args.fine
    console.print(
        "[bold]loop-analyse-hypothese[/bold] — "
        f"cycle={cycle_id}  as_of={as_of}  prior_rejects={len(rejects)}  fine={fine}"
    )
    if prior:
        console.print(
            f"Prior log: phase={prior.get('phase')} decision={prior.get('decision')} "
            f"hypothesis={prior.get('hypothesis_id', '-')}"
        )

    report = write_baseline_report(
        as_of=as_of,
        history_days=args.history_days,
        cycle_id=cycle_id,
        fine_sensitivity=fine,
    )
    baseline = report["baseline"]
    console.print(
        f"Baseline n={baseline['n_names']}  "
        f"spearman(final,composite)={baseline['spearman_final_vs_composite']:.4f}  "
        f"sparse={baseline['sparse_share']:.1%}  "
        f"mean|tilt|={baseline['mean_abs_tilt']:.2f}"
    )

    sens = sorted(
        report["sensitivity"],
        key=lambda row: (row["ranking_turnover_vs_baseline"], row["tilt_vs_baseline_mae"]),
    )
    console.print("Sensitivity (lowest turnover first, gated view):")
    for row in sens[:8]:
        console.print(
            f"  {row['label']}: turnover={row['ranking_turnover_vs_baseline']:.1%}  "
            f"spearman={row['spearman_final_vs_base']:.4f}  "
            f"|tilt|={row['mean_abs_tilt']:.2f}"
        )

    hyp_specs, deferred_specs = formulate_hypotheses(
        cycle_id=cycle_id,
        as_of=as_of,
        baseline=baseline,
        sensitivity=report["sensitivity"],
    )

    written: list[dict[str, str]] = []
    for spec in hyp_specs:
        hyp_path, cfg_path = write_hypothesis(
            hypothesis_id=spec["hypothesis_id"],
            basis=spec["basis"],
            overrides=spec["overrides"],
            prediction=spec["prediction"],
            cycle_id=cycle_id,
        )
        written.append(
            {"id": spec["hypothesis_id"], "hypothesis": str(hyp_path), "config": str(cfg_path)}
        )
        console.print(
            f"Hypothesis {spec['hypothesis_id']} {spec['overrides']} → {hyp_path}"
        )

    deferred_ids: list[str] = []
    for deferred in deferred_specs:
        deferred_path = write_deferred_hypothesis(
            hypothesis_id=deferred["hypothesis_id"],
            reason=deferred["reason"],
            overrides=deferred["overrides"],
            cycle_id=cycle_id,
        )
        deferred_ids.append(deferred["hypothesis_id"])
        console.print(f"Deferred {deferred['hypothesis_id']} → {deferred_path}")

    # Relativize report path for log portability
    report_path = report["report_path"]
    if report_path.startswith("/"):
        from standing.config import ROOT

        try:
            from pathlib import Path as _P

            report_path = str(_P(report_path).resolve().relative_to(ROOT.resolve()))
        except Exception:
            pass

    append_log(
        {
            "phase": "loop-analyse-hypothese",
            "cycle_id": cycle_id,
            "decision": "hypotheses_formulated",
            "as_of": as_of.isoformat(),
            "prior_rejects": [
                {"hypothesis_id": r.get("hypothesis_id"), "turnover": (r.get("metrics") or {}).get("ranking_turnover")}
                for r in rejects[-4:]
            ],
            "baseline": {
                "n_names": baseline["n_names"],
                "spearman_final_vs_composite": baseline["spearman_final_vs_composite"],
                "sparse_share": baseline["sparse_share"],
                "mean_abs_tilt": baseline["mean_abs_tilt"],
                "mean_confidence_c": baseline["mean_confidence_c"],
                "mean_n": baseline["mean_n"],
            },
            "hypotheses": [w["id"] for w in written],
            "deferred_hypotheses": deferred_ids,
            "report_path": report_path,
            "handoff": "loop-live-test-shadow",
            "productive_config_unchanged": True,
        }
    )
    console.print("Appended log entry; handoff → loop-live-test-shadow")
    console.print(f"Report: {report_path}")
    return 0


def cmd_loop_shadow(args: argparse.Namespace) -> int:
    """Shadow live-test: productive vs isolated hypothesis configs on shared data."""
    from standing.optimization.log import append_log
    from standing.optimization.cycle import latest_ready_hypothesis_ids
    from standing.optimization.paths import ensure_layout
    from standing.optimization.shadow import run_shadow_test

    ensure_layout()
    end_as_of = _parse_date(args.as_of)
    hypothesis_ids = args.hypothesis or latest_ready_hypothesis_ids() or [
        "H20260722-03",
        "H20260722-04",
    ]
    console.print(
        "[bold]loop-live-test-shadow[/bold] — "
        f"end={end_as_of}  days={args.days}  hypotheses={', '.join(hypothesis_ids)}"
    )

    results: list[dict] = []
    for hid in hypothesis_ids:
        summary = run_shadow_test(
            hypothesis_id=hid,
            end_as_of=end_as_of,
            n_days=args.days,
            history_days=args.history_days,
        )
        agg = summary["aggregates"]
        console.print(
            f"{hid}: turnover={agg['mean_ranking_turnover_vs_productive']:.1%}  "
            f"spearman_shadow={agg['mean_spearman_final_vs_composite_shadow']:.4f} "
            f"(prod={agg['mean_spearman_final_vs_composite_productive']:.4f})  "
            f"|tilt| {agg['mean_abs_tilt_productive']:.2f}→{agg['mean_abs_tilt_shadow']:.2f}  "
            f"fwd_lift={agg.get('mean_forward_spearman_lift', float('nan')):+.4f}"
        )
        append_log(
            {
                "phase": "loop-live-test-shadow",
                "cycle_id": summary.get("cycle_id"),
                "hypothesis_id": hid,
                "decision": "shadow_complete",
                "window": summary["window"],
                "aggregates": agg,
                "report_path": summary["report_path"],
                "handoff": "loop-vergleich-entscheidung",
                "productive_config_unchanged": True,
            }
        )
        results.append(summary)

    console.print(f"Completed {len(results)} shadow test(s); handoff → loop-vergleich-entscheidung")
    return 0


def cmd_loop_vergleich(args: argparse.Namespace) -> int:
    """Compare shadow vs productive and record accept/reject (no silent promote)."""
    from standing.optimization.log import append_log
    from standing.optimization.cycle import latest_ready_hypothesis_ids
    from standing.optimization.paths import ensure_layout
    from standing.optimization.vergleich import run_vergleich

    ensure_layout()
    hypothesis_ids = args.hypothesis or latest_ready_hypothesis_ids() or [
        "H20260722-03",
        "H20260722-04",
    ]
    console.print(
        "[bold]loop-vergleich-entscheidung[/bold] — "
        f"hypotheses={', '.join(hypothesis_ids)}"
    )
    for hid in hypothesis_ids:
        out = run_vergleich(hypothesis_id=hid)
        console.print(
            f"{hid}: [bold]{out['decision'].upper()}[/bold]  "
            f"accept_candidate={out.get('accept_candidate')}  "
            f"fwd_lift={out['metrics'].get('forward_spearman_lift_bootstrap', {}).get('mean', float('nan')):+.4f}  "
            f"turnover={out['metrics']['ranking_turnover']:.1%}  "
            f"promote={out['promote_to_productive']}"
        )
        console.print(f"  {out['rationale']}")
        append_log(
            {
                "phase": "loop-vergleich-entscheidung",
                "cycle_id": out.get("cycle_id"),
                "hypothesis_id": hid,
                "decision": out["decision"],
                "accept_candidate": out.get("accept_candidate"),
                "checks": out["checks"],
                "metrics": {
                    "spearman_lift": out["metrics"]["spearman_lift"],
                    "ranking_turnover": out["metrics"]["ranking_turnover"],
                    "tilt_delta": out["metrics"]["tilt_delta"],
                    "spearman_lift_bootstrap": out["metrics"]["spearman_lift_bootstrap"],
                    "forward_spearman_lift_bootstrap": out["metrics"].get(
                        "forward_spearman_lift_bootstrap"
                    ),
                    "top_decile_excess_lift_bootstrap": out["metrics"].get(
                        "top_decile_excess_lift_bootstrap"
                    ),
                },
                "promote_to_productive": out["promote_to_productive"],
                "decision_path": out["decision_path"],
                "rationale": out["rationale"],
                "handoff": "loop-analyse-hypothese",
                "productive_config_unchanged": out.get("productive_config_unchanged", True),
            }
        )
    console.print("Logged decisions; next cycle → loop-analyse-hypothese")
    return 0


def cmd_track_m_calibrate(args: argparse.Namespace) -> int:
    """Track M: validate IC apparatus on multi-year OHLCV momentum."""
    from standing.optimization.log import append_log
    from standing.research.momentum_calibrate import run_momentum_calibration

    console.print(
        "[bold]track-m-calibrate[/bold] — multi-year OHLCV momentum IC / σ_IC "
        f"(horizon={args.horizon_days}d, network={not args.offline})"
    )
    report = run_momentum_calibration(
        horizon_days=args.horizon_days,
        allow_network=not args.offline,
    )
    status = report.get("status")
    product = report.get("product_momentum_v2") or {}
    power = report.get("sigma_ic_for_power") or {}
    console.print(f"status={status}  apparatus_passed={report.get('apparatus_check', {}).get('passed')}")
    if product:
        console.print(
            f"product_momentum_v2: μ_IC={product.get('mean_ic')}  "
            f"σ_IC={product.get('sigma_ic')}  t={product.get('tstat')}  "
            f"n={product.get('n_ic_obs')}  T_80%={product.get('power_days_80')}"
        )
    console.print(f"power sizing: {power}")
    console.print(f"report: {report.get('report_path')}")
    append_log(
        {
            "phase": "track-m-calibrate",
            "track": "M",
            "decision": status,
            "apparatus_passed": report.get("apparatus_check", {}).get("passed"),
            "product_momentum_v2": product,
            "sigma_ic_for_power": power,
            "report_path": report.get("report_path"),
            "handoff": "loop-analyse-hypothese",
            "social_locked": True,
            "productive_config_unchanged": True,
        }
    )
    return 0 if status != "failed_empty_panel" else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="standing",
        description="Descriptive V/Q/M standing screener with bounded social attention tilt",
    )
    p.add_argument("--config", default=None, help="Path to scoring.yaml")
    p.add_argument(
        "--log-level",
        default=None,
        help="standing logger level (default: INFO or STANDING_LOG_LEVEL)",
    )
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
    w.add_argument(
        "--log-level",
        default="info",
        dest="serve_log_level",
        help="uvicorn access/log level (default: info)",
    )
    w.set_defaults(func=cmd_serve)

    la = sub.add_parser(
        "loop-analyse",
        help="Optimization cycle: baseline diagnostics + formulate hypotheses",
    )
    add_common(la)
    la.add_argument(
        "--fine",
        action="store_true",
        help="Force fine-grained sensitivity grid (also auto-enabled after rejects)",
    )
    la.set_defaults(func=cmd_loop_analyse)

    ls = sub.add_parser(
        "loop-shadow",
        help="Optimization cycle: shadow live-test productive vs hypothesis configs",
    )
    add_common(ls)
    ls.add_argument(
        "--hypothesis",
        action="append",
        default=None,
        help="Hypothesis ID (repeatable). Default: H20260722-03 H20260722-04",
    )
    ls.add_argument(
        "--days",
        type=int,
        default=7,
        help="Number of trading days in the shadow window (default: 7)",
    )
    ls.set_defaults(func=cmd_loop_shadow)

    lv = sub.add_parser(
        "loop-vergleich",
        help="Optimization cycle: compare shadow results and accept/reject",
    )
    lv.add_argument(
        "--hypothesis",
        action="append",
        default=None,
        help="Hypothesis ID (repeatable). Default: H20260722-03 H20260722-04",
    )
    lv.set_defaults(func=cmd_loop_vergleich)

    tm = sub.add_parser(
        "track-m-calibrate",
        help="Track M: calibrate IC apparatus on multi-year OHLCV momentum",
    )
    tm.add_argument("--horizon-days", type=int, default=21, help="Forward return horizon")
    tm.add_argument(
        "--offline",
        action="store_true",
        help="Use only cached/cassette OHLCV (no network fetch)",
    )
    tm.set_defaults(func=cmd_track_m_calibrate)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Prefer serve-specific uvicorn level only for uvicorn; standing logger uses --log-level / env.
    standing_level = getattr(args, "log_level", None)
    if args.cmd == "serve":
        args.log_level = getattr(args, "serve_log_level", "info")
        if standing_level is None:
            standing_level = args.log_level
    configure_logging(standing_level)
    log.info("Command start cmd=%s", args.cmd)
    try:
        code = args.func(args)
    except Exception:
        log.exception("Command failed cmd=%s", args.cmd)
        raise
    log.info("Command finished cmd=%s exit=%s", args.cmd, code)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
