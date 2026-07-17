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
_ISIN_QUOTE_CACHE: dict[str, dict] = {}
_ISIN_QUOTES_CACHE: dict[str, list] = {}   # alle kandidaten per ISIN (punt 2/3)


def _yahoo_isin_quote(isin: str) -> dict:
    """Volledige Yahoo-zoekresultaat voor een ISIN (symbol, shortname/longname, ...),
    of {}. Wordt gecachet zodat _yahoo_symbol_for_isin en de naamopzoeking in
    probe_isin_meta dezelfde ene netwerkcall hergebruiken — Yahoo's zoekresultaat
    bevat vaak al een naam, ook voor effecten zonder live Yahoo-koers."""
    if not _isin_valid(isin):
        return {}
    if isin in _ISIN_QUOTE_CACHE:
        return _ISIN_QUOTE_CACHE[isin]
    quote = {}
    try:
        import requests
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": isin, "quotesCount": 6, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.ok:
            quotes = resp.json().get("quotes", [])
            if quotes:
                quote = quotes[0]
    except Exception as e:
        logger.warning(f"_yahoo_isin_quote({isin}): {e}")
    _ISIN_QUOTE_CACHE[isin] = quote
    return quote


def _yahoo_symbol_for_isin(isin: str) -> str | None:
    """Zoek via het Yahoo search-endpoint een verhandelbaar symbool voor een ISIN."""
    if not _isin_valid(isin):
        return None
    if isin in _ISIN_SYMBOL_CACHE:
        return _ISIN_SYMBOL_CACHE[isin] or None
    sym = _yahoo_isin_quote(isin).get("symbol") or ""
    _ISIN_SYMBOL_CACHE[isin] = sym
    return sym or None


# ── Statuscontrole: tickerwijziging, meerdere producten, splits, naam (punt 2/3) ──

def _yahoo_isin_candidates(isin: str) -> list[dict]:
    """ALLE Yahoo-zoekresultaten voor een ISIN (niet enkel de eerste). Elk item:
    {'symbol','name','quoteType','exchange'}. Basis voor het opsporen van een
    tickerwijziging of van meerdere producten onder dezelfde ISIN (bv. SK Hynix, waar
    het oude symbool blijft bestaan maar niet meer beweegt naast het nieuwe)."""
    if not _isin_valid(isin):
        return []
    if isin in _ISIN_QUOTES_CACHE:
        return _ISIN_QUOTES_CACHE[isin]
    out = []
    try:
        import requests
        resp = requests.get(
            "https://query2.finance.yahoo.com/v1/finance/search",
            params={"q": isin, "quotesCount": 8, "newsCount": 0},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.ok:
            for q in resp.json().get("quotes", []):
                sym = (q.get("symbol") or "").strip()
                if not sym:
                    continue
                out.append({
                    "symbol":    sym,
                    "name":      q.get("longname") or q.get("shortname") or "",
                    "quoteType": (q.get("quoteType") or "").upper(),
                    "exchange":  q.get("exchDisp") or q.get("exchange") or "",
                })
    except Exception as e:
        logger.warning(f"_yahoo_isin_candidates({isin}): {e}")
    _ISIN_QUOTES_CACHE[isin] = out
    return out


def _yahoo_symbol_activity(symbol: str) -> tuple[float | None, float | None]:
    """(koers, epoch van de laatste noteringstijd) voor een Yahoo-symbool, of (None,None).
    De noteringstijd (regularMarketTime) onderscheidt een nog-verhandeld symbool van een
    'bevroren' oud symbool dat wel nog een (oude) slotkoers teruggeeft."""
    if not symbol:
        return None, None
    try:
        import requests
        resp = requests.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"range": "5d", "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0"}, timeout=6)
        if resp.ok:
            results = (resp.json().get("chart", {}) or {}).get("result") or []
            if results:
                meta = results[0].get("meta", {}) or {}
                price = _to_float(meta.get("regularMarketPrice"))
                t = meta.get("regularMarketTime")
                return price, (float(t) if t else None)
    except Exception as e:
        logger.info(f"_yahoo_symbol_activity({symbol}): {e}")
    return None, None


def resolve_active_symbol(isin: str) -> dict:
    """Kies uit de Yahoo-kandidaten voor een ISIN het symbool dat het RECENTST verhandeld
    werd (hoogste regularMarketTime). Zo wint bij een tickerwijziging het nieuwe, actieve
    symbool van het oude, bevroren symbool. Geeft {'symbol','candidates','multiple'}."""
    cands = _yahoo_isin_candidates(isin)
    if not cands:
        return {"symbol": None, "candidates": [], "multiple": False}
    best_sym, best_t = None, -1.0
    for c in cands[:6]:   # begrens netwerkcalls; Yahoo sorteert op relevantie
        price, t = _yahoo_symbol_activity(c["symbol"])
        c["price"] = price
        c["market_time"] = t
        if t is not None and t > best_t:
            best_t, best_sym = t, c["symbol"]
    if best_sym is None:
        with_price = [c for c in cands if c.get("price") is not None]
        best_sym = (with_price[0]["symbol"] if with_price else cands[0]["symbol"])
    return {"symbol": best_sym, "candidates": cands,
            "multiple": len({c["symbol"].upper() for c in cands}) > 1}


_NAME_NOISE = ("inc", "inc.", "incorporated", "corp", "corp.", "corporation", "co",
               "co.", "ltd", "ltd.", "limited", "plc", "ag", "nv", "n.v.", "sa",
               "s.a.", "se", "the", "holding", "holdings", "group", "adr",
               "american", "depositary", "shares", "class", "when", "issued")


def _norm_name(s: str) -> str:
    import re
    s = (s or "").lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [w for w in s.split() if w and w not in _NAME_NOISE]
    return " ".join(toks)


