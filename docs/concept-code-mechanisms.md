# Standing — Code Rules & Mechanisms

**Status:** Implementation concept (maps methodology → code)  
**Methodology source of truth:** [aktienradar-konzept-v2.md](./aktienradar-konzept-v2.md)  
**Data acquisition:** [datenbeschaffung.md](./datenbeschaffung.md)  
**Product plan:** [concept-plan.md](./concept-plan.md) · **Modular review:** [concept-modular-review.md](./concept-modular-review.md)  
**Config:** `config/scoring.yaml`, `config/rules.json`  
**Code root:** `src/standing/`

This document explains **in general** what the codebase does, then **in detail** every rule and mechanism the implementation enforces. It is the bridge between the Konzept v2 locks and the running Python package.

---

## Part A — General overview

### What the product is

**Standing** ranks liquid US equities and ADRs with an **editorial, descriptive** score — not a buy/sell tip.

| Output field | Meaning | Range |
|--------------|---------|-------|
| `composite_standing` | Equal-weight sector-relative Value / Quality / Momentum | 0–100 |
| `attention_tilt` | Bounded social adjustment after shrinkage (+ hype dampener) | ≈ ±`tilt_max` |
| `final_standing` | `clip(Base + Tilt, 0, 100)` — **the only** final score | 0–100 |

Declared epistemology: `score_kind = "editorial_descriptive"`. Product language avoids “Buy”, “Buyworthiness”, and “Buy-Rank”.

### One-sentence pipeline

```
Market + Social fixtures
  → admit universe
  → sector-relative V/Q/M base
  → social features → shrinkage → tanh tilt (+ dampener)
  → Final Standing snapshot (CSV / CLI / HTML)
```

There is **one** score-generation process. There is no renorm path, no floor path, and no alternate formula that could disagree with `final_standing`.

### Architectural layers

| Layer | Responsibility | I/O? |
|-------|----------------|------|
| `config/` | Methodology + admission parameters | files only |
| `domain/scoring/` | Pure scoring math | **no I/O** |
| `providers/` | Market / Social data behind shared interfaces | I/O (fixtures today) |
| `universe/` | Admission filters + sector occupancy flags | no external I/O |
| `pipeline/` | Orchestrate snapshot + persist + HTML report | I/O |
| `cli.py` | `standing table|heat|score|report` | I/O |

**Rule:** scoring logic lives in pure functions. Providers may be swapped (fixture → live) without changing formulas.

### Epistemic safety rules (enforced in config + tests)

1. `placeholder: true` until parameters are frozen on a real cross-section.
2. `methodology_version` and `universe_id` travel with every snapshot.
3. Missing social data shrinks toward the prior — it does **not** invent attention.
4. Thin sectors are flagged (`sector_low_confidence`), not silently trusted.
5. Social is a **tilt**, never a fourth weighted pillar.

---

## Part B — Detailed mechanisms

### B1 — Configuration contracts

#### `config/scoring.yaml`

Loaded by `standing.config.load_scoring_config()` into an immutable `ScoringConfig`.

| Block | Mechanism | Code consumer |
|-------|-----------|---------------|
| `methodology_version` | Stamped on every score row / snapshot | `pipeline.score_cross_section`, `StandingSnapshot` |
| `score_kind` | Must stay `editorial_descriptive` | tests + snapshot meta |
| `base.pillar_weights` | Weights for V/Q/M (≈⅓ each) | `compute_base_standing` |
| `base.peer_frame` | Sector-relative ranks (GICS-11) | `pillar_percentiles` |
| `base.winsorize` | Clip metrics at lower/upper quantiles before rank | `_sector_relative_percentile` |
| `base.quality_margin` | Operating margin (not net) — documented lock | market fixture fields |
| `base.momentum_secondary_global` | Emit `momentum_global` display field | `pillar_percentiles` |
| `social_tilt.tilt_max` | Soft cap on tilt magnitude (default 10) | `attention_tilt` |
| `social_tilt.beta` | Steepness of tanh (`placeholder`) | `attention_tilt` |
| `social_tilt.shape` | Must be `tanh` | tests |
| `social_tilt.symmetric` | Positive and negative tilts same shape in v1 | `attention_tilt` |
| `social_tilt.dampener_neg_share_pivot` | Pivot for hype dampener (0.5) | `hype_dampener` |
| `shrinkage.k` | Pseudo-count strength (`placeholder`) | `shrink_social` |
| `shrinkage.prior` | Flat prior (50) | `shrink_social` |
| `shrinkage.display_badges` | `sparse` / `thin` / `ok` thresholds on `n` | `_badge` in scoring pipeline |
| `social_pipeline.source_cap_per_ticker_day` | Max share per source/day (0.50) | `apply_source_cap` |
| `social_pipeline.mention_transform` | `log1p` → universe share → 7d agg | `aggregate_mentions` |
| `social_pipeline.reddit_comments` | `false` in v1 | config lock / tests |
| `universe.*` | Cap / ADV / sector occupancy targets | universe builder + flags |
| `placeholder` | Global “synthetic calibration” flag | CLI warning + snapshot |

