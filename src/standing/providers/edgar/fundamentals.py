"""Map SEC EDGAR concepts + price into Standing market fundamentals."""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from standing.providers.edgar.client import (
    EdgarClient,
    latest_as_of,
    ttm_sum_quarters,
    yoy_growth,
)
from standing.providers.yahoo_ohlcv import fetch_yahoo_bars, yahoo_features_for

# Prefer first available tag.
REVENUE_TAGS = ("Revenues", "SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax")
EQUITY_TAGS = ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")
SHARES_TAGS = (
    "CommonStockSharesOutstanding",
    "EntityCommonStockSharesOutstanding",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
)
EPS_TAG = "EarningsPerShareDiluted"
NI_TAG = "NetIncomeLoss"
OPINC_TAG = "OperatingIncomeLoss"

# SEC company_tickers.json occasionally remaps mega-caps incorrectly.
CIK_OVERRIDES: dict[str, str] = {
    "XOM": "0000034088",  # Exxon Mobil Corp (not ExxonMobil Holdings Corp)
}


def _first_points(client: EdgarClient, cik: str, tags: tuple[str, ...], **kwargs):
    for tag in tags:
        taxonomy = kwargs.get("taxonomy", "us-gaap")
        pts = client.concept_points(cik, tag, taxonomy=taxonomy)
        if pts:
            return tag, pts
    return None, []


def extract_fundamentals(
    client: EdgarClient,
    *,
    ticker: str,
    as_of: date,
    sector: str,
    listing: str = "US",
) -> dict[str, Any] | None:
    cik = client.cik_for(ticker)
    if ticker.upper() in CIK_OVERRIDES:
        cik = CIK_OVERRIDES[ticker.upper()]
    if not cik:
        return None

    _, eps_pts = _first_points(client, cik, (EPS_TAG,))
    _, ni_pts = _first_points(client, cik, (NI_TAG,))
    _, op_pts = _first_points(client, cik, (OPINC_TAG,))
    rev_tag, rev_pts = _first_points(client, cik, REVENUE_TAGS)
    _, eq_pts = _first_points(client, cik, EQUITY_TAGS)
    # shares: prefer DEI outstanding, then US-GAAP outstanding / diluted WASO
    sh_tag, sh_pts = _first_points(
        client, cik, ("EntityCommonStockSharesOutstanding",), taxonomy="dei"
    )
    if not sh_pts:
        sh_tag, sh_pts = _first_points(client, cik, SHARES_TAGS)

    eps_ttm = ttm_sum_quarters(eps_pts, as_of)
    if eps_ttm is None:
        eps_pt = latest_as_of(eps_pts, as_of)
        eps_ttm = eps_pt.val if eps_pt else None

    ni_ttm = ttm_sum_quarters(ni_pts, as_of)
    if ni_ttm is None:
        ni_pt = latest_as_of(ni_pts, as_of)
        ni_ttm = ni_pt.val if ni_pt else None

    op_ttm = ttm_sum_quarters(op_pts, as_of)
    if op_ttm is None:
        op_pt = latest_as_of(op_pts, as_of)
        op_ttm = op_pt.val if op_pt else None

    rev_ttm = ttm_sum_quarters(rev_pts, as_of)
    if rev_ttm is None:
        rev_pt = latest_as_of(rev_pts, as_of)
        rev_ttm = rev_pt.val if rev_pt else None

    equity_pt = latest_as_of(eq_pts, as_of)
    shares_pt = latest_as_of(sh_pts, as_of, forms=None)

    ohlcv = yahoo_features_for(ticker, as_of=as_of) or {}
    price = ohlcv.get("last_price")
    # Prefer last close on/before as_of from bars if available
    bars = fetch_yahoo_bars(ticker)
    if bars is not None and not bars.empty:
        cut = bars[bars["date"] <= pd.Timestamp(as_of)]
        if not cut.empty:
            price = float(cut["close"].iloc[-1])

    shares = shares_pt.val if shares_pt else None
    equity = equity_pt.val if equity_pt else None

    market_cap = None
    if price is not None and shares is not None and shares > 0:
        market_cap = float(price * shares)

    pe_ttm = None
    if price is not None and eps_ttm not in (None, 0):
        pe_ttm = float(price / eps_ttm)

    pb = None
    if market_cap is not None and equity not in (None, 0):
        pb = float(market_cap / equity)

    roe = None
    if ni_ttm is not None and equity not in (None, 0):
        roe = float(ni_ttm / equity)

    operating_margin = None
    if op_ttm is not None and rev_ttm not in (None, 0):
        operating_margin = float(op_ttm / rev_ttm)

    revenue_growth_yoy = yoy_growth(rev_pts, as_of)

    # EV/EBITDA not derived in v1 without debt/cash concepts — leave None
    # (scoring winsorizes / ranks with NaN handling via pillar medians)

    return {
        "ticker": ticker.upper(),
        "sector": sector,
        "listing": listing,
        "market_cap": market_cap,
        "adv_20d": ohlcv.get("adv_20d"),
        "pe_ttm": pe_ttm,
        "pb": pb,
        "ev_ebitda": None,
        "roe": roe,
        "operating_margin": operating_margin,
        "revenue_growth_yoy": revenue_growth_yoy,
        "ret_1m": ohlcv.get("ret_1m"),
        "ret_3m": ohlcv.get("ret_3m"),
        "ret_6m": ohlcv.get("ret_6m"),
        "relative_volume": ohlcv.get("relative_volume"),
        "as_of": as_of.isoformat(),
        "_edgar": {
            "cik": cik,
            "revenue_tag": rev_tag,
            "shares_tag": sh_tag,
            "eps_ttm": eps_ttm,
            "price": price,
            "shares": shares,
            "equity": equity,
        },
    }
