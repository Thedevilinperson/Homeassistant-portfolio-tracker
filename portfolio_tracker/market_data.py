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

def _lookup_isin(tkr, info: dict, ticker: str) -> str:
    """Best-effort ISIN-opzoeking. Yahoo geeft de ISIN voor Europese listings (.BR/.DE)
    vaak niet mee via het gewone info-object; we proberen daarom meerdere bronnen."""
    def _ok(v):
        return isinstance(v, str) and len(v) >= 10 and v not in ("-", "0", "None", "")

    # 1) Rechtstreeks in het info-object
    for key in ("isin", "isinCode"):
        v = info.get(key)
        if _ok(v):
            return v
    # 2) yfinance .isin (interne Yahoo-zoekopdracht)
    try:
        raw = tkr.isin
        if _ok(raw):
            return raw
    except Exception:
        pass
    # 3) Yahoo search-endpoint — bevat voor heel wat Europese effecten wél de ISIN
    try:
        import requests
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": ticker, "quotesCount": 6, "newsCount": 0, "enableFuzzyQuery": False},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.ok:
            quotes = resp.json().get("quotes", [])
            for q in quotes:  # eerst exacte symboolmatch
                if q.get("symbol", "").upper() == ticker.upper() and _ok(q.get("isin", "")):
                    return q["isin"]
            for q in quotes:  # anders de eerste met een geldige ISIN
                if _ok(q.get("isin", "")):
                    return q["isin"]
    except Exception:
        pass
    return ""


def get_stock_info(ticker: str) -> dict:
    try:
        tkr  = yf.Ticker(ticker)
        info = tkr.info or {}
        qt = info.get("quoteType", "").lower()
        # Bepaal of Yahoo écht iets gevonden heeft (geldige ticker)
        found = bool(
            info.get("longName") or info.get("shortName")
            or info.get("regularMarketPrice") is not None
            or info.get("currentPrice") is not None
            or info.get("previousClose") is not None
        )
        if not found:
            # Ticker gaf niets op Yahoo. Is het (of lijkt het op) een ISIN, probeer
            # dan een verhandelbaar symbool via de ISIN te vinden.
            cand = ticker.strip().upper()
            if _isin_valid(cand):
                sym = _yahoo_symbol_for_isin(cand)
                if sym:
                    tkr  = yf.Ticker(sym)
                    info = tkr.info or {}
                    qt = info.get("quoteType", "").lower()
                    if info.get("longName") or info.get("shortName") or info.get("regularMarketPrice") is not None:
                        return {
                            "found":    True,
                            "name":     info.get("longName") or info.get("shortName") or ticker,
                            "currency": info.get("currency", "EUR"),
                            "exchange": info.get("exchange", ""),
                            "type":     "etf" if qt == "etf" else "stock",
                            "isin":     cand,
                            "symbol":   sym,
                        }
            return {"found": False, "name": ticker, "currency": "EUR",
                    "exchange": "", "type": "stock", "isin": ""}
        return {
            "found":    True,
            "name":     info.get("longName") or info.get("shortName") or ticker,
            "currency": info.get("currency", "EUR"),
            "exchange": info.get("exchange", ""),
            "type":     "etf" if qt == "etf" else "stock",
            "isin":     _lookup_isin(tkr, info, ticker),
        }
    except Exception as e:
        logger.warning(f"get_stock_info({ticker}): {e}")
        return {"found": False, "name": ticker, "currency": "EUR",
                "exchange": "", "type": "stock", "isin": ""}


# ── Koersbronnen (ticker → ISIN-symbool → externe bronnen → handmatig) ──────────
# Volgorde bij het ophalen van een actuele koers:
#   1) Yahoo Finance op het ticker zelf
#   2) Yahoo Finance via een symbool dat we uit de ISIN afleiden
#   3) Externe (niet-Yahoo) bronnen op basis van de ISIN (Tradegate, Börse Frankfurt)
#   4) Handmatige koers — enkel als álle onlinebronnen falen (laatste redmiddel)
# Zo werken ook effecten zonder Yahoo-notering (bv. ING-warrants met enkel een ISIN)
# zonder dat je manueel koersen moet bijhouden.