#### `config/rules.json`

Loaded by `standing.config.load_rules()`. Admission + identity for the universe.

| Field | Rule |
|-------|------|
| `universe_id` | Stable id stamped on snapshots (`fixture-gics11-v1`) |
| `scope` | Listing must be in `["US", "ADR"]` when `listing` column exists |
| `min_market_cap_usd` | Drop names below threshold |
| `min_adv_usd_20d` | Drop names below 20-day ADV threshold |
| `min_names_per_sector` | Target occupancy (30); below → low confidence |
| `target_size` | Aspirational [400, 500]; fixture demo may be smaller |
| `peer_frame` | `GICS-11` |
| `placeholder` | Same epistemic flag as scoring config |

---

### B2 — Provider contracts

Interfaces in `standing.providers.base` make **fixture ≡ live** at the API boundary.

#### `MarketProvider.fetch(as_of, tickers?) → DataFrame`

Required columns:

```
ticker, sector, market_cap, adv_20d,
pe_forward, pe_ttm, pb, ev_ebitda, ev_ebit, ev_sales,
roe, operating_margin, revenue_growth_yoy,
ret_1m, ret_3m, ret_6m, relative_volume
```

Optional but used by admission: `listing`.

v1 implementation: `FixtureMarketProvider` (synthetic multi-sector demo).

#### `SocialProvider.fetch_since(cursor) → (DataFrame, next_cursor)`

Required columns:

```
date, ticker, source_id, mention_count, neg_share, upvotes
```

`FetchCursor(as_of, token?)` is identical for fixture and future live ingest.

v1 implementation: `FixtureSocialProvider` (simulated Reddit + StockTwits daily rows). Planned live: Bluesky backfill/search behind the same interface; Wikipedia pageviews as attention proxy (see [datenbeschaffung.md](./datenbeschaffung.md)).

**Rule:** scoring never imports a concrete provider. Orchestration wires providers in `pipeline.snapshot` / CLI.

---

### B3 — Universe admission

Module: `standing.universe.builder`

```
raw market rows
  → market_cap >= min_market_cap_usd
  → adv_20d   >= min_adv_usd_20d
  → listing ∈ scope (if column present)
  → UniverseSnapshot
```

`UniverseSnapshot` carries:

- `universe_id`, `methodology_version`, `as_of`
- `members` (admitted frame)
- `sector_counts`
- `low_confidence_sectors` (sectors with count < `min_names_per_sector`)
- raw `rules`

Snapshot orchestration then **restricts social rows** to admitted tickers before scoring.

---

### B4 — Base score (Value / Quality / Momentum)

Module: `standing.domain.scoring.base`

#### Winsorize

For each metric inside a peer group, clip to the configured quantile band (default 1st–99th) **before** ranking. Guards free-source outliers.

#### Sector-relative percentile

Within each GICS-11 sector:

1. Optionally winsorize.
2. Average-rank the valid values.
3. Map ranks to **0–100** percentiles (`(rank − 1) / (n − 1) * 100`).
4. NaNs stay NaN (no silent fill).

#### Pillar definitions

| Pillar | Inputs | Direction | Aggregation |
|--------|--------|-----------|-------------|
| **Value** | PE-ladder (`pe_forward`→`pe_ttm`), `pb`, EV-ladder | cheaper = better → invert `1/x` (non-positive → worst score 0) | **mean** of available sub-percentiles (renormalize) |
| **Quality** | `roe`, `operating_margin`, `revenue_growth_yoy` | higher = better | **median** of three sub-percentiles |
| **Momentum** | `ret_1m`, `ret_3m`, `ret_6m`, `relative_volume` | higher = better | **median** of four sub-percentiles |

All three pillars use the **same peer frame** (sector). Mixing frames inside the composite is forbidden.

#### Secondary display field

`momentum_global` = same momentum inputs ranked **across the whole universe** (still winsorized). Shown for interpretation; **not** fed into `composite_standing`.

