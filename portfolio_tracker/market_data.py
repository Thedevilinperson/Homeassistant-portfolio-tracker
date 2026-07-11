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
    cand = (ticker or "").strip().upper()
    # Een ISIN rechtstreeks aan yf.Ticker geven gooit een exception zodra Yahoo de
    # ISIN niet kent ("Invalid ISIN number"). Los een ISIN daarom eerst op naar een
    # verhandelbaar Yahoo-symbool via het search-endpoint; lukt dat niet, geef dan
    # meteen found=False terug zodat de ISIN-only-flow (externe bronnen) het overneemt.
    if _isin_valid(cand):
        sym = _yahoo_symbol_for_isin(cand)
        if not sym:
            return {"found": False, "name": ticker, "currency": "EUR",
                    "exchange": "", "type": "stock", "isin": cand}
        try:
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
        except Exception as e:
            logger.warning(f"get_stock_info({ticker}) via ISIN-symbool {sym}: {e}")
        return {"found": False, "name": ticker, "currency": "EUR",
                "exchange": "", "type": "stock", "isin": cand}
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
            try:
                data = resp.json()
            except ValueError:
                # Geen JSON terug: Tradegate kent deze ISIN wellicht niet (bv. een
                # certificaat dat er niet noteert). Geen fout, gewoon volgende bron.
                logger.info(f"_price_tradegate({isin}): geen notering op Tradegate")
                return None, None
            price = _to_float(data.get("last") or data.get("bid") or data.get("ask"))
            if price:
                return price, (data.get("currency") or "EUR")
    except Exception as e:
        logger.warning(f"_price_tradegate({isin}): {e}")
    return None, None


_BF_SALT_CACHE: dict = {"salt": None, "ts": 0.0, "source": None}
# Fallback-salt (uit een oudere JS-bundle). Wordt enkel gebruikt als het dynamisch
# ophalen faalt; de salt kan wijzigen, daarom halen we ze bij voorkeur live op.
_BF_SALT_FALLBACK = "w4icATTGtnjAZMbkL3kJwxMfEAKDa3MN"

_BF_SESSION = None
_BF_BLOCK = {"until": 0.0, "last_force": 0.0}

# Volwaardige browserheaders: de WAF van boerse-frankfurt.de weigert kale clients.
_BF_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Origin":  "https://www.boerse-frankfurt.de",
    "Referer": "https://www.boerse-frankfurt.de/",
}


def _bf_session():
    """Eén gedeelde requests.Session voor alle Börse-Frankfurt-verkeer. Belangrijk:
    de sessie bezoekt eerst de homepage zodat WAF-cookies verzameld worden — losse
    requests zonder cookies krijgen HTTP 403."""
    global _BF_SESSION
    if _BF_SESSION is None:
        import requests
        s = requests.Session()
        s.headers.update(_BF_BROWSER_HEADERS)
        _BF_SESSION = s
    return _BF_SESSION


def _bf_salt(force: bool = False) -> str:
    """Haal de (wisselende) salt van boerse-frankfurt.de dynamisch uit de JS-bundle.
    Ondersteunt zowel oude (main.HASH.js) als nieuwe (main-HASH.js) bundelnamen.
    ~24u gecachet; bij falen terugval op een bekende salt. Logt altijd de bron,
    zodat in de add-on-log zichtbaar is of de terugval (mogelijk verouderd) actief is."""
    import time
    now = time.time()
    if not force and _BF_SALT_CACHE["salt"] and (now - _BF_SALT_CACHE["ts"] < 86400):
        return _BF_SALT_CACHE["salt"]
    salt, why = None, ""
    try:
        import re
        s = _bf_session()
        resp = s.get("https://www.boerse-frankfurt.de/", timeout=8)
        if not resp.ok:
            why = f"homepage HTTP {resp.status_code}"
        else:
            # bundelnamen: main.HASH.js (oud) of main-HASH.js (nieuwe Angular-builds)
            files = re.findall(r'(?<=src=")[^"]*main[^"]*\.js', resp.text)
            if not files:
                why = "geen main-bundle gevonden in homepage"
            for f in files:
                url = f if f.startswith("http") else "https://www.boerse-frankfurt.de/" + f.lstrip("/")
                try:
                    js = s.get(url, timeout=10).text
                except Exception:
                    continue
                m = re.search(r'salt\s*[:=]\s*"(\w{8,})"', js)
                if m:
                    salt = m.group(1)
                    break
            if files and not salt:
                why = "salt niet gevonden in bundle(s)"
    except Exception as e:
        why = str(e)
    if salt:
        logger.info(f"_bf_salt: dynamisch opgehaald ({salt[:6]}...)")
        _BF_SALT_CACHE.update(salt=salt, ts=now, source="dynamisch")
    else:
        logger.warning(f"_bf_salt: TERUGVAL-salt gebruikt (dynamisch ophalen mislukt: {why}). "
                       "Als Börse Frankfurt 403 blijft geven, is deze salt wellicht verouderd.")
        _BF_SALT_CACHE.update(salt=_BF_SALT_FALLBACK, ts=now, source="terugval")
    return _BF_SALT_CACHE["salt"]