def _isin_valid(isin) -> bool:
    return isinstance(isin, str) and len(isin) == 12 and isin[:2].isalpha()


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace("\u202f", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def _price_from_yahoo_symbol(symbol: str) -> tuple[float | None, str | None]:
    """(prijs, munt) via Yahoo voor één concreet symbool, of (None, None)."""
    try:
        tkr = yf.Ticker(symbol)
        info = tkr.info or {}
        price = (info.get("regularMarketPrice")
                 or info.get("currentPrice")
                 or info.get("previousClose"))
        currency = info.get("currency") or "EUR"
        if price is None:
            hist = tkr.history(period="1d", auto_adjust=True)
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        if price is not None:
            return float(price), currency
    except Exception as e:
        logger.warning(f"_price_from_yahoo_symbol({symbol}): {e}")
    return None, None


_ISIN_SYMBOL_CACHE: dict[str, str] = {}


def _yahoo_symbol_for_isin(isin: str) -> str | None:
    """Zoek via het Yahoo search-endpoint een verhandelbaar symbool voor een ISIN."""
    if not _isin_valid(isin):
        return None
    if isin in _ISIN_SYMBOL_CACHE:
        return _ISIN_SYMBOL_CACHE[isin] or None
    try:
        import requests
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": isin, "quotesCount": 6, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.ok:
            for q in resp.json().get("quotes", []):
                sym = q.get("symbol")
                if sym:
                    _ISIN_SYMBOL_CACHE[isin] = sym
                    return sym
    except Exception as e:
        logger.warning(f"_yahoo_symbol_for_isin({isin}): {e}")
    _ISIN_SYMBOL_CACHE[isin] = ""
    return None


def _price_tradegate(isin: str) -> tuple[float | None, str | None]:
    """(prijs, munt) via Tradegate — dekt veel warrants, turbos en ETP's die niet
    op Yahoo staan. Geen sleutel nodig."""
    if not _isin_valid(isin):
        return None, None
    try:
        import requests
        resp = requests.get("https://www.tradegate.de/refresh.php",
                            params={"isin": isin},
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.ok:
            data = resp.json()
            price = _to_float(data.get("last") or data.get("bid") or data.get("ask"))
            if price:
                return price, (data.get("currency") or "EUR")
    except Exception as e:
        logger.warning(f"_price_tradegate({isin}): {e}")
    return None, None


_BF_SALT_CACHE: dict = {"salt": None, "ts": 0.0}
# Fallback-salt (uit een oudere JS-bundle). Wordt enkel gebruikt als het dynamisch
# ophalen faalt; de salt kan wijzigen, daarom halen we ze bij voorkeur live op.
_BF_SALT_FALLBACK = "w4icATTGtnjAZMbkL3kJwxMfEAKDa3MN"


def _bf_salt() -> str:
    """Haal de (wisselende) salt van boerse-frankfurt.de dynamisch uit de JS-bundle,
    zodat de beveiligingsheaders blijven kloppen als Börse Frankfurt de salt wijzigt.
    Resultaat wordt ~24u gecachet; bij falen valt hij terug op een bekende salt."""
    import time
    now = time.time()
    if _BF_SALT_CACHE["salt"] and (now - _BF_SALT_CACHE["ts"] < 86400):
        return _BF_SALT_CACHE["salt"]
    salt = None
    try:
        import re
        import requests
        html = requests.get("https://www.boerse-frankfurt.de/",
                            headers={"User-Agent": "Mozilla/5.0"}, timeout=6).text
        bundles = re.findall(r'src="([^"]*?(?:main|runtime|polyfills)[^"]*?\.js)"', html)
        for b in bundles:
            url = b if b.startswith("http") else "https://www.boerse-frankfurt.de/" + b.lstrip("/")
            try:
                js = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=8).text
            except Exception:
                continue
            m = re.search(r'salt:\s*"([A-Za-z0-9+/=_-]{16,})"', js)
            if m:
                salt = m.group(1)
                break
    except Exception as e:
        logger.warning(f"_bf_salt dynamisch ophalen faalde: {e}")
    salt = salt or _BF_SALT_FALLBACK
    _BF_SALT_CACHE.update(salt=salt, ts=now)
    return salt


def _bf_headers(url: str) -> dict:
    """Bereken de vereiste Börse-Frankfurt-headers (Client-Date, X-Client-TraceId,
    X-Security). X-Security gebruikt de tijd in Frankfurt (Europe/Berlin), ongeacht
    de tijdzone van deze server."""
    import hashlib
    import datetime
    try:
        from zoneinfo import ZoneInfo
        fra_now = datetime.datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        fra_now = datetime.datetime.utcnow() + datetime.timedelta(hours=1)
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    client_date = now_utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
    salt = _bf_salt()
    return {
        "Client-Date":      client_date,
        "X-Client-TraceId": hashlib.md5((client_date + url + salt).encode()).hexdigest(),
        "X-Security":       hashlib.md5(fra_now.strftime("%Y%m%d%H%M").encode()).hexdigest(),
        "Accept":           "application/json, text/plain, */*",
        "User-Agent":       "Mozilla/5.0",
        "Origin":           "https://www.boerse-frankfurt.de",
        "Referer":          "https://www.boerse-frankfurt.de/",
    }


# Handelsplaatsen (MIC) waarop we een koers proberen. Warrants/certificaten van
# bv. ING Markets noteren doorgaans op de Frankfurtse Zertifikate-beurs (XFRA).
_BF_MICS = ["XFRA", "XETR", "XSTU", "XGAT"]


def _price_boerse_frankfurt(isin: str) -> tuple[float | None, str | None]:
    """(prijs, munt) via de Börse-Frankfurt-API. Werkt ook voor warrants/certificaten
    (bv. ING Markets, ISIN NL0015002RI2). Gebruikt de vereiste beveiligingsheaders met
    een dynamisch opgehaalde salt, en probeert enkele handelsplaatsen."""
    if not _isin_valid(isin):
        return None, None
    import requests
    base = "https://api.boerse-frankfurt.de/v1/data/quote_box/single"
    for mic in _BF_MICS:
        url = f"{base}?isin={isin}&mic={mic}"
        try:
            resp = requests.get(url, headers=_bf_headers(url), timeout=8)
            if not resp.ok:
                continue
            data = resp.json() or {}
            price = _to_float(data.get("lastPrice"))
            if price is None:
                # geen last -> val terug op bied/laat (bv. bij illiquide certificaten)
                price = _to_float(data.get("bidPrice") or data.get("askPrice"))
            if price:
                return price, (data.get("currency") or data.get("tradingCurrency") or "EUR")
        except Exception as e:
            logger.warning(f"_price_boerse_frankfurt({isin},{mic}): {e}")
    return None, None


# Externe ISIN-bronnen, in volgorde geprobeerd na Yahoo. Uitbreidbaar met extra
# bronnen (bv. een ING-Markets-provider) door een functie (isin)->(prijs,munt) toe
# te voegen aan deze lijst. Börse Frankfurt eerst: dekt warrants/certificaten.
_ISIN_PROVIDERS = [_price_boerse_frankfurt, _price_tradegate]


def probe_isin(isin: str) -> tuple[float | None, str | None, str | None]:
    """Test of een ISIN op een externe bron (Yahoo-symbool of niet-Yahoo-bron)
    verhandeld wordt. Geeft (prijs, munt, bronnaam) terug, of (None, None, None).
    Handig bij het toevoegen van een effect zonder Yahoo-ticker (bv. een warrant):
    zo kunnen we de munt voorinvullen en bevestigen dat er automatisch een koers
    beschikbaar is."""
    if not _isin_valid(isin):
        return None, None, None
    sym = _yahoo_symbol_for_isin(isin)
    if sym:
        p, c = _price_from_yahoo_symbol(sym)
        if p is not None:
            return p, c, f"Yahoo ({sym})"
    names = {"_price_tradegate": "Tradegate", "_price_boerse_frankfurt": "Börse Frankfurt"}
    for provider in _ISIN_PROVIDERS:
        p, c = provider(isin)
        if p is not None:
            return p, c, names.get(provider.__name__, provider.__name__)
    return None, None, None


def _asset_isin(ticker: str) -> str:
    try:
        import database as _db
        a = _db.get_asset(ticker) or {}
        return (a.get("isin") or "").strip().upper()
    except Exception:
        return ""


def get_current_price(ticker: str) -> tuple[float | None, str | None]:
    """Actuele koers + munt. Probeert online bronnen eerst (Yahoo op ticker, dan via
    ISIN, dan niet-Yahoo-bronnen) en valt pas als álles faalt terug op een handmatige
    koers."""
    cached_price, cached_cur = _cached(ticker)
    if cached_price is not None:
        return cached_price, cached_cur

    isin = _asset_isin(ticker)
    # Geen ISIN op het activum, maar het ticker zelf is een ISIN (bv. een warrant die
    # met de ISIN als ticker werd toegevoegd)? Gebruik die dan.
    if not _isin_valid(isin) and _isin_valid(ticker.strip().upper()):
        isin = ticker.strip().upper()

    # 1) Yahoo op het ticker zelf
    price, currency = _price_from_yahoo_symbol(ticker)

    # 2) Yahoo via een uit de ISIN afgeleid symbool
    if price is None and _isin_valid(isin):
        sym = _yahoo_symbol_for_isin(isin)
        if sym and sym.upper() != ticker.upper():
            price, currency = _price_from_yahoo_symbol(sym)

    # 3) Externe (niet-Yahoo) bronnen op basis van de ISIN
    if price is None and _isin_valid(isin):
        for provider in _ISIN_PROVIDERS:
            p, c = provider(isin)
            if p is not None:
                price, currency = p, c
                break

    # 4) Handmatige koers — laatste redmiddel
    if price is None:
        try:
            import database as _db
            mp = _db.get_manual_price(ticker)
            if mp:
                return mp["price"], mp["currency"]
        except Exception:
            pass

    if price is not None:
        price = float(price)
        currency = currency or "EUR"
        _store(ticker, price, currency)
        return price, currency
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

def get_close_on_date(ticker: str, on_date: str) -> float | None:
    """Slotkoers (native valuta) op of vlak vóór 'YYYY-MM-DD'. Voor het fotomoment
    (31/12/2025). auto_adjust=False zodat de koers de werkelijke slotkoers van die
    dag is (zonder latere split-/dividendcorrectie)."""
    try:
        d = datetime.strptime(on_date[:10], "%Y-%m-%d")
        start = (d - timedelta(days=10)).strftime("%Y-%m-%d")
        end = (d + timedelta(days=1)).strftime("%Y-%m-%d")
        hist = yf.Ticker(ticker).history(start=start, end=end, auto_adjust=False)
        if not hist.empty:
            return round(float(hist["Close"].iloc[-1]), 4)
    except Exception as e:
        logger.warning(f"get_close_on_date({ticker},{on_date}): {e}")
    return None


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