def _name_differs(stored: str, yahoo: str) -> bool:
    """True als twee namen duidelijk verschillen (na normalisatie: hoofdletters,
    leestekens en veelvoorkomende suffixen weg). Conservatief, om ruis te vermijden:
    is de ene naam een deel van de andere, dan tellen ze als gelijk."""
    a, b = _norm_name(stored), _norm_name(yahoo)
    if not a or not b:
        return False
    if a == b or a in b or b in a:
        return False
    aw, bw = set(a.split()), set(b.split())
    overlap = len(aw & bw) / max(1, len(aw | bw))
    return overlap < 0.34


def asset_status_probe(asset: dict, online: bool = True) -> dict:
    """Netwerk-gebaseerde statuscontrole voor één activum. Geeft:
      {'resolved_symbol': str|None, 'events': [{kind,severity,message,detail}, ...],
       'splits': [(datum, ratio), ...]}
    Volledig defensief: bij offline of netwerkfouten geen events en geen crash.

    Checks: (1) tickerwijziging / meerdere producten onder één ISIN — kiest meteen het
    actieve symbool, (2) uitgevoerde aandelensplits via yfinance, (3) een naam die bij de
    bron afwijkt (mogelijke rebranding/fusie-indicatie)."""
    ticker = (asset.get("ticker") or "").upper()
    isin = (asset.get("isin") or "").strip().upper()
    stored_sym = (asset.get("resolved_symbol") or "").strip().upper() or None
    events, detected_splits, new_sym = [], [], None

    if not online:
        return {"resolved_symbol": stored_sym, "events": [], "splits": []}

    # 1) Tickerwijziging / meerdere producten onder dezelfde ISIN
    if _isin_valid(isin):
        try:
            res = resolve_active_symbol(isin)
            new_sym = (res.get("symbol") or "").upper() or None
            cand_syms = sorted({c["symbol"].upper() for c in res.get("candidates", [])})
            if new_sym and stored_sym and new_sym != stored_sym:
                events.append({
                    "kind": "ticker_change", "severity": "warning",
                    "message": f"Actief Yahoo-symbool gewijzigd: {stored_sym} → {new_sym}.",
                    "detail": {"old": stored_sym, "new": new_sym, "candidates": cand_syms},
                })
            elif len(cand_syms) > 1:
                events.append({
                    "kind": "ticker_change", "severity": "info",
                    "message": (f"Meerdere producten op Yahoo voor deze ISIN "
                                f"({', '.join(cand_syms)}); actief gekozen: {new_sym}."),
                    "detail": {"new": new_sym, "candidates": cand_syms},
                })
        except Exception as e:
            logger.info(f"asset_status_probe/ticker({ticker}): {e}")

    probe_sym = new_sym or stored_sym or (ticker if not _isin_valid(ticker) else None)

    # 2) Uitgevoerde aandelensplits
    if probe_sym:
        try:
            spl = yf.Ticker(probe_sym).splits
            if spl is not None and len(spl):
                for dt, ratio in spl.items():
                    d = dt.strftime("%Y-%m-%d") if hasattr(dt, "strftime") else str(dt)[:10]
                    r = float(ratio)
                    if r and abs(r - 1.0) > 1e-9:
                        detected_splits.append((d, r))
        except Exception as e:
            logger.info(f"asset_status_probe/splits({probe_sym}): {e}")

    # 3) Naamsafwijking (rebranding/fusie-indicatie)
    if probe_sym:
        try:
            info = yf.Ticker(probe_sym).info or {}
            yname = (info.get("longName") or info.get("shortName") or "").strip()
            stored_name = (asset.get("name") or "").strip()
            if yname and stored_name and _name_differs(stored_name, yname):
                events.append({
                    "kind": "name_change", "severity": "info",
                    "message": f"Naam bij de bron wijkt af: '{stored_name}' ↔ '{yname}'.",
                    "detail": {"stored": stored_name, "yahoo": yname},
                })
        except Exception as e:
            logger.info(f"asset_status_probe/name({probe_sym}): {e}")

    return {"resolved_symbol": (new_sym or stored_sym), "events": events,
            "splits": detected_splits}


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


import threading
_BF_LOCK = threading.Lock()  # gedeelde BF-sessie + salt-/blok-status zijn niet
                             # thread-safe; koersen worden sinds 0.30.0 parallel
                             # opgehaald, dus BF-calls verlopen een voor een


def _bf_request(function: str, params: dict, _retry: bool = True):
    """GET naar https://api.boerse-frankfurt.de/v1/data/<function>?<params> via de
    gedeelde sessie met de vereiste headers. Bij een 403 wordt eenmalig de salt vers
    opgehaald en opnieuw geprobeerd (de salt roteert af en toe). Blijft het 403, dan
    pauzeert de provider met exponentiële backoff (30s, 60s, 120s, ... max 10 min)
    zodat een tijdelijke weigering de interactieve app niet lang blokkeert; een
    geslaagde call reset de backoff. Logt status én een stukje van het antwoord.
    Deze functie is geserialiseerd met een lock (zie _BF_LOCK)."""
    import time
    import urllib.parse
    with _BF_LOCK:
        return _bf_request_locked(function, params, _retry)


def _bf_request_locked(function: str, params: dict, _retry: bool = True):
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
            return _bf_request_locked(function, params, _retry=False)
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


# ── Euronext Live ────────────────────────────────────────────────────────────
# live.euronext.com heeft sleutelloze JSON-endpoints (dezelfde die de site zelf
# gebruikt, en die ook door meerdere open-sourceprojecten worden aangesproken).
# Dit is DE bron voor effecten die enkel op Euronext noteren en die de Duitse
# platformen (onvista/Tradegate/L&S/Boerse Frankfurt) niet kennen - zoals de
# ING Markets-warrants (bv. NL0015002RI2) op Euronext Amsterdam, maar evengoed
# illiquide fondsen op Euronext Brussel.

