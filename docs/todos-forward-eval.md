# Standing — offene ToDos (Juli 2026)

Ausführungspriorität: **1 zuerst** (zeitkritisch), danach 2→6.

## 1 — Tägliche immutable Snapshots (Forward-Auswertung) ✅

Mit Live-Marktdaten im Default beginnt das Fenster für Spearman Score↔Forward-Return und Top-Decile-Trefferquote.

Ab dem ersten Live-Tag jeden Tagesstand unveränderlich mitschreiben:

- Score + Säulen-Subscores (V/Q/M, Tilt, Final)
- Coverage-Flags pro Metrik
- `universe_id` / Universumsversion
- Provider-Stand (Namen, Modi, as_of, Staleness)

Implementiert: `standing ingest` → `artifacts/snapshots/{as_of}/` (append-only; zweiter Write blockiert).
Serve bevorzugt den Store (`STANDING_PREFER_STORE=1`, optional `STANDING_SERVE_STORE_ONLY=1`).

## 2 — EV/EBITDA-Lücken ✅

| Fall | Ursache | Behandlung |
|------|---------|------------|
| 1 | Finnhub liefert Kennzahl nicht | Fallback-Leiter EV/EBIT → EV/Sales; Stufe in `value_ev_rung` |
| 2 | Strukturell unsinnig (Banken, Versicherer, REITs) | pe + pb/ptbv; EV = `inapplicable` |

Innerhalb der Value-Säule renormalisieren; `value_coverage` / `value_confidence` sichtbar.

## 3 — Margin-Qualität ✅

- `standing metrics-report` — Missing/non-positive Share pro Kennzahl
- Negative Multiples → schlechtestes Score (0), nicht NaN
- Signed Quality-Ranks (Negatives im schlechtesten Dezil)
- Winsorize vor Perzentilierung

## 4 — Kaltstart ✅

- `standing ingest` = nächtlicher Ingest+Score
- Serve liest Store bevorzugt; Footer zeigt `served_from` + Staleness-Zeitstempel

## 5 — Attention ohne kalibriertes NLP ✅

- `tilt_max: 5`, `attention_mode: volume_only` (weit unter alter 40%-Idee)
- Thin-sample Shrinkage `k=10`, Badges sparse/thin/ok
- Fixture-Social Banner + Drawer-Flag in der UI

## 6 — Universum (teilweise) ✅ / offen

- `universe_id` + `universe_as_of` im Snapshot-Meta
- `size_bucket` + Peer-Key-Helper `sector_x_size` vorbereitet (`peer_frame` default noch `sector`)
- Erweiterung 400–500 **vor** Start des Auswertungsfensters abschließen (Prozess, nicht Code)
