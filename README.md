# Standing

Descriptive **V / Q / M** equity standing screener with a bounded **Social Attention Tilt**.

This is an **editorial_descriptive** research demo — not investment advice, not a buy-rank product.

## Methodology (v2 locks)

- **Composite Standing** = equal-weight sector-relative Value / Quality / Momentum
- **Attention Tilt** = `tilt_max * tanh(β * (S_used − 50) / 50)` with shrinkage + hype dampener
- **Final Standing** = `clip(Base + Tilt, 0, 100)` — single score process (no renorm/floor)
- Social sources are **fixtures** in v1 (Reddit / StockTwits live gated)

See `docs/aktienradar-konzept-v2.md`, `docs/concept-modular-review.md`, and `docs/concept-plan.md`.

## Quick start

```bash
python -m pip install -e ".[dev]"
standing table --as-of 2026-07-22
standing heat --as-of 2026-07-22
standing score --as-of 2026-07-22 --out artifacts/snapshots
standing report --as-of 2026-07-22 --out artifacts/reports/standing.html
pytest
```

## Layout

```
config/scoring.yaml          # methodology_version 2.0.0, placeholder: true
config/rules.json            # universe admission + universe_id
src/standing/domain/scoring  # pure functions, no I/O
src/standing/providers       # MarketProvider / SocialProvider (fixture ≡ live API)
src/standing/universe        # admission + sector occupancy flags
src/standing/pipeline        # snapshot runner + persistence
```

## Notes

- Fixture universe is a compact multi-sector demo (~50 names). Full 400–500 with ≥30/sector is a data job; sectors are flagged `sector_low_confidence` until occupancy is met.
- Parameters are synthetic (`placeholder: true`) until an empirical freeze.
