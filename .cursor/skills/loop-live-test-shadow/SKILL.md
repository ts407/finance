---
name: loop-live-test-shadow
description: Implementiert eine Optimierungshypothese isoliert und testet sie im Shadow-Modus parallel zur produktiven Konfiguration auf Live-Daten. Nutzen nach Abschluss von loop-analyse-hypothese.
---

# Implementierung & Live-Test (Shadow-Modus)

## Implementierung
1. Setze die Änderung in einem isolierten Branch/Konfigurationssatz um —
   niemals direkt in der produktiven Konfiguration.
2. Versioniere jede Konfiguration mit Zeitstempel und Hypothesen-ID.

## Live-Test
1. Führe die veränderte Konfiguration parallel zur bestehenden aus (Shadow-Modus:
   beide Konfigurationen laufen gleichzeitig auf denselben Live-Daten).
2. Mindestzeitraum: 5–10 Handelstage (konfigurierbar je nach Datenverfügbarkeit
   und Volatilität der betroffenen Kennzahl).
3. Erfasse für beide Konfigurationen identische Kennzahlen im selben Zeitraster.
4. Beziehe die im Skill frontend-datenerfassung erfassten Rohdaten als
   gemeinsame Datengrundlage ein, damit Alt- und Neu-Konfiguration auf
   identischer Datenbasis verglichen werden.
5. Übergib die Testergebnisse an den Skill loop-vergleich-entscheidung.
