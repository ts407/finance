from __future__ import annotations

import argparse
from datetime import date, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from standing.config import load_scoring_config
from standing.pipeline.report import render_html_report
from standing.pipeline.snapshot import persist_snapshot, run_snapshot
from standing.providers import FixtureMarketProvider, FixtureSocialProvider

console = Console()


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def cmd_score(args: argparse.Namespace) -> int:
    cfg = load_scoring_config(Path(args.config) if args.config else None)
    if not cfg.placeholder:
        console.print("[yellow]Warning:[/yellow] placeholder is false — verify empirical freeze.")
    as_of = _parse_date(args.as_of)
    snap = run_snapshot(
        as_of=as_of,
        market=FixtureMarketProvider(),
        social=FixtureSocialProvider(history_days=args.history_days),
        cfg=cfg,
    )
    out = Path(args.out)
    path = persist_snapshot(snap, out)
    console.print(
        f"[bold]Final Standing snapshot[/bold]  as_of={snap.as_of}  "
        f"universe={snap.universe_id}  n={len(snap.standings)}  "
        f"score_kind={snap.score_kind}"
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
    snap = run_snapshot(
        as_of=as_of,
        market=FixtureMarketProvider(),
        social=FixtureSocialProvider(history_days=args.history_days),
        cfg=cfg,
    )
    top = snap.standings.head(args.top)

    table = Table(
        title=(
            f"Final Standing (editorial_descriptive) — {snap.as_of} "
            f"[placeholder={snap.placeholder}]"
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
    snap = run_snapshot(
        as_of=as_of,
        market=FixtureMarketProvider(),
        social=FixtureSocialProvider(history_days=args.history_days),
        cfg=cfg,
    )
    heat = snap.standings.sort_values("s_used", ascending=False).head(args.top)

    table = Table(title=f"Attention Heat Board — {snap.as_of}  (loud ≠ good)")
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
    snap = run_snapshot(
        as_of=as_of,
        market=FixtureMarketProvider(),
        social=FixtureSocialProvider(history_days=args.history_days),
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


def cmd_loop_analyse(args: argparse.Namespace) -> int:
    """Baseline diagnostics + hypothesis artifacts for optimization cycle 1."""
    from standing.optimization.analyse import write_baseline_report
    from standing.optimization.hypotheses import write_hypothesis
    from standing.optimization.log import append_log, latest_entry
    from standing.optimization.paths import ensure_layout

    ensure_layout()
    as_of = _parse_date(args.as_of)
    prior = latest_entry()
    console.print(
        "[bold]loop-analyse-hypothese[/bold] — "
        f"as_of={as_of}  prior_log={'yes' if prior else 'empty (baseline cycle)'}"
    )
    report = write_baseline_report(as_of=as_of, history_days=args.history_days)
    cycle_id = report["cycle_id"]
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
        reverse=True,
    )
    console.print("Sensitivity (top by ranking turnover):")
    for row in sens[:4]:
        console.print(
            f"  {row['label']}: turnover={row['ranking_turnover_vs_baseline']:.1%}  "
            f"tilt_mae={row['tilt_vs_baseline_mae']:.3f}  "
            f"sparse={row['sparse_share']:.1%}"
        )

    hyp_specs = [
        {
            "hypothesis_id": "H20260722-03",
            "basis": (
                f"Largest actionable deviation: Social tilt reorders rankings "
                f"(baseline spearman(final,composite)={baseline['spearman_final_vs_composite']:.4f}, "
                f"mean|tilt|={baseline['mean_abs_tilt']:.2f}). Sensitivity tilt_max=8 → "
                f"turnover={next(r['ranking_turnover_vs_baseline'] for r in sens if r['label']=='tilt_max=8'):.1%}, "
                f"spearman rises toward composite. Conservative tilt cap is the primary shadow candidate."
            ),
            "overrides": {"social_tilt.tilt_max": 8},
            "prediction": {
                "metric": "spearman_final_vs_composite",
                "expected_direction": "increase",
                "secondary_metric": "mean_abs_tilt",
                "expected_secondary": "decrease",
                "rationale": "tilt_max:10→8 scales tanh tilt down; offline delta already shows ~52% rank moves.",
            },
        },
        {
            "hypothesis_id": "H20260722-04",
            "basis": (
                f"Second-largest tilt-shape lever: beta=1.0 shows "
                f"turnover={next(r['ranking_turnover_vs_baseline'] for r in sens if r['label']=='beta=1.0'):.1%} "
                f"and higher final↔composite Spearman vs baseline. Chosen over shrinkage.k because "
                f"fixture mean_n={baseline['mean_n']:.0f} makes k:10→15 nearly inert "
                f"(offline turnover≈0%)."
            ),
            "overrides": {"social_tilt.beta": 1.0},
            "prediction": {
                "metric": "ranking_turnover_vs_baseline",
                "expected_direction": "material_but_less_than_tilt_max_6",
                "secondary_metric": "spearman_final_vs_composite",
                "expected_secondary": "increase",
                "rationale": "beta:1.5→1.0 flattens tanh response around S_used=50 without changing tilt_max.",
            },
        },
    ]

    # Deferred: H20260722-01 (k↑) — keep as documented deferral for live sparse regimes.
    deferred = {
        "hypothesis_id": "H20260722-01",
        "status": "deferred",
        "reason": (
            "Offline sensitivity on fixtures: shrinkage.k=15 → 0% ranking turnover "
            f"(mean_n={baseline['mean_n']:.0f}, mean_c={baseline['mean_confidence_c']:.3f}). "
            "Revisit when live Social has thin n / non-zero sparse_share."
        ),
        "overrides": {"shrinkage.k": 15},
    }

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
        console.print(f"Hypothesis {spec['hypothesis_id']} → {hyp_path}")

    from standing.optimization.hypotheses import write_deferred_hypothesis

    deferred_path = write_deferred_hypothesis(
        hypothesis_id=deferred["hypothesis_id"],
        reason=deferred["reason"],
        overrides=deferred["overrides"],
        cycle_id=cycle_id,
    )
    console.print(f"Deferred {deferred['hypothesis_id']} → {deferred_path}")

    append_log(
        {
            "phase": "loop-analyse-hypothese",
            "cycle_id": cycle_id,
            "decision": "hypotheses_formulated",
            "as_of": as_of.isoformat(),
            "baseline": {
                "n_names": baseline["n_names"],
                "spearman_final_vs_composite": baseline["spearman_final_vs_composite"],
                "sparse_share": baseline["sparse_share"],
                "mean_abs_tilt": baseline["mean_abs_tilt"],
                "mean_confidence_c": baseline["mean_confidence_c"],
                "mean_n": baseline["mean_n"],
            },
            "hypotheses": [w["id"] for w in written],
            "deferred_hypotheses": [deferred["hypothesis_id"]],
            "report_path": report["report_path"],
            "handoff": "loop-live-test-shadow",
            "productive_config_unchanged": True,
        }
    )
    console.print("Appended log entry; handoff → loop-live-test-shadow")
    console.print(f"Report: {report['report_path']}")
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

    la = sub.add_parser(
        "loop-analyse",
        help="Optimization cycle: baseline diagnostics + formulate hypotheses",
    )
    add_common(la)
    la.set_defaults(func=cmd_loop_analyse)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