_EURONEXT_MIC_CACHE: dict[str, str] = {}   # isin -> werkende MIC (bv. XAMS)

# Kandidaat-handelsplaatsen per ISIN-landcode. Wordt afgetast als het zoek-endpoint
# niets teruggeeft (dat gebeurt o.a. voor gestructureerde producten/warrants, die niet
# in de gewone instrumentenzoeker zitten). Volgorde = meest waarschijnlijk eerst.
_EURONEXT_MIC_CANDIDATES = {
    "NL": ["XAMS", "TNLA", "ALXA", "MTAA"],
    "BE": ["XBRU", "ALXB", "MLXB", "TNLB"],
    "FR": ["XPAR", "ALXP", "XMLI"],
    "PT": ["XLIS", "ALXL"],
    "IE": ["XMSM", "XESM"],
    "NO": ["XOSL", "MERK"],
    "IT": ["MTAA", "ETLX"],
    "DE": ["XAMS", "XPAR"],   # DE-ISIN's van emittenten die op Euronext noteren
    "LU": ["XAMS", "XPAR"],
}
_EURONEXT_DEFAULT_MICS = ["XAMS", "XBRU", "XPAR"]


def _euronext_mic_candidates(isin: str) -> list[str]:
    seen, out = set(), []
    for m in _EURONEXT_MIC_CANDIDATES.get(isin[:2], []) + _EURONEXT_DEFAULT_MICS:
        if m not in seen:
            seen.add(m)
            out.append(m)
    return out


