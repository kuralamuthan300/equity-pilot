"""
yscreener_tools.py
==================
Equity screener tools for the equity-pilot MCP server.

Wraps ``yfinance.screen`` and ``yfinance.EquityQuery`` into self-contained
functions that each return a plain ``dict``.  Every function is registered
as an MCP tool via ``register_all_screener_mcp_tools``.

This module is **not** run directly — it is imported by ``mcp_server.py``
(the production entry point) or by ``screener_mcp_tools.py`` (the shim).
For stand-alone testing you can run it directly::

    uv run mcp_server/yscreener_tools.py

Sections
--------
1.  Helpers & shared utilities
2.  Predefined screener tools
3.  Sector / Industry tools
4.  Peer-group tools
5.  Valuation tools
6.  Momentum & technical tools
7.  Fundamental quality tools
8.  Dividend & income tools
9.  Short-interest tools
10. Regional / exchange tools
10b. India (NSE / BSE) specific tools
11. Custom / free-form query builder
11b. Company data tools (search / info / financials)
12. MCP auto-registration helper & entry-point
"""

from __future__ import annotations

import traceback
from typing import Any, Dict, List, Optional

import yfinance as yf
from yfinance import EquityQuery
from fastmcp import FastMCP

# ---------------------------------------------------------------------------
# 1.  Helpers
# ---------------------------------------------------------------------------

_PREDEFINED = list(yf.PREDEFINED_SCREENER_QUERIES.keys())

_VALID_REGIONS = [
    "ae","ar","at","au","be","br","ca","ch","cl","cn","co","cz","de","dk",
    "ee","eg","es","fi","fr","gb","gr","hk","hu","id","ie","il","in","is",
    "it","jp","kr","kw","lk","lt","lv","mx","my","nl","no","nz","pe","ph",
    "pk","pl","pt","qa","ro","ru","sa","se","sg","sr","th","tr","tw","us",
    "ve","vn","za",
]

_VALID_SECTORS = [
    "Basic Materials","Communication Services","Consumer Cyclical",
    "Consumer Defensive","Energy","Financial Services","Healthcare",
    "Industrials","Real Estate","Technology","Utilities",
]

_VALID_EXCHANGES_US = ["NMS", "NYQ", "ASE", "NGM", "NCM", "PCX"]

# India-specific constants
# yfinance region code for India is "in"
# NSI = NSE (National Stock Exchange), BSE = Bombay Stock Exchange
_INDIA_REGION = "in"
_INDIA_EXCHANGES = ["NSI", "BSE"]   # NSI = NSE in yfinance
_INDIA_EXCHANGE_NSE = "NSI"
_INDIA_EXCHANGE_BSE = "BSE"

# Market-cap tiers in USD (yfinance always uses USD for intradaymarketcap).
# Approximate INR equivalents at ~84 INR/USD shown for reference.
#   Large cap  : >= $2.4 B  (~₹20,000 Cr+)   — Nifty 100 universe
#   Mid cap    : $600 M – $2.4 B (~₹5,000–20,000 Cr) — Nifty Midcap 150
#   Small cap  : $120 M – $600 M  (~₹1,000–5,000 Cr)  — Nifty Smallcap 250
#   Micro cap  : < $120 M  (~₹1,000 Cr)
_INDIA_LARGECAP_MIN  = 2_400_000_000   # ~₹20,000 Cr
_INDIA_MIDCAP_MIN    =   600_000_000   # ~₹5,000  Cr
_INDIA_MIDCAP_MAX    = 2_400_000_000
_INDIA_SMALLCAP_MIN  =   120_000_000   # ~₹1,000  Cr
_INDIA_SMALLCAP_MAX  =   600_000_000


def _run(query, sort_field: str, sort_asc: bool, size: int, offset: int) -> Dict[str, Any]:
    """Execute yf.screen and normalise the result into a plain dict."""
    try:
        raw = yf.screen(
            query,
            sortField=sort_field,
            sortAsc=sort_asc,
            size=size,
            offset=offset,
        )
        quotes = raw.get("quotes", [])
        return {
            "total": raw.get("total", len(quotes)),
            "count": len(quotes),
            "quotes": quotes,
        }
    except Exception as exc:
        return {"error": str(exc), "traceback": traceback.format_exc()}


def _and(*conditions) -> EquityQuery:
    return EquityQuery("and", list(conditions))


def _eq(field: str, value: str) -> EquityQuery:
    return EquityQuery("eq", [field, value])


def _isin(field: str, *values) -> EquityQuery:
    return EquityQuery("is-in", [field, *values])


def _gt(field: str, value: float) -> EquityQuery:
    return EquityQuery("gt", [field, value])


def _gte(field: str, value: float) -> EquityQuery:
    return EquityQuery("gte", [field, value])


def _lt(field: str, value: float) -> EquityQuery:
    return EquityQuery("lt", [field, value])


def _lte(field: str, value: float) -> EquityQuery:
    return EquityQuery("lte", [field, value])


def _btwn(field: str, low: float, high: float) -> EquityQuery:
    return EquityQuery("btwn", [field, low, high])


# ---------------------------------------------------------------------------
# 2.  Predefined screener tools
# ---------------------------------------------------------------------------

