# Standing

Descriptive **V / Q / M** equity standing screener with a bounded **Social Attention Tilt**.

This is an **editorial_descriptive** research demo — not investment advice, not a buy-rank product.

## Methodology (v2 locks)

- **Composite Standing** = equal-weight sector-relative Value / Quality / Momentum
- **Attention Tilt** = `tilt_max * tanh(β * (S_used − 50) / 50)` with shrinkage + hype dampener
- **Final Standing** = `clip(Base + Tilt, 0, 100)` — single score process (no renorm/floor)
- Social sources: **fixtures** for Reddit / StockTwits in v1; **Bluesky backfill** and **Wikipedia pageviews** are the open attention paths ([datenbeschaffung.md](./docs/datenbeschaffung.md))

See:

- `docs/concept-code-mechanisms.md` — **rules & mechanisms implemented in code** (general + detailed)
- `docs/aktienradar-konzept-v2.md` — methodology source of truth
- `docs/datenbeschaffung.md` — data acquisition paths, alternatives, order
- `docs/concept-modular-review.md` / `docs/concept-plan.md` — product concept

## Quick start

```bash
python -m pip install -e ".[dev]"
pytest

# Fixture (CI / offline)
standing table --as-of 2026-07-22 --market fixture --social fixture

# Live desk — SEC EDGAR fundamentals + Yahoo OHLCV + Wikipedia/Bluesky attention
standing table --as-of 2026-07-22 --market live --social open
standing serve --host 127.0.0.1 --port 8000
# UI defaults: Market=Live · Attention=Wiki+Bluesky
# Optional: FINNHUB_API_KEY=... to prefer Finnhub fundamentals under market=live
```

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

Desk controls: presets (balanced / value_led / quality_led / momentum_led / attention_confirmed), sector filter, search (`/` focuses), CSV export.

## Layout

```
config/scoring.yaml          # methodology_version 2.0.0, placeholder: true
config/rules.json            # universe admission + universe_id
src/standing/domain/scoring  # pure functions, no I/O
src/standing/providers       # MarketProvider / SocialProvider (fixture ≡ live API)
src/standing/universe        # admission + sector occupancy flags
src/standing/pipeline        # snapshot runner + persistence
src/standing/web             # FastAPI desk UI + JSON API
```

## Notes

- Fixture universe is a compact multi-sector demo (~50 names). Full 400–500 with ≥30/sector is a data job; sectors are flagged `sector_low_confidence` until occupancy is met.
- Parameters are synthetic (`placeholder: true`) until an empirical freeze.
