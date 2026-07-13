"""Bulk-import van transacties, dividenden en rekeningkosten via een gestructureerde Excel.

Drie databladen: 'Transacties', 'Dividenden', 'Kosten'. Een vierde blad 'Instructies'
beschrijft de kolommen. Onbekende activa (tickers) worden automatisch aangemaakt op basis
van de optionele kolommen (naam/type/munt); vul die in voor een correcte TOB-berekening.

Alles is puur en testbaar: parse_workbook() valideert en geeft rijen + fouten terug;
apply_import() voert pas in na bevestiging.
"""

from __future__ import annotations
import io
from datetime import datetime, date

import pandas as pd

import logging
import database as db
import market_data as md
import belgian_tax as tax

logger = logging.getLogger(__name__)


# ── Kolomdefinities (voor de template en de instructies) ──────────────────────

TXN_COLUMNS = [
    "ticker", "type", "datum", "aantal", "prijs_per_stuk", "munt",
    "totaalbedrag", "fx_koers", "kosten", "kosten_munt", "rekening",
    "koersdoel", "performance_share", "personenbelasting_eur",
    "naam", "activumtype", "etf_type", "be_genoteerd", "land",
]
DIV_COLUMNS = [
    "ticker", "datum", "munt", "fx_koers",
    "bruto_voor_bronbelasting", "buitenlandse_bronbelasting",
    "bruto_na_bronbelasting", "netto", "rekening", "cash_basis", "kind",
]
COST_COLUMNS = ["rekening", "datum", "omschrijving", "bedrag", "munt"]

INSTRUCTIONS = [
    ("Blad", "Kolom", "Verplicht", "Uitleg"),
    ("Transacties", "ticker", "ja", "Symbool, bv. AAPL of VWCE.DE"),
    ("Transacties", "type", "ja", "buy / sell (of aankoop / verkoop)"),
    ("Transacties", "datum", "ja", "JJJJ-MM-DD, bv. 2026-03-15"),
    ("Transacties", "aantal", "ja", "Aantal stuks"),
    ("Transacties", "prijs_per_stuk", "ja", "Prijs per stuk in 'munt'"),
    ("Transacties", "munt", "nee", "Standaard EUR"),
    ("Transacties", "totaalbedrag", "nee", "Leeg = aantal × prijs_per_stuk"),
    ("Transacties", "fx_koers", "nee", "Leeg = historische koers op datum"),
    ("Transacties", "kosten", "nee", "Transactiekosten (standaard 0)"),
    ("Transacties", "kosten_munt", "nee", "Standaard EUR"),
    ("Transacties", "rekening", "nee", "Standaard de eerste rekening"),
    ("Transacties", "koersdoel", "nee", "Optioneel koersdoel (native munt)"),
    ("Transacties", "performance_share", "nee", "ja/nee — toekenning i.p.v. aankoop (geen TOB)"),
    ("Transacties", "personenbelasting_eur", "nee", "Enkel bij performance_share: betaalde belasting in EUR"),
    ("Transacties", "naam/activumtype/etf_type/be_genoteerd/land", "nee",
     "Enkel gebruikt om een NIEUW activum aan te maken (type=stock/etf/bond, etf_type=distributing/accumulating, be_genoteerd=ja/nee, land=2-letterige code bv. US)"),
    ("Dividenden", "ticker / datum", "ja", "Zoals bij transacties"),
    ("Dividenden", "munt / fx_koers", "nee", "Standaard EUR / historische koers"),
    ("Dividenden", "bruto_voor_bronbelasting", "nee", "A: bruto vóór buitenlandse bronbelasting"),
    ("Dividenden", "buitenlandse_bronbelasting", "nee", "B: buitenlandse bronbelasting"),
    ("Dividenden", "bruto_na_bronbelasting", "nee", "C: bruto na bronbelasting (= A − B)"),
    ("Dividenden", "netto", "nee", "D: netto na Belgische RV. Lege velden worden afgeleid."),
    ("Dividenden", "cash_basis", "nee", "Welk veld naar het cash-grootboek gaat: netto (standaard), bruto_na of bruto_voor"),
    ("Dividenden", "kind", "nee", "dividend (standaard), interest of securities_lending — enkel dividend telt voor de 833-vrijstelling"),
    ("Kosten", "rekening / datum / bedrag", "ja", "Rekeningkost (beheerskosten e.d.)"),
    ("Kosten", "omschrijving / munt", "nee", "Standaard EUR"),
]