def run_predefined_screener(
    name: str,
    size: int = 25,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Run one of Yahoo Finance's built-in predefined screeners.

    Parameters
    ----------
    name : str
        One of the predefined screener keys.  Call list_predefined_screeners()
        to see all available names.
    size : int
        Number of results (1-250).  Default 25.
    offset : int
        Pagination offset.  Default 0.

    Returns
    -------
    dict  { total, count, quotes }

    MCP tool name : run_predefined_screener
    """
    if name not in _PREDEFINED:
        return {
            "error": f"Unknown screener '{name}'.",
            "available": _PREDEFINED,
        }
    try:
        raw = yf.screen(name, count=size, offset=offset)
        quotes = raw.get("quotes", [])
        return {"total": raw.get("total", len(quotes)), "count": len(quotes), "quotes": quotes}
    except Exception as exc:
        return {"error": str(exc)}


def list_predefined_screeners() -> Dict[str, Any]:
    """
    Return the full list of predefined Yahoo Finance screener names.

    MCP tool name : list_predefined_screeners
    """
    return {"screeners": _PREDEFINED, "count": len(_PREDEFINED)}


# ---------------------------------------------------------------------------
# 3.  Sector / Industry tools
# ---------------------------------------------------------------------------

def screen_by_sector(
    sector: str,
    region: str = "us",
    min_market_cap: Optional[float] = None,
    sort_field: str = "percentchange",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find stocks in a specific sector within a region.

    Parameters
    ----------
    sector : str
        e.g. "Technology", "Healthcare", "Energy".
    region : str
        Two-letter region code, default "us".
    min_market_cap : float | None
        Minimum intraday market cap in USD (e.g. 2_000_000_000 for 2B).
    sort_field : str
        Field to sort by.  Default "percentchange".
    sort_asc : bool
        Ascending sort?  Default False.
    size : int
        Number of results.  Default 50.

    MCP tool name : screen_by_sector
    """
    conditions = [_eq("sector", sector), _eq("region", region)]
    if min_market_cap is not None:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_by_industry(
    industry: str,
    region: str = "us",
    min_market_cap: Optional[float] = None,
    sort_field: str = "percentchange",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find stocks in a specific industry within a region.

    Parameters
    ----------
    industry : str
        e.g. "Semiconductors", "Biotechnology", "Software—Application".
    region : str
        Two-letter region code, default "us".
    min_market_cap : float | None
        Minimum intraday market cap in USD.
    sort_field : str
        Sort field.  Default "percentchange".

    MCP tool name : screen_by_industry
    """
    conditions = [_eq("industry", industry), _eq("region", region)]
    if min_market_cap is not None:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_sector_by_market_cap_range(
    sector: str,
    min_cap: float,
    max_cap: float,
    region: str = "us",
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Stocks in a sector filtered to a market-cap band (e.g. mid-caps only).

    Parameters
    ----------
    sector : str
        Sector name.
    min_cap : float
        Minimum market cap in USD.
    max_cap : float
        Maximum market cap in USD.

    MCP tool name : screen_sector_by_market_cap_range
    """
    q = _and(
        _eq("sector", sector),
        _eq("region", region),
        _btwn("intradaymarketcap", min_cap, max_cap),
    )
    return _run(q, sort_field, sort_asc, size, offset)


# ---------------------------------------------------------------------------
# 4.  Peer-group tools
# ---------------------------------------------------------------------------

def screen_by_peer_group(
    peer_group: str,
    region: str = "us",
    sort_field: str = "percentchange",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find stocks / funds belonging to a Yahoo Finance peer group.

    Peer groups are very granular (e.g. "Semiconductors", "Biotechnology",
    "US Fund Large Growth").  Useful for direct peer comparison.

    Parameters
    ----------
    peer_group : str
        Exact peer group name as listed in EquityQuery.valid_values["peer_group"].
    region : str
        Two-letter region code.  Default "us".

    MCP tool name : screen_by_peer_group
    """
    conditions: List[EquityQuery] = [_eq("peer_group", peer_group)]
    if region:
        conditions.append(_eq("region", region))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def find_peers_in_sector_and_industry(
    sector: str,
    industry: str,
    region: str = "us",
    min_market_cap: Optional[float] = None,
    max_market_cap: Optional[float] = None,
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
    size: int = 30,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find direct peers by matching both sector AND industry, optionally
    restricting to a similar market-cap band.

    This is the primary tool for finding comparable stocks to a given ticker
    when you already know its sector and industry.

    Parameters
    ----------
    sector : str
        e.g. "Technology"
    industry : str
        e.g. "Semiconductors"
    region : str
        Default "us".
    min_market_cap : float | None
        Lower bound on market cap (USD).
    max_market_cap : float | None
        Upper bound on market cap (USD).

    MCP tool name : find_peers_in_sector_and_industry
    """
    conditions: List[EquityQuery] = [
        _eq("sector", sector),
        _eq("industry", industry),
        _eq("region", region),
    ]
    if min_market_cap is not None:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    if max_market_cap is not None:
        conditions.append(_lte("intradaymarketcap", max_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


# ---------------------------------------------------------------------------
# 5.  Valuation tools
# ---------------------------------------------------------------------------

def screen_undervalued_stocks(
    region: str = "us",
    max_pe: float = 20,
    max_peg: float = 1.0,
    min_eps_growth: float = 10,
    exchanges: Optional[List[str]] = None,
    sort_field: str = "eodvolume",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Screen for undervalued stocks: low P/E, low PEG, positive EPS growth.

    Parameters
    ----------
    region : str
        Default "us".
    max_pe : float
        Maximum trailing P/E ratio.  Default 20.
    max_peg : float
        Maximum 5-year PEG ratio.  Default 1.0.
    min_eps_growth : float
        Minimum LTM EPS growth (%).  Default 10.
    exchanges : list[str] | None
        Restrict to exchange(s), e.g. ["NMS","NYQ"].  Defaults to NMS+NYQ.

    MCP tool name : screen_undervalued_stocks
    """
    exch = exchanges or _VALID_EXCHANGES_US[:2]
    q = _and(
        _btwn("peratio.lasttwelvemonths", 0, max_pe),
        _lt("pegratio_5y", max_peg),
        _gte("epsgrowth.lasttwelvemonths", min_eps_growth),
        _isin("exchange", *exch),
    )
    return _run(q, sort_field, sort_asc, size, offset)


def screen_by_pe_range(
    min_pe: float,
    max_pe: float,
    sector: Optional[str] = None,
    region: str = "us",
    min_market_cap: Optional[float] = None,
    sort_field: str = "peratio.lasttwelvemonths",
    sort_asc: bool = True,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find stocks whose trailing P/E falls within [min_pe, max_pe].

    Useful for checking whether a stock is cheap/expensive vs sector peers.

    Parameters
    ----------
    min_pe : float
        Lower P/E bound (use 0 to start from profitable companies).
    max_pe : float
        Upper P/E bound.
    sector : str | None
        Optional sector filter.
    region : str
        Default "us".

    MCP tool name : screen_by_pe_range
    """
    conditions: List[EquityQuery] = [
        _btwn("peratio.lasttwelvemonths", min_pe, max_pe),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_by_price_to_book(
    max_pb: float = 3.0,
    min_pb: float = 0.0,
    sector: Optional[str] = None,
    region: str = "us",
    sort_field: str = "pricebookratio.quarterly",
    sort_asc: bool = True,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Filter stocks by quarterly price-to-book ratio.

    Parameters
    ----------
    max_pb : float
        Maximum P/B ratio.  Default 3.0.
    min_pb : float
        Minimum P/B ratio.  Default 0.0.

    MCP tool name : screen_by_price_to_book
    """
    conditions: List[EquityQuery] = [
        _btwn("pricebookratio.quarterly", min_pb, max_pb),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_by_ev_ebitda(
    max_ev_ebitda: float = 15.0,
    sector: Optional[str] = None,
    region: str = "us",
    sort_field: str = "lastclosetevebitda.lasttwelvemonths",
    sort_asc: bool = True,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find stocks trading below a given EV/EBITDA multiple.

    Parameters
    ----------
    max_ev_ebitda : float
        Maximum EV/EBITDA.  Default 15.

    MCP tool name : screen_by_ev_ebitda
    """
    conditions: List[EquityQuery] = [
        _lt("lastclosetevebitda.lasttwelvemonths", max_ev_ebitda),
        _gt("lastclosetevebitda.lasttwelvemonths", 0),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


# ---------------------------------------------------------------------------
# 6.  Momentum & technical tools
# ---------------------------------------------------------------------------

def screen_day_gainers(
    region: str = "us",
    min_change_pct: float = 3.0,
    min_market_cap: float = 2_000_000_000,
    min_price: float = 5.0,
    min_volume: float = 15_000,
    sort_field: str = "percentchange",
    sort_asc: bool = False,
    size: int = 25,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Top intraday gainers with liquidity filters.

    Parameters
    ----------
    region : str
        Default "us".
    min_change_pct : float
        Minimum % change today.  Default 3.0.
    min_market_cap : float
        Minimum market cap in USD.  Default 2B.
    min_price : float
        Minimum stock price.  Default 5.0.
    min_volume : int
        Minimum day volume.  Default 15 000.

    MCP tool name : screen_day_gainers
    """
    q = _and(
        _gt("percentchange", min_change_pct),
        _eq("region", region),
        _gte("intradaymarketcap", min_market_cap),
        _gte("intradayprice", min_price),
        _gt("dayvolume", min_volume),
    )
    return _run(q, sort_field, sort_asc, size, offset)


def screen_day_losers(
    region: str = "us",
    max_change_pct: float = -2.5,
    min_market_cap: float = 2_000_000_000,
    min_price: float = 5.0,
    min_volume: float = 20_000,
    sort_field: str = "percentchange",
    sort_asc: bool = True,
    size: int = 25,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Top intraday losers with liquidity filters.

    Parameters
    ----------
    max_change_pct : float
        Maximum (most negative) % change today.  Default -2.5.

    MCP tool name : screen_day_losers
    """
    q = _and(
        _lt("percentchange", max_change_pct),
        _eq("region", region),
        _gte("intradaymarketcap", min_market_cap),
        _gte("intradayprice", min_price),
        _gt("dayvolume", min_volume),
    )
    return _run(q, sort_field, sort_asc, size, offset)


def screen_near_52w_high(
    region: str = "us",
    threshold_pct: float = 5.0,
    min_market_cap: float = 1_000_000_000,
    sector: Optional[str] = None,
    sort_field: str = "lastclose52weekhigh.lasttwelvemonths",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find stocks trading within threshold_pct% of their 52-week high.

    A negative lastclose52weekhigh means the stock is BELOW the high by
    that percentage; a value close to 0 means it is near the high.

    Parameters
    ----------
    threshold_pct : float
        How close to 52-week high in %.  Default 5 (within 5% of high).
    min_market_cap : float
        Minimum market cap.  Default 1B.

    MCP tool name : screen_near_52w_high
    """
    conditions: List[EquityQuery] = [
        _gte("lastclose52weekhigh.lasttwelvemonths", -threshold_pct),
        _eq("region", region),
        _gte("intradaymarketcap", min_market_cap),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_near_52w_low(
    region: str = "us",
    threshold_pct: float = 10.0,
    min_market_cap: float = 1_000_000_000,
    sector: Optional[str] = None,
    sort_field: str = "lastclose52weeklow.lasttwelvemonths",
    sort_asc: bool = True,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find stocks that have fallen to within threshold_pct% above their
    52-week low — potential buy-the-dip candidates.

    Parameters
    ----------
    threshold_pct : float
        Max % above 52-week low.  Default 10.

    MCP tool name : screen_near_52w_low
    """
    conditions: List[EquityQuery] = [
        _lte("lastclose52weeklow.lasttwelvemonths", threshold_pct),
        _gt("lastclose52weeklow.lasttwelvemonths", 0),
        _eq("region", region),
        _gte("intradaymarketcap", min_market_cap),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_high_volume_movers(
    region: str = "us",
    min_volume: float = 5_000_000,
    min_market_cap: float = 2_000_000_000,
    sort_field: str = "dayvolume",
    sort_asc: bool = False,
    size: int = 25,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Most-active stocks by today's volume.

    Parameters
    ----------
    min_volume : float
        Minimum day volume.  Default 5M.
    min_market_cap : float
        Minimum market cap.  Default 2B.

    MCP tool name : screen_high_volume_movers
    """
    q = _and(
        _eq("region", region),
        _gte("intradaymarketcap", min_market_cap),
        _gt("dayvolume", min_volume),
    )
    return _run(q, sort_field, sort_asc, size, offset)


def screen_by_beta(
    min_beta: float,
    max_beta: float,
    region: str = "us",
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "beta",
    sort_asc: bool = True,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Filter stocks by beta range.  Useful for volatility-adjusted
    peer comparisons.

    Parameters
    ----------
    min_beta : float
        Lower beta bound (e.g. 0.8).
    max_beta : float
        Upper beta bound (e.g. 1.5).

    MCP tool name : screen_by_beta
    """
    conditions: List[EquityQuery] = [
        _btwn("beta", min_beta, max_beta),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


# ---------------------------------------------------------------------------
# 7.  Fundamental quality tools
# ---------------------------------------------------------------------------

def screen_growth_stocks(
    region: str = "us",
    min_revenue_growth: float = 20.0,
    min_eps_growth: float = 20.0,
    sector: Optional[str] = None,
    exchanges: Optional[List[str]] = None,
    sort_field: str = "epsgrowth.lasttwelvemonths",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    High-growth stocks: strong quarterly revenue growth + LTM EPS growth.

    Parameters
    ----------
    min_revenue_growth : float
        Min quarterly revenue growth (%).  Default 20.
    min_eps_growth : float
        Min LTM EPS growth (%).  Default 20.

    MCP tool name : screen_growth_stocks
    """
    exch = exchanges or _VALID_EXCHANGES_US[:2]
    conditions: List[EquityQuery] = [
        _gte("quarterlyrevenuegrowth.quarterly", min_revenue_growth),
        _gte("epsgrowth.lasttwelvemonths", min_eps_growth),
        _isin("exchange", *exch),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_profitable_stocks(
    region: str = "us",
    min_roe: float = 15.0,
    min_net_margin: float = 10.0,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "returnonequity.lasttwelvemonths",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    High-quality stocks: strong ROE and net margin.

    Parameters
    ----------
    min_roe : float
        Minimum Return on Equity (%).  Default 15.
    min_net_margin : float
        Minimum net income margin (%).  Default 10.

    MCP tool name : screen_profitable_stocks
    """
    conditions: List[EquityQuery] = [
        _gte("returnonequity.lasttwelvemonths", min_roe),
        _gte("netincomemargin.lasttwelvemonths", min_net_margin),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_low_leverage_stocks(
    region: str = "us",
    max_debt_equity: float = 1.0,
    max_net_debt_ebitda: float = 3.0,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "totaldebtequity.lasttwelvemonths",
    sort_asc: bool = True,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Financially conservative stocks: low debt ratios.

    Parameters
    ----------
    max_debt_equity : float
        Maximum total debt / equity.  Default 1.0 (= 100%).
    max_net_debt_ebitda : float
        Maximum net debt / EBITDA.  Default 3.0.

    MCP tool name : screen_low_leverage_stocks
    """
    conditions: List[EquityQuery] = [
        _lte("totaldebtequity.lasttwelvemonths", max_debt_equity),
        _lte("netdebtebitda.lasttwelvemonths", max_net_debt_ebitda),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_strong_cashflow_stocks(
    region: str = "us",
    min_fcf: float = 0,
    min_cfo_growth: float = 10.0,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "leveredfreecashflow.lasttwelvemonths",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find companies with positive levered free cash flow and growing operating
    cash flow.

    Parameters
    ----------
    min_fcf : float
        Minimum levered FCF in USD.  Default 0 (positive only).
    min_cfo_growth : float
        Minimum YoY CFO growth (%).  Default 10.

    MCP tool name : screen_strong_cashflow_stocks
    """
    conditions: List[EquityQuery] = [
        _gt("leveredfreecashflow.lasttwelvemonths", min_fcf),
        _gte("cashfromoperations1yrgrowth.lasttwelvemonths", min_cfo_growth),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_by_ebitda_margin(
    min_ebitda_margin: float = 20.0,
    sector: Optional[str] = None,
    region: str = "us",
    min_market_cap: Optional[float] = None,
    sort_field: str = "ebitdamargin.lasttwelvemonths",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find stocks with high EBITDA margins — often moat businesses.

    Parameters
    ----------
    min_ebitda_margin : float
        Minimum EBITDA margin (%).  Default 20.

    MCP tool name : screen_by_ebitda_margin
    """
    conditions: List[EquityQuery] = [
        _gte("ebitdamargin.lasttwelvemonths", min_ebitda_margin),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


# ---------------------------------------------------------------------------
# 8.  Dividend & income tools
# ---------------------------------------------------------------------------

def screen_dividend_stocks(
    region: str = "us",
    min_yield: float = 2.0,
    min_consecutive_growth_years: int = 5,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "forward_dividend_yield",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find dividend-paying stocks with a minimum yield and consecutive
    years of dividend growth (dividend growers / aristocrats).

    Parameters
    ----------
    min_yield : float
        Minimum forward dividend yield (%).  Default 2.0.
    min_consecutive_growth_years : int
        Minimum years of consecutive dividend growth.  Default 5.

    MCP tool name : screen_dividend_stocks
    """
    conditions: List[EquityQuery] = [
        _gte("forward_dividend_yield", min_yield),
        _gte("consecutive_years_of_dividend_growth_count", min_consecutive_growth_years),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_high_yield_stocks(
    region: str = "us",
    min_yield: float = 4.0,
    max_yield: float = 15.0,
    min_market_cap: float = 500_000_000,
    sector: Optional[str] = None,
    sort_field: str = "forward_dividend_yield",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    High-yield equity income stocks.  Max yield cap avoids dividend traps.

    Parameters
    ----------
    min_yield : float
        Minimum forward dividend yield (%).  Default 4.0.
    max_yield : float
        Maximum forward dividend yield (%).  Default 15 (trap filter).

    MCP tool name : screen_high_yield_stocks
    """
    conditions: List[EquityQuery] = [
        _btwn("forward_dividend_yield", min_yield, max_yield),
        _gte("intradaymarketcap", min_market_cap),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


# ---------------------------------------------------------------------------
# 9.  Short-interest tools
# ---------------------------------------------------------------------------

def screen_high_short_interest(
    region: str = "us",
    min_short_pct_float: float = 10.0,
    min_avg_volume: float = 200_000,
    min_price: float = 1.0,
    sort_field: str = "short_percentage_of_float.value",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Stocks with high short interest (potential short-squeeze candidates or
    market conviction on the bearish side).

    Parameters
    ----------
    min_short_pct_float : float
        Minimum short interest as % of float.  Default 10.
    min_avg_volume : float
        Minimum 3-month avg daily volume.  Default 200k.
    min_price : float
        Minimum share price.  Default 1.0.

    MCP tool name : screen_high_short_interest
    """
    q = _and(
        _eq("region", region),
        _gt("intradayprice", min_price),
        _gt("avgdailyvol3m", min_avg_volume),
        _gte("short_percentage_of_float.value", min_short_pct_float),
    )
    return _run(q, sort_field, sort_asc, size, offset)


def screen_low_short_interest(
    region: str = "us",
    max_short_pct: float = 3.0,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Stocks with very low short interest — institutions not betting against them.

    Parameters
    ----------
    max_short_pct : float
        Maximum short % of shares outstanding.  Default 3.

    MCP tool name : screen_low_short_interest
    """
    conditions: List[EquityQuery] = [
        _lte("short_percentage_of_shares_outstanding.value", max_short_pct),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


# ---------------------------------------------------------------------------
# 10. Regional / exchange tools
# ---------------------------------------------------------------------------

def screen_by_region_and_exchange(
    region: str,
    exchanges: List[str],
    min_market_cap: Optional[float] = None,
    sector: Optional[str] = None,
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Screen stocks on specific exchanges within a region.

    Parameters
    ----------
    region : str
        Two-letter region code, e.g. "in" for India, "gb" for UK.
    exchanges : list[str]
        Exchange codes valid for that region,
        e.g. ["BSE","NSI"] for India, ["LSE"] for UK.
    sector : str | None
        Optional sector filter.

    MCP tool name : screen_by_region_and_exchange
    """
    conditions: List[EquityQuery] = [
        _eq("region", region),
        _isin("exchange", *exchanges),
    ]
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_large_caps(
    region: str = "us",
    min_market_cap: float = 10_000_000_000,
    sector: Optional[str] = None,
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Filter for large-cap stocks (default >= $10B).

    MCP tool name : screen_large_caps
    """
    conditions: List[EquityQuery] = [
        _gte("intradaymarketcap", min_market_cap),
        _eq("region", region),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_small_caps(
    region: str = "us",
    max_market_cap: float = 2_000_000_000,
    min_market_cap: float = 300_000_000,
    sector: Optional[str] = None,
    exchanges: Optional[List[str]] = None,
    sort_field: str = "eodvolume",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Filter for small-cap stocks ($300M–$2B market cap by default).

    MCP tool name : screen_small_caps
    """
    exch = exchanges or _VALID_EXCHANGES_US[:2]
    conditions: List[EquityQuery] = [
        _btwn("intradaymarketcap", min_market_cap, max_market_cap),
        _isin("exchange", *exch),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


# ---------------------------------------------------------------------------
# 10b. India (NSE / BSE) specific tools
# ---------------------------------------------------------------------------
# All market-cap thresholds are in USD.  See the _INDIA_* constants above
# for the approximate INR / Crore equivalents.
# ---------------------------------------------------------------------------

def screen_india_stocks(
    exchange: str = "NSI",
    min_market_cap: Optional[float] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    General-purpose screener for Indian equities.

    Parameters
    ----------
    exchange : str
        "NSI" for NSE (default) or "BSE" for Bombay Stock Exchange.
        Pass "BOTH" to include both exchanges.
    min_market_cap : float | None
        Minimum market cap in USD.  e.g. 2_400_000_000 for large-caps.
    sector : str | None
        Optional sector filter, e.g. "Technology", "Financial Services".
    industry : str | None
        Optional industry filter, e.g. "Software—Application".
    sort_field : str
        Default "intradaymarketcap".
    size : int
        Number of results (max 250).  Default 50.

    MCP tool name : screen_india_stocks
    """
    if exchange.upper() == "BOTH":
        conditions: List[EquityQuery] = [_isin("exchange", *_INDIA_EXCHANGES)]
    else:
        exch = exchange.upper()
        if exch not in _INDIA_EXCHANGES:
            return {"error": f"Invalid exchange '{exchange}'. Use 'NSI', 'BSE', or 'BOTH'."}
        conditions = [_eq("exchange", exch)]

    conditions.append(_eq("region", _INDIA_REGION))
    if min_market_cap is not None:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    if sector:
        conditions.append(_eq("sector", sector))
    if industry:
        conditions.append(_eq("industry", industry))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_india_large_caps(
    exchange: str = "NSI",
    sector: Optional[str] = None,
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
    size: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Indian large-cap stocks (>= ~₹20,000 Cr / $2.4B) — Nifty 100 universe.

    Parameters
    ----------
    exchange : str
        "NSI" (NSE, default), "BSE", or "BOTH".
    sector : str | None
        Optional sector filter.
    size : int
        Default 100 — covers the full Nifty 100 in one call.

    MCP tool name : screen_india_large_caps
    """
    return screen_india_stocks(
        exchange=exchange,
        min_market_cap=_INDIA_LARGECAP_MIN,
        sector=sector,
        sort_field=sort_field,
        sort_asc=sort_asc,
        size=size,
        offset=offset,
    )


def screen_india_mid_caps(
    exchange: str = "NSI",
    sector: Optional[str] = None,
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
    size: int = 150,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Indian mid-cap stocks (~₹5,000–₹20,000 Cr / $600M–$2.4B)
    — Nifty Midcap 150 universe.

    Parameters
    ----------
    exchange : str
        "NSI" (NSE, default), "BSE", or "BOTH".
    sector : str | None
        Optional sector filter.
    size : int
        Default 150 — covers the full Nifty Midcap 150 in one call.

    MCP tool name : screen_india_mid_caps
    """
    if exchange.upper() == "BOTH":
        exch_conditions = [_isin("exchange", *_INDIA_EXCHANGES)]
    else:
        exch_conditions = [_eq("exchange", exchange.upper())]

    conditions: List[EquityQuery] = [
        *exch_conditions,
        _eq("region", _INDIA_REGION),
        _btwn("intradaymarketcap", _INDIA_MIDCAP_MIN, _INDIA_MIDCAP_MAX),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_india_small_caps(
    exchange: str = "NSI",
    sector: Optional[str] = None,
    sort_field: str = "eodvolume",
    sort_asc: bool = False,
    size: int = 100,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Indian small-cap stocks (~₹1,000–₹5,000 Cr / $120M–$600M)
    — Nifty Smallcap 250 universe.

    Parameters
    ----------
    exchange : str
        "NSI" (NSE, default), "BSE", or "BOTH".
    sector : str | None
        Optional sector filter.

    MCP tool name : screen_india_small_caps
    """
    if exchange.upper() == "BOTH":
        exch_conditions = [_isin("exchange", *_INDIA_EXCHANGES)]
    else:
        exch_conditions = [_eq("exchange", exchange.upper())]

    conditions: List[EquityQuery] = [
        *exch_conditions,
        _eq("region", _INDIA_REGION),
        _btwn("intradaymarketcap", _INDIA_SMALLCAP_MIN, _INDIA_SMALLCAP_MAX),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_india_sector(
    sector: str,
    exchange: str = "NSI",
    min_market_cap: Optional[float] = None,
    sort_field: str = "percentchange",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    All Indian stocks in a given sector on NSE or BSE.

    Parameters
    ----------
    sector : str
        e.g. "Technology", "Financial Services", "Healthcare", "Energy".
    exchange : str
        "NSI" (NSE, default), "BSE", or "BOTH".
    min_market_cap : float | None
        Optional minimum market cap in USD.

    MCP tool name : screen_india_sector
    """
    return screen_india_stocks(
        exchange=exchange,
        min_market_cap=min_market_cap,
        sector=sector,
        sort_field=sort_field,
        sort_asc=sort_asc,
        size=size,
        offset=offset,
    )


def find_india_peers(
    sector: str,
    industry: str,
    exchange: str = "BOTH",
    min_market_cap: Optional[float] = None,
    max_market_cap: Optional[float] = None,
    sort_field: str = "intradaymarketcap",
    sort_asc: bool = False,
    size: int = 30,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Find peer companies for an Indian stock by matching sector + industry,
    optionally restricting to a market-cap band (same tier = true peers).

    This is the primary peer-discovery tool for Indian equities.

    Parameters
    ----------
    sector : str
        e.g. "Technology"
    industry : str
        e.g. "Software—Application", "IT Services", "Pharmaceuticals"
    exchange : str
        "NSI", "BSE", or "BOTH" (default — maximises peer universe).
    min_market_cap : float | None
        Lower bound in USD (e.g. 600_000_000 for mid-cap+).
    max_market_cap : float | None
        Upper bound in USD.

    MCP tool name : find_india_peers
    """
    if exchange.upper() == "BOTH":
        exch_conditions = [_isin("exchange", *_INDIA_EXCHANGES)]
    else:
        exch_conditions = [_eq("exchange", exchange.upper())]

    conditions: List[EquityQuery] = [
        *exch_conditions,
        _eq("region", _INDIA_REGION),
        _eq("sector", sector),
        _eq("industry", industry),
    ]
    if min_market_cap is not None:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    if max_market_cap is not None:
        conditions.append(_lte("intradaymarketcap", max_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_india_growth_stocks(
    exchange: str = "NSI",
    min_revenue_growth: float = 20.0,
    min_eps_growth: float = 20.0,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "epsgrowth.lasttwelvemonths",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    High-growth Indian stocks: strong quarterly revenue + LTM EPS growth.

    Parameters
    ----------
    exchange : str
        "NSI" (default), "BSE", or "BOTH".
    min_revenue_growth : float
        Minimum quarterly revenue growth (%).  Default 20.
    min_eps_growth : float
        Minimum LTM EPS growth (%).  Default 20.
    sector : str | None
        Optional sector filter.
    min_market_cap : float | None
        Optional minimum market cap in USD.

    MCP tool name : screen_india_growth_stocks
    """
    if exchange.upper() == "BOTH":
        exch_conditions = [_isin("exchange", *_INDIA_EXCHANGES)]
    else:
        exch_conditions = [_eq("exchange", exchange.upper())]

    conditions: List[EquityQuery] = [
        *exch_conditions,
        _eq("region", _INDIA_REGION),
        _gte("quarterlyrevenuegrowth.quarterly", min_revenue_growth),
        _gte("epsgrowth.lasttwelvemonths", min_eps_growth),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_india_undervalued(
    exchange: str = "NSI",
    max_pe: float = 25.0,
    max_peg: float = 1.5,
    min_eps_growth: float = 10.0,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "peratio.lasttwelvemonths",
    sort_asc: bool = True,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Undervalued Indian stocks: low P/E + low PEG + positive EPS growth.

    Indian markets typically trade at higher P/E multiples than the US,
    so defaults (max_pe=25, max_peg=1.5) are calibrated accordingly.

    Parameters
    ----------
    exchange : str
        "NSI" (default), "BSE", or "BOTH".
    max_pe : float
        Maximum trailing P/E.  Default 25.
    max_peg : float
        Maximum 5-year PEG ratio.  Default 1.5.
    min_eps_growth : float
        Minimum LTM EPS growth (%).  Default 10.
    sector : str | None
        Optional sector filter.

    MCP tool name : screen_india_undervalued
    """
    if exchange.upper() == "BOTH":
        exch_conditions = [_isin("exchange", *_INDIA_EXCHANGES)]
    else:
        exch_conditions = [_eq("exchange", exchange.upper())]

    conditions: List[EquityQuery] = [
        *exch_conditions,
        _eq("region", _INDIA_REGION),
        _btwn("peratio.lasttwelvemonths", 0, max_pe),
        _lt("pegratio_5y", max_peg),
        _gte("epsgrowth.lasttwelvemonths", min_eps_growth),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_india_dividend_stocks(
    exchange: str = "NSI",
    min_yield: float = 2.0,
    min_consecutive_growth_years: int = 3,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "forward_dividend_yield",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Dividend-paying Indian stocks with a minimum yield and consistent
    dividend growth.

    Note: Indian dividend culture differs from the US — the default
    min_consecutive_growth_years is lower (3 vs 5) to find relevant results.

    Parameters
    ----------
    exchange : str
        "NSI" (default), "BSE", or "BOTH".
    min_yield : float
        Minimum forward dividend yield (%).  Default 2.0.
    min_consecutive_growth_years : int
        Minimum consecutive years of dividend growth.  Default 3.
    sector : str | None
        Optional sector filter (e.g. "Financial Services" for bank dividends).

    MCP tool name : screen_india_dividend_stocks
    """
    if exchange.upper() == "BOTH":
        exch_conditions = [_isin("exchange", *_INDIA_EXCHANGES)]
    else:
        exch_conditions = [_eq("exchange", exchange.upper())]

    conditions: List[EquityQuery] = [
        *exch_conditions,
        _eq("region", _INDIA_REGION),
        _gte("forward_dividend_yield", min_yield),
        _gte("consecutive_years_of_dividend_growth_count", min_consecutive_growth_years),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_india_high_roe(
    exchange: str = "NSI",
    min_roe: float = 20.0,
    min_net_margin: float = 10.0,
    sector: Optional[str] = None,
    min_market_cap: Optional[float] = None,
    sort_field: str = "returnonequity.lasttwelvemonths",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    High-quality Indian compounders: strong ROE + net margin.

    Particularly useful for identifying quality stocks in the Indian market
    where a ROE > 20% is considered excellent (e.g. HDFC Bank, TCS, Infosys).

    Parameters
    ----------
    exchange : str
        "NSI" (default), "BSE", or "BOTH".
    min_roe : float
        Minimum Return on Equity (%).  Default 20.
    min_net_margin : float
        Minimum net income margin (%).  Default 10.
    sector : str | None
        Optional sector filter.

    MCP tool name : screen_india_high_roe
    """
    if exchange.upper() == "BOTH":
        exch_conditions = [_isin("exchange", *_INDIA_EXCHANGES)]
    else:
        exch_conditions = [_eq("exchange", exchange.upper())]

    conditions: List[EquityQuery] = [
        *exch_conditions,
        _eq("region", _INDIA_REGION),
        _gte("returnonequity.lasttwelvemonths", min_roe),
        _gte("netincomemargin.lasttwelvemonths", min_net_margin),
    ]
    if sector:
        conditions.append(_eq("sector", sector))
    if min_market_cap:
        conditions.append(_gte("intradaymarketcap", min_market_cap))
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


def screen_india_day_movers(
    direction: str = "gainers",
    min_change_pct: float = 2.0,
    exchange: str = "NSI",
    min_market_cap: float = 120_000_000,
    sort_field: str = "percentchange",
    size: int = 25,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Top intraday gainers or losers on NSE / BSE.

    Parameters
    ----------
    direction : str
        "gainers" (default) or "losers".
    min_change_pct : float
        Minimum absolute % move today.  Default 2.0.
    exchange : str
        "NSI" (default), "BSE", or "BOTH".
    min_market_cap : float
        Minimum market cap in USD.  Default $120M (~₹1,000 Cr).

    MCP tool name : screen_india_day_movers
    """
    if exchange.upper() == "BOTH":
        exch_conditions = [_isin("exchange", *_INDIA_EXCHANGES)]
    else:
        exch_conditions = [_eq("exchange", exchange.upper())]

    if direction.lower() == "losers":
        change_condition = _lt("percentchange", -abs(min_change_pct))
        sort_asc = True
    else:
        change_condition = _gt("percentchange", abs(min_change_pct))
        sort_asc = False

    conditions: List[EquityQuery] = [
        *exch_conditions,
        _eq("region", _INDIA_REGION),
        change_condition,
        _gte("intradaymarketcap", min_market_cap),
    ]
    return _run(_and(*conditions), sort_field, sort_asc, size, offset)


# ---------------------------------------------------------------------------
# 11. Custom / free-form query builder
# ---------------------------------------------------------------------------

# _OP_MAP maps operator name strings to their EquityQuery builder callables.
# Used by build_and_run_custom_query to convert free-form filter dicts
# into EquityQuery objects without a long if/elif chain.
_OP_MAP = {
    "eq":  _eq,
    "gt":  lambda f, v: EquityQuery("gt",  [f, v]),
    "lt":  lambda f, v: EquityQuery("lt",  [f, v]),
    "gte": lambda f, v: EquityQuery("gte", [f, v]),
    "lte": lambda f, v: EquityQuery("lte", [f, v]),
}

def build_and_run_custom_query(
    filters: List[Dict[str, Any]],
    logic: str = "and",
    sort_field: str = "percentchange",
    sort_asc: bool = False,
    size: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """
    Build and execute a fully custom EquityQuery from a list of filter dicts.

    This is the most flexible tool — the agent can compose any combination
    of EquityQuery operators without hard-coded helpers.

    Parameters
    ----------
    filters : list[dict]
        Each filter dict must have:
          - "op"    : str  — one of "eq","is-in","btwn","gt","lt","gte","lte"
          - "field" : str  — a valid EquityQuery field name
          - "value" : any  — single value for eq/gt/lt/gte/lte;
                            list of strings for is-in;
                            [low, high] for btwn.

        Examples:
          {"op": "eq",    "field": "sector",                     "value": "Technology"}
          {"op": "gte",   "field": "intradaymarketcap",          "value": 1000000000}
          {"op": "btwn",  "field": "peratio.lasttwelvemonths",   "value": [0, 25]}
          {"op": "is-in", "field": "exchange",                   "value": ["NMS","NYQ"]}

    logic : str
        Top-level combinator: "and" | "or".  Default "and".

    sort_field : str
        Field to sort by.  Default "percentchange".
    sort_asc : bool
        Ascending?  Default False.
    size : int
        Results to return (max 250).  Default 50.
    offset : int
        Pagination offset.

    Returns
    -------
    dict  { total, count, quotes }  or  { error, detail }

    MCP tool name : build_and_run_custom_query
    """
    if not filters:
        return {"error": "filters list is empty."}

    conditions: List[EquityQuery] = []
    for f in filters:
        op = f.get("op", "").lower()
        field = f.get("field", "")
        value = f.get("value")
        try:
            if op == "eq":
                conditions.append(_eq(field, str(value)))
            elif op == "is-in":
                vals = value if isinstance(value, list) else [value]
                conditions.append(_isin(field, *vals))
            elif op == "btwn":
                lo, hi = value[0], value[1]
                conditions.append(_btwn(field, lo, hi))
            elif op == "gt":
                conditions.append(_gt(field, float(value)))
            elif op == "lt":
                conditions.append(_lt(field, float(value)))
            elif op == "gte":
                conditions.append(_gte(field, float(value)))
            elif op == "lte":
                conditions.append(_lte(field, float(value)))
            else:
                return {"error": f"Unknown operator '{op}'. Use: eq, is-in, btwn, gt, lt, gte, lte."}
        except Exception as exc:
            return {"error": f"Could not build filter {f}: {exc}"}

    root = EquityQuery(logic, conditions)
    return _run(root, sort_field, sort_asc, size, offset)


def get_valid_fields_and_values() -> Dict[str, Any]:
    """
    Return the full catalogue of valid EquityQuery fields and their
    allowed values (for categorical fields).

    The agent should call this first to know what fields are available
    before constructing a custom query.

    MCP tool name : get_valid_fields_and_values
    """
    eq = EquityQuery("eq", ["region", "us"])   # dummy instance for introspection
    try:
        fields = eq.valid_fields
        values = eq.valid_values
        return {"valid_fields": fields, "valid_values": values}
    except Exception:
        # Fallback — return documented fields inline
        return {
            "valid_fields": {
                "eq_fields": ["exchange", "industry", "peer_group", "region", "sector"],
                "price": ["eodprice", "percentchange", "intradaymarketcap", "intradayprice",
                          "lastclose52weekhigh.lasttwelvemonths", "lastclose52weeklow.lasttwelvemonths"],
                "trading": ["avgdailyvol3m", "beta", "dayvolume", "eodvolume",
                            "pctheldinsider", "pctheldinst"],
                "valuation": ["peratio.lasttwelvemonths", "pegratio_5y", "pricebookratio.quarterly",
                              "lastclosetevebitda.lasttwelvemonths", "lastclosetevebit.lasttwelvemonths"],
                "profitability": ["returnonequity.lasttwelvemonths", "returnonassets.lasttwelvemonths",
                                  "forward_dividend_yield", "consecutive_years_of_dividend_growth_count"],
                "income_statement": ["epsgrowth.lasttwelvemonths", "quarterlyrevenuegrowth.quarterly",
                                     "netincomemargin.lasttwelvemonths", "ebitdamargin.lasttwelvemonths",
                                     "grossprofit.lasttwelvemonths"],
                "leverage": ["totaldebtequity.lasttwelvemonths", "netdebtebitda.lasttwelvemonths"],
                "cash_flow": ["leveredfreecashflow.lasttwelvemonths",
                              "cashfromoperations1yrgrowth.lasttwelvemonths"],
                "short_interest": ["short_percentage_of_float.value",
                                   "short_percentage_of_shares_outstanding.value"],
            },
            "valid_values": {
                "region": _VALID_REGIONS,
                "sector": _VALID_SECTORS,
                "exchange_us": _VALID_EXCHANGES_US,
                "exchange_india": _INDIA_EXCHANGES,
                "india_region_code": _INDIA_REGION,
                "india_market_cap_tiers_usd": {
                    "large_cap_min": _INDIA_LARGECAP_MIN,
                    "mid_cap_range": [_INDIA_MIDCAP_MIN, _INDIA_MIDCAP_MAX],
                    "small_cap_range": [_INDIA_SMALLCAP_MIN, _INDIA_SMALLCAP_MAX],
                },
            },
        }

# ---------------------------------------------------------------------------
# 11b. Company data tools (search / info / financials)
# ---------------------------------------------------------------------------

def search_company(company_name: str, max_results: int = 10) -> list:
    """
    Search Yahoo Finance for companies matching a name or keyword.

    Parameters
    ----------
    company_name : str
        The company name or search keyword (e.g. "Apple", "Reliance").
    max_results : int
        Maximum number of results to return (default 10).

    Returns
    -------
    list
        A list of matching quote dicts (symbol, shortName, exchange, etc.).
    """
    search = yf.Search(company_name, max_results=max_results)
    return search.quotes


def get_company_info(symbol: str) -> dict:
    """
    Fetch the full company profile / metadata for a given ticker symbol.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. "AAPL", "RELIANCE.NS").

    Returns
    -------
    dict
        Company profile including sector, industry, market cap, description, etc.
    """
    return yf.Ticker(symbol).info


def get_company_financials(symbol: str) -> dict:
    """
    Retrieve the latest annual financial statements for a ticker.

    Fetches the balance sheet, cash-flow statement, and income statement
    from Yahoo Finance and returns them in a single structured dict.

    Parameters
    ----------
    symbol : str
        Ticker symbol (e.g. "AAPL", "RELIANCE.NS").

    Returns
    -------
    dict
        Keys: "balance_sheet", "cashflow", "income_statement" — each
        value is itself a dict keyed by metric name.
    """
    ticker = yf.Ticker(symbol)
    return {
        "balance_sheet":     ticker.get_balance_sheet(as_dict=True, pretty=False, freq="yearly"),
        "cashflow":          ticker.get_cashflow(as_dict=True,      pretty=False, freq="yearly"),
        "income_statement":  ticker.get_income_stmt(as_dict=True,   pretty=False, freq="yearly"),
    }


# ---------------------------------------------------------------------------
# 12. MCP auto-registration helper
# ---------------------------------------------------------------------------

# ALL_TOOLS maps each MCP tool name to its implementing function.
# This is the single source of truth for which tools are exposed to the
# MCP server.  To add a new tool, define the function above and add an
# entry here — register_all_screener_mcp_tools will pick it up automatically.
ALL_TOOLS: Dict[str, Any] = {
    # Predefined
    "run_predefined_screener": run_predefined_screener,
    "list_predefined_screeners": list_predefined_screeners,
    # Sector / industry
    "screen_by_sector": screen_by_sector,
    "screen_by_industry": screen_by_industry,
    "screen_sector_by_market_cap_range": screen_sector_by_market_cap_range,
    # Peers
    "screen_by_peer_group": screen_by_peer_group,
    "find_peers_in_sector_and_industry": find_peers_in_sector_and_industry,
    # Valuation
    "screen_undervalued_stocks": screen_undervalued_stocks,
    "screen_by_pe_range": screen_by_pe_range,
    "screen_by_price_to_book": screen_by_price_to_book,
    "screen_by_ev_ebitda": screen_by_ev_ebitda,
    # Momentum / technical
    "screen_day_gainers": screen_day_gainers,
    "screen_day_losers": screen_day_losers,
    "screen_near_52w_high": screen_near_52w_high,
    "screen_near_52w_low": screen_near_52w_low,
    "screen_high_volume_movers": screen_high_volume_movers,
    "screen_by_beta": screen_by_beta,
    # Fundamental quality
    "screen_growth_stocks": screen_growth_stocks,
    "screen_profitable_stocks": screen_profitable_stocks,
    "screen_low_leverage_stocks": screen_low_leverage_stocks,
    "screen_strong_cashflow_stocks": screen_strong_cashflow_stocks,
    "screen_by_ebitda_margin": screen_by_ebitda_margin,
    # Dividend / income
    "screen_dividend_stocks": screen_dividend_stocks,
    "screen_high_yield_stocks": screen_high_yield_stocks,
    # Short interest
    "screen_high_short_interest": screen_high_short_interest,
    "screen_low_short_interest": screen_low_short_interest,
    # Regional / size
    "screen_by_region_and_exchange": screen_by_region_and_exchange,
    "screen_large_caps": screen_large_caps,
    "screen_small_caps": screen_small_caps,
    # India (NSE / BSE)
    "screen_india_stocks": screen_india_stocks,
    "screen_india_large_caps": screen_india_large_caps,
    "screen_india_mid_caps": screen_india_mid_caps,
    "screen_india_small_caps": screen_india_small_caps,
    "screen_india_sector": screen_india_sector,
    "find_india_peers": find_india_peers,
    "screen_india_growth_stocks": screen_india_growth_stocks,
    "screen_india_undervalued": screen_india_undervalued,
    "screen_india_dividend_stocks": screen_india_dividend_stocks,
    "screen_india_high_roe": screen_india_high_roe,
    "screen_india_day_movers": screen_india_day_movers,
    # Custom
    "build_and_run_custom_query": build_and_run_custom_query,
    "get_valid_fields_and_values": get_valid_fields_and_values,
    # Company data
    "search_company": search_company,
    "get_company_info": get_company_info,
    "get_company_financials": get_company_financials,
}


def register_all_screener_mcp_tools(mcp) -> None:
    """Register every tool in ALL_TOOLS with a FastMCP server instance.

    This is the primary entry point used by ``mcp_server.py`` to expose all
    screener and company-data tools to MCP-compatible clients.

    Usage example (from mcp_server.py)::

        from fastmcp import FastMCP
        from screener_mcp_tools import register_all_screener_mcp_tools

        mcp = FastMCP("equity-pilot")
        register_all_screener_mcp_tools(mcp)
        mcp.run()

    Parameters
    ----------
    mcp : FastMCP
        Any MCP server object that exposes a ``.tool(name=...)`` decorator
        method (e.g. a ``FastMCP`` instance).
    """
    for name, fn in ALL_TOOLS.items():
        mcp.tool(name=name)(fn)


if __name__ == "__main__":
    # Stand-alone mode: spin up a server exposing only the screener tools.
    # In production, use mcp_server.py which also wires in other tool modules.
    mcp = FastMCP("equity-pilot")
    register_all_screener_mcp_tools(mcp)
    mcp.run()