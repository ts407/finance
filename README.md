# Standing

**Standing** is a research demo that ranks liquid US equities (and ADRs) by a descriptive **Value / Quality / Momentum** composite, then applies a small, bounded **Social Attention Tilt**.

It is **not** investment advice, a tip sheet, or a buy-rank product. Scores are labeled `editorial_descriptive`.

| Field | Meaning |
|-------|---------|
| **Composite Standing** | Equal-weight sector-relative V / Q / M (0–100) |
| **Attention Tilt** | Bounded social adjustment after shrinkage (±`tilt_max`) |
| **Final Standing** | `clip(Base + Tilt, 0, 100)` — the only final score |

Desk defaults: **market=live** (Finnhub if `FINNHUB_API_KEY` in `.env`, else SEC EDGAR + Yahoo OHLCV) · **attention=open** (Wikipedia + Bluesky). Fixtures remain for CI/offline.

---

## Requirements

- Python **3.11+**
- macOS / Linux / WSL (Windows untested)

---

## Install

```bash
git clone https://github.com/ts407/finance.git
cd finance
python -m pip install -e ".[dev,web]"
cp .env.example .env   # optional: FINNHUB_API_KEY (gitignored)
```

---

## Quick start

```bash
pytest

# Fixture (CI / offline)
standing table --as-of 2026-07-22 --market fixture --social fixture

# Live desk
standing table --as-of 2026-07-22 --market live --social open
standing ingest --market live --social open   # immutable day log (forward eval)
standing metrics-report --market live       # missing/non-positive metric check
standing serve --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000/**

---

## Web desk URL map

| URL | Purpose |
|-----|---------|
| http://127.0.0.1:8000/ | Standing desk (Final Standing + Attention Heat + evidence drawer) |
| http://127.0.0.1:8000/methodology | Methodology page (live params from config) |
| `/api/health` | Health + score_kind |
| `/api/methodology` | Formulas + live scoring.yaml params |
| `/api/snapshot` | JSON standings (`preset`, `sector`, `q`, `sort`, `as_of`) |
| `/api/snapshot.csv` | CSV export with the same filters |
| `/api/ticker/{ticker}` | Single-name evidence payload |
| `/api/client-logs` | Batched UI log ingest (`POST`) |

Desk controls: presets (balanced / value_led / quality_led / momentum_led / attention_confirmed), sector filter, search (`/` focuses), CSV export.

---

## Logging

- Backend uses the stdlib `standing.*` logger hierarchy (`standing.web`, `standing.pipeline.snapshot`, `standing.cli`, …).
- Level via `STANDING_LOG_LEVEL` or `standing --log-level debug <cmd>`.
- Web desk ships request middleware plus `POST /api/client-logs` for batched UI events from `/static/logger.js`.
- `standing serve --log-level info` controls uvicorn; use `--log-level` / env for Standing’s own logger.

---

## How scoring works (short)

1. **Admit** names by market-cap, ADV, and listing scope (`US` / `ADR`).
2. **Base** = sector-relative percentiles of Value, Quality, Momentum (equal weight).
3. **Social** = capped source shares → shrinkage → `tanh` tilt (volume-only until calibrated sentiment).
4. **Final** = clip(Base + Tilt, 0, 100). No second renorm/floor path.

Full formulas: **[docs/concept-code-mechanisms.md](docs/concept-code-mechanisms.md)** · methodology source: **[docs/aktienradar-konzept-v2.md](docs/aktienradar-konzept-v2.md)** · data paths: **[docs/datenbeschaffung.md](docs/datenbeschaffung.md)**

---

## Configuration

| File | Role |
|------|------|
| [`config/scoring.yaml`](config/scoring.yaml) | Methodology: pillar weights, tilt, shrinkage, `placeholder` |
| [`config/rules.json`](config/rules.json) | Universe admission: caps, ADV, scope, `universe_id` |

Current locks: `score_kind: editorial_descriptive` · `methodology_version: "2.1.0"` · `placeholder: true` · `tilt_max: 5` (volume-only attention).

---

## Project layout

```
config/scoring.yaml          # methodology
config/rules.json            # universe admission
src/standing/domain/scoring  # pure functions, no I/O
src/standing/providers       # MarketProvider / SocialProvider (fixture ≡ live)
src/standing/universe        # admission + sector occupancy flags
src/standing/pipeline        # snapshot runner + immutable day store
src/standing/web             # FastAPI desk UI + JSON API
src/standing/optimization    # shadow / vergleich optimization loop
```

---

## Current limits

- Fixture universe is a compact multi-sector demo (~50 names). Target 400–500 with ≥30/sector; thin sectors flagged `sector_low_confidence`.
- Parameters are synthetic (`placeholder: true`) until an empirical freeze.
- Reddit/StockTwits remain fixture-only; Wikipedia + Bluesky are the open attention path.
- Not investment advice.

---

## Disclaimer

Standing produces **editorial, descriptive** research scores for demonstration and methodology exploration. Nothing in this repository is a recommendation to buy, sell, or hold any security.
