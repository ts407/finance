"""Ticker → English Wikipedia article title (underscore form).

Static seed for the fixture universe. Full coverage later via Wikidata P414
(ticker symbol) SPARQL — not required for the first live provider path.
"""

from __future__ import annotations

# Keys are uppercase tickers; values are enwiki titles with spaces as underscores.
WIKIPEDIA_TITLES: dict[str, str] = {
    "AAPL": "Apple_Inc.",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "ORCL": "Oracle_Corporation",
    "CRM": "Salesforce",
    "AMZN": "Amazon_(company)",
    "TSLA": "Tesla,_Inc.",
    "HD": "The_Home_Depot",
    "NKE": "Nike,_Inc.",
    "SBUX": "Starbucks",
    "KO": "The_Coca-Cola_Company",
    "PEP": "PepsiCo",
    "WMT": "Walmart",
    "COST": "Costco",
    "PG": "Procter_&_Gamble",
    "JPM": "JPMorgan_Chase",
    "BAC": "Bank_of_America",
    "GS": "Goldman_Sachs",
    "V": "Visa_Inc.",
    "MA": "Mastercard",
    "JNJ": "Johnson_&_Johnson",
    "UNH": "UnitedHealth_Group",
    "PFE": "Pfizer",
    "ABBV": "AbbVie",
    "MRK": "Merck_&_Co.",
    "XOM": "ExxonMobil",
    "CVX": "Chevron_Corporation",
    "COP": "ConocoPhillips",
    "SLB": "Schlumberger",
    "CAT": "Caterpillar_Inc.",
    "GE": "GE_Aerospace",
    "HON": "Honeywell",
    "UPS": "United_Parcel_Service",
    "BA": "Boeing",
    "LIN": "Linde_plc",
    "APD": "Air_Products",
    "SHW": "Sherwin-Williams",
    "NEM": "Newmont",
    "NEE": "NextEra_Energy",
    "DUK": "Duke_Energy",
    "SO": "Southern_Company",
    "AMT": "American_Tower",
    "PLD": "Prologis",
    "O": "Realty_Income",
    "META": "Meta_Platforms",
    "GOOGL": "Alphabet_Inc.",
    "NFLX": "Netflix",
    "DIS": "The_Walt_Disney_Company",
    "TM": "Toyota",
    "SONY": "Sony",
    "ASML": "ASML_Holding",
    "SAP": "SAP",
    "NVO": "Novo_Nordisk",
    "UL": "Unilever",
}


def wikipedia_title_for(ticker: str) -> str | None:
    return WIKIPEDIA_TITLES.get(ticker.upper())
