# Live Desk — Einführungsplan

Ziel: echte Attention- und Marktdaten im Standing-UI, schrittweise.

## Schritte

1. **Attention live im UI** — Default `wikipedia` (schnell, kein Key); Dropdown `fixture|wikipedia|bluesky|open`.
2. **Markt ohne Key** — Stooq-OHLCV überlagert Fixture-Fundamentals (echte Returns/ADV/RelVol).
3. **Markt mit Key** — Finnhub fundamentals + Stooq OHLCV, wenn `FINNHUB_API_KEY` gesetzt.
4. **Caching** — Disk-Cache für Wiki/Bluesky/Stooq und Snapshot-API, damit der Desk nutzbar bleibt.
5. **CLI/Web einheitlich** — `--market` / `--social` und Query-Params `market` / `social`.

## Noch später (nicht Blocker für „echte Daten sehen“)

- SEC EDGAR Point-in-Time Fundamentals
- Reddit/RFR, StockTwits Firestream
- NLP auf Archivkorpora
- Volles 400–500 Universum (heute: Fixture-Liste bzw. Seed-Subset)