# ── Hulpfuncties ──────────────────────────────────────────────────────────────

def _is_blank(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    try:
        if pd.isna(v):
            return True
    except (TypeError, ValueError):
        pass
    return isinstance(v, str) and v.strip() == ""


def _f(v):
    """Naar float of None."""
    if _is_blank(v):
        return None
    if isinstance(v, str):
        v = v.strip().replace(" ", "").replace(",", ".")
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _s(v) -> str:
    return "" if _is_blank(v) else str(v).strip()


def _date(v) -> str | None:
    """Naar 'JJJJ-MM-DD' of None."""
    if _is_blank(v):
        return None
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s[:19] if len(s) > 10 else s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _yesno(v) -> bool:
    return _s(v).lower() in ("ja", "yes", "true", "1", "y", "j", "x")


def _norm_type(v) -> str | None:
    t = _s(v).lower()
    if t in ("buy", "aankoop", "koop", "b", "aankopen"):
        return "buy"
    if t in ("sell", "verkoop", "verkopen", "s"):
        return "sell"
    return None


def _compute_eur(amount, currency, date_str):
    """(fx_rate, eur_bedrag) op datum.

    Zelfde correctie als in app.py: NOOIT stilzwijgend terugvallen op koers 1,0 — dan
    zou het 'EUR-bedrag' gewoon het bedrag in vreemde munt zijn en werd de TOB (0,35%)
    op dat vreemde bedrag berekend. Lukt de historische koers niet, dan gebruiken we de
    actuele koers als benadering (met een waarschuwing in de log); lukt ook dat niet,
    dan geven we (None, None) terug zodat de import de rij als probleem meldt in plaats
    van een fout bedrag weg te schrijven."""
    if not amount or currency == "EUR":
        return 1.0, float(amount or 0.0)
    rate = md.get_historical_exchange_rate(currency, str(date_str), "EUR")
    if not rate:
        rate = md.get_exchange_rate(currency, "EUR")
        if rate:
            logger.warning(f"_compute_eur({currency},{date_str}): historische koers niet "
                           "beschikbaar — benaderd met de actuele koers.")
    if not rate:
        logger.error(f"_compute_eur({currency},{date_str}): geen wisselkoers gevonden.")
        return None, None
    return float(rate), float(amount) * float(rate)


# ── Inlezen + valideren ───────────────────────────────────────────────────────

def _read_sheet(xls, name) -> pd.DataFrame | None:
    if name not in xls.sheet_names:
        return None
    df = xls.parse(name)
    # normaliseer kolomnamen (lowercase, underscores)
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df


def parse_workbook(file) -> dict:
    """Lees en valideer een geüploade Excel. Geeft per blad geldige rijen + een
    foutenlijst terug. Voert NIETS in de database in."""
    result = {"transacties": [], "dividenden": [], "kosten": [], "errors": [],
              "new_assets": {}}
    try:
        xls = pd.ExcelFile(file, engine="openpyxl")
    except Exception as exc:
        result["errors"].append(f"Kon het Excel-bestand niet lezen: {exc}")
        return result

    known = {a["ticker"].upper() for a in db.get_assets()}
    accounts = db.get_accounts()
    default_acct = accounts[0] if accounts else db.DEFAULT_ACCOUNT

    # ── Transacties ──
    tdf = _read_sheet(xls, "Transacties")
    if tdf is not None:
        for i, row in tdf.iterrows():
            rn = i + 2  # +2: header + 1-indexed
            if all(_is_blank(row.get(c)) for c in ("ticker", "type", "datum", "aantal")):
                continue
            tk = _s(row.get("ticker")).upper()
            ttype = _norm_type(row.get("type"))
            d = _date(row.get("datum"))
            qty = _f(row.get("aantal"))
            price = _f(row.get("prijs_per_stuk"))
            errs = []
            if not tk:        errs.append("ticker ontbreekt")
            if not ttype:     errs.append("type moet buy/sell zijn")
            if not d:         errs.append("datum ongeldig (gebruik JJJJ-MM-DD)")
            if qty is None or qty <= 0:   errs.append("aantal ontbreekt/ongeldig")
            if price is None or price < 0: errs.append("prijs_per_stuk ontbreekt/ongeldig")
            if errs:
                result["errors"].append(f"Transacties rij {rn}: " + "; ".join(errs))
                continue
            cur = _s(row.get("munt")).upper() or "EUR"
            total = _f(row.get("totaalbedrag"))
            if total is None:
                total = qty * price
            acct = _s(row.get("rekening")) or default_acct
            perf = _yesno(row.get("performance_share"))
            rec = {
                "ticker": tk, "type": ttype, "date": d, "quantity": qty,
                "price_per_unit": price, "currency": cur, "total_amount": total,
                "fx_rate_in": _f(row.get("fx_koers")),
                "costs": _f(row.get("kosten")) or 0.0,
                "costs_currency": _s(row.get("kosten_munt")).upper() or "EUR",
                "account": acct,
                "price_target": _f(row.get("koersdoel")),
                "performance_share": perf,
                "income_tax_eur": _f(row.get("personenbelasting_eur")) or 0.0,
            }
            result["transacties"].append(rec)
            if tk not in known and tk not in result["new_assets"]:
                _land = _s(row.get("land")).upper()
                result["new_assets"][tk] = {
                    "name": _s(row.get("naam")) or tk,
                    "asset_type": (_s(row.get("activumtype")).lower() or "stock"),
                    "etf_subtype": (_s(row.get("etf_type")).lower() or "distributing"),
                    "currency": cur,
                    "belgian_registered": _yesno(row.get("be_genoteerd")) if not _is_blank(row.get("be_genoteerd")) else True,
                    "country": _land if len(_land) == 2 and _land.isalpha() else "BE",
                }

    # ── Dividenden ──
    ddf = _read_sheet(xls, "Dividenden")
    if ddf is not None:
        for i, row in ddf.iterrows():
            rn = i + 2
            if all(_is_blank(row.get(c)) for c in ("ticker", "datum")):
                continue
            tk = _s(row.get("ticker")).upper() or None
            d = _date(row.get("datum"))
            _kd = _s(row.get("kind")).lower()
            kind = {"dividend": "dividend", "interest": "interest", "interesten": "interest",
                    "securities_lending": "securities_lending", "lending": "securities_lending"}.get(_kd, "dividend")
            errs = []
            # Ticker is enkel verplicht bij een echt dividend — dat wordt altijd
            # door een specifiek activum uitgekeerd. Interest is meestal algemene
            # cash-rekeninginterest; securities lending is niet noodzakelijk aan
            # één activum gekoppeld. Beide mogen dus zonder ticker.
            if kind == "dividend" and not tk:
                errs.append("ticker ontbreekt (verplicht bij kind=dividend)")
            if not d:  errs.append("datum ongeldig")
            A = _f(row.get("bruto_voor_bronbelasting"))
            B = _f(row.get("buitenlandse_bronbelasting"))
            C = _f(row.get("bruto_na_bronbelasting"))
            D = _f(row.get("netto"))
            if A is None and C is None and D is None:
                errs.append("geef minstens een bruto- of nettobedrag")
            if errs:
                result["errors"].append(f"Dividenden rij {rn}: " + "; ".join(errs))
                continue
            cur = _s(row.get("munt")).upper() or "EUR"
            _cb = _s(row.get("cash_basis")).lower()
            cash_basis = {"netto": "net", "net": "net", "bruto_na": "gross_after",
                          "gross_after": "gross_after", "bruto_voor": "gross_before",
                          "gross_before": "gross_before"}.get(_cb, "net")
            result["dividenden"].append({
                "ticker": tk, "date": d, "currency": cur,
                "fx_rate_in": _f(row.get("fx_koers")),
                "A": A, "B": B, "C": C, "D": D,
                "account": _s(row.get("rekening")) or default_acct,
                "cash_basis": cash_basis, "kind": kind,
            })
            if tk and tk not in known and tk not in result["new_assets"]:
                result["new_assets"][tk] = {"name": tk, "asset_type": "stock",
                                            "etf_subtype": "distributing",
                                            "currency": cur, "belgian_registered": True,
                                            "country": "BE"}

    # ── Kosten ──
    cdf = _read_sheet(xls, "Kosten")
    if cdf is not None:
        for i, row in cdf.iterrows():
            rn = i + 2
            if all(_is_blank(row.get(c)) for c in ("rekening", "datum", "bedrag")):
                continue
            d = _date(row.get("datum"))
            amount = _f(row.get("bedrag"))
            errs = []
            if not d: errs.append("datum ongeldig")
            if amount is None or amount < 0: errs.append("bedrag ontbreekt/ongeldig")
            if errs:
                result["errors"].append(f"Kosten rij {rn}: " + "; ".join(errs))
                continue
            result["kosten"].append({
                "account": _s(row.get("rekening")) or default_acct,
                "date": d, "amount": amount,
                "currency": _s(row.get("munt")).upper() or "EUR",
                "description": _s(row.get("omschrijving")) or None,
            })

    return result


# ── Invoeren ──────────────────────────────────────────────────────────────────

def apply_import(parsed: dict) -> dict:
    """Voer de geparste, gevalideerde rijen in de database in. Maakt ontbrekende
    activa aan. Geeft een samenvatting met aantallen terug."""
    summary = {"assets": 0, "transacties": 0, "dividenden": 0, "kosten": 0, "errors": []}
    errors = summary["errors"]

    # 1) Ontbrekende activa aanmaken
    for tk, info in parsed.get("new_assets", {}).items():
        try:
            db.add_asset(tk, info["name"], info.get("asset_type", "stock"),
                         info.get("etf_subtype", "distributing"),
                         currency=info.get("currency", "EUR"),
                         belgian_registered=info.get("belgian_registered", True),
                         country=info.get("country", "BE"))
            summary["assets"] += 1
        except Exception:
            pass  # bestaat mogelijk al

    a_info = {a["ticker"]: a for a in db.get_assets()}

    # 2) Transacties
    for r in parsed.get("transacties", []):
        info = a_info.get(r["ticker"], {})
        # Een koers in het bestand = JOUW koers (die van je broker): die blijft bij de
        # transactie hangen en wordt niet overschreven door een latere herberekening.
        fx = r["fx_rate_in"]
        fx_manual = 1 if fx is not None else 0
        if fx is None:
            fx, tot_eur = _compute_eur(r["total_amount"], r["currency"], r["date"])
        else:
            tot_eur = r["total_amount"] * fx
        if fx is None or tot_eur is None:
            errors.append(f"{r['ticker']} {r['date']}: geen wisselkoers voor {r['currency']} — "
                          "vul een eigen koers in (kolom fx_rate) of voeg de transactie "
                          "handmatig toe.")
            continue
        _, costs_eur = _compute_eur(r["costs"], r["costs_currency"], r["date"])
        costs_eur = costs_eur or 0.0
        if r["performance_share"]:
            tob = 0.0
        else:
            tob = tax.calculate_tob(info.get("asset_type", "stock"),
                                    info.get("etf_subtype", "distributing"), tot_eur,
                                    bool(info.get("belgian_registered", 1)), txn_date=r["date"])
        db.add_transaction(r["ticker"], r["type"], r["date"], r["quantity"],
                           r["price_per_unit"], r["total_amount"], r["currency"], tob,
                           None, account=r["account"], costs=r["costs"],
                           costs_currency=r["costs_currency"], fx_rate=fx,
                           total_amount_eur=tot_eur, costs_eur=costs_eur,
                           price_target=r["price_target"],
                           is_performance_share=int(r["performance_share"]),
                           income_tax_eur=r["income_tax_eur"],
                           fx_manual=fx_manual)
        summary["transacties"] += 1

    # 3) Dividenden (keten aanvullen met tarieven, EUR via fx)
    _s = db.get_all_settings()
    rv_rate = float(_s.get("withholding_tax_rate", "0.30"))
    for r in parsed.get("dividenden", []):
        cur = r["currency"]
        info = a_info.get(r["ticker"], {})
        atype = info.get("asset_type", "stock")
        country = (info.get("country") or "BE").upper()
        # Tarief van het jaar van het dividend (bronbelastingen wijzigen over de jaren)
        wht_rate = tax.get_wht_rate(country, tax.year_of(r["date"]))
        kind = r.get("kind", "dividend")
        # Interesten/securities lending: geen buitenlandse bronbelasting-driehoek, wel RV
        _wht = wht_rate if (kind == "dividend" and country != "BE") else 0.0
        ch = tax.resolve_dividend_chain(r["A"], r["B"], r["C"], r["D"],
                                        rv_rate=rv_rate, wht_rate=_wht)
        fx = r["fx_rate_in"]
        if fx is None:
            fx, _ = _compute_eur(1.0, cur, r["date"]) if cur != "EUR" else (1.0, 1.0)
        gross = ch["a"] if ch["a"] is not None else (ch["c"] if ch["c"] is not None else (r["D"] or 0.0))
        wht_foreign = ch["b"] or 0.0
        rv = ch["rv"] or 0.0
        withholding = wht_foreign + rv
        net = ch["d"] if ch["d"] is not None else (gross - withholding)
        cbk = r.get("cash_basis") or "net"
        cash_native = {"gross_before": ch["a"], "gross_after": ch["c"], "net": net}.get(cbk)
        if cash_native is None:
            cash_native = net
        details = {
            "gross_before_wht": ch["a"], "gross_before_wht_cur": cur,
            "foreign_wht_amt": ch["b"], "foreign_wht_cur": cur,
            "gross_after_wht": ch["c"], "gross_after_wht_cur": cur,
            "belgian_rv_amt": ch["rv"], "net_received": ch["d"], "net_received_cur": cur,
            "net_eur": (net or 0.0) * fx,
            "cash_basis": cbk,
            "cash_eur": (cash_native or 0.0) * fx,
            "kind": kind,
        }
        db.add_dividend(r["ticker"], r["date"], gross, withholding, cur, None, fx,
                        gross_eur=(gross or 0.0) * fx, withholding_eur=(withholding or 0.0) * fx,
                        account=r["account"], details=details)
        summary["dividenden"] += 1

    # 4) Rekeningkosten
    for r in parsed.get("kosten", []):
        fx, amount_eur = _compute_eur(r["amount"], r["currency"], r["date"])
        db.add_account_cost(r["account"], r["date"], r["amount"], r["currency"],
                            r["description"], fx, amount_eur)
        summary["kosten"] += 1

    return summary


# ── Template ──────────────────────────────────────────────────────────────────

def build_template() -> bytes:
    """Genereer een lege Excel-template (bytes) met voorbeeldrijen en instructies."""
    accounts = db.get_accounts()
    acct = accounts[0] if accounts else "Hoofdrekening"

    txn_example = pd.DataFrame([
        {"ticker": "AAPL", "type": "buy", "datum": "2026-03-15", "aantal": 10,
         "prijs_per_stuk": 180, "munt": "USD", "totaalbedrag": "", "fx_koers": "",
         "kosten": 5, "kosten_munt": "EUR", "rekening": acct, "koersdoel": "",
         "performance_share": "nee", "personenbelasting_eur": "",
         "naam": "Apple Inc.", "activumtype": "stock", "etf_type": "", "be_genoteerd": "nee",
         "land": "US"},
        {"ticker": "VWCE.DE", "type": "buy", "datum": "2026-04-01", "aantal": 5,
         "prijs_per_stuk": 110, "munt": "EUR", "totaalbedrag": "", "fx_koers": "",
         "kosten": 2, "kosten_munt": "EUR", "rekening": acct, "koersdoel": "",
         "performance_share": "nee", "personenbelasting_eur": "",
         "naam": "Vanguard FTSE All-World", "activumtype": "etf",
         "etf_type": "accumulating", "be_genoteerd": "nee", "land": "IE"},
    ], columns=TXN_COLUMNS)

    div_example = pd.DataFrame([
        {"ticker": "AAPL", "datum": "2026-05-15", "munt": "USD", "fx_koers": "",
         "bruto_voor_bronbelasting": 25, "buitenlandse_bronbelasting": 3.75,
         "bruto_na_bronbelasting": 21.25, "netto": 14.88, "rekening": acct,
         "cash_basis": "netto", "kind": "dividend"},
    ], columns=DIV_COLUMNS)

    cost_example = pd.DataFrame([
        {"rekening": acct, "datum": "2026-06-30", "omschrijving": "Beheerskosten Q2",
         "bedrag": 12.5, "munt": "EUR"},
    ], columns=COST_COLUMNS)

    instr = pd.DataFrame(INSTRUCTIONS[1:], columns=INSTRUCTIONS[0])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        instr.to_excel(xw, sheet_name="Instructies", index=False)
        txn_example.to_excel(xw, sheet_name="Transacties", index=False)
        div_example.to_excel(xw, sheet_name="Dividenden", index=False)
        cost_example.to_excel(xw, sheet_name="Kosten", index=False)
        # Kolombreedtes wat ruimer
        for ws in xw.book.worksheets:
            for col in ws.columns:
                width = max((len(str(c.value)) for c in col if c.value is not None), default=10)
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 12), 48)
    return buf.getvalue()