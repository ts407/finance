# Datenbeschaffung — Wege, Alternativen, Reihenfolge

**Status:** Strategie-Korrektur (Juli 2026)  
**Bezieht sich auf:** [aktienradar-konzept-v2.md](./aktienradar-konzept-v2.md) §0 / §7 / §11  
**Kern:** Social ist überwiegend ein **Beschaffungsproblem mit mehreren offenen Wegen**, kein reines Echtzeit-Erhebungsproblem („die Uhr läuft").

---

## Korrektur — „Social ist nicht backfillbar" gilt nicht für alle Quellen

| Quelle | Historie backfillbar? | Begründung |
|--------|----------------------|------------|
| Reddit | **nein** | kein Date-Range-Search, Listing-Cap, approval-gated |
| StockTwits | **nein** | neue Developer-Registrierung geschlossen; Live nur Firestream |
| **Bluesky** | **ja** | AT-Proto-Sync ist bewusst unauthentifiziert und öffentlich |

### Bluesky — verifizierter Backfill-Pfad

- `com.atproto.sync.getRepo` liefert das vollständige Repository eines Accounts als **CAR-Datei** und verlangt **keine Authentifizierung** — Nutzer-Repos-Inhalt ist öffentlich wie eine Website.
- Bluesky dokumentiert das Vorgehen: über `listRepos` alle Repos enumerieren, für jedes `getRepo` abrufen → vollständige Netzwerk-Replik möglich ([Backfilling the Network](https://docs.bsky.app/docs/advanced-guides/backfill)).
- `listReposByCollection` unterstützt Backfill **nach Record-Typ** (z. B. nur Repos mit `app.bsky.feed.post`).

**Konsequenz:** Bei Bluesky ist Historie beschaffbar, nicht nur mitschreibbar. Der Zeitdruck, der die bisherige Prioritätenordnung getragen hat, entfällt.

**Pragmatik für Ticker-Erwähnungen:** Vollnetz-Replik ist überdimensioniert. Die Suchschnittstelle mit Datumsbereich ist der ökonomischere Weg. Für rein akademische Nutzung zusätzlich Communalytic (Historical Posts Data Collector) für Posts zu einer Suchanfrage in einem Datumsbereich.

---

## A — Marktdaten (Preise, Volumen)

| Weg | Tiefe | Kosten | Haken |
|-----|-------|--------|-------|
| Anbieter-API mit Free-Tier | >10 J. täglich | 0 € | Tageskontingent begrenzt Universumsgröße |
| Bulk-CSV-Quellen (z. B. Stooq) | Jahrzehnte | 0 € | keine Garantien, Bereinigung prüfen |
| Bezahlter Tier bei einem Anbieter | dieselbe | ~20–150 $/Mon. | löst nur das Kontingent, nicht die Qualität |
| Börsen-/Indexanbieter direkt | tief | teuer | für dieses Vorhaben überdimensioniert |

**Stand:** kein strategisches Problem, nur Kostenfrage. Im Repo bereits durch Fixtures + optionale Free-Live-Adapter abgedeckt.

---

## B — Fundamentaldaten (Value, Quality)

**Bevorzugter Weg (selten genommen):** [SEC EDGAR](https://www.sec.gov/edgar) liefert **XBRL-Fundamentaldaten frei**, inklusive Einreichungsdatum.

| Vorteil | Nachteil |
|---------|----------|
| echte **Point-in-Time**-Daten (wann war die Zahl öffentlich?) | mehr Eigenarbeit: XBRL-Tags mappen, Restatements behandeln |
| Look-ahead-Bias tatsächlich ausschließbar | nur US-Emittenten |
| qualitativ besser als Vendor-Kennzahlen ohne Bekanntheitszeitpunkt | — |

Vendor-Endpunkte liefern oft „P/E für Fiskaljahr 2024", aber mit welchem Kurs und zu welchem Bekanntheitszeitpunkt, steht nirgends. Für ein **US-first-Universum** ist der EDGAR-only-Scope kein Verlust.

---

## C — Attention (der eigentliche Engpass)

Drei getrennte Kategorien — **nicht vermischen**:

### C1 — Direkte Social-Quellen

| Quelle | Live | Historie | Zugang |
|--------|------|----------|--------|
| **Bluesky** | ja | **ja** | offen, kein Antrag |
| Reddit | nur nach Freigabe | nein | Ticket-Queue, oft abgelehnt |
| StockTwits | nur mit Alt-Key | nein | Registrierung geschlossen |
| Mastodon | ja | teilweise | offen, aber sehr dünne Finanzdiskussion |

### C2 — Backfillbare Attention-Proxies

Die akademische Literatur zu Retail-Attention arbeitet überwiegend **nicht** mit Social-Posts, sondern mit Proxies:

| Proxy | Zugang | Historie / Auflösung | Hinweis |
|-------|--------|----------------------|---------|
| **Wikipedia-Pageviews** | freie REST-API, kein Key | täglich, ab ~2015 | Ticker→Artikel über Wikidata (Tickersymbol als Eigenschaft). **Pragmatischster Attention-Proxy überhaupt** — kein Gatekeeper, sofort mehrjährig. |
| Such-Volumen-Index (SVI) | schlecht | klassischer Literatur-Proxy | Offizielle Trends-API seit Juli 2025 application-gated Alpha, 2026 nicht allgemein verfügbar; `pytrends` April 2025 archiviert. Antrag stellen kostet nichts, planbar ist es nicht. |
| Short Interest | frei | halbmonatlich, lange Historie | kein Attention-Maß im engen Sinn; Positionierungs-Signal |
| Abnormales Handelsvolumen | 0 Extra-Kosten | steckt in OHLCV | **Doppelzählungsgefahr:** relatives Volumen sitzt bereits in Momentum → als Attention-Proxy nicht unabhängig |

**Konzeptioneller Wert:** Mit C2 ist die Attention-Hypothese **über Jahre testbar**, bevor klar ist, ob die Social-Quelle trägt. Findet man in mehreren Jahren Wikipedia-Pageviews keinen Zusammenhang zu Forward-Returns, ist die Wahrscheinlichkeit gering, dass ausgerechnet Bluesky-Cashtags einen liefern.

### C3 — Archive für die NLP-Entwicklung

Historische Reddit- und StockTwits-Korpora existieren als öffentliche Forschungsdatensätze.

- **Nicht** geeignet als Live-Zeitreihe für den Score.
- **Genau richtig** für: Sentiment-Lexikon und Klassifikator **heute** entwickeln, kalibrieren, validieren — statt erst, wenn Live-Daten da sind.

Das entkoppelt die NLP-Komponente vollständig von der Datenbeschaffung.

---

## D — Der akademische Hebel

Universitäres Umfeld öffnet Wege, die kommerziell verschlossen sind:

- **Reddit for Researchers (RFR)** — ausschließlich nicht-kommerziell ([Reddit Help](https://support.reddithelp.com/)).
- Finanzdatenbanken oft bereits über Hochschullizenzen vorhanden.

**Harte Einschränkung (nicht wegreden):** RFR-Teilnehmer dürfen Daten nicht über das für das unmittelbare Forschungsprojekt Nötige hinaus aufbewahren und müssen Abfragen gegen aktuelle Exporte erneut laufen lassen. Solche Daten können ein **Produkt nicht speisen**. Sie können die **Methodik validieren**: prüfen, ob das Attention-Konstrukt auf einer sauberen Reddit-Historie funktioniert, und die Erkenntnis auf die frei nutzbare Quelle übertragen.

---

## Abgeleitete Reihenfolge

| # | Schritt | Warum zuerst |
|---|---------|--------------|
| 1 | **Bluesky-Backfill** (nicht nur Mitschrift) | Historie beschaffbar → Wartezeit entfällt; Social sofort mit Monaten Tiefe analysierbar |
| 2 | **Wikipedia-Pageviews parallel** | Mehrjährige Attention-Reihe ohne Gatekeeper; Hypothese unabhängig von Bluesky-Dichte testbar |
| 3 | **Sentiment-Modell auf Archivkorpora** | Läuft komplett parallel, blockiert nichts |
| 4 | **Reddit-Antrag / RFR prüfen** | möglicher Bonus, **nicht** Voraussetzung |

### Was sich an der Konzeption ändert

| Vorher (zu pauschal) | Jetzt |
|----------------------|-------|
| „Social ist nicht backfillbar" | gilt für Reddit/StockTwits, **nicht** für Bluesky |
| Zeitdruck: vorwärts mitschreiben, ≥7 Tage warten | bei Bluesky entfällt der Bootstrap-Druck |
| Fixtures als einziger gangbarer Social-Pfad | Fixtures bleiben für Reddit/ST und CI; **Bluesky + Wikipedia** sind offene Live-/Historie-Pfade |
| Social = Echtzeit-Erhebungsproblem | Social = Beschaffungsproblem mit mehreren offenen Wegen |

## Integration — how to wire the open services

Providers share `SocialProvider.fetch_since` and land in the existing cap → aggregate → tilt path.

| Mode | CLI | Contents |
|------|-----|----------|
| `fixture` | default | Reddit/ST stubs (CI) |
| `wikipedia` | `--social wikipedia` | live pageviews |
| `bluesky` | `--social bluesky` | live cashtag search (`api.bsky.app`) |
| `open` | `--social open` | Wikipedia + Bluesky |
| `all` | `--social all` | fixture + open |

```bash
standing table --as-of 2026-07-22 --social wikipedia --history-days 14
standing heat --as-of 2026-07-22 --social open --history-days 30
STANDING_SOCIAL=open standing serve
```

Code map: `providers/wikipedia_pageviews.py`, `providers/bluesky.py`, `providers/composite_social.py`, `providers/factory.py`.