def _euronext_headers() -> dict:
    return {"User-Agent": _BF_BROWSER_HEADERS["User-Agent"],
            "Accept": "*/*",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": "https://live.euronext.com/"}


def _euronext_search_mic(isin: str) -> str | None:
    """Handelsplaats (MIC) via het zoek-endpoint van Euronext Live.

    Het antwoord verschilt per instrumenttype (soms JSON, soms HTML-fragment, en de
    sleutelnamen wisselen). Daarom zoeken we niet naar vaste sleutels maar naar het
    'DNA' dat Euronext overal gebruikt: de tekst ISIN-MIC (bv. NL0011794037-XAMS).
    Dat werkt ongeacht de vorm van het antwoord. Niets gevonden -> None."""
    import re
    import requests
    try:
        resp = requests.get("https://live.euronext.com/en/instrumentSearch/searchJSON",
                            params={"q": isin}, headers=_euronext_headers(), timeout=8)
        if not resp.ok:
            logger.info(f"_euronext_search_mic({isin}): HTTP {resp.status_code}")
            return None
        m = re.search(rf"{re.escape(isin)}-([A-Z0-9]{{4}})", resp.text or "")
        if m:
            return m.group(1)
        logger.info(f"_euronext_search_mic({isin}): niet gevonden in de zoeker "
                    f"(antwoord {len(resp.text or '')} tekens) — handelsplaatsen worden afgetast")
    except Exception as e:
        logger.warning(f"_euronext_search_mic({isin}): {e}")
    return None


def _euronext_num(txt: str) -> float | None:
    """Getal uit een cel van Euronext Live. We vragen de ENGELSE pagina op, dus daar geldt
    '1,234.56' (komma = duizendtal). Maar de cel kan ook '12,34' bevatten als Euronext
    lokaliseert. Regel: staan er zowel een komma als een punt in, dan is de LAATSTE het
    decimaalteken. Staat er enkel een komma en volgen er exact drie cijfers na, dan is het
    een duizendtalscheiding (1,234); anders is het het decimaalteken (12,34)."""
    import re
    if not txt:
        return None
    t = re.sub(r"[^0-9,.\-]", "", txt.replace("\u202f", "").replace("\u00a0", ""))
    if not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        dec = "," if t.rindex(",") > t.rindex(".") else "."
        t = t.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in t:
        frac = t.split(",")[-1]
        t = t.replace(",", "" if (len(frac) == 3 and t.count(",") >= 1) else ".")
    try:
        return float(t)
    except ValueError:
        return None


def _euronext_table(html: str) -> dict[str, str]:
    """Het detailed-quote-fragment van Euronext is een HTML-TABEL (label | waarde | tijdstip).
    We parsen ze generiek naar {label_in_kleine_letters: waarde} in plaats van met vaste
    regexes per label: de opmaak van de labelcel varieert (soms <td>, soms <th>, soms met
    <strong> errond), en dat deed de vorige, positionele regex stilzwijgend falen — de reden
    dat 'bestaat (HTTP 200) maar geeft geen koers terug' in je log verscheen."""
    import html as _html
    import re
    out: dict[str, str] = {}

    def _clean(cell: str) -> str:
        txt = re.sub(r"<[^>]+>", " ", cell)
        return re.sub(r"\s+", " ", _html.unescape(txt)).strip()

    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
        if len(cells) < 2:
            continue
        key, val = _clean(cells[0]).lower(), _clean(cells[1])
        if key and key not in out:
            out[key] = val
    return out


# Labels waarin een bruikbare koers kan staan, in volgorde van voorkeur. Voor een illiquide
# product (warrant zonder trade vandaag) is de laatste koers vaak leeg en moeten we terugvallen
# op de waarderings-/slotkoers of op bied/laat.
_EURONEXT_PRICE_LABELS = [
    "last traded price", "last price", "laatste koers", "dernier cours",
    "valuation price", "valuation close", "closing price", "previous close",
    "vorige slotkoers", "clôture précédente", "bid", "ask", "bied", "laat",
]


def _euronext_price_from_table(tbl: dict[str, str]) -> tuple[float | None, str | None, str | None]:
    """(prijs, munt, gebruikt_label) uit de geparste tabel. Zoekt eerst op exact label,
    daarna op deellabel (Euronext varieert: 'Last traded price' vs 'Last traded price *')."""
    cur = None
    for k in ("currency", "valuta", "devise"):
        if tbl.get(k):
            import re
            m = re.search(r"[A-Z]{3}", tbl[k])
            if m:
                cur = m.group(0)
                break
    for lbl in _EURONEXT_PRICE_LABELS:
        raw = tbl.get(lbl)
        if raw is None:
            match = next((v for k, v in tbl.items() if lbl in k), None)
            raw = match
        if raw is None:
            continue
        price = _euronext_num(raw)
        if price:
            if not cur:
                if "€" in raw or "EUR" in raw.upper():
                    cur = "EUR"
                elif "$" in raw:
                    cur = "USD"
            return price, cur or "EUR", lbl
    return None, cur, None


def _euronext_quote(isin: str, mic: str) -> tuple[float | None, str | None, int]:
    """(prijs, munt, http-status) via het detailed-quote-fragment van Euronext Live.
    Endpoint: /en/intraday_chart/getDetailedQuoteAjax/<ISIN>-<MIC>/full (GET).

    Een onbekend instrument geeft 404 OF een 200 zonder tabel; daarom telt hier enkel een
    ECHTE tabel als bewijs dat het instrument bestaat (zie _euronext_quote_table)."""
    price, cur, status, _tbl = _euronext_quote_table(isin, mic)
    return price, cur, status


def _euronext_quote_table(isin: str, mic: str):
    """Zoals _euronext_quote, maar geeft ook de geparste tabel terug — nodig om (a) te weten
    of het instrument echt bestaat en (b) te loggen WELKE labels Euronext teruggeeft wanneer
    er geen koers uit te halen valt."""
    import requests
    url = ("https://live.euronext.com/en/intraday_chart/getDetailedQuoteAjax/"
           f"{isin}-{mic}/full")
    try:
        resp = requests.get(url, headers=_euronext_headers(), timeout=8)
        if not resp.ok:
            return None, None, resp.status_code, {}
        tbl = _euronext_table(resp.text or "")
        price, cur, lbl = _euronext_price_from_table(tbl)
        if price:
            logger.info(f"_euronext_quote({isin},{mic}): koers {price} {cur} via label '{lbl}'")
        return price, cur, resp.status_code, tbl
    except Exception as e:
        logger.warning(f"_euronext_quote({isin},{mic}): {e}")
        return None, None, 0, {}


def _euronext_chart_last(isin: str, mic: str, period: str) -> float | None:
    """Recentste koerspunt uit de chartdata van Euronext Live ('intraday' voor vandaag,
    'max' voor de volledige daghistoriek). Geeft None bij lege data."""
    import requests
    try:
        resp = requests.get(f"https://live.euronext.com/intraday_chart/getChartData/"
                            f"{isin}-{mic}/{period}",
                            headers=_euronext_headers(), timeout=8)
        if not resp.ok:
            return None
        try:
            pts = resp.json()
        except ValueError:
            return None
        if isinstance(pts, dict):
            pts = pts.get("data") or []
        if isinstance(pts, list) and pts:
            last = pts[-1]
            if isinstance(last, dict):
                return _to_float(last.get("price") or last.get("close") or last.get("last")
                                 or last.get("value"))
            if isinstance(last, (list, tuple)) and len(last) > 1:
                return _to_float(last[1])
    except Exception as e:
        logger.warning(f"_euronext_chart_last({isin},{mic},{period}): {e}")
    return None


def _euronext_resolve(isin: str) -> str | None:
    """De werkende handelsplaats (MIC) voor een ISIN, of None als Euronext het
    instrument niet kent. Eerst de zoeker; levert die niets op (typisch voor warrants
    en andere gestructureerde producten), dan worden de kandidaat-MIC's van het land
    ECHT AFGETAST tegen het quote-endpoint. Het resultaat wordt gecachet — ook een
    negatief resultaat, zodat we niet elke 5 minuten opnieuw 4 beurzen aftasten."""
    if isin in _EURONEXT_MIC_CACHE:
        return _EURONEXT_MIC_CACHE[isin] or None
    mic = _euronext_search_mic(isin)
    if mic:
        _EURONEXT_MIC_CACHE[isin] = mic
        logger.info(f"_euronext_resolve({isin}): handelsplaats {mic} (via de zoeker)")
        return mic
    # Aftasten. HTTP 200 alleen is GEEN bewijs: Euronext geeft ook 200 op een leeg fragment.
    # Enkel een echt geparste tabel (>= 3 rijen) telt als "dit instrument bestaat hier".
    best = None
    for cand in _euronext_mic_candidates(isin):
        price, _cur, status, tbl = _euronext_quote_table(isin, cand)
        if status == 200 and len(tbl) >= 3:
            _EURONEXT_MIC_CACHE[isin] = cand
            logger.info(f"_euronext_resolve({isin}): handelsplaats {cand} (afgetast, "
                        f"{len(tbl)} tabelrijen"
                        + (f", koers {price}" if price else ", nog geen koers")
                        + ")")
            return cand
        if status == 200 and best is None:
            best = cand
    _EURONEXT_MIC_CACHE[isin] = ""
    if best:
        logger.info(f"_euronext_resolve({isin}): {best} gaf wel HTTP 200 maar een LEEG fragment "
                    "(geen instrumenttabel) — Euronext kent dit instrument dus niet.")
    else:
        logger.info(f"_euronext_resolve({isin}): Euronext kent dit instrument niet "
                    f"(geen van {', '.join(_euronext_mic_candidates(isin))} gaf een tabel)")
    return None


def _price_euronext(isin: str) -> tuple[float | None, str | None]:
    """(prijs, munt) via Euronext Live — de bron voor effecten die enkel op Euronext
    noteren en die de Duitse platformen niet kennen. Werkwijze: handelsplaats bepalen
    (zoeker of aftasten), dan de detailed quote (dekt ook illiquide producten zonder
    trade vandaag via de bied-/laat-/vorige koers), en als terugval de chartdata."""
    if not _isin_valid(isin):
        return None, None
    mic = _euronext_resolve(isin)
    if not mic:
        return None, None
    price, currency, status, tbl = _euronext_quote_table(isin, mic)
    if price:
        return price, currency or "EUR"
    for period in ("intraday", "max"):
        p = _euronext_chart_last(isin, mic, period)
        if p:
            logger.info(f"_price_euronext({isin}): koers {p} via de chartdata ({period})")
            return p, currency or "EUR"
    # Geen koers gevonden: log WELKE labels Euronext wél teruggaf. Zo is meteen zichtbaar of
    # het label anders heet (dan kan het aan _EURONEXT_PRICE_LABELS worden toegevoegd) of dat
    # alle koersvelden gewoon leeg staan (dan is er echt geen notering).
    if tbl:
        preview = "; ".join(f"{k}={v!r}" for k, v in list(tbl.items())[:14])
        logger.info(f"_price_euronext({isin}): {isin}-{mic} bestaat (HTTP {status}) maar geen "
                    f"koers uit de tabel. Labels van Euronext: {preview}")
    else:
        logger.info(f"_price_euronext({isin}): {isin}-{mic} gaf HTTP {status} zonder tabel.")
    return None, None


# Externe ISIN-bronnen, in volgorde geprobeerd na Yahoo. Uitbreidbaar met extra
# bronnen door een functie (isin)->(prijs,munt) toe te voegen aan deze lijst.
# onvista eerst: open API zonder salt/TLS-verdediging die ook derivaten dekt.
# Börse Frankfurt staat nu LAATST: hun WAF blijft ondanks dynamische salt en
# Chrome-TLS-imitatie regelmatig 403 geven, en elke poging kost door de
# salt-/cookie-/retry-afhandeling merkbaar meer tijd dan de andere drie bronnen.
# Zo kosten activa die toch al bij geen enkele bron gevonden worden (bv. heel
# illiquide warrants) niet nodeloos de traagste, minst betrouwbare poging eerst.
# Euronext staat direct na onvista: snel (2 kleine calls), sleutelloos, en het
# dekt precies het gat van de Duitse platformen - producten die enkel op
# Euronext noteren (ING Markets-warrants, illiquide Brusselse fondsen, ...).
_ISIN_PROVIDERS = [_price_onvista, _price_euronext, _price_tradegate,
                   _price_lang_schwarz, _price_boerse_frankfurt]


def probe_isin_meta(isin: str) -> dict:
    """Zoek naam/type/beurs voor een ISIN die niet op Yahoo staat, zodat het
    activaformulier ook 'Naam' en 'Beurs' kan voorinvullen. Probeert eerst het
    Yahoo-zoekresultaat (dat vaak al een naam bevat, ook zonder live Yahoo-koers —
    en die zoekopdracht gebeurt toch al elders in de flow, dus dit kost geen extra
    netwerkcall), dan onvista (geeft ook type terug), dan de instrument_information
    van Börse Frankfurt. Geeft {} terug als niets gevonden wordt."""
    if not _isin_valid(isin):
        return {}
    yq = _yahoo_isin_quote(isin)
    yname = yq.get("longname") or yq.get("shortname")
    ytype_map = {"EQUITY": "stock", "ETF": "etf", "MUTUALFUND": "etf", "BOND": "bond"}
    if yname:
        return {"name": yname, "type": ytype_map.get((yq.get("quoteType") or "").upper(), "stock"),
               "exchange": yq.get("exchDisp") or ""}
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
             "_price_lang_schwarz": "Lang & Schwarz", "_price_onvista": "onvista",
             "_price_euronext": "Euronext"}
    for provider in _ISIN_PROVIDERS:
        p, c = provider(isin)
        if p is not None:
            return p, c, names.get(provider.__name__, provider.__name__)
    return None, None, None