#### Composite Standing

```
Base = w_V·V + w_Q·Q + w_M·M
```

Default weights ≈ equal thirds. Rows missing any pillar stay `NaN` — **no silent renorm of remaining pillars**.

#### Sector occupancy flag

`sector_low_confidence = (sector_size < min_names_per_sector)`. Fixture demos are expected to flag most sectors until the full 400–500 universe is populated.

---

### B5 — Social feature pipeline

Module: `standing.domain.scoring.social_features`

#### Source cap

Per `(ticker, date)`, each `source_id` may contribute at most `source_cap_per_ticker_day` (default **0.50**) of that day’s mentions.

- Overflow is **downsampled** (scaled so share == cap).
- Overflow is **not** redistributed to other sources.
- Emits `mention_count_capped`, `source_share`, `cap_headroom`.

#### 7-day aggregation

Over `[as_of − 6d, as_of]`:

1. `log_count = log1p(mention_count_capped)`
2. `day_share = log_count / Σ_universe(log_count)` that day
3. Per ticker:
   - `n` = sum of capped counts in window
   - `universe_share_7d` = sum of day shares in window
   - `neg_share` = count-weighted average of daily `neg_share` (else 0.5)

#### Observational social score

```
S_obs = percentile_rank(universe_share_7d) ∈ [0, 100]
```

Cross-sectional among tickers present in the social aggregate. Tickers with **no** social rows later default to `S_obs = 50`, `n = 0`, `neg_share = 0.5` at alignment time (neutral observation, zero evidence).

---

### B6 — Shrinkage

Module: `standing.domain.scoring.shrinkage`

```
c      = n / (n + k)
S_used = c · S_obs + (1 − c) · prior
```

| Symbol | Meaning |
|--------|---------|
| `n` | Effective mention mass in the 7-day window |
| `k` | Shrinkage strength (`placeholder`, default 10) |
| `prior` | Neutral center (default 50) |
| `c` | Model confidence (`confidence_c` on output rows) |

**Properties enforced by tests:**

- Continuous and monotonic in `n` toward `S_obs`
- `n = 0` → `S_used = prior`, `c = 0`
- Large `n` → `S_used ≈ S_obs`, `c ≈ 1`

Display badges from `n` (config thresholds):

| Badge | Condition (defaults) |
|-------|----------------------|
| `sparse` | `n < 5` |
| `thin` | `5 ≤ n < 15` |
| `ok` | `n ≥ 15` |

Shrinkage replaces any need for a separate renorm/floor score process.

---

### B7 — Attention tilt & Final Standing

Module: `standing.domain.scoring.tilt`

#### Symmetric tanh tilt

```
Tilt_raw = tilt_max · tanh( β · (S_used − 50) / 50 )
```

- Neutral at `S_used = 50` → tilt `0`
- Saturates toward ±`tilt_max` (never fully reaches at finite β·1)
- Mid-range approximately linear
- One extreme observation cannot fully max out the tilt (vs linear)

#### Hype dampener (positive tilt only)

```
d = clip( 1 − 2 · max(0, neg_share − pivot) , 0, 1 )
Tilt = Tilt_raw · d    if Tilt_raw > 0
Tilt = Tilt_raw        otherwise
```

Negative / polarizing loudness reduces **upward** attention influence; downward tilt is unchanged in v1.

#### Final Standing (single process)

```
Final = clip( Base + Tilt , 0 , 100 )
```

**Invariant (tested):** there is no second formula. `|Tilt| ≤ tilt_max`. Dampener only scales positive raw tilt.

---

### B8 — Cross-section orchestration

Module: `standing.domain.scoring.pipeline` → `score_cross_section`

Ordered steps:

1. `pillar_percentiles(market)` → V, Q, M, `momentum_global`
2. `compute_base_standing` → `composite_standing`
3. `sector_occupancy_flags`
4. `apply_source_cap(social_daily)`
5. `aggregate_mentions` → `S_obs`, `n`, `neg_share`
6. Align social to market tickers (missing → prior-neutral defaults)
7. `shrink_social` → `S_used`, `confidence_c`
8. `attention_tilt` (+ dampener)
9. `final_standing`
10. Emit row schema including badges, `score_kind`, `methodology_version`, `as_of`

Output is one row per admitted ticker.

---

### B9 — Snapshot persistence & surfaces

Module: `standing.pipeline.snapshot` + `report` + `cli`

#### `run_snapshot`

