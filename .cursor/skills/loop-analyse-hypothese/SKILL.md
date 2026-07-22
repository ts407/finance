---
name: loop-analyse-hypothese
description: Analysiert den Ist-Zustand des AktienRadar-Scoring-Systems (Gewichtungen, Schwellenwerte, zuletzt dokumentierte Performance) und formuliert daraus konkrete, testbare Optimierungshypothesen. Einstiegspunkt jedes neuen Optimierungszyklus.
---

# Analyse & Hypothesenbildung

## Analyse (Ist-Zustand)
1. Lies aktuelle Scoring-Parameter, Gewichtungen (Value/Quality/Momentum/Social) und
   Schwellenwerte (Mention-Schwellen, Confidence-Diskontierung) aus dem persistenten
   Status-File (z. B. `config/scoring.yaml`).
2. Lies die zuletzt dokumentierte Performance aus dem Optimierungs-Log
   (siehe Skill loop-vergleich-entscheidung).
3. Identifiziere Kennzahlen mit größter Abweichung zwischen erwarteter und
   tatsächlicher Wirkung (z. B. Score-Rang vs. tatsächliche Kursentwicklung im
   Beobachtungsfenster).

## Hypothesenbildung
1. Formuliere auf Basis der Analyse eine oder mehrere konkrete, testbare Änderungen
   (z. B. Gewichtsverschiebung Social 40% → 30%, Anhebung Mention-Schwelle 5 → 8).
2. Jede Hypothese erhält:
   - eine eindeutige ID
   - eine Begründung (welche Abweichung soll sie adressieren)
   - eine Vorhersage der erwarteten Wirkung auf definierte Zielmetriken
3. Übergib die Hypothese(n) an den Skill loop-live-test-shadow.
