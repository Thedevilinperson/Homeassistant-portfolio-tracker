"""
market_data.py — yfinance wrapper met in-memory cache
Haalt koersen, wisselkoersen (actueel + historisch) en basisbedrijfsinfo op.
"""
import time
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yfinance as yf

logger = logging.getLogger(__name__)

# ── In-memory cache (5 minuten TTL) ─────────────────────────────────────────
_CACHE: dict[str, tuple[float, float, str]] = {}  # ticker -> (epoch, price, currency)
CACHE_TTL = 300  # seconden

# Aparte cache voor historische reeksen (1 uur TTL)
_HIST_CACHE: dict[str, tuple[float, object]] = {}
HIST_TTL = 3600


def _cached(ticker: str) -> tuple[float, str] | tuple[None, None]:
    entry = _CACHE.get(ticker)
    if entry and (time.time() - entry[0]) < CACHE_TTL:
        return entry[1], entry[2]
    return None, None


def _store(ticker: str, price: float, currency: str):
    _CACHE[ticker] = (time.time(), price, currency)


# ── Publieke API ─────────────────────────────────────────────────────────────

def get_stock_info(ticker: str) -> dict:
    try:
        tkr  = yf.Ticker(ticker)
        info = tkr.info
        qt = info.get("quoteType", "").lower()
        isin = ""
        try:
            raw = tkr.isin
            if raw and raw not in ("-", "0", "None"):
                isin = raw
        except Exception:
            pass
        return {
            "name":     info.get("longName") or info.get("shortName") or ticker,
            "currency": info.get("currency", "EUR"),
            "exchange": info.get("exchange", ""),
            "type":     "etf" if qt == "etf" else "stock",
            "isin":     isin,
        }
    except Exception as e:
        logger.warning(f"get_stock_info({ticker}): {e}")
        return {"name": ticker, "currency": "EUR", "exchange": "", "type": "stock", "isin": ""}


def get_current_price(ticker: str) -> tuple[float | None, str | None]:
    cached_price, cached_cur = _cached(ticker)
    if cached_price is not None:
        return cached_price, cached_cur
    try:
        tkr = yf.Ticker(ticker)
        info = tkr.info
        price = (
            info.get("regularMarketPrice")
            or info.get("currentPrice")
            or info.get("previousClose")
        )
        currency = info.get("currency", "EUR")
        if price is None:
            hist = tkr.history(period="1d", auto_adjust=True)
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        if price is not None:
            price = float(price)
            _store(ticker, price, currency)
            return price, currency
    except Exception as e:
        logger.warning(f"get_current_price({ticker}): {e}")
    return None, None


def get_prices_for_tickers(tickers: list[str]) -> dict[str, dict]:
    result = {}
    for ticker in tickers:
        price, currency = get_current_price(ticker)
        result[ticker] = {"price": price, "currency": currency}
    return result


def get_exchange_rate(from_currency: str, to_currency: str = "EUR") -> float | None:
    """Actuele wisselkoers from_currency → to_currency."""
    if from_currency == to_currency:
        return 1.0
    pair = f"{from_currency}{to_currency}=X"
    cached_price, _ = _cached(pair)
    if cached_price is not None:
        return cached_price
    try:
        tkr = yf.Ticker(pair)
        info = tkr.info
        rate = info.get("regularMarketPrice")
        if rate is None:
            hist = tkr.history(period="1d")
            if not hist.empty:
                rate = float(hist["Close"].iloc[-1])
        if rate:
            rate = float(rate)
            _store(pair, rate, to_currency)
            return rate
    except Exception as e:
        logger.warning(f"get_exchange_rate({from_currency}/{to_currency}): {e}")
    return None


def convert_to_eur(amount: float, currency: str) -> float | None:
    if currency == "EUR":
        return amount
    rate = get_exchange_rate(currency, "EUR")
    return amount * rate if rate else None


# ── Historische data ─────────────────────────────────────────────────────────

def get_historical_exchange_rate(from_currency: str, on_date: str,
                                 to_currency: str = "EUR") -> float | None:
    """
    Wisselkoers from→to op (of vlak vóór) een specifieke datum 'YYYY-MM-DD'.
    Gebruikt voor het correct omrekenen van transacties op hun eigen datum.
    """
    if from_currency == to_currency:
        return 1.0
    pair = f"{from_currency}{to_currency}=X"
    try:
        d = datetime.strptime(on_date[:10], "%Y-%m-%d")
        start = (d - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (d + timedelta(days=1)).strftime("%Y-%m-%d")
        hist = yf.Ticker(pair).history(start=start, end=end)
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.warning(f"get_historical_exchange_rate({pair},{on_date}): {e}")
    # Val terug op de actuele koers als historisch niet lukt
    return get_exchange_rate(from_currency, to_currency)


def get_price_series(ticker: str, start: str, end: str | None = None):
    """
    Dagelijkse slotkoersen (native valuta) als pandas Series, geïndexeerd op datum.
    Cache: 1 uur. Geeft None bij fout.
    """
    key = f"series:{ticker}:{start}:{end}"
    entry = _HIST_CACHE.get(key)
    if entry and (time.time() - entry[0]) < HIST_TTL:
        return entry[1]
    try:
        end = end or (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=True)
        if hist.empty:
            return None
        series = hist["Close"].copy()
        series.index = series.index.tz_localize(None).normalize()
        _HIST_CACHE[key] = (time.time(), series)
        return series
    except Exception as e:
        logger.warning(f"get_price_series({ticker}): {e}")
        return None


def get_fx_series(from_currency: str, start: str, end: str | None = None):
    """Dagelijkse wisselkoers from→EUR als pandas Series. None=1.0 (EUR)."""
    if from_currency == "EUR":
        return None
    return get_price_series(f"{from_currency}EUR=X", start, end)


# ── Beurstijden ──────────────────────────────────────────────────────────────

EXCHANGE_HOURS = {
    "ENX":   (9, 0,  17, 35, "Europe/Brussels"),
    "AMS":   (9, 0,  17, 35, "Europe/Amsterdam"),
    "EPA":   (9, 0,  17, 35, "Europe/Paris"),
    "EBR":   (9, 0,  17, 35, "Europe/Brussels"),
    "XETR":  (9, 0,  17, 35, "Europe/Berlin"),
    "NMS":   (15, 30, 22, 0, "US/Eastern"),
    "NYQ":   (15, 30, 22, 0, "US/Eastern"),
    "NGM":   (15, 30, 22, 0, "US/Eastern"),
}


def is_market_open(exchange: str) -> bool:
    now_brussels = datetime.now(ZoneInfo("Europe/Brussels"))
    if now_brussels.weekday() >= 5:
        return False
    hours = EXCHANGE_HOURS.get(exchange)
    if not hours:
        return False
    oh, om, ch, cm = hours[:4]
    tz = hours[4]
    now_local = datetime.now(ZoneInfo(tz))
    open_mins  = oh * 60 + om
    close_mins = ch * 60 + cm
    current_mins = now_local.hour * 60 + now_local.minute
    return open_mins <= current_mins < close_mins


def get_market_state(ticker: str) -> str:
    try:
        info = yf.Ticker(ticker).info
        return info.get("marketState", "CLOSED")
    except Exception:
        return "UNKNOWN"