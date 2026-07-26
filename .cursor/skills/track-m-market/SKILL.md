---
name: track-m-market
description: Spur M — Markt/V/Q/M-Optimierung auf historischem OHLCV. Nutzen für Momentum-IC, σ_IC, Universumsregeln, Peer-Gruppen, Winsorisierung. Social-Hypothesen verboten.
---

# Spur M (Markt)

## Ziel
V/Q/M und den Evaluationsapparat auf realer Markthistorie eichen — unabhängig von Social.

## Erster Pflichttest
1. Lade multi-year OHLCV (Yahoo-Cache unter `artifacts/market/ohlcv/`).
2. Baue look-ahead-freie Momentum-Scores (roh + sektor-relativ + Produkt-Definition).
3. Miss IC(t) = Spearman(Score@t, Forward-Return t→t+H), H=21 Handelstage.
4. Berichte μ_IC, σ_IC, t-Stat, `T ≈ (2.80 · σ_IC / μ_IC)²`.
5. CLI: `standing track-m-calibrate`

Wenn Produkt-Momentum in mehrjährigem Panel **nicht** gefunden wird, ist die Kette
verdächtig — nicht erst Social.

## Zulässige Loop-Hypothesen (Spur M)
- Momentum-Definition / Lookback (1M/3M/6M, rel. Volumen)
- Winsorisierung
- Peer-Gruppen-Schnitt (Sektor)
- Aufnahmeschwellen (Cap, ADV)

## Gesperrt
Alles mit Social-Bezug (`social_tilt.*`, `shrinkage.*`, `social_pipeline.*`) —
siehe Spur S / Guardrails.
