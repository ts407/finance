# Equity Attention Screener — Concept Plan

**Status:** Concept plan v2 (revised)  
**Companion review:** [concept-modular-review.md](./concept-modular-review.md)  
**Source of truth:** [aktienradar-konzept-v2.md](./aktienradar-konzept-v2.md)  
**Code mechanisms:** [concept-code-mechanisms.md](./concept-code-mechanisms.md)  
**Methodology:** Descriptive–explanatory V/Q/M base + bounded Social tilt

---

## 1. Product intent

Ship a **non-commercial research demo** that ranks liquid US equities (+ ADRs) by:

1. **Composite Standing** — equal-weight descriptive V/Q/M  
2. **Attention Tilt** — bounded social adjustment after shrinkage  
3. **Final Standing** — clipped sum, with heat/attention as a **primary** UI surface clearly separated from the composite

Not a tip sheet. Not a buy-rank product.

---

## 2. Scope

### In scope (v1)

- Universe: US-listed + liquid ADRs (~400–500 names; **≥30 per GICS-11 sector**)
- Market path: fixtures (required) + optional **Finnhub** live EOD/fundamentals
- Social path: **fixtures only** (Reddit + StockTwits simulated); live marked “later”
- Scoring: Base, shrinkage, tanh tilt, hype dampener — single generation process
- Surfaces: standing table, heat/attention board, methodology page, evidence/breakdown
- Snapshot persistence: `as_of`, `universe_id`, `methodology_version`
- Research IC: **notebook only**, look-ahead-free, evaluable only after weeks of ingest

### Out of scope (v1)

- UK/CA/AU listings  
- Reddit comments as inputs  
- News inside Pulse  
- Commercial social firehose (Firestream / paid Reddit)  
- Portfolio construction, execution, options  
- Any “Buy” / “Buyworthiness” product label  
- Freezing tilt/shrinkage parameters on synthetic data

---

## 3. Delivery posture (API reality → product shape)

| Constraint (July 2026) | Plan response |
|------------------------|---------------|
| Reddit approval-gated, no backfill | Fixture social; optional forward OAuth ingest only after approval |
| StockTwits closed to new developers | Fixture social; Firestream = post-v1 partnership track |
| No social history for sale | Bootstrap ≥7 days before claiming stable social scores |
| Polygon/Massive paid-only | Prefer Finnhub free live for market; Massive only if tick/realtime required |
| yfinance brittle / ToS-grey | Dev stopgap at most — not production |

**Confirm with stakeholders:** v1 is explicitly a **non-commercial research demo** (fixtures + optional Finnhub market live, social simulated). Live Reddit/StockTwits stays labeled “later, after approval/Firestream.”

---

## 4. Data matrix

### Social

| Source | Live status (Jul 2026) | v1 role |
|--------|------------------------|---------|
| Reddit | Approval-gated; no backfill/date-range; commercial five-figures | **Fixture**; live only as forward OAuth after approval |
| StockTwits | New registrations closed; Firestream partnership | **Fixture**; live “after ToS/Firestream” |
| Third-party wrappers | ToS-unsafe | **Not** for published product |

### Market

| Source | Status | Role |
|--------|--------|------|
| Fixtures + seed CSV | Reproducible | **Required** for CI/dev |
| **Finnhub** | Free 60 calls/min; fundamentals + news-sentiment | **Free live path** (replaces yfinance recommendation) |
| Twelve Data | Free 800 calls/day | Global coverage v1.1 |
| EODHD | ~€20/mo, bulk | Universe-wide fundamentals / backtest |
| Polygon → Massive | No free tier, ~$99+/mo | Only if tick/realtime needed — oversized for EOD screener |
| yfinance | Unofficial | Dev stopgap only |

Provider interfaces stay identical for fixture and live:

```
MarketProvider.fetch(...)
SocialProvider.fetch_since(cursor)
```

---