def diagnose_isin(isin: str) -> list[dict]:
    """Diagnose per koersbron voor één ISIN: wat antwoordt elke bron precies?

    Geeft een lijst van {bron, ok, koers, munt, detail} terug. Bedoeld voor de knop
    'Bronnen diagnose' in het activaoverzicht: zo zie je zwart op wit of een effect
    ergens gekend is, in plaats van enkel 'alle bronnen faalden'. Vindt GEEN ENKELE
    bron het instrument (ook Euronext niet), dan is het vrijwel zeker niet publiek
    genoteerd en is een handmatige koers het juiste antwoord — geen codeprobleem."""
    out: list[dict] = []
    if not _isin_valid(isin):
        return [{"bron": "—", "ok": False, "koers": None, "munt": None,
                 "detail": "Geen geldige ISIN (12 tekens, begint met 2 letters)."}]

    # 1) Yahoo via de ISIN
    sym = _yahoo_symbol_for_isin(isin)
    if sym:
        p, c = _price_from_yahoo_symbol(sym)
        out.append({"bron": f"Yahoo ({sym})", "ok": p is not None, "koers": p, "munt": c,
                    "detail": ("Symbool gevonden en koers opgehaald." if p is not None
                               else "Symbool gevonden, maar Yahoo geeft geen koers.")})
    else:
        out.append({"bron": "Yahoo", "ok": False, "koers": None, "munt": None,
                    "detail": "Yahoo kent deze ISIN niet (geen verhandelbaar symbool)."})

    # 2) Euronext — met de handelsplaats erbij, want die is het kernprobleem bij warrants
    mic = _euronext_resolve(isin)
    if mic:
        p, c, status, tbl = _euronext_quote_table(isin, mic)
        if p is None:
            keys = ", ".join(list(tbl)[:10]) or "(geen tabel)"
            detail = (f"Instrument gekend op {mic} (HTTP {status}, {len(tbl)} velden), maar geen "
                      f"koersveld met een waarde. Velden: {keys}")
        else:
            detail = f"Instrument gekend op {mic} (HTTP {status}); koers gevonden."
        out.append({"bron": f"Euronext ({mic})", "ok": p is not None, "koers": p, "munt": c,
                    "detail": detail})
    else:
        cands = ", ".join(_euronext_mic_candidates(isin))
        out.append({"bron": "Euronext", "ok": False, "koers": None, "munt": None,
                    "detail": f"Onbekend instrument: geen enkele handelsplaats ({cands}) "
                              "geeft een geldig antwoord."})

    # 3) De overige externe bronnen
    names = {"_price_onvista": "onvista", "_price_tradegate": "Tradegate",
             "_price_lang_schwarz": "Lang & Schwarz",
             "_price_boerse_frankfurt": "Börse Frankfurt"}
    for provider in _ISIN_PROVIDERS:
        if provider.__name__ == "_price_euronext":
            continue  # hierboven al, uitgebreider
        p, c = provider(isin)
        out.append({"bron": names.get(provider.__name__, provider.__name__),
                    "ok": p is not None, "koers": p, "munt": c,
                    "detail": ("Koers gevonden." if p is not None
                               else "Instrument niet gekend of geen koers (zie de log voor detail).")})
    return out


