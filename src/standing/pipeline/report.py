from __future__ import annotations

from html import escape
from pathlib import Path

import pandas as pd

from standing.pipeline.snapshot import StandingSnapshot


def render_html_report(snapshot: StandingSnapshot, out_path: Path) -> Path:
    """Self-contained Standing + Heat report. Factual language only."""
    df = snapshot.standings.copy()
    heat = df.sort_values("s_used", ascending=False)

    def table(frame: pd.DataFrame, cols: list[str]) -> str:
        head = "".join(f"<th>{escape(c)}</th>" for c in cols)
        body_rows = []
        for _, row in frame.iterrows():
            cells = []
            for c in cols:
                val = row[c]
                if isinstance(val, float):
                    cells.append(f"<td>{val:.2f}</td>")
                else:
                    cells.append(f"<td>{escape(str(val))}</td>")
            body_rows.append("<tr>" + "".join(cells) + "</tr>")
        return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"

    standing_cols = [
        "ticker",
        "sector",
        "value",
        "quality",
        "momentum",
        "composite_standing",
        "attention_tilt",
        "final_standing",
        "social_badge",
    ]
    heat_cols = [
        "ticker",
        "s_obs",
        "s_used",
        "n",
        "confidence_c",
        "neg_share",
        "attention_tilt",
        "final_standing",
        "social_badge",
    ]

    low = ", ".join(snapshot.meta.get("low_confidence_sectors") or []) or "none"
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Standing report — {escape(snapshot.as_of.isoformat())}</title>
  <style>
    :root {{
      --bg: #f3efe6;
      --ink: #1c2418;
      --muted: #5c6756;
      --line: #cfc6b4;
      --accent: #2f5d50;
      --card: #fffaf1;
    }}
    body {{
      margin: 0;
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at 10% 0%, #e7f0ea 0%, transparent 40%),
        linear-gradient(180deg, #f7f2e8, #ebe4d6);
      color: var(--ink);
      padding: 2rem;
    }}
    h1, h2 {{ font-family: "Iowan Old Style", "Palatino Linotype", serif; font-weight: 600; }}
    h1 {{ font-size: 2.2rem; margin: 0 0 0.25rem; color: var(--accent); }}
    .sub {{ color: var(--muted); margin-bottom: 1.5rem; }}
    .banner {{
      background: var(--card);
      border: 1px solid var(--line);
      padding: 1rem 1.25rem;
      margin-bottom: 1.5rem;
    }}
    section {{ margin-bottom: 2.5rem; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      background: var(--card);
      font-size: 0.92rem;
    }}
    th, td {{
      border-bottom: 1px solid var(--line);
      padding: 0.45rem 0.55rem;
      text-align: left;
    }}
    th {{ color: var(--muted); font-weight: 600; }}
    .note {{ color: var(--muted); font-size: 0.9rem; }}
  </style>
</head>
<body>
  <h1>Standing</h1>
  <p class="sub">editorial_descriptive · methodology {escape(snapshot.methodology_version)} ·
     universe {escape(snapshot.universe_id)} · as_of {escape(snapshot.as_of.isoformat())}</p>
  <div class="banner">
    <strong>Not investment advice.</strong>
    Composite Standing describes peer-relative Value / Quality / Momentum.
    Attention Tilt is a bounded secondary adjustment. Loud ≠ good.
    placeholder={str(snapshot.placeholder).lower()} · n={snapshot.meta.get("n_names")} ·
    low-confidence sectors: {escape(low)}
  </div>

  <section>
    <h2>Final Standing</h2>
    <p class="note">Sorted by Final Standing = clip(Composite Standing + Attention Tilt, 0, 100).</p>
    {table(df, standing_cols)}
  </section>

  <section>
    <h2>Attention Heat Board</h2>
    <p class="note">Primary heat surface, separated from the composite. Sorted by shrunk social score S_used.</p>
    {table(heat, heat_cols)}
  </section>
</body>
</html>
"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return out_path
