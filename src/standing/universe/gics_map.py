"""Static Finnhub industry → GICS-11 mapping.

Finnhub `finnhubIndustry` is not GICS. Unmapped labels raise in strict mode
and become None (caller must drop) in lenient mode.
"""

from __future__ import annotations

from standing.domain.scoring.base import GICS_11

# Curated overrides for common Finnhub industry strings observed in free profile2.
FINNHUB_INDUSTRY_TO_GICS: dict[str, str] = {
    "Technology": "Information Technology",
    "Semiconductors": "Information Technology",
    "Software": "Information Technology",
    "IT Services": "Information Technology",
    "Electronic Equipment": "Information Technology",
    "Communication Services": "Communication Services",
    "Media": "Communication Services",
    "Telecommunications": "Communication Services",
    "Telecom": "Communication Services",
    "Internet": "Communication Services",
    "Retail": "Consumer Discretionary",
    "Automobiles": "Consumer Discretionary",
    "Auto Manufacturers": "Consumer Discretionary",
    "Apparel": "Consumer Discretionary",
    "Leisure": "Consumer Discretionary",
    "Hotels": "Consumer Discretionary",
    "Restaurants": "Consumer Discretionary",
    "Consumer Cyclical": "Consumer Discretionary",
    "Consumer Defensive": "Consumer Staples",
    "Food Products": "Consumer Staples",
    "Beverages": "Consumer Staples",
    "Household Products": "Consumer Staples",
    "Tobacco": "Consumer Staples",
    "Personal Products": "Consumer Staples",
    "Banks": "Financials",
    "Banks Diversified": "Financials",
    "Insurance": "Financials",
    "Capital Markets": "Financials",
    "Financial Services": "Financials",
    "Credit Services": "Financials",
    "Biotechnology": "Health Care",
    "Drug Manufacturers": "Health Care",
    "Healthcare": "Health Care",
    "Health Care": "Health Care",
    "Medical Devices": "Health Care",
    "Medical Instruments & Supplies": "Health Care",
    "Oil & Gas E&P": "Energy",
    "Oil & Gas Integrated": "Energy",
    "Oil & Gas Midstream": "Energy",
    "Oil & Gas Equipment & Services": "Energy",
    "Energy": "Energy",
    "Aerospace & Defense": "Industrials",
    "Industrial Products": "Industrials",
    "Farm & Heavy Construction Machinery": "Industrials",
    "Airlines": "Industrials",
    "Transportation": "Industrials",
    "Business Services": "Industrials",
    "Conglomerates": "Industrials",
    "Chemicals": "Materials",
    "Metals & Mining": "Materials",
    "Building Materials": "Materials",
    "Packaging & Containers": "Materials",
    "Utilities": "Utilities",
    "Utilities - Regulated": "Utilities",
    "Utilities - Independent Power Producers": "Utilities",
    "REIT": "Real Estate",
    "REITs": "Real Estate",
    "Real Estate": "Real Estate",
    # Already-GICS labels pass through.
    **{s: s for s in GICS_11},
}


def map_finnhub_industry(industry: str | None, *, strict: bool = False) -> str | None:
    if industry is None or str(industry).strip() == "":
        if strict:
            raise ValueError("Missing finnhubIndustry")
        return None
    key = str(industry).strip()
    if key in FINNHUB_INDUSTRY_TO_GICS:
        return FINNHUB_INDUSTRY_TO_GICS[key]
    # Case-insensitive fallback
    lower = {k.lower(): v for k, v in FINNHUB_INDUSTRY_TO_GICS.items()}
    mapped = lower.get(key.lower())
    if mapped is not None:
        return mapped
    if strict:
        raise ValueError(f"Unmapped finnhubIndustry: {industry!r}")
    return None
