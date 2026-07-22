# Equity Attention Screener — Concept Plan

**Status:** Concept plan (revised)  
**Companion:** [concept-modular-review.md](./concept-modular-review.md)  
**Methodology:** Descriptive V / Q / M + Social tilt

---

## 1. Product intent

Build an **equity attention screener** that helps a researcher answer:

> “Which liquid equities deserve desk time today, given valuation, quality, momentum, and unusual attention?”

Success looks like a **repeatable discovery → evidence → watchlist** loop, not a tip sheet.

---

## 2. Problem

| Pain | Why it matters |
|------|----------------|
| Pure movers lists lack fundamental context | Time wasted on noisy names |
| Pure fundamental screens miss attention shifts | Misses timely research catalysts |
| Black-box composites hide trade-offs | Users cannot trust or learn from ranks |
| Social tools over-weight hype | Attention without hygiene creates false urgency |

---

## 3. Solution sketch

A screening surface that:

1. Applies liquidity / listing hygiene
2. Scores **Value, Quality, Momentum** as independent descriptive modules
3. Computes a **Social Attention** score used only as a **tilt**
4. Ranks a research queue with visible component mix
5. Opens an evidence panel (freshness, contributors, tags) before follow-up actions

---

## 4. Scope

### In scope (v1 concept)

- U.S. listed equities (expandable later)
- V / Q / M descriptive percentiles + labels
- Social attention velocity (+ optional polarity) as tilt
- Filters: sector, market cap, liquidity, exchange, completeness
- Presets: value-led, quality-led, momentum-led, attention-confirmed, balanced
- Row evidence drawer + export / watchlist hooks

### Out of scope (v1)

- Portfolio optimization / risk model
- Auto-trading / broker execution
- Options / crypto / private markets
- Full NLP narrative generation
- Guaranteed multi-vendor social coverage for all tickers

---

## 5. User journeys

### Journey A — Morning research queue

1. Open default **Balanced** preset (V/Q/M blend, Social ≤ 10% tilt)
2. Filter to liquid large/mid caps
3. Sort by Signal Score; scan tags
4. Open 5–10 evidence drawers
5. Add survivors to watchlist; export CSV

### Journey B — Attention confirmation

1. Select **Attention-confirmed** preset
2. Require Social velocity spike **and** at least one strong V/Q/M module
3. Exclude attention-only rows
4. Review polarity / breadth if available
5. Save screen + alert for new matches

### Journey C — Value trap audit

1. Filter Cheap (high V) + Weak Q
2. Disable Social tilt (or set tilt weight to 0)
3. Use list as “investigate carefully” set, not buy queue

---

## 6. Information architecture

```
Screener
├── Controls: universe, filters, preset, sort
├── Results table
│   ├── Identity: ticker, name, sector, mkt cap
│   ├── Market: price, volume, rvol
│   ├── Modules: V · Q · M percentiles
│   ├── Social: Attention score · tilt badge
│   └── Mix: Signal Score · tags · freshness
└── Evidence drawer
    ├── Module breakdowns
    ├── Social inputs & coverage
    ├── Data freshness / gaps
    └── Actions: watchlist · export · alert · open research
```

---

## 7. Scoring & ranking plan

Align implementation with the modular review:

| Layer | Behavior |
|-------|----------|
| Hygiene | Hard gates before ranking |
| V / Q / M | Independent peer-relative scores |
| Social | Attention score; tilt only |
| Signal Score | Optional explainable blend; Social soft-capped |
| Tags | Derived from which modules dominate |

### Preset definitions (initial)

| Preset | Intent |
|--------|--------|
| Balanced | Equal V/Q/M emphasis; Social tilt on |
| Value-led | Sort/filter emphasizing V; Q floor optional |
| Quality-led | Emphasize Q; avoid weak-balance-sheet names |
| Momentum-led | Emphasize M; liquidity required |
| Attention-confirmed | Social spike required; V/Q/M not all weak |
| Watchlist | Intersection with user list |

---

## 8. Data dependencies

| Domain | Need | Notes |
|--------|------|-------|
| Prices / volume | Daily OHLCV, ADV | Momentum + liquidity |
| Fundamentals | Multiples, profitability, leverage, FCF | Value + Quality |
| Peer map | Sector/industry membership | Relative ranks |
| Social | Mentions, velocity, optional polarity | Tilt only |
| Reference | Tickers, exchanges, corporate actions | Hygiene |

Fallback policy: if Social is missing → neutral tilt; if a V/Q/M module is incomplete → show gap and lower confidence.

---

## 9. Delivery phases

### Phase 0 — Concept freeze

- Lock descriptive V/Q/M definitions and Social tilt rules ([modular review](./concept-modular-review.md))
- Agree soft-cap for Social in blend sort
- Agree hygiene defaults

### Phase 1 — Scoring skeleton

- Universe + hygiene
- V / Q / M pipelines with peer percentiles
- Unit tests for edge cases (losses, missing FCF, financials)

### Phase 2 — Social tilt

- Attention velocity feature
- Tilt application + tags
- Coverage / freshness surfaces

### Phase 3 — Screener UX

- Table, presets, filters, evidence drawer
- Save screen / alert / export / watchlist hooks

### Phase 4 — Hardening

- Monitoring for data gaps
- Documentation of labels and non-advisory language
- Calibration pass on peer groups and Social windows

---

## 10. Acceptance criteria (concept → build)

- [ ] V, Q, and M each render independently with percentile + label
- [ ] Social never outranks a complete V/Q/M mix under default weights
- [ ] Attention-only names are tagged and deprioritized in Balanced preset
- [ ] Missing module data is visible (no silent fill)
- [ ] Evidence drawer shows contributors for the current Signal Score
- [ ] Copy frames outputs as research context, not recommendations

---

## 11. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Social noise / manipulation | Velocity + breadth + soft cap; attention-only tag |
| Peer-group distortion | Document peer map; sector overrides for banks |
| Overfitting blend weights | Keep modules primary; blend is convenience sort |
| Stale fundamentals | Freshness badges; as-of dates in drawer |
| Users treating score as advice | Explicit non-advisory framing in UI and docs |

---

## 12. Success metrics

- Time from open → first watchlist add
- % of opened drawers that lead to watchlist/export
- Share of ranked rows with complete V/Q/M coverage
- Rate of attention-only rows surfaced under Balanced (should stay low)
- Qualitative: researchers can explain *why* a row ranked without reading code

---

## 13. Decision log (revised methodology)

| Decision | Choice |
|----------|--------|
| Output type | Descriptive modules, not a recommendation engine |
| Core factors | Value, Quality, Momentum |
| Social role | Tilt / confirmation only (capped influence) |
| Primary UX | Modular mix visible before any blend sort |
| Product shape | Attention-aware research screener |

---

## 14. Next actions

1. Review and ratify [concept-modular-review.md](./concept-modular-review.md)
2. Choose initial data vendors for fundamentals and social attention
3. Specify peer-group taxonomy and Social velocity windows
4. Prototype Phase 1 scoring on a liquid subset
5. Design evidence-drawer wireframe aligned to module breakdowns
