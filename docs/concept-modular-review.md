# Equity Attention Screener — Modular Concept Review

**Status:** Concept (revised)  
**Methodology:** Descriptive V / Q / M + Social tilt  
**Audience:** Product, research, and engineering stakeholders

---

## 1. Purpose

The equity attention screener turns a broad listed-equity universe into a **ranked research queue**. It does **not** issue buy/sell recommendations.

Each name is described along four independent lenses:

| Module | Role |
|--------|------|
| **V — Value** | How cheap or expensive the name looks on peer-relative multiples |
| **Q — Quality** | How strong the business/balance-sheet profile looks |
| **M — Momentum** | How the price (and earnings) path compares to peers |
| **S — Social tilt** | Whether attention is unusually elevated, used only as confirmation |

The revision keeps V/Q/M **descriptive and modular**. Social is a **tilt**, not a fourth equal factor and not a primary rank driver.

---

## 2. Design principles (revised)

1. **Descriptive, not advisory.** Outputs characterize positioning (“cheap vs peers”, “strong quality”, “elevated attention”). They do not produce a single “buy” score.
2. **Modular first.** V, Q, and M are independently interpretable. A weak Value module must not be hidden inside a blended composite.
3. **Social is secondary.** Attention can promote a name *within* an already credible V/Q/M profile; it cannot override weak fundamentals, liquidity, or missing data.
4. **Evidence over opacity.** Every rank position must expose component contributions, peer context, and data freshness.
5. **Honest gaps.** Missing inputs are visible. Modules with insufficient coverage are marked incomplete rather than imputed into a false precision score.

---

## 3. Universe and hygiene gates

Before scoring:

- Exchange / listing eligibility
- Minimum price and average dollar volume (liquidity floor)
- Market-cap band (configurable; default excludes micro-illiquid names)
- Basic data-completeness thresholds per module

Names that fail hygiene remain searchable but are excluded from ranked attention queues.

---

## 4. Module V — Value (descriptive)

**Question answered:** *Relative to peers, how attractive is the valuation surface?*

### Typical inputs (peer-relative)

- Earnings yield / P/E (exclude loss-makers from P/E component)
- Book / P/B
- Cash-flow or EV/EBITDA style yield
- Optional: free-cash-flow yield when coverage is reliable

### Output

- Peer-relative percentile (0–100) and quintile band
- Short label: e.g. Cheap / Fair / Expensive (defined thresholds)
- Component breakdown so users see which multiple drives the read

### Caveats

- Sector/peer definition matters; financials and early-stage growth names need peer-aware handling
- Value alone can surface traps — Quality and Momentum exist to keep the profile honest

---

## 5. Module Q — Quality (descriptive)

**Question answered:** *How durable does the fundamental profile look?*

### Typical inputs (peer-relative where sensible)

- Profitability (ROE / ROIC / margins)
- Leverage (debt/equity or net-debt/EBITDA; invert so lower leverage ranks higher)
- Cash generation consistency (e.g. FCF positivity rate)
- Optional screens: accruals quality, simple distress/quality checklists

### Output

- Peer-relative percentile and quintile
- Short label: e.g. Strong / Average / Weak quality
- Flags for extreme leverage or inconsistent cash conversion

### Caveats

- Banks and insurers need sector-specific quality definitions
- High quality does not imply cheapness or positive momentum

---

## 6. Module M — Momentum (descriptive)

**Question answered:** *Is the market already confirming or rejecting the story in price?*

### Typical inputs (peer-relative)

- Intermediate price momentum (e.g. 12–1 month return; skip most recent month to reduce short-term reversal noise)
- Shorter confirmation windows (e.g. 3m / 6m) at lower weight
- Optional: earnings-revision / surprise proxies when available

### Output

- Peer-relative percentile and quintile
- Short label: e.g. Strong / Neutral / Weak momentum
- Separate display of short vs intermediate contributions

### Caveats

- Momentum is regime-sensitive; treat as context, not destiny
- Extreme positive momentum with rich Value is a different research job than cheap + improving momentum

---

## 7. Social tilt (S) — confirmation only

**Question answered:** *Is attention unusually elevated for this name right now?*

Social is **not** a co-equal V/Q/M factor. It is a **tilt** applied after the descriptive profile is formed.

### Typical inputs

- Mention volume and **velocity** (short window vs longer baseline)
- Sentiment polarity when classification coverage is adequate
- Cross-source breadth (more than one channel) as a quality check
- Bot / low-quality mention dampening where available

### How the tilt works

1. Compute an Attention score (peer- or history-relative velocity; polarity as secondary modifier).
2. Apply tilt **only** when hygiene gates pass and at least two of V/Q/M are complete.
3. Use tilt to:
   - **Re-order** within a shortlist (attention boost among already interesting profiles)
   - **Tag** rows as attention-led confirmation
   - **Never** rescue a name with weak liquidity, broken data, or uniformly poor V/Q/M

### Hard rules

- Social cannot dominate Signal mix presentation
- Social spikes without price/liquidity confirmation stay labeled “attention-only”
- Missing social coverage → no tilt (neutral), not a penalty by default

---

## 8. Modular review workflow

The intended human workflow is modular, not composite-first:

```
Universe → Hygiene gates
        → Score V, Q, M independently
        → Build descriptive profile (V | Q | M)
        → Compute Social Attention (optional tilt)
        → Rank research queue with visible mix + tilt tags
        → Open evidence drawer before deeper work
```

### Profile archetypes (examples, not strategies)

| Profile | Typical read |
|---------|----------------|
| Cheap + Strong Q + Improving M | Classic fundamental confirmation queue |
| Fair Value + Strong Q + Strong M | Quality-momentum follow-up |
| Cheap + Weak Q | Possible value trap — attention tilt discouraged |
| Rich + Strong M + High Attention | Attention/momentum watch — fundamentals secondary |
| High Attention only | Noise candidate unless liquidity + another module confirms |

---

## 9. Ranking presentation (anti-black-box)

Each row should expose:

- V, Q, M percentiles (and completeness)
- Social Attention score + tilt applied (yes/no, magnitude)
- Status / tags (e.g. `value-led`, `quality-led`, `momentum-led`, `attention-confirmed`)
- Liquidity, sector, market cap, data freshness

A single blended “Signal Score” may exist for sorting convenience, but it must remain **explainable as a weighted view of modules**, with Social capped so it cannot overwhelm V/Q/M.

**Suggested default blend (illustrative):**

- Value 30% · Quality 30% · Momentum 30% · Social tilt ≤ 10% (soft cap)
- Incomplete modules reduce confidence rather than silently renormalizing to 100%

---

## 10. Non-goals

- Not portfolio construction or position sizing
- Not automated trading signals
- Not a pure social/meme scanner
- Not a substitute for filings, news, or fundamental research

---

## 11. Open questions for the next revision

- Exact peer grouping (sector vs industry vs GICS leaf)
- Social data vendors and velocity window defaults
- Whether earnings momentum belongs inside M or as a separate module
- Soft-cap vs hard-cap behavior for Social in the optional blend sort

---

## 12. Summary

The revised concept is a **descriptive V/Q/M screener with a Social attention tilt**: three modular fundamental/market lenses for characterization, plus a constrained attention overlay that helps prioritize research when the crowd is already looking — without letting noise replace evidence.