def _asset_isin(ticker: str) -> str:
    try:
        import database as _db
        a = _db.get_asset(ticker) or {}
        return (a.get("isin") or "").strip().upper()
    except Exception:
        return ""


def _resolved_symbol(ticker: str) -> str | None:
    """Laatst gevonden Yahoo-symbool voor de ISIN van dit activum (gemakskolom,
    NIET de bron van waarheid — dat is de ISIN zelf)."""
    try:
        import database as _db
        a = _db.get_asset(ticker) or {}
        return (a.get("resolved_symbol") or "").strip().upper() or None
    except Exception:
        return None


def _remember_resolved_symbol(ticker: str, symbol: str) -> None:
    try:
        import database as _db
        _db.update_asset(ticker, resolved_symbol=symbol)
    except Exception as e:
        logger.warning(f"_remember_resolved_symbol({ticker},{symbol}): {e}")


def _yf_symbol(ticker: str) -> str | None:
    """Yahoo-veilig symbool voor een ticker. Is het ticker een ISIN, dan wordt
    eerst een verhandelbaar symbool opgezocht (rauwe ISIN's laten yfinance een
    exception gooien zodra Yahoo ze niet kent). Geen symbool -> None."""
    cand = (ticker or "").strip().upper()
    if _isin_valid(cand):
        return _yahoo_symbol_for_isin(cand)
    return ticker


# Na zoveel mislukte pogingen op rij stopt de app met koersen ophalen voor een activum.
# Vijf bronnen die tien keer na elkaar niets vinden = geen tijdelijke storing.
MAX_PRICE_FAILURES = 10
_GIVEN_UP_LOGGED: set[str] = set()   # één waarschuwing per proces, geen logspam

_FAIL_CACHE: dict[str, float] = {}   # ticker -> epoch van laatste volledige mislukking
FAIL_CACHE_TTL = 1800  # 30 min — genoeg om herhaling elke 5 min te vermijden,
                       # kort genoeg om een terugkerende bron snel op te pikken


