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
_BF_BLOCK = {"until": 0.0, "last_force": 0.0, "fails": 0}


def _bf_urlencode(params: dict) -> str:
    """Canonieke, deterministische query-string voor de trace-id-hash. De server
    herrekent de hash over de URL die hij ontvangt; de gehashte string moet dus
    byte-identiek zijn aan wat effectief verstuurd wordt. Daarom: percent-encoding
    (quote, dus %20 i.p.v. '+', zodat geen enkele HTTP-client iets hernormaliseert),
    JS-stijl booleans ('true'/'false' i.p.v. Pythons 'True'/'False') en een vaste
    (insertie-)volgorde van de parameters."""
    import urllib.parse
    norm = []
    for k, v in params.items():
        if isinstance(v, bool):
            v = "true" if v else "false"
        norm.append((k, v))
    return urllib.parse.urlencode(norm, quote_via=urllib.parse.quote)

# Volwaardige browserheaders: de WAF van boerse-frankfurt.de weigert kale clients.
_BF_BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"),
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    # Bewust GEEN 'br': requests pakt Brotli alleen uit als het brotli-pakket is
    # geïnstalleerd; anders krijg je gecomprimeerde bytes als 'tekst' terug en
    # vindt de salt-detectie niets in de homepage.
    "Accept-Encoding": "gzip, deflate",
    "Sec-Fetch-Site": "same-site",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Origin":  "https://www.boerse-frankfurt.de",
    "Referer": "https://www.boerse-frankfurt.de/",
}


def _bf_session():
    """Eén gedeelde sessie voor alle Börse-Frankfurt-verkeer. Bij voorkeur via
    curl_cffi met Chrome-imitatie: hun WAF blokkeert clients op TLS-vingerafdruk,
    en de standaard Python-requests-handdruk wordt als bot herkend (403 met leeg
    antwoord, ondanks correcte salt en headers). curl_cffi zit al in de container
    (dependency van yfinance). Terugval: gewone requests.Session. De sessie bezoekt
    eerst de homepage zodat WAF-cookies verzameld worden."""
    global _BF_SESSION
    if _BF_SESSION is None:
        s = None
        try:
            from curl_cffi import requests as curl_requests
            s = curl_requests.Session(impersonate="chrome")
            # curl_cffi zet zelf consistente Chrome-headers (UA, sec-ch-ua, encoding);
            # enkel context toevoegen, de imitatie niet overschrijven.
            s.headers.update({
                "Origin":  "https://www.boerse-frankfurt.de",
                "Referer": "https://www.boerse-frankfurt.de/",
                "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
            })
            logger.info("_bf_session: curl_cffi met Chrome-imitatie actief")
        except Exception as e:
            logger.warning(f"_bf_session: curl_cffi niet bruikbaar ({e}); terugval op requests "
                           "(kans op 403 door TLS-vingerafdruk)")
            import requests
            s = requests.Session()
            s.headers.update(_BF_BROWSER_HEADERS)
        _BF_SESSION = s
    return _BF_SESSION


