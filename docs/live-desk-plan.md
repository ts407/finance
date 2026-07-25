# Live Desk — Einführungsplan

Ziel: echte Attention- und Marktdaten im Standing-UI, schrittweise.

## Schritte

1. **Attention live im UI** — Default `wikipedia` (schnell, kein Key); Dropdown `fixture|wikipedia|bluesky|open`.
2. **Markt ohne Key** — Stooq-OHLCV (Yahoo-Fallback bei Challenge) überlagert Fixture-Fundamentals.
3. **Markt mit Key** — Finnhub fundamentals + Stooq/Yahoo OHLCV, wenn `FINNHUB_API_KEY` gesetzt.
4. **Caching** — Disk-Cache für Wiki/Bluesky und parallele Wiki-Requests.
5. **CLI/Web einheitlich** — `--market` / `--social` und Query-Params; UI-Dropdowns.

## Aktueller Stand

- UI Defaults: **Market=live** (EDGAR fundamentals + Yahoo OHLCV; Finnhub if key), **Attention=open** (Wikipedia + Bluesky)
- Ohne Key: volle Live-Kette (V/Q aus EDGAR, Momentum aus Yahoo, Attention aus Wiki/Bluesky)
- Erster Load cached auf Disk (`artifacts/cache/`); Folgeload deutlich schneller

## Noch später (nicht Blocker für „echte Daten sehen“)

- SEC EDGAR Point-in-Time Fundamentals
- Reddit/RFR, StockTwits Firestream
- NLP auf Archivkorpora
- Volles 400–500 Universum (heute: Fixture-Liste bzw. Seed-Subset)
