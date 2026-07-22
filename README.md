# Standing

**Standing** is a research demo that ranks liquid US equities (and ADRs) by a descriptive **Value / Quality / Momentum** composite, then applies a small, bounded **Social Attention Tilt**.

It is **not** investment advice, a tip sheet, or a buy-rank product. Scores are labeled `editorial_descriptive`.

| Field | Meaning |
|-------|---------|
| **Composite Standing** | Equal-weight sector-relative V / Q / M (0–100) |
| **Attention Tilt** | Bounded social adjustment after shrinkage (±`tilt_max`) |
| **Final Standing** | `clip(Base + Tilt, 0, 100)` — the only final score |

v1 ships **fixture-first**: market and social data are synthetic so the pipeline is reproducible without gated live APIs (Reddit / StockTwits).

---

## Requirements

- Python **3.11+**
- macOS / Linux / WSL (Windows untested)

---

## Install

```bash
git clone https://github.com/ts407/finance.git
cd finance
python -m pip install -e ".[dev]"
```

This installs the `standing` CLI and pulls `numpy`, `pandas`, `pyyaml`, and `rich`.

---

## Quick start

```bash
# Ranked Final Standing table
standing table --as-of 2026-07-22

# Attention / heat board (loud ≠ good)
standing heat --as-of 2026-07-22

# Persist CSV + meta snapshot
standing score --as-of 2026-07-22 --out artifacts/snapshots

# HTML report (also writes a sibling snapshots/ folder)
standing report --as-of 2026-07-22 --out artifacts/reports/standing.html

# Tests
pytest
```

Common flags:

| Flag | Default | Purpose |
|------|---------|---------|
| `--as-of` | today | Snapshot date `YYYY-MM-DD` |
| `--history-days` | `14` | Social fixture lookback fed into the 7-day window |
| `--top` | `20` | Rows for `table` / `heat` |
| `--config` | `config/scoring.yaml` | Scoring methodology file |
| `--out` | command-specific | Output path for `score` / `report` |

---

## How scoring works (short)

```
Market fixtures ─┐
                 ├─→ admit universe ─→ V/Q/M base ─┐
Social fixtures ─┘         │                       ├─→ Final Standing
                           └─→ social features     │
                                 → shrinkage       │
                                 → tanh tilt       ┘
                                 (+ hype dampener)
```

1. **Admit** names by market-cap, ADV, and listing scope (`US` / `ADR`).
2. **Base** = sector-relative percentiles of Value, Quality, Momentum (equal weight).
3. **Social** = capped source shares → `log1p` → universe share → 7-day aggregate → `S_obs`.
4. **Shrink** sparse attention toward a neutral prior: `S_used = c·S_obs + (1−c)·50`.
5. **Tilt** with `tanh` (soft-capped), dampen positive tilt when mentions are negatively skewed.
6. **Final** = clip(Base + Tilt, 0, 100). No second renorm/floor path.

Full formulas, invariants, and file map: **[docs/concept-code-mechanisms.md](docs/concept-code-mechanisms.md)**.

---

## Outputs

### CLI tables

- `standing table` — Final Standing with V / Q / M, tilt, confidence, social badge  
- `standing heat` — Attention board sorted by `s_used` (attention context, not a recommendation)

### Snapshot artifacts (`standing score`)

```
artifacts/snapshots/
  standings_YYYY-MM-DD.csv
  standings_YYYY-MM-DD.meta.json
```

Every snapshot stamps `as_of`, `universe_id`, `methodology_version`, `score_kind`, and `placeholder`.

### HTML report (`standing report`)

Writes a self-contained report plus a snapshot copy under the report parent’s `snapshots/` directory.

---

## Configuration

| File | Role |
|------|------|
| [`config/scoring.yaml`](config/scoring.yaml) | Methodology: pillar weights, tilt, shrinkage, social pipeline, `placeholder` |
| [`config/rules.json`](config/rules.json) | Universe admission: caps, ADV, scope, `universe_id` |

Important locks for v1:

- `score_kind: editorial_descriptive`
- `methodology_version: "2.0.0"`
- `placeholder: true` — parameters are synthetic until an empirical freeze
- Social is a **tilt**, not a fourth weighted pillar
- Reddit comments and live social ingest are **out of scope** for v1

---

## Project layout

```
config/
  scoring.yaml                 # scoring methodology
  rules.json                   # universe admission
docs/
  concept-code-mechanisms.md   # rules & mechanisms (code-facing)
  aktienradar-konzept-v2.md    # methodology source of truth
  concept-plan.md              # product plan
  concept-modular-review.md    # modular review
src/standing/
  cli.py                       # standing table|heat|score|report
  config.py                    # loaders
  domain/scoring/              # pure math (no I/O)
  providers/                   # MarketProvider / SocialProvider (fixtures)
  universe/                    # admission + sector occupancy
  pipeline/                    # snapshot + HTML report
tests/
  test_scoring_required.py     # shrinkage / tilt / config locks
  test_pipeline.py             # end-to-end fixture snapshot
```

Providers share the same interfaces for fixture and future live data — scoring never depends on a concrete provider.

---

## Current limits (v1)

- **Fixture universe** is a compact multi-sector demo (~50 names). The design target is ~400–500 with ≥30 names per GICS-11 sector; thin sectors are flagged `sector_low_confidence`.
- **Social & market live paths** are not wired. Reddit is approval-gated; StockTwits is closed to new developers. Fixtures are the publishable v1 path.
- **Parameters** (`k`, `β`, dampener, admission thresholds, …) are marked `placeholder: true` and must not be treated as empirically frozen.
- **No** portfolio construction, execution, options, news-in-pulse, or “Buy” product labels.

---

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/concept-code-mechanisms.md](docs/concept-code-mechanisms.md) | General + detailed explanation of every rule the code enforces |
| [docs/aktienradar-konzept-v2.md](docs/aktienradar-konzept-v2.md) | Methodology source of truth (Konzept v2) |
| [docs/concept-plan.md](docs/concept-plan.md) | Product scope and delivery posture |
| [docs/concept-modular-review.md](docs/concept-modular-review.md) | Modular review of design locks |

---

## Disclaimer

Standing produces **editorial, descriptive** research scores for demonstration and methodology exploration. Nothing in this repository is a recommendation to buy, sell, or hold any security.
