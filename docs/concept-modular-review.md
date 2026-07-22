# Equity Attention Screener — Modular Concept Review

**Status:** Concept v2 (revised)  
**Source of truth:** [aktienradar-konzept-v2.md](./aktienradar-konzept-v2.md)  
**Code mechanisms:** [concept-code-mechanisms.md](./concept-code-mechanisms.md)  
**Methodology:** Descriptive–explanatory V/Q/M base + bounded Social tilt  
**Verification snapshot:** July 2026 (API / market-data landscape)

All parameters calibrated on synthetic data are marked `placeholder` and have no empirical basis until a real cross-section freeze.

---

## 1. Purpose & epistemology

The screener produces an **editorial, descriptive** standing for liquid equities — not a buy/sell recommendation.

| API / UI concept | Meaning |
|------------------|---------|
| `score_kind = "editorial_descriptive"` | Declared kind on API and methodology page |
| **Composite Standing** | Equal-weight V/Q/M base (0–100, percentile interpretation) |
| **Attention Tilt** | Bounded social adjustment (not a fourth pillar) |
| **Final Standing** | `clip(Base + Tilt, 0, 100)` |

**Strike “Buyworthiness” / “Buy-Rank” from the product surface.** That semantics is the concrete regulatory attack surface (see §9 in the source). Keep language factual: relative standing and attention data. Methodology may cite Barber/Odean (2008) and Da/Engelberg/Gao (2011).

Working name candidates (avoid “Radar”; measurement, not forecast): **Standing**, **Mentions Desk**, **Retail Attention Board**. Brand search before lock.

---

## 2. Reality check that shapes v1 (verified July 2026)

1. **Reddit is largely closed for product ingest.** Responsible Builder Policy is approval-gated; unauthenticated `.json` returns 403 since May 2026; no date-range search, no comment search, ~1k listing cap, **no historical backfill**. Commercial pricing starts effectively five-figures.
2. **StockTwits is not accepting new developers.** Live path is Enterprise Firestream partnership only. Third-party wrappers are ToS-unsafe for a published product.
3. **Market-data landscape shifted.** Polygon → **Massive.com**, no free tier (~$99+/mo). Pragmatic free live path: **Finnhub** (60 calls/min, fundamentals + news-sentiment endpoint) — not yfinance.

### Hard consequences

- **Fixtures are the only viable v1 social path** for a publishable demo.
- **No social history to backfill** → 7-day windows must accumulate via forward ingest; scores stabilize only after ≥7 days of continuous operation.
- **Parameters must not be frozen** until measured on a real cross-section (`placeholder: true` in config).

---

## 3. Base score — Value / Quality / Momentum

| Pillar | v1 definition | Peer frame |
|--------|---------------|------------|
| **Value** | Percentile of **P/E (TTM), P/B, EV/EBITDA** (cheaper = higher); median of the three sub-percentiles | **Sector-relative** |
| **Quality** | Percentile of **ROE, Operating Margin (EBIT/sales, TTM), revenue growth (YoY)** | **Sector-relative** |
| **Momentum** | Percentile of **1M / 3M / 6M total return + relative volume** | **Sector-relative (primary)** |

### Frame consistency (v1 correction)

V, Q, and M are **uniformly sector-relative**. Mixing global momentum with sector-relative V/Q made the composite uninterpretable.

- Show a **cross-sectoral momentum percentile as a secondary display field**.
- Do **not** feed that secondary field into the composite.

### Further locks

- **Margin = Operating Margin**, not Net Margin (Net is distorted by capital structure, tax, one-offs). Gross Margin optional secondary.
- **Peer group = GICS-11 sectors.** Finer industry is too thin in v1. Normalize provider sector strings via a static override table onto the 11 GICS sectors.
- **Winsorize before rank** at the 1st / 99th percentile per metric.
- **`Base = (V + Q + M) / 3`** (equal weights).

---

## 4. Social tilt — mathematics (not a 40% pillar)

Additive 40% social was double-counting (social correlates with momentum/volume). Tilt instead of pillar:

```
Tilt  = tilt_max · tanh( β · (S_used − 50) / 50 )
Final = clip( Base + Tilt , 0 , 100 )
```

| Parameter | v1 value | Notes |
|-----------|----------|--------|
| `tilt_max` | `10` | Soft cap on influence |
| `β` | `1.5` (`placeholder`) | Mid-range ~linear; extremes flatten |
| Shape | `tanh` | One extreme must not max out the tilt |
| Symmetry | Symmetric in v1 | “Attention ≠ good” is handled by the hype dampener |

**No renorm, no floor.** Sparse/edge cases are handled by shrinkage (§5) so there remains **one** score-generation process.

### Hype dampener (`placeholder`)

Dampens **positive** tilt when volume is negatively driven / polarized:

```
d = 1 − 2 · max(0, neg_share − 0.5)   # neg_share = share of negative mentions in window
Tilt_pos_effective = d · Tilt_pos     # applied only to positive tilt
```

Asymmetric tilt itself is a **v1.1 experiment**.

---

## 5. Shrinkage (concrete parameters)

```
S_used = c · S_obs + (1 − c) · prior ,   c = n / (n + k)
```

| Symbol | v1 | Role |
|--------|----|------|
| `n` | Mentions in 7-day window | Sample size |
| `k` | `10` (`placeholder`) | Target: median-coverage ticker `c ≈ 0.6–0.7` |
| `prior` | `50` (flat) | Sector-neutral prior = v1.1 |
| `c` | Derived | **Is** confidence (model quantity, not UI chrome) — display `c` and `n` |