def get_current_price(ticker: str) -> tuple[float | None, str | None]:
    """Actuele koers + munt. De ISIN is de bron van waarheid voor koersopzoeking
    (uniek en ondubbelzinnig, i.t.t. een Yahoo-ticker met beurssuffix). Volgorde:
    1) ISIN → (gecachet) Yahoo-symbool, 2) ISIN → externe niet-Yahoo-bronnen,
    3) de opgeslagen ticker rechtstreeks op Yahoo (enkel als er géén ISIN is, of de
    ISIN niets oplevert), 4) handmatige koers als allerlaatste redmiddel.

    Faalden zonet nog ALLE online bronnen voor dit ticker, dan worden ze de
    eerstvolgende 30 minuten overgeslagen (rechtstreeks naar de handmatige koers) —
    dat scheelt 4+ netwerkcalls en flink wat logregels bij elke koersverversing
    (om de 5 min) voor een effect dat toch bij geen enkele bron gevonden wordt."""
    cached_price, cached_cur = _cached(ticker)
    if cached_price is not None:
        return cached_price, cached_cur

    # Enkel-handmatig: dit effect is nergens publiek genoteerd (bv. een niet-beursgenoteerde
    # warrant). Sla álle onlinebronnen over — anders kost elke koersverversing vijf mislukte
    # netwerkcalls en evenveel foutregels in de log, voor een koers die er toch niet is.
    try:
        import database as _db
        if _db.is_manual_only(ticker):
            mp = _db.get_manual_price(ticker)
            if mp:
                _store(ticker, mp["price"], mp["currency"])
                return mp["price"], mp["currency"]
            logger.info(f"get_current_price({ticker}): staat op 'enkel handmatig', maar er is "
                        "geen handmatige koers ingesteld.")
            return None, None

        # Faalgrens: tien keer op rij niets gevonden bij álle bronnen is geen tijdelijke
        # storing meer. Verdere pogingen zijn enkel verspilde netwerkcalls en logruis, dus
        # de app stopt met proberen tot je de teller terugzet (Activa → koersophaling
        # heractiveren) of een handmatige koers instelt.
        if _db.get_price_fail_count(ticker) >= MAX_PRICE_FAILURES:
            mp = _db.get_manual_price(ticker)
            if mp:
                _store(ticker, mp["price"], mp["currency"])
                return mp["price"], mp["currency"]
            if ticker not in _GIVEN_UP_LOGGED:
                _GIVEN_UP_LOGGED.add(ticker)
                logger.warning(
                    f"get_current_price({ticker}): {MAX_PRICE_FAILURES}x na elkaar geen koers "
                    "gevonden bij geen enkele bron — koersophaling is gestopt voor dit activum. "
                    "Zet een handmatige koers, of heractiveer het ophalen op de Activa-pagina.")
            return None, None
    except Exception as exc:
        logger.warning(f"get_current_price({ticker}): status-check faalde ({exc})")

    recently_failed = (time.time() - _FAIL_CACHE.get(ticker, 0)) < FAIL_CACHE_TTL

    isin = _asset_isin(ticker)
    ticker_is_isin = _isin_valid(ticker.strip().upper())
    if not _isin_valid(isin) and ticker_is_isin:
        isin = ticker.strip().upper()

    price, currency = None, None

    if not recently_failed:
        # 1) ISIN → Yahoo-symbool (eerst het laatst gevonden/gecachete symbool
        #    proberen, dat is sneller dan een nieuwe zoekopdracht en meestal nog
        #    steeds correct)
        if _isin_valid(isin):
            cached_sym = _resolved_symbol(ticker)
            for sym in ([cached_sym] if cached_sym else []) + [None]:
                if sym is None:
                    sym = _yahoo_symbol_for_isin(isin)
                if not sym:
                    continue
                p, c = _price_from_yahoo_symbol(sym)
                if p is not None:
                    price, currency = p, c
                    if sym != cached_sym:
                        _remember_resolved_symbol(ticker, sym)
                    break

        # 2) Externe (niet-Yahoo) bronnen op basis van de ISIN
        if price is None and _isin_valid(isin):
            for provider in _ISIN_PROVIDERS:
                p, c = provider(isin)
                if p is not None:
                    price, currency = p, c
                    break

        # 3) De opgeslagen ticker rechtstreeks op Yahoo — enkel als terugval (geen
        #    ISIN, of de ISIN leverde niets op). Niet bij een ISIN-als-ticker:
        #    yfinance gooit dan een exception zodra Yahoo de ISIN niet kent
        #    ("Invalid ISIN number").
        if price is None and not ticker_is_isin:
            price, currency = _price_from_yahoo_symbol(ticker)

    # 4) Handmatige koers — laatste redmiddel
    if price is None:
        try:
            import database as _db
            mp = _db.get_manual_price(ticker)
            if mp:
                _FAIL_CACHE.pop(ticker, None)
                return mp["price"], mp["currency"]
        except Exception:
            pass

    if price is not None:
        price = float(price)
        currency = currency or "EUR"
        _store(ticker, price, currency)
        _FAIL_CACHE.pop(ticker, None)
        # Gelukt: de faalteller terug op nul. Een tijdelijke storing mag een activum niet
        # stilaan naar de faalgrens duwen.
        try:
            import database as _db
            if _db.get_price_fail_count(ticker):
                _db.reset_price_failures(ticker)
                _GIVEN_UP_LOGGED.discard(ticker)
        except Exception:
            pass
        return price, currency

    if not recently_failed:
        _FAIL_CACHE[ticker] = time.time()
    # Mislukt: tel dit mee. Bereikt de teller MAX_PRICE_FAILURES, dan stopt de app hierboven
    # met verdere pogingen voor dit activum.
    try:
        import database as _db
        n = _db.record_price_failure(ticker)
        if n == MAX_PRICE_FAILURES:
            logger.warning(
                f"get_current_price({ticker}): {n}e mislukte poging op rij — koersophaling "
                "wordt voor dit activum GESTOPT. Zet een handmatige koers, of heractiveer het "
                "ophalen op de Activa-pagina.")
        elif n and n % 3 == 0:
            logger.info(f"get_current_price({ticker}): {n}/{MAX_PRICE_FAILURES} mislukte "
                        "pogingen op rij.")
    except Exception:
        pass
    return None, None


