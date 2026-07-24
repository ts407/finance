# AktienRadar — Konzept v2: verifizierte Fakten & konkrete Angaben

Fortschreibung der modularen Review. Basis: deskriptiv-explanatorisch, V/Q/M als Base,
Social als begrenzter Tilt (nicht 40 %-Säule), Shrinkage statt Renorm/Floor, Scope EN-Märkte + ADRs.
Alle mit synthetischen Daten kalibrierten Zahlen sind als `placeholder` markiert und ohne empirische Basis.

Verifikationsstand der operativen Fakten: **Juli 2026** (Websuche). Rechtliche Punkte sind keine Rechtsberatung.

---

## 0 — Realitäts-Check: was sich seit v1 verschoben hat (verifiziert)

Drei Dinge, die den Bauplan direkt betreffen — nicht Meinung, sondern geprüfter Stand:

**Reddit ist weitgehend zu.**
- *Responsible Builder Policy* (Nov 2025): **jeder** Zugriff ist approval-gated, auch nicht-kommerziell. Self-Service-Registrierung geschlossen; manuelle Freigabe 2–4 Wochen, viele reine Read-only-Projekte werden abgelehnt oder bleiben unbeantwortet.
- Unauthentifizierte `.json`-Endpunkte liefern **seit Mai 2026 HTTP 403** — der alte „URL + .json"-Trick ist tot.
- Free-Tier: 100 QPM (OAuth, nur non-commercial), 10 QPM unauth. Kommerziell ~$0,24/1k, aber **in 50-Mio-Call-Blöcken**; effektiver Einstieg fünfstellig. GummySearch wurde Nov 2025 genau daran eingestellt (API-Kosten je Kunde > Abo-Preis).
- **Strukturell entscheidend:** kein Date-Range-Search, kein Comment-Search, 1.000-Item-Cap je Listing, nur die jüngsten ~1.000 Einträge, **kein historischer Zugriff**. Historische Analyse nur über r/pushshift-Dumps (Snapshots, nicht live).

**StockTwits nimmt aktuell keine neuen Developer auf.** Das offizielle Developer-Portal steht auf „APIs, Doku und Terms under review, keine neuen Registrierungen". Realer Live-Pfad ist die Enterprise-Firehose *Firestream* (Partnerschaft). Dritt-Wrapper (RapidAPI/Jentic) sind ToS-unsicher und für ein publiziertes Produkt untauglich.

**Marktdaten-Landschaft hat sich verschoben.** Polygon.io ist zu **Massive.com** rebrandet und hat **kein Free-Tier mehr** (Start ~$99/Monat). Der pragmatische Free-Live-Pfad ist jetzt **Finnhub** (60 Calls/min, inkl. Fundamentals und eigenem News-Sentiment-Endpunkt) — nicht mehr yfinance.

**Korrektur (Juli 2026):** „Social ist nicht backfillbar" gilt **nicht für Bluesky**. `com.atproto.sync.getRepo` liefert unauthentifiziert die volle Repo-CAR; `listRepos` / `listReposByCollection` ermöglichen Netzwerk- bzw. collection-gezielten Backfill. Details und Reihenfolge: [datenbeschaffung.md](./datenbeschaffung.md).

### Harte Konsequenz für v1

