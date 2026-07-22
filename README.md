# Standing

Descriptive **V / Q / M** equity standing screener with a bounded **Social Attention Tilt**.

This is an **editorial_descriptive** research demo — not investment advice, not a buy-rank product.

## Methodology (v2 locks)

- **Composite Standing** = equal-weight sector-relative Value / Quality / Momentum
- **Attention Tilt** = `tilt_max * tanh(β * (S_used − 50) / 50)` with shrinkage + hype dampener
- **Final Standing** = `clip(Base + Tilt, 0, 100)` — single score process (no renorm/floor)
- Social sources are **fixtures** in v1 (Reddit / StockTwits live gated)

See:

- `docs/concept-code-mechanisms.md` — **rules & mechanisms implemented in code** (general + detailed)
- `docs/aktienradar-konzept-v2.md` — methodology source of truth
- `docs/concept-modular-review.md` / `docs/concept-plan.md` — product concept

## Quick start

```bash
python -m pip install -e ".[dev]"
pytest
standing table --as-of 2026-07-22
standing heat --as-of 2026-07-22
standing score --as-of 2026-07-22 --out artifacts/snapshots
standing report --as-of 2026-07-22 --out artifacts/reports/standing.html
standing serve --host 127.0.0.1 --port 8000
# Adapter validation only (does not feed scored Final / desk):
standing market-preview --provider finnhub \
  --cassette-dir tests/cassettes/finnhub --tickers AAPL,MSFT \
  --as-of 2026-07-22 --out artifacts/preview/market.csv
```

Scored surfaces (`table` / `heat` / `score` / `report` / web desk) stay on **fixture** market + social. Live Finnhub mapping + Stooq OHLCV + universe seed loaders are behind `standing market-preview` / `STANDING_MARKET_PROVIDER=finnhub` for adapter validation. Field checklist: `docs/field-mapping-finnhub.md`.

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
src/standing/providers/finnhub  # free metric+profile2 adapter (cassettes / live key)
src/standing/providers/stooq    # free OHLCV for returns + true ADV_20d
src/standing/universe        # admission + seed loaders + GICS map
config/universe              # SP500 / NDX100 / liquid ADR seed CSVs
src/standing/pipeline        # snapshot runner + persistence
src/standing/web             # FastAPI desk UI + JSON API
```

## Notes

- Fixture universe is a compact multi-sector demo (~50 names). Seed lists under `config/universe/` target the full 400–500 path; sectors are flagged `sector_low_confidence` until occupancy is met.
- Parameters are synthetic (`placeholder: true`) until an empirical freeze.
- Finnhub free tier: `/stock/metric` + `/stock/profile2` yes; `/stock/candle` premium (403) — use Stooq for exact returns/ADV.
- Live market is **not** wired into Final Standing while social remains fixture-gated.

## Live adapter env

| Variable | Purpose |
|----------|---------|
| `FINNHUB_API_KEY` | Enables live Finnhub transport |
| `STANDING_MARKET_PROVIDER` | `fixture` (default) or `finnhub` |
| `STANDING_FINNHUB_CASSETTES` | Golden JSON dir for offline mapping |
| `STANDING_STOOQ_CASSETTES` | Stooq CSV cassette dir |
| `STANDING_ALLOW_NETWORK` | `0` forces cassette-only |