## 5. Concrete config (`config/scoring.yaml`)

```yaml
methodology_version: "2.0.0"
score_kind: "editorial_descriptive"

base:
  pillar_weights: { value: 0.3333, quality: 0.3333, momentum: 0.3334 }
  peer_frame: "sector"          # GICS-11
  winsorize: { lower: 0.01, upper: 0.99 }
  quality_margin: "operating"   # not "net"
  momentum_secondary_global: true

social_tilt:
  tilt_max: 10
  beta: 1.5                     # placeholder
  shape: "tanh"
  symmetric: true               # asymmetric = v1.1
  dampener_neg_share_pivot: 0.5 # placeholder

shrinkage:
  k: 10                         # placeholder
  prior: 50                     # sector-neutral = v1.1
  display_badges: { sparse_below: 5, ok_at: 15 }

social_pipeline:
  sources: [reddit, stocktwits]
  include_wsb: true
  source_cap_per_ticker_day: 0.50
  mention_transform: "log1p_then_universe_share"
  reddit_comments: false        # v1.1
  sentiment_engagement_weight: "1+log1p(upvotes)"

universe:
  scope: ["US", "ADR"]
  min_market_cap_usd: 1.0e9     # placeholder
  min_adv_usd_20d: 5.0e6        # placeholder
  min_names_per_sector: 30
  target_size: [400, 500]

placeholder: true               # entire set calibrated on synthetic data
```

Universe admission thresholds also live in versioned `rules_json`. Seed: `S&P 500 ∪ Nasdaq-100 ∪ liquid ADR list`, deduped, ADV-trimmed.

---

## 6. Architecture plan

```
providers/          MarketProvider + SocialProvider (fixture ≡ live API)
domain/scoring/     Pure functions: V/Q/M, shrinkage, tilt, dampener, final
workers/            Async sentiment (VADER now; FinBERT optional)
snapshots/          Persist as_of + universe_id + methodology_version from day 1
fixtures/           NB-mentions + AR(1)-sentiment; config placeholder: true
ui/                 Standing table + Heat board + methodology / non-advice copy
notebooks/          Research IC only — never product claims
```

### Non-negotiables

1. Fixture/live interface identical (no rewrite at switch).  
2. Forward-ingest bootstrap; scores trustworthy after ≥7 days.  
3. Scoring has **no I/O** — unit-testable pure functions.  
4. Required tests: `test_shrinkage_continuity`, `test_no_two_score_processes`, fixture configs assert `placeholder: true`.  
5. Before parameter freeze: publish `(V,Q,M,S)` correlation matrix and tilt’s variance share of Final Standing (methodology appendix).

---

## 7. Phased delivery

### Phase 0 — Concept freeze

- Ratify modular review + this plan  
- Confirm non-commercial research-demo posture  
- Name shortlist + trademark search  
- Legal review gate before any EU public distribution (MAR)

### Phase 1 — Scoring skeleton

- Universe builder + `rules_json` versioning  
- Winsorize + GICS-11 sector percentiles for V/Q/M  
- Composite Standing + secondary global momentum field  
- Unit tests for financials edge cases (losses, missing EV/EBITDA, banks)

### Phase 2 — Social fixtures + tilt

- Fixture Reddit/StockTwits pipeline (WSB included with cap + lexicon)  
- Shrinkage (`k=10`, prior 50), tanh tilt, hype dampener  
- Display `c`, `n`, sparse/ok badges  
- Continuity / single-process tests

### Phase 3 — Surfaces

- Standing table (Base / Tilt / Final + module breakdown)  
- Heat / attention board (primary, “loud ≠ good”)  
- Methodology page (`score_kind`, literature, non-advice)  
- Snapshot browser with version stamps

### Phase 4 — Optional live market + bootstrap social

- Finnhub market provider behind same interface  
- If Reddit OAuth approved (non-commercial): forward ingest only  
- StockTwits live remains blocked pending Firestream/ToS  
- Run research-IC notebook after ≥7 days continuous social data

