---
name: track-s-social-feasibility
description: Spur S — Social ist analytisch gesperrt bis Live-Dichte existiert. Nur Machbarkeits-Logging (n, sparse_share, Ticker-Mapping). Kein Score-Shadow auf Social-Parametern.
---

# Spur S (Social) — gesperrt für Analyse

## Ehrlicher Stand
Es existieren keine Social-Historie und kein Backfill. Score-wirksame Social-Hypothesen
sind verboten, bis Live-Ingest messbare Dichte liefert.

## Erste Woche = Machbarkeit, keine Optimierung
Erfasse nur:
- Verteilung von `n` je Ticker im 7-Tage-Fenster
- `sparse_share` (Anteil Ticker mit n=0 / unter Badge-Schwelle)
- Stichprobe Fehlzuordnung Ticker↔Mention

Daraus: deskriptives `k`-Kalibrierungssignal und ob die Quelle überhaupt eine Säule tragen kann.

## Loop-Regel
`loop-analyse-hypothese` / `loop-shadow` dürfen **keine** Änderungen an
`social_tilt`, `shrinkage`, `social_pipeline` formulieren oder shadowen, solange
diese Spur gesperrt ist.