1. Build admitted universe from market provider  
2. Fetch social since cursor  
3. Filter social to admitted tickers  
4. Score cross-section  
5. Sort by `final_standing` descending  
6. Attach meta: sector counts, low-confidence sectors, provider names  

#### Persistence

`persist_snapshot` writes:

- `standings_{as_of}.csv`
- `standings_{as_of}.meta.json` (`as_of`, `universe_id`, `methodology_version`, `score_kind`, `placeholder`, meta)

#### CLI surfaces

| Command | Purpose |
|---------|---------|
| `standing table` | Ranked Final Standing table |
| `standing heat` | Attention-oriented view (tilt / social fields primary) |
| `standing score` | Persist snapshot artifacts |
| `standing report` | HTML report |

CLI warns if `placeholder` is flipped to `false` without an empirical freeze.

---

### B10 — Hard non-goals encoded as absences

The code deliberately does **not** implement:

| Non-goal | How absence shows up |
|----------|----------------------|
| Social as 40% pillar | No social weight in `pillar_weights` |
| Renorm / floor alternate score | Only `final_standing = clip(base+tilt)` |
| Reddit comments | `reddit_comments: false`; fixtures are submission-grain |
| News inside Pulse | No news provider / feature columns |
| Live Reddit / StockTwits | Only fixture providers wired in CLI; Bluesky/Wikipedia = planned open paths |
| Silent pillar renorm | Incomplete V/Q/M → `NaN` base |
| “Buy” product labels | `score_kind` + field names use Standing / Tilt |

---

### B11 — Testing contracts

| Test focus | Rule locked |
|------------|-------------|
| `test_shrinkage_continuity` | Shrinkage continuous; endpoints prior / obs |
| `test_no_two_score_processes` | Single Final identity; dampener polarity; \|tilt\| bound |
| `test_placeholder_true_on_fixture_config` | Epistemic + tilt shape locks |
| `test_tilt_tanh_saturates` | Neutral zero; extremes approach but don’t explode past max |
| Pipeline integration tests | End-to-end fixture snapshot produces ranked standings |

---

## Part C — Quick reference formulas

```
# Admission
keep if market_cap ≥ min_cap AND adv_20d ≥ min_adv AND listing ∈ scope

# Pillars (per sector, after winsorize)
V = median( pct(1/PE), pct(1/PB), pct(1/EV_EBITDA) )
Q = median( pct(ROE), pct(OpMargin), pct(RevYoY) )
M = median( pct(ret_1m), pct(ret_3m), pct(ret_6m), pct(rel_vol) )
Base = (V + Q + M) / 3     # or configured weights; all three required

# Social
capped_count = downsample so source_share ≤ 0.50
day_share = log1p(capped) / Σ_universe log1p(capped)
S_obs = pct( Σ_7d day_share )
c = n / (n + k)
S_used = c·S_obs + (1−c)·50

# Tilt + Final
Tilt_raw = 10 · tanh( 1.5 · (S_used − 50) / 50 )
d = clip(1 − 2·max(0, neg_share − 0.5), 0, 1)
Tilt = Tilt_raw·d if Tilt_raw > 0 else Tilt_raw
Final = clip(Base + Tilt, 0, 100)
```

Defaults marked `placeholder` in config are synthetic until an empirical freeze.

---

## Part D — File map

| Path | Mechanism |
|------|-----------|
| `config/scoring.yaml` | Methodology parameters |
| `config/rules.json` | Universe admission identity |
| `src/standing/config.py` | Loaders / `ScoringConfig` |
| `src/standing/domain/scoring/base.py` | Winsorize, percentiles, V/Q/M, base |
| `src/standing/domain/scoring/social_features.py` | Source cap, 7d share, `S_obs` |
| `src/standing/domain/scoring/shrinkage.py` | `S_used`, confidence `c` |
| `src/standing/domain/scoring/tilt.py` | tanh tilt, dampener, Final |
| `src/standing/domain/scoring/pipeline.py` | Single cross-section orchestration |
| `src/standing/universe/builder.py` | Admission + occupancy |
| `src/standing/providers/base.py` | Market/Social interfaces |
| `src/standing/providers/*_fixture.py` | v1 data |
| `src/standing/pipeline/snapshot.py` | Snapshot run + persist |
| `src/standing/pipeline/report.py` | HTML report |
| `src/standing/cli.py` | Operator surfaces |
| `tests/test_scoring_required.py` | Core mathematical locks |
| `tests/test_pipeline.py` | Integration locks |