Thresholds 5 / 15 are **display badges** only (`sparse` / `ok`), not scoring mechanics. Parametric shrinkage with fixed `k` is enough for descriptive use; empirical Bayes (`τ²` from the cross-section) is diagnostic only.

---

## 6. Social pipeline (concrete parameters)

| Topic | v1 lock |
|-------|---------|
| Sources | Reddit (incl. **r/wallstreetbets**, with cap + own lexicon + breakdown) + StockTwits — both **fixtures** until live paths open |
| Source cap | Per ticker/day, share per `source_id` ≤ **0.50**; overflow downsampled; show “cap headroom” in Pulse |
| Mention feature | `log1p(count)` → **share of that day’s universe total volume** → 7-day aggregate |
| Engagement | Volume feature = **raw count share**; sentiment aggregation = **engagement-weighted** `w = 1 + log1p(upvotes)`, capped |
| Reddit content | **Submissions only** (title + body); comments = v1.1 |
| Sentiment | VADER + finance slang lexicon; StockTwits bull/bear blend where present; separate WSB lexicon; FinBERT optional async worker |
| News in Pulse | **No.** News is a different DGP; if later, separate axis (Finnhub already has an endpoint) |

Excluding WSB would be a silent measurement bias — include it with cap + lexicon + breakdown.

Optional v1.1: ASVI-style `log(mentions_7d) − median(log(mentions_{t-8..t-1}))`.

---

## 7. Universe & peer groups

- **v1 scope:** US-listed + liquid ADRs. UK/CA/AU → v1.1 once a language-matched social source exists. Regions without social coverage produce systematically devalued rows and fake completeness.
- **Binding constraint is peer-group occupancy, not headline universe size.** Quantile estimation error ~ 1/√n per sector. **Target ≥ 30 names per GICS sector.** At ~400–500 names across 11 sectors ≈ 36–45 / group. Under-threshold sectors are flagged low-confidence on percentiles.
- **Admission rules** in `rules_json` (`placeholder`): min market cap ≥ **$1B**, min 20-day ADV ≥ **$5M**. Seed: `S&P 500 ∪ Nasdaq-100 ∪ liquid ADR list`, deduped, trimmed by ADV to ~400–500.
- **Versioning mandatory:** `universe_id` + `methodology_version` on **every** score snapshot.

---

## 8. Modular review workflow

```
Universe (rules_json, versioned)
  → Hygiene / admission
  → Winsorize → sector-relative V, Q, M percentiles
  → Base = (V + Q + M) / 3          → Composite Standing
  → Social features → shrinkage → S_used
  → Tilt (tanh) + hype dampener     → Attention Tilt
  → Final = clip(Base + Tilt, 0, 100) → Final Standing
  → Persist snapshot (as_of, universe_id, methodology_version)
```

Heat / attention UI is a **primary** surface feature, clearly separated from the composite, with the message **“loud ≠ good.”**

---

## 9. Decision log (open questions → v1 recommendation)

| ID | Question | v1 recommendation |
|----|----------|-------------------|
| A1 | Heat main or side feature | **Main**, separated from composite |
| A2/B | Research IC | **Yes, notebook only**, never a product claim |
| B1 | Keep “Buyworthiness” | **Remove** from surface |
| C1 | Momentum sector/global | **Sector in composite**, global as secondary field |
| C2 | Margin | **Operating** |
| C3 | GICS vs provider strings | **GICS-11**, mapped |
| D1 | Tilt shape | **tanh** |
| D2 | Asymmetric tilt | **Symmetric v1**; dampener carries asymmetry |
| E1 | Source cap | **0.50** |
| E2 | Comments | **No in v1** |
| E3 | Engagement | **Raw volume, engagement-weighted sentiment** |
| F1 | Shrinkage `k` | **10** (`placeholder`) |
| F2 | Prior | **Flat 50** v1 |
| G1 | US+ADR first | **Yes** |
| G2 | ADV/cap in rules_json | **Yes**, versioned |
| H1 | Commercial posture | **Non-commercial research demo**, fixture-first |
| H2 | Fallback without Reddit live | **Fixtures**; live later after approval/Firestream |
| K1 | Product name | **No “Radar”** — Standing / Mentions Desk / Retail Attention Board |

---

## 10. Non-negotiable architecture implications

1. **Fixture and live providers share the same interface** (`MarketProvider.fetch` / `SocialProvider.fetch_since(cursor)`).
2. **Forward-ingest bootstrap** — persist snapshots from day 1; treat scores as reliable only after ≥7 days.
3. **Pure scoring functions without I/O** under `domain/scoring/`; async sentiment worker.
4. **Required tests:** `test_shrinkage_continuity`, `test_no_two_score_processes`, and a check that `placeholder: true` is set on every fixture-bound config path.
5. **Before any parameter freeze:** publish correlation matrix `(V,Q,M,S)` and the variance share of Final Standing attributable to the tilt — methodology appendix, not silent fitting.

---

## 11. Summary

v2 locks a **descriptive V/Q/M Composite Standing** (equal weight, GICS-11 sector peers, operating margin, sector-relative momentum) plus a **bounded tanh Social Attention Tilt** with shrinkage and a hype dampener. Social is not a 40% pillar. Fixtures-first is mandatory given gated Reddit/StockTwits. Language stays factual; buy-semantics stay off the product surface.
