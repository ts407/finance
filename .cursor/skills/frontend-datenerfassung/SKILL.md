---
name: frontend-datenerfassung
description: Spezifiziert die zentrale Erfassung aller für den Optimierungs-Loop relevanten Frontend-Daten. Nutzen bei Frontend-Änderungen oder wenn Rohdaten für Live-Test/Vergleich fehlen.
---

# Frontend-Datenerfassung

- Rohdaten pro Ticker zum jeweiligen Zeitpunkt: Value-/Quality-/Momentum-Rohkennzahlen,
  Social-Rohsignale (Mention-Volumen, Sentiment, Confidence), berechneter Gesamtscore.
- Nutzerinteraktionen, sofern vorhanden (z. B. welche Ticker angesehen/gefiltert wurden),
  ausschließlich als aggregierte, anonymisierte Nutzungsmetrik, nicht als
  personenbezogene Daten.
- Jede Erfassung mit Zeitstempel (UTC) und Referenz auf die aktive
  Modellkonfigurations-ID, damit spätere Vergleiche eindeutig einer Konfiguration
  zuordenbar sind.
- Exportierbarkeit der erfassten Daten in strukturierter Form (JSON/CSV) als
  Grundlage für den Skill loop-live-test-shadow.
