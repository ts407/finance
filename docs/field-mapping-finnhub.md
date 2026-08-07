# Field mapping — Finnhub / Stooq → `MarketProvider` frame

**Status:** adapter checklist (Phase 4 prep).  
**Scored desk:** remains fixture-fed until social has a real path or a labeled fundamentals-only preview is deliberately shipped.

## Endpoint posture (free tier)

| Endpoint | Free tier | Role |
|----------|-----------|------|
| `GET /stock/metric?metric=all` | Yes (US) | V, Q, M-proxy, ADV-proxy in one call |
| `GET /stock/profile2` | Yes (US) | Sector (`finnhubIndustry`), market cap |
| `GET /stock/candle` | No (403 on free) | Do **not** use; OHLCV via Stooq instead |
| Stooq daily CSV `q/d/l/?s={sym}.US&i=d` | No key | Exact returns + true 20d dollar ADV |

Per ticker cold path: **~2 Finnhub calls** (+ optional Stooq CSV). Batch job only — never on the web request path.

## Standing columns

| Standing column | Primary source | Field / derivation | Fallback | Notes |
|-----------------|----------------|--------------------|----------|-------|
| `ticker` | profile2 | `ticker` | seed symbol | Uppercase |
| `sector` | profile2 | `finnhubIndustry` → GICS-11 map | — | Finnhub industry ≠ GICS; static table required |
| `listing` | seed lists | `US` / `ADR` | profile2 country/exchange heuristic | Admission uses this |
| `market_cap` | profile2 | `marketCapitalization * 1e6` | metric `marketCapitalization * 1e6` | Finnhub reports millions |
| `pe_ttm` | metric | `peTTM` | — | Ratio (not %); trailing |
| `pe_forward` | metric | `forwardPeRatio` | `forwardPE`, `peForward` | Consensus NTM; PE-ladder prefers this over TTM |
| `pb` | metric | `pb` | — | Ratio |
| `ev_ebitda` | metric | `currentEv/ebitdaAnnual` | `enterpriseValueMultipleTTM` | Ratio |
| `roe` | metric | `roeTTM` | — | Often percent → `/100` when `|x| > 2` |
| `operating_margin` | metric | `operatingMarginTTM` | — | Often percent → `/100` when `|x| > 2` |
| `revenue_growth_yoy` | metric | `revenueGrowthTTMYoy` | — | Often percent → `/100` when `|x| > 1` |
| `ret_1m` | Stooq | close[t]/close[t−21] − 1 | — | Exact; no strong Finnhub 1M field |
| `ret_3m` | Stooq | close[t]/close[t−63] − 1 | `13WeekPriceReturnDaily / 100` | Proxy when Stooq missing |
| `ret_6m` | Stooq | close[t]/close[t−126] − 1 | `26WeekPriceReturnDaily / 100` | Proxy when Stooq missing |
| `adv_20d` | Stooq | mean(close × volume, 20d) | `10DayAverageTradingVolume × lastPrice × 1e6` | Volume fields are share-millions |
| `relative_volume` | Stooq | adv_shares_10 / adv_shares_60 | `10DayAverageTradingVolume / (3MonthAverageTradingVolume / ~6.5)` | Soft feature |
| `as_of` | runner | ISO date | — | Live provider: latest ingest only |

## Completeness policy (mapping layer)

- Missing pillar inputs stay `NaN` in the market frame.
- Adapter emits `pillar_completeness` metadata counts; it does **not** invent values.
- Scoring still owns peer percentiles; incomplete-pillar Base mean is a separate scoring change (not required for adapter validation).

## Historical `as_of`

`FinnhubMarketProvider.supports_historical() → False`.  
Cassette/offline validation may pin a fixed `as_of` for determinism; live mode must refuse arbitrary history until a stamped snapshot store exists.

## Not wired into Final

`STANDING_MARKET_PROVIDER=finnhub` builds the adapter for `standing market-preview` only.  
CLI `score` / `table` / `heat` / `report` / web desk stay on `FixtureMarketProvider` + `FixtureSocialProvider`.