1. **Reddit und StockTwits bleiben gated** — Fixtures sind für diese beiden Quellen und für CI weiterhin Pflicht, nicht „nice to have".
2. **Bluesky ist backfillbar** — der bisherige Zeitdruck („≥7 Tage vorwärts mitschreiben, bevor Social belastbar ist") entfällt für diese Quelle. Für Reddit/ST gilt der Vorwärts-Bootstrap weiter, falls sie jemals live gehen.
3. **Attention ist testbar ohne Social-Live:** Wikipedia-Pageviews (C2) und Archivkorpora für NLP (C3) laufen parallel; siehe Datenbeschaffungs-Reihenfolge.
4. **Die Parameter dürfen nicht eingefroren werden.** Alles unten Kalibrierte ist gegen synthetische Daten gesetzt.

---

## 1 — Name & Epistemik (Festlegung)

- `score_kind = "editorial_descriptive"` als API-Feld und auf der Methodik-Seite.
- **„Buyworthiness" / „Buy-Rank" von der Produktoberfläche streichen.** Grund ist nicht Kosmetik, sondern Modul 9: die „Buy"-Semantik ist der konkrete regulatorische Angriffspunkt.
  - Base → **„Composite Standing"**, Tilt → **„Attention Tilt"**, Ergebnis → **„Final Standing"** (0–100, Perzentil-Interpretation).
  - „Buyworthiness" höchstens auf der Methodik-Seite, mit expliziter Definition, oder ganz raus.
- Methodik-Seite zitiert die Attention-Literatur (Barber/Odean 2008; Da/Engelberg/Gao 2011) — Transparenz senkt das „stiller Tipp"-Risiko, statt es zu erhöhen.
- Namenskandidaten (kein „Radar", bewusst unspektakulär, Messung statt Prognose): **`Standing`**, **`Mentions Desk`**, **`Retail Attention Board`**. Markenrecherche vor Festlegung.

---

## 2 — Base-Score V/Q/M (konkrete Definitionen)

| Größe | Konkrete Definition v1 | Peer-Frame |
|---|---|---|
| Value | Perzentil aus **P/E (TTM), P/B, EV/EBITDA** (günstiger = höher); Median über die drei Sub-Perzentile | sektorrelativ |
| Quality | Perzentil aus **ROE, Operating Margin (EBIT/Umsatz, TTM), Umsatzwachstum (YoY)** | sektorrelativ |
| Momentum | Perzentil aus **1M/3M/6M-Total-Return + relativem Volumen** | sektorrelativ (primär) |

**Frame-Konsistenz (Korrektur zur v1-Skizze):** V/Q/M **einheitlich sektorrelativ** perzentilieren. Die v1-Idee „global Momentum + sektorrelativ V/Q" mischt zwei Referenzrahmen in einem Score und macht das Komposit uninterpretierbar. Der Preis: Momentum verliert seine übliche cross-sektionale Lesart. Deshalb: **cross-sektorales Momentum-Perzentil zusätzlich als sekundäres Anzeigefeld** ausweisen, aber **nicht** ins Komposit nehmen. Ein Rahmen im Score, beide Sichten sichtbar.

Weitere konkrete Festlegungen:
- **Margin = Operating Margin**, nicht Net Margin (Net ist durch Kapitalstruktur, Steuern, Einmaleffekte verzerrt und schlechter cross-firm vergleichbar). Gross Margin als optionales Sekundärfeld.
- **Peer-Gruppe = GICS-11-Sektoren.** Feinere Industry-Ebene ist v1 zu dünn besetzt. Sektor-Strings des Providers über eine statische Override-Tabelle auf die 11 GICS-Sektoren normalisieren.
- **Winsorizing vor Rank** (1./99. Perzentil je Kennzahl), gegen Ausreißer und Datenfehler freier Quellen.
- `Base = (V + Q + M) / 3`.

---

## 3 — Social-Tilt (konkrete Mathematik)

Additive 40 % waren doppelte Zählung (Social korreliert mit Momentum/Volume). Tilt statt Säule:

```
Tilt  = tilt_max · tanh( β · (S_used − 50) / 50 )
Final = clip( Base + Tilt , 0 , 100 )
```

- `tilt_max = 10`, `β = 1.5` (Mittelbereich ~linear, Extreme flachen ab). **tanh statt linear** (Korrektur/Entscheidung zu D1): ein einzelner Extremwert soll den Tilt nicht ausreizen.
- **v1 symmetrisch** (Interpretierbarkeit). Die „Attention ≠ gut"-Asymmetrie trägt der Hype-Dampener, nicht der Tilt. Asymmetrischer Tilt = v1.1-Experiment.
- **Kein Renorm, kein Floor** — die Sonderfälle löst die Shrinkage (Modul 5), es bleibt **ein** Score-Erzeugungsprozess.

Hype-Dampener (konkrete Form v1, `placeholder`): dämpft **positiven** Tilt bei polarisierter/negativ getriebener Lautstärke.

```
d = 1 − 2 · max(0, neg_share − 0.5)      # neg_share = Anteil negativer Mentions im Fenster
Tilt_pos_effektiv = d · Tilt_pos          # nur auf positiven Tilt angewendet
```

---

## 4 — Social-Pipeline (konkrete Parameter)

- **Quellen v1:** **Bluesky** (offener Backfill-/Live-Pfad) plus Reddit/StockTwits als Fixture (inkl. **r/wallstreetbets, mit Cap + eigenem Lexikon + Breakdown**). Ausschluss von WSB wäre stille Messverzerrung. Parallel: Wikipedia-Pageviews als Attention-Proxy ([datenbeschaffung.md](./datenbeschaffung.md)).
- **Source-Cap:** je Ticker/Tag Anteil je `source_id` ≤ **0,50**; Overflow downsampeln. Sichtbar als „cap headroom" im Pulse.
- **Mention-Features:** `log1p(count)` → **Anteil am Tages-Gesamtvolumen des Universums** → 7-Tage-Aggregat. Share (statt Rohzahl) kontrolliert plattformweite Aktivitätstage und Sampling-Lücken. ASVI-Analogon (`log(mentions_7d) − median(log(mentions_{t-8..t-1}))`) optional v1.1.
- **Engagement (Entscheidung zu E3):** getrennt behandeln —
  - *Mention-Volumen-Feature* = **rohe Count-Share** (manipulationsresistent, ein viraler Post soll das Volumen nicht dominieren).
  - *Sentiment-Aggregation* = **engagement-gewichtet**, `w = 1 + log1p(upvotes)`, gedeckelt.
- **Reddit-Comments:** **v1 nur Submissions (Titel + Body)**; Comments (Noise↑, API-Calls↑) erst v1.1.
- **Sentiment v1:** VADER + Finance-Slang-Lexikon; StockTwits Bull/Bear-Label als Blend, wo vorhanden; separates WSB-Lexikon. FinBERT optional als async Worker (API darf nicht am Modell hängen).
- **Keine News im Pulse.** News ist ein anderer datengenerierender Prozess (professionell, ereignisgetrieben, minutenschnell eingepreist) und wenig mit Retail-SVI korreliert. Falls später: eigene Achse (Finnhub liefert dafür bereits einen Endpunkt).

---

## 5 — Shrinkage (konkrete Parameter)

```
S_used = c · S_obs + (1 − c) · prior ,   c = n / (n + k)
```

- `n` = Mentions im 7-Tage-Fenster, `k = 10` (`placeholder`; auf die reale Cross-Section kalibrieren, Ziel: Median-Coverage-Ticker `c ≈ 0.6–0.7`).
- `prior = 50` (flach) in v1. **Sektor-neutraler Prior** (Median der Sektor-Social-Scores) = v1.1 — vermeidet, sparse Namen gegen einen global neutralen Wert zu ziehen, kostet aber Robustheit.
- `c` **ist** die Confidence (echte Modellgröße, kein UI-Label). Anzeige von `c` und `n`.
- Schwellen 5 / 15 nur noch **Anzeige-Badges** („sparse" / „ok"), nicht Scoring-Mechanik.
- Parametrische Shrinkage (festes `k`) reicht deskriptiv; echtes Empirical Bayes (`τ²` aus der Cross-Section geschätzt) nur als Diagnose.

---

## 6 — Universum & Peer-Gruppen (konkrete Regeln)

- **v1-Scope:** US-gelistet + liquide ADRs. UK/CA/AU erst in v1.1, sobald eine sprachlich passende Social-Quelle existiert. Regionen ohne Social-Abdeckung aufzunehmen erzeugt systematisch entwertete Einträge und täuscht Vollständigkeit vor.
- **Bindende Regel ist nicht die Gesamtgröße, sondern die Besetzung je Peer-Gruppe.** Quantil-Schätzfehler ~ 1/√n je Sektor. **Ziel: ≥ 30 Namen je GICS-Sektor.** Bei ~400–500 Titeln über 11 Sektoren ≈ 36–45/Gruppe. Sektoren unter der Schwelle werden erkannt und ihre Perzentile als low-confidence geflaggt.
- **Aufnahmeregeln in `rules_json`** (`placeholder`-Schwellen): Min. Market Cap ≥ **$1 Mrd.**, Min. 20-Tage-ADV ≥ **$5 Mio.** Seed: `S&P 500 ∪ Nasdaq-100 ∪ liquide ADR-Liste`, dedupliziert, nach ADV auf ~400–500 getrimmt.
- **Versionierung Pflicht:** `universe_id` + `methodology_version` an **jedem** Score-Snapshot. Sonst sind historische Scores nach der ersten Universumsänderung nicht mehr interpretierbar.

---

## 7 — Datenquellen (konkrete Matrix, post-Verifikation)

Vollständige Wege / Alternativen / Reihenfolge: [datenbeschaffung.md](./datenbeschaffung.md).

### Social (C1) und Attention-Proxies (C2)

| Quelle | Live-Status Juli 2026 | Historie | Rolle |
|---|---|---|---|
| **Bluesky** | offen, kein Antrag | **ja** (`getRepo` / Suche mit Datumsbereich) | **primärer offener Social-Pfad**; Backfill vor Mitschrift |
| Reddit | approval-gated, kein Backfill/Date-Range, kommerziell fünfstellig | nein | **Fixture**; Live nur vorwärts nach Freigabe; RFR = Methodik-Bonus, nicht Produkt-Feed |
| StockTwits | neue Registrierungen geschlossen; Live nur Firestream | nein | **Fixture**; Live „coming after ToS/Firestream" |
| Wikipedia-Pageviews | REST frei, kein Key | täglich ab ~2015 | **Attention-Proxy parallel**; Hypothese unabhängig von Social-Dichte testen |
| Dritt-Wrapper | ToS-unsicher | — | **nicht** für publiziertes Produkt |

### Markt & Fundamentals

| Quelle | Stand Juli 2026 | Rolle |
|---|---|---|
| Fixtures + Seed-CSV | reproduzierbar | Pflicht für CI/Dev |
| **Finnhub** | Free 60 Calls/min, Fundamentals + News-Sentiment | **Free-Live-Pfad (ersetzt yfinance-Empfehlung)** |
| Stooq / Bulk-CSV | Jahrzehnte OHLCV, 0 € | Backfill-Markt; Bereinigung prüfen |
| **SEC EDGAR (XBRL)** | frei, inkl. Einreichungsdatum | **Point-in-Time-Fundamentals** (US); Look-ahead-Bias ausschließbar |
| Twelve Data | Free 800 Calls/Tag, 50+ Börsen | globale Abdeckung v1.1 |
| EODHD | ~€20/Mon., 150k Ticker, Bulk-Download | universumsweite Fundamentals / Backtest |
| Polygon → **Massive** | kein Free-Tier mehr, ab ~$99/Mon. | nur falls Tick/Realtime nötig — für EOD-Screener **überdimensioniert** |
| yfinance | inoffiziell, brüchig, ToS-grau | allenfalls Dev-Notbehelf |

Interface bleibt `MarketProvider.fetch(...)` / `SocialProvider.fetch_since(cursor)` — **identisch** für Fixture und Live. Attention-Proxies (Wikipedia) hinter demselben Feature-Kontrakt oder als eigener `AttentionProvider`, der in denselben Shrinkage-/Tilt-Pfad mündet.

---

## 8 — `config/scoring.yaml` (konkreter Parametersatz)

```yaml
methodology_version: "2.0.0"
score_kind: "editorial_descriptive"

base:
  pillar_weights: { value: 0.3333, quality: 0.3333, momentum: 0.3334 }
  peer_frame: "sector"          # GICS-11
  winsorize: { lower: 0.01, upper: 0.99 }
  quality_margin: "operating"   # nicht "net"
  momentum_secondary_global: true

social_tilt:
  tilt_max: 10
  beta: 1.5                     # placeholder
  shape: "tanh"
  symmetric: true               # asymmetrisch = v1.1
  dampener_neg_share_pivot: 0.5 # placeholder

shrinkage:
  k: 10                         # placeholder
  prior: 50                     # sektor-neutral = v1.1
  display_badges: { sparse_below: 5, ok_at: 15 }

social_pipeline:
  sources: [bluesky, reddit, stocktwits]  # reddit/stocktwits = fixture until gated; bluesky = open backfill
  attention_proxies: [wikipedia_pageviews]  # C2 — parallel hypothesis test
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

placeholder: true               # gesamter Satz gegen synthetische Daten gesetzt
```

---

## 9 — Recht & Framing (konkrete Auflagen, keine Rechtsberatung)

Geprüfter Stand zu **Art. 20 MAR + DelVO (EU) 2016/958**:

- Der Anwendungsbereich wurde **auf alle Ersteller und Verbreiter** ausgedehnt, nicht nur Profis. Ein privat publiziertes Ranking ist also nicht automatisch draußen.
- **Rein faktische** Information ist außerhalb des Anwendungsbereichs; Material, das explizit **oder implizit** eine Anlagestrategie empfiehlt, fällt hinein. → Die **„Buy"-Semantik** ist der konkrete Auslöser; faktisches „relative standing / attention data" ist deutlich verteidigbarer.
- ESMA-Hinweis: eine Aussage über eine **sehr kleine Zahl von Emittenten** kann als Empfehlung gelten. → Eng auf einzelne Ticker zugespitzte „Top-Buy"-Darstellungen erhöhen das Risiko.
- Fällt es hinein: **objektive Darstellung** + **Offenlegung eigener Interessen/Interessenkonflikte** (bei Firmen zusätzlich quartalsweise Buy/Hold/Sell-Quoten). Ein Disclaimer allein entscheidet nichts — maßgeblich ist die objektive Darstellung.

Konkrete Auflagen fürs Produkt:
1. Neutrale, faktische Sprache (Modul 1), keine „Buy"-Etiketten.
2. Prominente Methodik- und Non-Advice-Offenlegung.
3. Bei je-Betrieb aus DE und Verbreitung in der EU vor Veröffentlichung juristisch prüfen lassen — Einzelfall.
4. Reddit-Terms (Attribution, keine Weiterlizenzierung, User-Deletion-Pflichten) und StockTwits-Firestream-ToS **getrennt** prüfen; das ist ein Blocker, kein Detail.

---

## 10 — Entscheidungs-Log (offene Fragen → Empfehlung)

| # | Frage | Empfehlung v1 | Kern-Begründung |
|---|---|---|---|
| A1 | Heat Haupt- oder Nebenfeature | **Haupt**, klar „laut ≠ gut", vom Composite getrennt | Differenzierung + Transparenz |
| A2/B | Research-IC | **ja, nur Notebook**, nie Produkt-Claim | billige Absicherung, look-ahead-frei, erst nach Wochen Ingest |
| B1 | „Buyworthiness" behalten | **streichen** von der Oberfläche | regulatorischer Auslöser |
| C1 | Momentum sektor/global | **sektorrelativ im Komposit**, global als Sekundärfeld | ein Referenzrahmen |
| C2 | Margin | **Operating** | cross-firm vergleichbarer als Net |
| C3 | GICS vs Yahoo | **GICS-11**, Provider-String gemappt | robuste, ausreichend besetzte Peers |
| D1 | Tilt linear/gedämpft | **tanh** | Extreme nicht überhebeln |
| D2 | asymmetrisch | **v1 symmetrisch**, Dampener trägt Asymmetrie | Interpretierbarkeit |
| E1 | Cap | **0,50** | eine Quelle darf Ticker-Tag nicht dominieren |
| E2 | Comments | **nein v1** | Noise/API-Kosten |
| E3 | Engagement | **Volumen roh, Sentiment engagement-gewichtet** | „wie laut" ≠ „gewichtete Stimmung" |
| F1 | `k` | **10** (`placeholder`) | Median-Coverage → `c≈0.6–0.7` |
| F2 | Prior | **50 flach** v1 | eine Bewegung weniger; sektorneutral v1.1 |
| G1 | US+ADR zuerst | **ja** | dort ist Social-Abdeckung |
| G2 | ADV/Cap in rules_json | **ja**, versioniert | Reproduzierbarkeit |
| H1 | commercial/non-commercial | **non-commercial Research-Demo**, Fixture-first für Reddit/ST | Reddit/ST gated; Bluesky + Wikipedia offen |
| H2 | Fallback ohne Reddit-Live | **Bluesky-Backfill + Wikipedia-Pageviews**; Reddit/ST weiter Fixture | Social ist Beschaffung, kein reiner Zeitdruck |
| K1 | Name | **kein „Radar"**: Standing / Mentions Desk / Retail Attention Board | Prognose-Konnotation meiden |
| — | Fixtures | **ja**, NB-Mentions + AR(1)-Sentiment, `placeholder: true` in Config | UI nicht gegen gutartige Daten tunen |

---

## 11 — Was v1 architektonisch erzwingt (nicht verhandelbar)

1. **Fixture/Live-Interface identisch**, sonst ist der spätere Live-Switch ein Rewrite.
2. **Social-Historie wo möglich backfüllen** (Bluesky zuerst); Vorwärts-Bootstrap gilt nur noch für Quellen ohne Historie (Reddit/ST). Snapshots ab Tag 1 persistieren (`as_of`, `universe_id`, `methodology_version`).
3. **Attention-Hypothese parallel über Proxies testen** (Wikipedia-Pageviews), unabhängig von Social-Dichte.
4. **Pure Scoring-Funktionen ohne I/O** (`domain/scoring/`), unit-testbar; Sentiment auf Archivkorpora entwickeln (C3), async Worker.
5. **Pflicht-Tests:** `test_shrinkage_continuity`, `test_no_two_score_processes`, plus ein Test, der prüft, dass `placeholder: true` in jedem Fixture-gebundenen Config-Pfad gesetzt ist.
6. **Empirische Pflichtarbeit vor jedem Parameter-Freeze:** Korrelationsmatrix `(V,Q,M,S)` und Varianzanteil des Final-Scores durch den Tilt ausweisen — als Methodik-Anhang, nicht als heimliches Fitting.

---

## 12 — Offen / braucht Freigabe

- Reihenfolge der Datenbeschaffung bestätigen: **Bluesky-Backfill → Wikipedia parallel → NLP auf Archiven → Reddit/RFR als Bonus** ([datenbeschaffung.md](./datenbeschaffung.md)).
- Ist v1 **explizit non-commercial Research-Demo**? Reddit/StockTwits bleiben Fixture bzw. „später"; Bluesky + Wikipedia sind die offenen Attention-Pfade.
- Namensentscheidung + Markenrecherche.
- Zielgröße 400 vs. 500 — die Sektor-Besetzung ≥ 30 ist die eigentliche Bedingung; die Gesamtzahl folgt daraus.
- Juristische Einzelfallprüfung MAR **vor** jeder öffentlichen Verbreitung aus der EU.
- SEC-EDGAR-XBRL vs. Vendor-Fundamentals für Point-in-Time-Value/Quality.