def _frankfurt_now():
    """Huidige tijd in Frankfurt (Europe/Berlin), ook zonder tzdata in de container:
    val dan terug op een handmatige CET/CEST-berekening (laatste zondag van maart
    t.e.m. laatste zondag van oktober = zomertijd, UTC+2; anders UTC+1)."""
    import datetime
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("Europe/Berlin"))
    except Exception:
        utc = datetime.datetime.now(datetime.timezone.utc)
        year = utc.year
        # laatste zondag van maart, 01:00 UTC -> zomertijd aan; laatste zondag oktober, 01:00 UTC -> uit
        def last_sunday(month):
            d = datetime.datetime(year, month + 1, 1, 1, tzinfo=datetime.timezone.utc) - datetime.timedelta(days=1)
            return d - datetime.timedelta(days=(d.weekday() + 1) % 7)
        dst = last_sunday(3) <= utc < last_sunday(10)
        return utc + datetime.timedelta(hours=2 if dst else 1)


def _bf_headers(url: str) -> dict:
    """Vereiste Börse-Frankfurt-headers: Client-Date (UTC ISO), X-Client-TraceId
    (md5 van datum+URL+salt) en X-Security (md5 van de Frankfurt-tijd JJJJMMDDUUMM).
    Algoritme geverifieerd tegen het gedocumenteerde voorbeeld en tegen bf4py."""
    import hashlib
    import datetime
    now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
    client_date = now_utc.isoformat(timespec="milliseconds") + "Z"
    salt = _bf_salt()
    return {
        "client-date":      client_date,
        "x-client-traceid": hashlib.md5((client_date + url + salt).encode()).hexdigest(),
        "x-security":       hashlib.md5(_frankfurt_now().strftime("%Y%m%d%H%M").encode()).hexdigest(),
        "accept":           "application/json, text/plain, */*",
    }


def _bf_request(function: str, params: dict, _retry: bool = True):
    """GET naar https://api.boerse-frankfurt.de/v1/data/<function>?<params> via de
    gedeelde sessie (cookies!) met de vereiste headers. Bij een 403 wordt eenmalig
    de salt vers opgehaald en opnieuw geprobeerd (de salt roteert af en toe). Blijft
    het 403, dan pauzeert de provider 10 minuten (circuit-breaker) om logspam en
    trage verversingen te vermijden. Logt status én een stukje van het antwoord."""
    import time
    import urllib.parse
    if time.time() < _BF_BLOCK["until"]:
        return None  # recent geblokkeerd (403): even niet opnieuw proberen
    url = "https://api.boerse-frankfurt.de/v1/data/" + function + "?" + urllib.parse.urlencode(params)
    try:
        s = _bf_session()
        resp = s.get(url, headers=_bf_headers(url), timeout=(3.5, 10))
        if resp.status_code == 403 and _retry and time.time() - _BF_BLOCK["last_force"] > 300:
            # Salt mogelijk geroteerd of cookies verlopen: vers ophalen en 1x opnieuw.
            logger.info(f"_bf_request({function}): 403 — salt/cookies verversen en opnieuw proberen")
            _BF_BLOCK["last_force"] = time.time()
            _bf_salt(force=True)
            return _bf_request(function, params, _retry=False)
        if resp.status_code == 403:
            body = (resp.text or "")[:120].replace("\n", " ")
            logger.warning(f"_bf_request({function}): HTTP 403 blijft na verse salt "
                           f"(salt={_BF_SALT_CACHE.get('source')}) | {body} — "
                           "Börse Frankfurt 10 min gepauzeerd")
            _BF_BLOCK["until"] = time.time() + 600
            return None
        if not resp.ok or not resp.text:
            body = (resp.text or "")[:120].replace("\n", " ")
            logger.warning(f"_bf_request({function}): HTTP {resp.status_code} "
                           f"(salt={_BF_SALT_CACHE.get('source')}) | {body}")
            return None
        data = resp.json()
        if isinstance(data, dict) and data.get("messages"):
            logger.warning(f"_bf_request({function}): geweigerd: {data['messages']}")
            return None
        return data
    except Exception as e:
        logger.warning(f"_bf_request({function}): {e}")
        return None