def _bf_salt(force: bool = False) -> str:
    """Haal de (wisselende) salt van boerse-frankfurt.de dynamisch op. De salt zit in
    een JS-bundle waarvan de naam per build/framework verandert (main.HASH.js,
    main-HASH.js, index-HASH.js, chunks...). Daarom generiek: eerst de homepage-HTML
    zelf doorzoeken, daarna álle script-/preload-bundles (main-achtige eerst).
    ~24u gecachet; bij falen terugval op een bekende salt. Logt altijd de bron en bij
    falen wélke bundles er gevonden werden, zodat de add-on-log de diagnose toont."""
    import time
    now = time.time()
    if not force and _BF_SALT_CACHE["salt"] and (now - _BF_SALT_CACHE["ts"] < 86400):
        return _BF_SALT_CACHE["salt"]
    salt, why = None, ""
    SALT_RE = r'salt\s*[:=]\s*["\'](\w{8,})["\']'
    try:
        import re
        s = _bf_session()
        resp = s.get("https://www.boerse-frankfurt.de/", timeout=8)
        if not resp.ok:
            why = f"homepage HTTP {resp.status_code}"
        else:
            html = resp.text or ""
            # Vangnet: sommige CDN's sturen toch Brotli; pak uit als het pakket er is.
            enc = (getattr(resp, "headers", {}) or {}).get("Content-Encoding", "").lower()
            if "br" in enc and "<" not in html[:200]:
                try:
                    import brotli
                    html = brotli.decompress(resp.content).decode("utf-8", "replace")
                except Exception:
                    pass
            # 1) Salt soms rechtstreeks in de HTML (inline config)
            m = re.search(SALT_RE, html)
            if m:
                salt = m.group(1)
            else:
                # 2) Alle JS-bundles verzamelen: <script src=...>, <link href=...>,
                #    beide quotestijlen, absolute en relatieve paden.
                srcs = re.findall(r'(?:src|href)=["\']([^"\']+\.js(?:\?[^"\']*)?)["\']', html)
                seen, ordered = set(), []
                for f in srcs:
                    if f not in seen:
                        seen.add(f)
                        ordered.append(f)
                # main-achtige eerst, dan index/chunk, dan de rest; max 6 downloads
                ordered.sort(key=lambda f: (0 if "main" in f else (1 if ("index" in f or "chunk" in f) else 2)))
                if not ordered:
                    why = f"geen script-bundles in homepage; begin: {html[:120]!r}"
                salt_context = None
                for f in ordered[:6]:
                    url = f if f.startswith("http") else "https://www.boerse-frankfurt.de/" + f.lstrip("/")
                    try:
                        js = s.get(url, timeout=10).text
                    except Exception:
                        continue
                    m = re.search(SALT_RE, js)
                    if m:
                        salt = m.group(1)
                        break
                    # Diagnose: komt het woord 'salt' voor maar matcht het patroon
                    # niet, bewaar dan de context — dat verraadt de nieuwe vorm
                    # (hernoemd, geobfusceerd of in een groter config-object).
                    if salt_context is None:
                        i = js.lower().find("salt")
                        if i >= 0:
                            salt_context = js[max(0, i - 20):i + 60]
                if ordered and not salt:
                    names = ", ".join(x.split("/")[-1].split("?")[0] for x in ordered[:4])
                    why = f"salt niet gevonden in {len(ordered)} bundle(s): {names}"
                    if salt_context:
                        why += f" | context rond 'salt': {salt_context!r}"
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
    gedeelde sessie met de vereiste headers. Bij een 403 wordt eenmalig de salt vers
    opgehaald en opnieuw geprobeerd (de salt roteert af en toe). Blijft het 403, dan
    pauzeert de provider met exponentiële backoff (30s, 60s, 120s, ... max 10 min)
    zodat een tijdelijke weigering de interactieve app niet lang blokkeert; een
    geslaagde call reset de backoff. Logt status én een stukje van het antwoord."""
    import time
    import urllib.parse
    if time.time() < _BF_BLOCK["until"]:
        return None  # recent geblokkeerd (403): even niet opnieuw proberen
    url = "https://api.boerse-frankfurt.de/v1/data/" + function + "?" + _bf_urlencode(params)
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
            _BF_BLOCK["fails"] = min(_BF_BLOCK["fails"] + 1, 6)
            pause = min(600, 30 * (2 ** (_BF_BLOCK["fails"] - 1)))  # 30,60,120,240,480,600
            _BF_BLOCK["until"] = time.time() + pause
            body = (resp.text or "")[:120].replace("\n", " ")
            logger.warning(f"_bf_request({function}): HTTP 403 blijft na verse salt "
                           f"(salt={_BF_SALT_CACHE.get('source')}) | {body} — "
                           f"Börse Frankfurt {pause}s gepauzeerd (poging {_BF_BLOCK['fails']})")
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
        _BF_BLOCK["fails"] = 0  # succes: backoff resetten
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


def _price_lang_schwarz(isin: str) -> tuple[float | None, str | None]:
    """(prijs, munt) via Lang & Schwarz (ls-tc.de) — een toegankelijker platform
    zonder salt-beveiliging, als vangnet naast Börse Frankfurt en Tradegate. L&S
    verhandelt veel warrants/certificaten. Werkwijze: instrument opzoeken op ISIN
    (JSON-search) en daarna de recentste koers uit de mini-chartdata halen. Alle
    stappen zijn defensief: elk afwijkend antwoord wordt gelogd en levert gewoon
    (None, None) op zodat de volgende bron het overneemt."""
    if not _isin_valid(isin):
        return None, None
    import requests
    headers = {"User-Agent": _BF_BROWSER_HEADERS["User-Agent"],
               "Accept": "application/json, text/plain, */*",
               "Referer": "https://www.ls-tc.de/"}
    try:
        resp = requests.get("https://www.ls-tc.de/_rpc/json/.lstc/instrument/search/main",
                            params={"q": isin, "localeId": 2},
                            headers=headers, timeout=8)
        if not resp.ok:
            logger.info(f"_price_lang_schwarz({isin}): zoek-HTTP {resp.status_code}")
            return None, None
        try:
            found = resp.json()
        except ValueError:
            logger.info(f"_price_lang_schwarz({isin}): zoekantwoord geen JSON")
            return None, None
        # Antwoord kan een lijst zijn of een dict met een lijst erin
        items = found if isinstance(found, list) else \
            (found.get("items") or found.get("data") or found.get("instruments") or [])
        inst_id = None
        for it in items:
            if isinstance(it, dict):
                if (it.get("isin") or "").upper() in ("", isin):
                    inst_id = it.get("instrumentId") or it.get("id")
                    if inst_id:
                        break
        if not inst_id:
            logger.info(f"_price_lang_schwarz({isin}): geen instrument gevonden")
            return None, None
        resp2 = requests.get("https://www.ls-tc.de/_rpc/json/instrument/chart/dataForInstrument",
                             params={"container": "chart1", "instrumentId": inst_id,
                                     "marketId": 1, "quotetype": "mid",
                                     "series": "intraday,history", "type": "mini"},
                             headers=headers, timeout=8)
        if not resp2.ok:
            logger.info(f"_price_lang_schwarz({isin}): chart-HTTP {resp2.status_code}")
            return None, None
        try:
            chart = resp2.json()
        except ValueError:
            logger.info(f"_price_lang_schwarz({isin}): chartantwoord geen JSON")
            return None, None
        series = (chart or {}).get("series") or {}
        for key in ("intraday", "history"):
            sdata = series.get(key) or {}
            pts = sdata.get("data") or []
            if pts:
                last = pts[-1]
                price = _to_float(last[1] if isinstance(last, (list, tuple)) and len(last) > 1 else last)
                if price:
                    return price, "EUR"
        logger.info(f"_price_lang_schwarz({isin}): geen koerspunten in chartdata")
    except Exception as e:
        logger.warning(f"_price_lang_schwarz({isin}): {e}")
    return None, None


_ONVISTA_TYPE_PATH = {
    "STOCK": "stocks", "FUND": "funds", "BOND": "bonds", "DERIVATIVE": "derivatives",
    "INDEX": "indices", "ETF": "etfs", "CURRENCY": "currencies",
}

_ONVISTA_HEADERS_BASE = {
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://www.onvista.de/",
}


def _onvista_headers() -> dict:
    h = dict(_ONVISTA_HEADERS_BASE)
    h["User-Agent"] = _BF_BROWSER_HEADERS["User-Agent"]
    return h


def _onvista_search(isin: str) -> dict | None:
    """Zoek een instrument op ISIN via de open onvista-API. Geeft het gevonden
    item terug (met o.a. entityType, entityValue en name), of None."""
    if not _isin_valid(isin):
        return None
    import requests
    try:
        resp = requests.get("https://api.onvista.de/api/v1/instruments/search/facet",
                            params={"perType": 10, "searchValue": isin},
                            headers=_onvista_headers(), timeout=8)
        if not resp.ok:
            logger.info(f"_onvista_search({isin}): HTTP {resp.status_code}")
            return None
        for facet in (resp.json() or {}).get("facets", []):
            for it in facet.get("results", []) or []:
                if (it.get("isin") or "").upper() == isin:
                    return it
        logger.info(f"_onvista_search({isin}): geen instrument gevonden")
    except Exception as e:
        logger.warning(f"_onvista_search({isin}): {e}")
    return None


def _onvista_snapshot(isin: str, etype: str) -> dict | None:
    """Snapshot van een instrument (quote + noteringen), of None."""
    import requests
    for p in [_ONVISTA_TYPE_PATH.get(etype, (etype or "").lower() + "s"), etype]:
        if not p:
            continue
        try:
            resp = requests.get(f"https://api.onvista.de/api/v1/{p}/ISIN:{isin}/snapshot",
                                headers=_onvista_headers(), timeout=8)
            if resp.ok:
                return resp.json() or {}
        except Exception as e:
            logger.warning(f"_onvista_snapshot({isin},{p}): {e}")
    return None


def _price_onvista(isin: str) -> tuple[float | None, str | None]:
    """(prijs, munt) via de open onvista-API (api.onvista.de) — geen salt of
    TLS-verdediging, dekt ook derivaten zoals warrants/certificaten. Werkwijze
    (zelfde patroon als het pyOnvista-project): instrument zoeken op ISIN,
    daarna een snapshot en de koers uit quote.last (terugval: bid/laat, daarna
    quoteList-noteringen)."""
    it = _onvista_search(isin)
    if not it:
        return None, None
    snap = _onvista_snapshot(isin, it.get("entityType") or "")
    if snap is None:
        logger.info(f"_price_onvista({isin}): geen snapshot (type {it.get('entityType')})")
        return None, None
    quotes = [snap.get("quote") or {}]
    quotes += ((snap.get("quoteList") or {}).get("list") or [])
    for q in quotes:
        price = _to_float(q.get("last") or q.get("bid") or q.get("ask"))
        if price:
            cur = q.get("isoCurrency") or (snap.get("instrument") or {}).get("isoCurrency") or "EUR"
            return price, cur
    logger.info(f"_price_onvista({isin}): snapshot zonder bruikbare koers")
    return None, None


def _onvista_close_on_date(isin: str, on_date: str) -> float | None:
    """Slotkoers op of vlak vóór 'YYYY-MM-DD' via onvista chart_history — voor
    effecten zonder Yahoo-notering (bv. warrants, fotomomentwaarde 31/12)."""
    import requests
    from datetime import datetime as _dt, timedelta as _td
    it = _onvista_search(isin)
    if not it:
        return None
    etype, uid = it.get("entityType"), it.get("entityValue")
    snap = _onvista_snapshot(isin, etype or "")
    if not snap or not uid:
        return None
    notations = ((snap.get("quoteList") or {}).get("list") or [])
    id_notation = None
    for n in notations:
        id_notation = ((n.get("market") or {}).get("idNotation")) or n.get("idNotation")
        if id_notation:
            break
    if not id_notation:
        logger.info(f"_onvista_close_on_date({isin}): geen notering (idNotation) gevonden")
        return None
    try:
        d = _dt.strptime(on_date[:10], "%Y-%m-%d")
        resp = requests.get(
            f"https://api.onvista.de/api/v1/instruments/{etype}/{uid}/chart_history",
            params={"idNotation": id_notation, "resolution": "1D",
                    "startDate": (d - _td(days=10)).strftime("%Y-%m-%d"),
                    "endDate": (d + _td(days=1)).strftime("%Y-%m-%d")},
            headers=_onvista_headers(), timeout=8)
        if not resp.ok:
            logger.info(f"_onvista_close_on_date({isin}): chart-HTTP {resp.status_code}")
            return None
        data = resp.json() or {}
        lasts = data.get("last") or []
        if lasts:
            price = _to_float(lasts[-1])
            if price:
                return round(price, 4)
        logger.info(f"_onvista_close_on_date({isin}): geen datapunten in venster")
    except Exception as e:
        logger.warning(f"_onvista_close_on_date({isin}): {e}")
    return None


# Externe ISIN-bronnen, in volgorde geprobeerd na Yahoo. Uitbreidbaar met extra
# bronnen door een functie (isin)->(prijs,munt) toe te voegen aan deze lijst.
# onvista eerst: open API zonder salt/TLS-verdediging die ook derivaten dekt.
# Daarna Börse Frankfurt (intraday bied/laat), Tradegate en Lang & Schwarz.
_ISIN_PROVIDERS = [_price_onvista, _price_boerse_frankfurt, _price_tradegate, _price_lang_schwarz]


def probe_isin_meta(isin: str) -> dict:
    """Zoek naam/type/beurs voor een ISIN die niet op Yahoo staat, zodat het
    activaformulier ook 'Naam' en 'Beurs' kan voorinvullen. Probeert eerst
    onvista (geeft naam + type terug), anders de instrument_information van
    Börse Frankfurt. Geeft {} terug als niets gevonden wordt."""
    if not _isin_valid(isin):
        return {}
    it = _onvista_search(isin)
    if it:
        etype = (it.get("entityType") or "").upper()
        type_map = {"STOCK": "stock", "FUND": "etf", "ETF": "etf", "DERIVATIVE": "stock",
                   "BOND": "bond"}
        return {"name": it.get("name") or "", "type": type_map.get(etype, "stock"),
               "exchange": ""}
    data = _bf_request("instrument_information", {"isin": isin})
    if isinstance(data, dict):
        name = None
        def _find_name(obj):
            nonlocal name
            if name or not isinstance(obj, dict):
                return
            for key in ("name", "instrumentName", "shortName"):
                v = obj.get(key)
                if isinstance(v, str) and v:
                    name = v
                    return
            for v in obj.values():
                _find_name(v)
        _find_name(data)
        if name:
            return {"name": name, "type": "stock", "exchange": "Frankfurt"}
    return {}


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
    names = {"_price_tradegate": "Tradegate", "_price_boerse_frankfurt": "Börse Frankfurt",
             "_price_lang_schwarz": "Lang & Schwarz", "_price_onvista": "onvista"}
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


def _yf_symbol(ticker: str) -> str | None:
    """Yahoo-veilig symbool voor een ticker. Is het ticker een ISIN, dan wordt
    eerst een verhandelbaar symbool opgezocht (rauwe ISIN's laten yfinance een
    exception gooien zodra Yahoo ze niet kent). Geen symbool -> None."""
    cand = (ticker or "").strip().upper()
    if _isin_valid(cand):
        return _yahoo_symbol_for_isin(cand)
    return ticker


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
    dag is (zonder latere split-/dividendcorrectie). Is het ticker een ISIN zonder
    Yahoo-notering (bv. een warrant), dan wordt eerst een Yahoo-symbool opgezocht
    en anders teruggevallen op onvista/Tradegate — geen rauwe ISIN naar yfinance
    (dat gooit een 'Invalid ISIN number'-exception)."""
    cand = (ticker or "").strip().upper()
    if _isin_valid(cand):
        sym = _yahoo_symbol_for_isin(cand)
        if sym:
            try:
                d = datetime.strptime(on_date[:10], "%Y-%m-%d")
                start = (d - timedelta(days=10)).strftime("%Y-%m-%d")
                end = (d + timedelta(days=1)).strftime("%Y-%m-%d")
                hist = yf.Ticker(sym).history(start=start, end=end, auto_adjust=False)
                if not hist.empty:
                    return round(float(hist["Close"].iloc[-1]), 4)
            except Exception as e:
                logger.warning(f"get_close_on_date({ticker},{on_date}) via {sym}: {e}")
        price = _onvista_close_on_date(cand, on_date)
        if price is not None:
            return price
        p, _ = _price_tradegate(cand)
        return p
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
    sym = _yf_symbol(ticker)
    if not sym:
        return "UNKNOWN"
    try:
        info = yf.Ticker(sym).info
        return info.get("marketState", "CLOSED")
    except Exception:
        return "UNKNOWN"