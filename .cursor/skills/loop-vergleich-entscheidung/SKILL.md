---
name: loop-vergleich-entscheidung
description: Vergleicht Alt- vs. Neu-Konfiguration anhand quantitativer Kriterien und entscheidet über Übernahme oder Verwerfen. Abschluss- und Dokumentationsschritt jedes Optimierungszyklus.
---

# Vergleich & Entscheidung

## Vergleich
1. Vergleiche Alt- vs. Neu-Konfiguration anhand vordefinierter, quantitativer Kriterien:
   - Rangkorrelation Score vs. Forward-Return
   - Trefferquote im Top-Perzentil
   - Stabilität des Rankings (Turnover)
   - Sensitivität gegenüber Social-Datenlücken
2. Kein rein visueller Vergleich: Ergebnis muss ein numerisches Entscheidungskriterium
   mit Signifikanzabschätzung liefern (z. B. Bootstrap-Konfidenzintervall bei kleiner
   Stichprobe).
3. Ziehe, sofern vorhanden, Einträge aus dem Trading-Tagebuch (Skill
   frontend-trading-tagebuch) als qualitative Zusatzreferenz heran — nicht als
   quantitativen Bestandteil des Entscheidungskriteriums.

## Entscheidung & Dokumentation
1. Übernimm die neue Konfiguration nur, wenn das Vergleichskriterium eine klar
   definierte Verbesserungsschwelle überschreitet; andernfalls verwerfen.
2. Schreibe unabhängig vom Ausgang einen Log-Eintrag (Hypothese, Ergebnis,
   Entscheidung, Zeitstempel) in ein append-only Optimierungs-Log.
3. Starte danach den nächsten Zyklus mit Skill loop-analyse-hypothese.