# Handelsplaatsen (MIC) die we proberen als het instrument ze niet zelf meldt.
# Warrants/certificaten (bv. ING Markets) noteren doorgaans op XFRA (Börse
# Frankfurt Zertifikate) of XSC1/XSCO (Scoach); aandelen/ETF's op XETR.
_BF_MICS = ["XFRA", "XSC1", "XSCO", "XETR", "XSTU"]


def _bf_available_mics(isin: str) -> list:
    """Vraag de handelsplaatsen van dit instrument op via instrument_information;
    val terug op de standaardlijst als dat niet lukt."""
    data = _bf_request("instrument_information", {"isin": isin})
    mics = []
    try:
        def _collect(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if k in ("mic", "micCode") and isinstance(v, str) and len(v) == 4:
                        mics.append(v.upper())
                    else:
                        _collect(v)
            elif isinstance(obj, list):
                for it in obj:
                    _collect(it)
        _collect(data)
    except Exception:
        pass
    seen, ordered = set(), []
    for m in mics + _BF_MICS:
        if m not in seen:
            seen.add(m)
            ordered.append(m)
    return ordered


def _price_boerse_frankfurt(isin: str) -> tuple[float | None, str | None]:
    """(prijs, munt) via de Börse-Frankfurt-API. Werkt ook voor warrants en
    certificaten (bv. ING Markets NL0015002RI2). Probeert per handelsplaats eerst
    de recentste bied-/laatkoers (intraday) en daarna de laatste EOD-slotkoers."""
    if not _isin_valid(isin):
        return None, None
    import datetime
    for mic in _bf_available_mics(isin)[:6]:
        # 1) Recentste bied/laat (dekt illiquide certificaten zonder recente trade)
        now = datetime.datetime.now(datetime.timezone.utc)
        frm = (now - datetime.timedelta(days=5)).isoformat(timespec="seconds").replace("+00:00", "Z")
        to  = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        data = _bf_request("bid_ask_history",
                           {"limit": 1, "offset": 0, "isin": isin, "mic": mic,
                            "from": frm, "to": to})
        if isinstance(data, dict) and data.get("data"):
            row = data["data"][0]
            price = _to_float(row.get("bidPrice") or row.get("askPrice")
                              or row.get("bidLimit") or row.get("askLimit"))
            if price:
                return price, "EUR"
        # 2) Laatste EOD-slotkoers (afgelopen 14 dagen)
        today = datetime.date.today()
        data = _bf_request("price_history",
                           {"isin": isin, "mic": mic, "limit": 20, "offset": 0,
                            "minDate": (today - datetime.timedelta(days=14)).isoformat(),
                            "maxDate": today.isoformat(),
                            "cleanSplit": False, "cleanPayout": False,
                            "cleanSubscription": False})
        if isinstance(data, dict) and data.get("data"):
            rows = sorted(data["data"], key=lambda r: r.get("date") or "", reverse=True)
            for r in rows:
                price = _to_float(r.get("close") or r.get("last"))
                if price:
                    return price, "EUR"
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
    ticker_is_isin = _isin_valid(ticker.strip().upper())
    if not _isin_valid(isin) and ticker_is_isin:
        isin = ticker.strip().upper()

    # 1) Yahoo op het ticker zelf — maar niet als het ticker een ISIN is: yfinance
    #    gooit dan een exception zodra Yahoo de ISIN niet kent ("Invalid ISIN number").
    price, currency = (None, None) if ticker_is_isin else _price_from_yahoo_symbol(ticker)

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