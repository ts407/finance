---
name: frontend-trading-tagebuch
description: Spezifiziert das persönliche Logging-Feature (Börsen-Tagebuch) im Frontend. Nutzen bei Frontend-Änderungen am Tagebuch/Journal-Feature.
---

# Frontend: Persönliches Logging-Feature (Börsen-Tagebuch)

- Manueller Eintrag durch den Nutzer, auslösbar pro Ticker oder pro
  Beobachtungszeitpunkt.
- Jeder Eintrag speichert automatisch die Kerndaten des gegebenen Zeitpunkts:
  aktueller Buyworthiness Score, Teilscores (Value/Quality/Momentum/Social), Kurs,
  Social-Pulse-Kennzahlen, aktive Modellkonfigurations-ID, Zeitstempel.
- Zusätzlich ein Freitextfeld für einen eigenen Kommentar des Nutzers
  (z. B. Einschätzung, Entscheidungsbegründung, Beobachtung).
- Einträge sind unveränderlich nach Speicherung (append-only) oder zumindest mit
  Versionierung bei Bearbeitung, um die Integrität als Entscheidungsprotokoll
  zu wahren.
- Chronologische Ansicht mit Filter- und Suchfunktion (nach Ticker, Zeitraum,
  Freitext).
- Kein Anlageberatungscharakter: Tagebuch dokumentiert ausschließlich die eigene,
  historische Einschätzung des Nutzers, keine Handlungsempfehlung.