### Phase 5 — Empirical calibration (pre-freeze)

- Real cross-section: retune `k`, `β`, dampener pivot  
- Set `placeholder: false` only after methodology appendix published  
- Consider v1.1: sector-neutral prior, asymmetric tilt, comments, ASVI

---

## 8. UX & framing requirements

1. Neutral factual language — **no Buy labels** on UI.  
2. Prominent methodology + non-advice disclosure.  
3. Show module breakdowns, tilt magnitude, shrinkage confidence (`c`, `n`).  
4. Heat separated from Composite Standing.  
5. Cap headroom visible in Pulse when a source hits 0.50.  
6. Low-confidence flag when a sector has &lt;30 names.

Naming: avoid “Radar.” Prefer Standing / Mentions Desk / Retail Attention Board after brand search.

---

## 9. Legal & ToS gates (not legal advice)

Checked framing vs **Art. 20 MAR + DelVO (EU) 2016/958** (July 2026 understanding):

- Scope covers creators/disseminators, not only professionals.  
- Purely factual information is outside; material that **explicitly or implicitly** recommends an investment strategy is inside → **Buy semantics are the concrete trigger**.  
- Very small issuer sets framed as “top buys” raise risk.  
- If in scope: objective presentation + conflict disclosures (firms: quarterly buy/hold/sell ratios). A disclaimer alone is not decisive.

**Product obligations**

1. Factual language (module review §1).  
2. Methodology + non-advice disclosure.  
3. Case-by-case legal review before public EU distribution from DE.  
4. Reddit Terms (attribution, no sublicensing, user-deletion) and StockTwits Firestream ToS reviewed **separately** — blockers, not details.

---

## 10. Acceptance criteria

- [ ] `score_kind = "editorial_descriptive"` on API and methodology page  
- [ ] No Buyworthiness/Buy-Rank on product surface  
- [ ] V/Q/M each sector-relative; Base = equal average; global M secondary only  
- [ ] Operating margin used for Quality  
- [ ] Tilt uses tanh with `tilt_max=10`; Social never a 40% pillar  
- [ ] Shrinkage is the only sparse-data mechanism (no renorm/floor second process)  
- [ ] Fixtures drive CI; `placeholder: true` asserted  
- [ ] Snapshots carry `as_of`, `universe_id`, `methodology_version`  
- [ ] Heat is a primary surface, copy states loud ≠ good  
- [ ] Required scoring tests green  

---

## 11. Open items needing explicit approval

1. Confirm v1 = **non-commercial research demo** (fixtures + optional Finnhub market; social simulated).  
2. Product name + trademark search.  
3. Target size 400 vs 500 — driven by **≥30 names/sector**, not vanity headcount.  
4. Legal MAR review **before** any public EU distribution.  
5. Whether to pursue Reddit OAuth (non-commercial) and/or StockTwits Firestream for post-v1 live social.

---

## 12. Success metrics

- Researchers can explain Final Standing from Base + Tilt without reading code  
- Share of ranked rows with complete V/Q/M and sector occupancy ≥30  
- Attention-only / maxed-tilt rows stay rare under default params  
- Time-to-first meaningful heat read after bootstrap ≥7 days  
- Zero accidental Buy-semantics regressions in UI copy checks  
- Parameter freeze only after published `(V,Q,M,S)` correlation appendix  

---

## 13. Next actions

1. Stakeholder confirmations on §11.  
2. Check in `config/scoring.yaml` + `rules_json` stubs with `placeholder: true`.  
3. Implement `domain/scoring/` pure functions + required tests.  
4. Build fixture social/market providers behind the shared interfaces.  
5. Wire Standing + Heat UI with methodology/non-advice framing.  
6. Optional: Finnhub market live behind `MarketProvider`.  
7. Schedule legal + ToS reviews before any public distribution.