def get_prices_for_tickers(tickers: list[str], max_stale_minutes: int | None = None) -> dict[str, dict]:
    """Koersen voor een lijst tickers.

    max_stale_minutes=None (standaard, gedrag van de scheduler): alles live
    ophalen, maar nu PARALLEL i.p.v. een voor een - de totale duur wordt zo
    ongeveer die van het traagste effect i.p.v. de som van allemaal.

    max_stale_minutes=<n> (gebruikt door de app): lees eerst de recentste
    opgeslagen koers uit price_history (die de scheduler elke 5 minuten al
    bijwerkt in een apart proces). Is die jonger dan n minuten, dan is er GEEN
    enkele netwerkcall nodig en laadt de pagina vrijwel meteen. Enkel tickers
    zonder (verse) opgeslagen koers worden nog live (parallel) opgehaald."""
    result: dict[str, dict] = {}
    remaining = list(tickers)

    if max_stale_minutes is not None and remaining:
        try:
            import database as _db
            from datetime import datetime as _dt
            stored = _db.get_latest_prices(remaining)
            now = _dt.now()
            fresh_remaining = []
            for t in remaining:
                row = stored.get(t.upper())
                age_ok = False
                if row:
                    try:
                        ts = _dt.strptime(row["timestamp"][:19], "%Y-%m-%d %H:%M:%S")
                        age_ok = (now - ts).total_seconds() < max_stale_minutes * 60
                    except (ValueError, TypeError):
                        age_ok = False
                if row and age_ok:
                    cur = row.get("currency") or "EUR"
                    result[t] = {"price": row["price"], "currency": cur}
                    # Ook in de in-memory cache: losse get_current_price-aanroepen
                    # elders in de app (detailweergaves e.d.) zijn dan even snel.
                    _store(t, float(row["price"]), cur)
                else:
                    fresh_remaining.append(t)
            remaining = fresh_remaining
        except Exception as e:
            logger.warning(f"get_prices_for_tickers: opgeslagen koersen lezen faalde ({e}) "
                           "- terugval op live ophalen")

    if remaining:
        from concurrent.futures import ThreadPoolExecutor
        workers = min(8, len(remaining))
        with ThreadPoolExecutor(max_workers=workers) as ex:
            for ticker, (price, currency) in zip(remaining, ex.map(get_current_price, remaining)):
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
    Yahoo-notering (bv. een warrant), dan wordt eerst een Yahoo-symbool opgezocht,
    anders teruggevallen op onvista of Börse Frankfurt (beide echte HISTORISCHE
    koersen) — geen rauwe ISIN naar yfinance (dat gooit een 'Invalid ISIN number'-
    exception), en bewust GEEN actuele koers als terugval: dat zou een foutieve
    (want niet-historische) fotomomentwaarde in de belastingberekening kunnen
    invoeren. Geen resultaat betekent meestal gewoon dat dit effect op 31/12/2025
    nog niet bestond of niet verhandeld werd (bv. een pas in 2026 uitgegeven
    warrant) — dan is er sowieso geen fotomomentwaarde nodig."""
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
        return _bf_close_on_date(cand, on_date)
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


def _bf_close_on_date(isin: str, on_date: str) -> float | None:
    """Echte historische slotkoers via Börse Frankfurt (price_history), voor het
    fotomoment. Anders dan _price_boerse_frankfurt (actuele koers) wordt hier
    specifiek rond on_date gezocht, niet vandaag."""
    try:
        d = datetime.strptime(on_date[:10], "%Y-%m-%d")
    except Exception:
        return None
    for mic in _bf_available_mics(isin)[:6]:
        data = _bf_request("price_history",
                           {"isin": isin, "mic": mic, "limit": 30, "offset": 0,
                            "minDate": (d - timedelta(days=10)).strftime("%Y-%m-%d"),
                            "maxDate": (d + timedelta(days=1)).strftime("%Y-%m-%d"),
                            "cleanSplit": False, "cleanPayout": False,
                            "cleanSubscription": False})
        if isinstance(data, dict) and data.get("data"):
            rows = sorted(data["data"], key=lambda r: r.get("date") or "", reverse=True)
            for r in rows:
                price = _to_float(r.get("close") or r.get("last"))
                if price:
                    return round(price, 4)
    return None


_FX_HIST_CACHE: dict[tuple, float] = {}


def get_historical_exchange_rate(from_currency: str, on_date: str,
                                 to_currency: str = "EUR") -> float | None:
    """
    Wisselkoers from→to op (of vlak vóór) een specifieke datum 'YYYY-MM-DD'.
    Gebruikt voor het correct omrekenen van transacties op hun eigen datum.

    Permanent gecachet per (from, to, datum): een AFGESLOTEN handelsdag heeft een
    vaste slotkoers die niet meer verandert. Zonder deze cache leverde elke aparte
    aanroep (bv. één keer voor de TOB-preview, één keer bij het opslaan) een eigen
    netwerkcall op — bij een tijdelijke hapering viel die aparte call terug op de
    ACTUELE koers, waardoor TOB en het opgeslagen EUR-bedrag op een net iets andere
    koers gebaseerd konden zijn. Met deze cache geeft dezelfde (munt, datum)-combinatie
    binnen één sessie altijd exact dezelfde koers terug. De terugval-op-actuele-koers
    wordt bewust NIET gecachet, zodat een latere aanroep alsnog de echte historische
    koers kan ophalen zodra die (weer) beschikbaar is.
    """
    if from_currency == to_currency:
        return 1.0
    key = (from_currency, to_currency, str(on_date)[:10])
    if key in _FX_HIST_CACHE:
        return _FX_HIST_CACHE[key]
    pair = f"{from_currency}{to_currency}=X"
    try:
        d = datetime.strptime(on_date[:10], "%Y-%m-%d")
        start = (d - timedelta(days=7)).strftime("%Y-%m-%d")
        end = (d + timedelta(days=1)).strftime("%Y-%m-%d")
        hist = yf.Ticker(pair).history(start=start, end=end)
        if not hist.empty:
            rate = float(hist["Close"].iloc[-1])
            _FX_HIST_CACHE[key] = rate
            return rate
    except Exception as e:
        logger.warning(f"get_historical_exchange_rate({pair},{on_date}): {e}")
    # Val terug op de actuele koers als historisch niet lukt (bewust niet gecachet)
    return get_exchange_rate(from_currency, to_currency)


def get_price_series(ticker: str, start: str, end: str | None = None):
    """
    Dagelijkse slotkoersen (native valuta) als pandas Series, geïndexeerd op datum.
    Cache: 1 uur. Geeft None bij fout. Is het ticker een ISIN zonder Yahoo-notering
    (bv. een warrant), dan wordt eerst een Yahoo-symbool opgezocht — geen rauwe ISIN
    naar yfinance (dat gooit een 'Invalid ISIN number'-exception).
    """
    key = f"series:{ticker}:{start}:{end}"
    entry = _HIST_CACHE.get(key)
    if entry and (time.time() - entry[0]) < HIST_TTL:
        return entry[1]
    cand = (ticker or "").strip().upper()
    yf_ticker = ticker
    if _isin_valid(cand):
        sym = _yahoo_symbol_for_isin(cand)
        if not sym:
            return None  # geen Yahoo-notering voor deze ISIN; geen historische reeks beschikbaar
        yf_ticker = sym
    try:
        end = end or (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        hist = yf.Ticker(yf_ticker).history(start=start, end=end, auto_adjust=True)
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