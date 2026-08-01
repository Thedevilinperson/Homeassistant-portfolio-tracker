"""
views/common.py — gedeelde bouwstenen voor alle pagina's.

Opmaakfuncties (bedragen, percentages), de gecachete portefeuilleweergave, de
blijvende filters, de herberekeningen en de terugkerende widgets. Alles wat meer dan
een pagina nodig heeft, staat hier; wat maar op een plek gebruikt wordt, hoort in de
paginamodule zelf.

Deze module mag NOOIT een paginamodule importeren — dan ontstaat er een kringloop.
De pijl wijst altijd van pagina naar common, nooit omgekeerd.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

import pandas as pd
import streamlit as st

import belgian_tax as tax_mod
import database as db
import market_data as md

logger = logging.getLogger("app.common")

# De bedragen van een dividend worden op EEN plek gerekend: in database.py. Hier
# staan alleen de doorverwijzingen, zodat de pagina's ze onder een korte naam kunnen
# gebruiken zonder dat er een tweede berekening ontstaat.
dividend_gross_eur = db.dividend_gross_eur
dividend_net_eur   = db.dividend_net_eur
dividend_cash_eur  = db.dividend_cash_eur
dividends_net_eur  = db.dividends_net_eur



# ── Hulpfuncties ──────────────────────────────────────────────────────────────

def _trim_zeros(s: str) -> str:
    """Verwijdert overbodige nullen achter de komma: '1,234.00' -> '1,234',
    '100.50' -> '100.5', '10.2500' -> '10.25'. Echte cijfers blijven staan.

    Bewust consequent: de tabellen gebruiken het '%.10g'-formaat, dat óók alle
    trailing nullen weglaat. Zouden de metrics '€100,50' tonen en de tabellen
    '€100,5', dan zag dezelfde waarde er op twee plaatsen anders uit."""
    if "." not in s:
        return s
    return s.rstrip("0").rstrip(".")


def eur(val: float | None, decimals: int = 2) -> str:
    """Bedrag in euro. Gehele bedragen tonen geen nullen na de komma: €100, niet €100,00."""
    if val is None:
        return "—"
    return f"€{_trim_zeros(f'{val:,.{decimals}f}')}"


def pct(val: float | None, decimals: int = 2) -> str:
    """Percentage met teken. Gehele percentages tonen geen nullen: +5%, niet +5,00%."""
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{_trim_zeros(f'{val:.{decimals}f}')}%"


def num(val: float | None, decimals: int = 2) -> str:
    """Gewoon getal (aantal, koers) zonder overbodige nullen: 10 i.p.v. 10,00.
    Standaard max. 2 decimalen (0.35 → 0.36: hele app op 2 decimalen). Roep expliciet
    met een hoger 'decimals' aan waar meer precisie nodig is (wisselkoersen, aantallen)."""
    if val is None:
        return "—"
    return _trim_zeros(f"{val:,.{decimals}f}")


def _short_ts(ts: str | None) -> str:
    """Formatteer een price_history-timestamp ('JJJJ-MM-DD UU:MM:SS') als 'DD/MM UU:MM'.
    De timestamps staan al in lokale tijd (de container draait op TZ=Europe/Brussels),
    dus geen omrekening nodig. Leeg/onbekend -> '—'."""
    if not ts:
        return "—"
    try:
        dt = datetime.strptime(str(ts)[:16], "%Y-%m-%d %H:%M")
        return dt.strftime("%d/%m %H:%M")
    except (ValueError, TypeError):
        return str(ts)[:16] or "—"


def show_df(df, dec: int = 2, **kwargs):
    """st.dataframe met de floats afgerond op 'dec' decimalen. Samen met de '%.10g'-
    kolomformaten zorgt dat ervoor dat gehele getallen ZONDER nullen na de komma
    verschijnen (10 i.p.v. 10,00) terwijl echte decimalen behouden blijven — en dat
    afrondingsruis (333.29999999999995) geen eindeloze decimalen oplevert.

    Standaard 2 decimalen (0.36: hele app op max. 2 decimalen na de komma, zonder
    overbodige nullen). Geef expliciet dec=<n> mee voor een read-only tabel die méér
    precisie nodig heeft (bv. een wisselkoerstabel).
    Enkel voor read-only tabellen; data_editor blijft ongewijzigd, want daar zou
    afronden de opgeslagen waarden kunnen aanpassen."""
    try:
        out = df.copy()
        for c in out.columns:
            if pd.api.types.is_float_dtype(out[c]):
                out[c] = out[c].round(dec)
    except Exception:
        out = df
    return st.dataframe(out, **kwargs)


def sign_icon(val: float | None) -> str:
    if val is None:
        return "⚪"
    return "🟢" if val >= 0 else "🔴"


RATING_BADGE = {"strong_buy": "🟢🟢 Sterk kopen", "buy": "🟢 Kopen",
                "hold": "⚪ Behouden", "sell": "🔴 Verkopen",
                "strong_sell": "🔴🔴 Sterk verkopen"}


def change_arrow(change: dict | None) -> str:
    """Pijl die aangeeft of het advies sinds de vorige ronde wijzigde (↑ bullisher,
    ↓ bearisher). Lege string als er geen wijziging is."""
    if not change:
        return ""
    return " 🔺" if change.get("up") else " 🔻"


def ai_badge(rec: str | None, change: dict | None = None) -> str:
    """Tekstlabel voor een AI-rating, met optionele wijzigingspijl."""
    if not rec:
        return "—"
    return RATING_BADGE.get(rec, "—") + change_arrow(change)


def delta_color(val: float | None) -> str:
    if val is None or val == 0:
        return "off"
    return "normal" if val >= 0 else "inverse"


@st.cache_data(ttl=60, show_spinner=False)
def get_overview(year: int, account=None, live: bool = False) -> dict:
    """Gecachte portfolioverzicht (60 s TTL). account=None -> alle rekeningen;
    mag ook een tuple van rekeningnamen zijn (multiselect).

    Koersen komen standaard uit price_history (die de scheduler elke 5 minuten
    in de achtergrond bijwerkt): geen netwerkcalls tijdens het renderen, dus de
    pagina laadt vrijwel meteen. Enkel voor tickers zonder opgeslagen koers van
    de laatste 20 minuten wordt nog live (parallel) opgehaald. live=True (via de
    knop 'Ververs prijzen') forceert wel een volledig live rondje."""
    assets = db.get_assets()
    # Enkel open posities hebben een actuele koers nodig; voor een volledig verkochte
    # positie zou dat alleen maar netwerkcalls kosten. (De historiek en de gerealiseerde
    # meerwaarden komen sowieso uit de transacties, niet uit de actuele koers.)
    # Dezelfde FIFO-logica als het dashboard zelf — geen tweede positieberekening.
    tickers, _closed = tax_mod.open_position_tickers()
    prices = md.get_prices_for_tickers(tickers,
                                       max_stale_minutes=None if live else 20)
    overview = tax_mod.calculate_tax_overview(year=year, current_prices=prices,
                                              account=account)
    # Geblokkeerde stukken (werkgeversplannen/FCPE) meteen mee berekenen en in het
    # gecachete resultaat stoppen. Dit deed voorheen een VOLLEDIGE tweede FIFO-pass
    # over alle transacties, bij elke render van zowel het dashboard als de
    # portefeuille — precies het werk dat deze cache moest vermijden. Het hoort bij
    # de rest van de positieberekening en niet in de pagina's zelf.
    accset = None
    if account is not None:
        accset = {account} if isinstance(account, str) else set(account)
    _lk_txns = [t for t in db.get_transactions()
                if accset is None or (t.get("account") or db.DEFAULT_ACCOUNT) in accset]
    overview["locked"] = tax_mod.locked_summary(_lk_txns)
    return overview, assets, prices


def clear_cache():
    get_overview.clear()


def daily_pl(pv: dict, accounts=None) -> dict:
    """Dagelijkse winst/verlies per positie — inclusief de transacties van vandaag.

    Referentie is de laatste koers die vóór vandaag in price_history staat (de
    scheduler schrijft elke 5 minuten weg, dus dat is in de praktijk de slotkoers
    van de vorige beursdag). Alles komt uit de database: geen netwerkcalls.

    WAAROM DE TRANSACTIES VAN VANDAAG MEETELLEN
    Koop je vandaag 10 stuks bij, dan is de eenvoudige formule
    (koers_nu − vorige_slot) × aantal_nu fout: ze rekent voor die 10 nieuwe stuks
    ook de beweging aan die vóór jouw aankoop plaatsvond, terwijl je die nooit
    gemaakt hebt. Hetzelfde geldt omgekeerd bij een verkoop van vandaag. Daarom
    wordt het dagresultaat opgebouwd als een echte kasstroomredenering:

        dag-P/L = eindwaarde − beginwaarde − aankopen vandaag + verkopen vandaag

    met beginwaarde = (aantal bij opening × vorige slotkoers). Het aantal bij
    opening volgt uit het huidige aantal, gecorrigeerd voor wat er vandaag bij kwam
    of wegging. Zo klopt het resultaat ook bij MEERDERE transacties op één dag: elke
    aankoop telt aan zijn eigen prijs, elke verkoop aan de zijne.

    De 'referentie' die teruggegeven wordt, is de gewogen gemiddelde instapkoers van
    de dag: het bedrag dat je vandaag effectief 'in' de positie had, gedeeld door het
    huidige aantal. Bij een dag zonder transacties valt die samen met de vorige
    slotkoers, precies zoals vroeger.

    Per ticker: {prev, ref, price, change_pct, pl_eur, quantity, qty_open,
    bought_today, sold_today, n_txn}. De omrekening naar EUR gebeurt met de
    wisselkoers die al in de positie zit (huidige waarde ÷ (aantal × koers)), zodat
    er geen aparte FX-call nodig is. accounts = set/lijst rekeningen (None = alle),
    zodat het dagresultaat de rekeningfilter van de pagina volgt."""
    if not pv:
        return {}
    today = datetime.now().strftime("%Y-%m-%d")
    prev_map = db.get_previous_closes(list(pv.keys()), today)

    # Transacties van vandaag, per ticker (split-gecorrigeerd zoals overal elders).
    todays: dict[str, list[dict]] = {}
    try:
        for t in db.get_transactions():
            if (t.get("date") or "")[:10] != today:
                continue
            if accounts is not None and (t.get("account") or db.DEFAULT_ACCOUNT) not in accounts:
                continue
            if t.get("is_performance_share") or t.get("is_stock_dividend"):
                continue      # toekenning/stockdividend: geen aan- of verkoop op de markt
            todays.setdefault(t["ticker"].upper(), []).append(t)
    except Exception as exc:
        logger.warning(f"daily_pl: transacties van vandaag niet opgehaald ({exc})")

    out = {}
    for ticker, pos in pv.items():
        price = pos.get("current_price")
        qty = pos.get("quantity") or 0
        if not price or not qty:
            continue
        prev_row = prev_map.get(ticker.upper())
        prev = prev_row["price"] if prev_row else None

        txns = todays.get(ticker.upper(), [])
        bought = sum(t["quantity"] for t in txns if t["transaction_type"] == "buy")
        sold   = sum(t["quantity"] for t in txns if t["transaction_type"] == "sell")
        buy_amt  = sum(t["quantity"] * (t["price_per_unit"] or 0)
                       for t in txns if t["transaction_type"] == "buy")
        sell_amt = sum(t["quantity"] * (t["price_per_unit"] or 0)
                       for t in txns if t["transaction_type"] == "sell")
        qty_open = qty - bought + sold

        # Zonder vorige slotkoers is er enkel een dagresultaat als de hele positie
        # vandaag gekocht is — dan is de aankoopprijs zelf de referentie.
        if not prev:
            if abs(qty_open) > 1e-9 or not bought:
                continue
            basis = buy_amt - sell_amt
        else:
            basis = qty_open * prev + buy_amt - sell_amt
        if basis <= 0:
            continue

        ref = basis / qty
        cur_val = pos.get("current_value")
        fx = (cur_val / (qty * price)) if (cur_val and qty and price) else 1.0
        out[ticker] = {
            "prev":         prev,
            "ref":          ref,
            "price":        price,
            "quantity":     qty,
            "qty_open":     qty_open,
            "bought_today": bought,
            "sold_today":   sold,
            "n_txn":        len(txns),
            "change_pct":   (price - ref) / ref * 100,
            "pl_eur":       (qty * price - basis) * fx,
        }
    return out


def _section_radio(key: str, labels: list) -> str:
    """Blijvende sectiekeuze i.p.v. st.tabs. Anders dan st.tabs onthoudt dit de gekozen
    sectie over reruns heen (bv. na het kiezen van een filter), zodat de weergave niet
    terugspringt naar het eerste tabblad — en sinds 0.35 ook over een HERLAAD van de app
    heen (de keuze wordt in de database bewaard)."""
    sticky(key, labels[0], labels)
    out = st.radio("sectie", labels, key=key, horizontal=True, label_visibility="collapsed")
    sticky_save(key)
    return out


def asset_name_map() -> dict:
    """{ticker: naam} voor alle geregistreerde activa."""
    return {a["ticker"]: (a.get("name") or a["ticker"]) for a in db.get_assets()}


def asset_label(ticker: str, names: dict | None = None) -> str:
    """Toon 'Naam (TICKER)'; valt terug op enkel de ticker als er geen naam is.
    ticker=None (interest/securities lending zonder gekoppeld activum) geeft een
    duidelijk label i.p.v. de letterlijke tekst 'None'."""
    if not ticker:
        return "— Algemeen (niet gekoppeld) —"
    names = names if names is not None else asset_name_map()
    nm = names.get(ticker, ticker)
    return f"{nm} ({ticker})" if nm and nm != ticker else ticker


def per_asset_result(overview: dict, year=None, accounts=None) -> dict:
    """Per activum het gecombineerde resultaat over de geselecteerde rekeningen:
    ongerealiseerde W/V (lopende positie) + gerealiseerde W/V (verkopen, over álle
    geselecteerde rekeningen heen), plus netto dividenden en de aan het aandeel
    gelinkte kosten (transactiekosten + TOB). year=None telt alle jaren mee, anders
    enkel dat jaar. accounts = set rekeningen (None = alle).

    Velden per ticker: quantity, current_value, unrealized, realized, total
    (= unrealized+realized), dividends, costs, net_total
    (= unrealized+realized+dividends−costs).

    Bevat ook activa zonder open positie maar mét historiek (bv. volledig verkocht op
    de ene rekening en elders heraangekocht)."""
    pv = overview.get("position_values", {})
    realized = overview.get("selection_realized_gains", [])
    if year is not None:
        realized = [g for g in realized if g["year"] == year]
    real_by: dict[str, float] = {}
    for g in realized:
        real_by[g["ticker"]] = real_by.get(g["ticker"], 0.0) + g["gain_loss"]

    # Netto dividenden per ticker (rekening- en periode-bewust)
    div_by: dict[str, float] = {}
    for d in db.get_dividends(year=year):
        if accounts is not None and (d.get("account") or db.DEFAULT_ACCOUNT) not in accounts:
            continue
        div_by[d["ticker"]] = div_by.get(d["ticker"], 0.0) + dividend_net_eur(d)

    # Aan het aandeel gelinkte kosten per ticker: transactiekosten + TOB (in EUR),
    # de personenbelasting op performance shares, en de toekenningswaarde (perf_basis)
    # van die performance shares (= kostbasis die in de W/V zit; nodig voor het reële model).
    cost_by: dict[str, float] = {}
    inctax_by: dict[str, float] = {}
    perfbasis_by: dict[str, float] = {}
    for t in db.get_transactions():
        if accounts is not None and (t.get("account") or db.DEFAULT_ACCOUNT) not in accounts:
            continue
        if year is not None and str(t["date"])[:4] != str(year):
            continue
        cost_by[t["ticker"]] = cost_by.get(t["ticker"], 0.0) + (t.get("costs_eur") or 0.0) + (t.get("tob_tax") or 0.0)
        inctax_by[t["ticker"]] = inctax_by.get(t["ticker"], 0.0) + (t.get("income_tax_eur") or 0.0)
        if t.get("is_performance_share") and t["transaction_type"] == "buy":
            perfbasis_by[t["ticker"]] = perfbasis_by.get(t["ticker"], 0.0) + (t.get("total_amount_eur") or 0.0)

    out: dict[str, dict] = {}
    for t in set(pv) | set(real_by) | set(div_by) | set(cost_by) | set(inctax_by):
        p = pv.get(t, {})
        unreal = p.get("unrealized_gain_loss") or 0.0
        realg  = real_by.get(t, 0.0)
        divg   = div_by.get(t, 0.0)
        costg  = cost_by.get(t, 0.0)
        inctax = inctax_by.get(t, 0.0)
        perfb  = perfbasis_by.get(t, 0.0)
        net_total = unreal + realg + divg - costg
        out[t] = {
            "quantity":      p.get("quantity") or 0.0,
            "current_value": p.get("current_value") or 0.0,
            "unrealized":    unreal,
            "realized":      realg,
            "total":         unreal + realg,
            "dividends":     divg,
            "costs":         costg,
            "income_tax":    inctax,
            "perf_basis":    perfb,
            "net_total":     net_total,                         # zuivere W/V-zienswijze (toekenningswaarde als basis)
            "net_real":      net_total + perfb - inctax,        # reële zienswijze (betaalde belasting als kost)
        }
    return out


PERF_MODES = ["cost", "invested", "grant"]


PERF_MODE_LABELS = {
    "cost":     "Personenbelasting als kost (aandelen 'gratis', kostbasis €0)",
    "invested": "Personenbelasting als investering (kostbasis = betaalde belasting)",
    "grant":    "Personenbelasting negeren (meerwaarde t.o.v. toekenningsprijs)",
}


def perf_mode() -> str:
    m = db.get_setting("perf_display_mode", "invested")
    return m if m in PERF_MODES else "invested"


def perf_net(r: dict, mode=None) -> float:
    """Netto resultaat van een activum volgens de gekozen zienswijze voor performance shares.
      - 'grant'    : zuivere meerwaarde t.o.v. de toekenningswaarde (personenbelasting genegeerd).
      - 'invested' : personenbelasting = kostbasis -> reële winst (huidige waarde − belasting).
      - 'cost'     : personenbelasting = kost, aandelen kostbasis €0 (zelfde netto als 'invested').
    Backwards compat: mode kan ook een bool zijn (True=invested, False=grant)."""
    if mode is None:
        mode = perf_mode()
    if isinstance(mode, bool):
        mode = "invested" if mode else "grant"
    if mode == "grant":
        return r["net_total"]
    # 'invested' en 'cost' geven hetzelfde netto; enkel de opsplitsing verschilt
    return r["net_real"]


def perf_held_summary(accounts=None) -> dict:
    """Aggregaat voor de MOMENTEEL AANGEHOUDEN performance shares (voor dashboard-metrics).
    Retourneert vesting-kostbasis en toegerekende personenbelasting van de aangehouden
    stukken, plus de totale personenbelasting in de selectie.
    Toerekening gebeurt pro rata (aangehouden aantal / toegekend aantal) per ticker."""
    accset = set(accounts) if accounts else None
    grant_qty, grant_vest, grant_tax = {}, {}, {}
    for t in db.get_transactions():
        if not (t.get("is_performance_share") and t["transaction_type"] == "buy"):
            continue
        if accset is not None and (t.get("account") or db.DEFAULT_ACCOUNT) not in accset:
            continue
        tk = t["ticker"]
        grant_qty[tk]  = grant_qty.get(tk, 0.0)  + (t.get("quantity") or 0.0)
        grant_vest[tk] = grant_vest.get(tk, 0.0) + (t.get("total_amount_eur") or 0.0)
        grant_tax[tk]  = grant_tax.get(tk, 0.0)  + (t.get("income_tax_eur") or 0.0)

    held_qty = {}
    try:
        assets = db.get_assets()
        snaps = {a["ticker"]: a["snapshot_price_eur"] for a in assets if a.get("snapshot_price_eur") is not None}
        pos_by_key, _, _ = tax_mod._fifo_core(db.get_transactions(), snaps)
        for (tk, acct), pos in pos_by_key.items():
            if accset is not None and (acct or db.DEFAULT_ACCOUNT) not in accset:
                continue
            held_qty[tk] = held_qty.get(tk, 0.0) + (pos.get("total_quantity") or 0.0)
    except Exception:
        pass

    held_vest = held_tax = total_tax = 0.0
    per_ticker: dict[str, dict] = {}
    for tk, gq in grant_qty.items():
        total_tax += grant_tax.get(tk, 0.0)
        ratio = min(1.0, (held_qty.get(tk, 0.0) / gq)) if gq else 0.0
        v = grant_vest.get(tk, 0.0) * ratio
        x = grant_tax.get(tk, 0.0) * ratio
        held_vest += v
        held_tax  += x
        per_ticker[tk] = {"vesting": v, "tax": x}
    return {"held_vesting": held_vest, "held_tax": held_tax, "total_tax": total_tax,
            "per_ticker": per_ticker}


def has_income_tax(accounts=None) -> bool:
    """Staat er in DEZE selectie (rekeningen) minstens één performance share waarop
    personenbelasting betaald is? accounts=None (alle rekeningen) kijkt naar alles.
    Bepaalt of de zienswijzekeuze rond personenbelasting überhaupt getoond wordt —
    voor een rekening zonder zulke producten is die keuze zinloos."""
    accset = set(accounts) if accounts else None
    for t in db.get_transactions():
        if (t.get("income_tax_eur") or 0) <= 0:
            continue
        if accset is None or (t.get("account") or db.DEFAULT_ACCOUNT) in accset:
            return True
    return False


def render_realized_history(realized_list, names=None, empty_msg="Nog geen gerealiseerde meer-/minwaarden."):
    """Tabel met gerealiseerde meer-/minwaarden (verkopen), over alle jaren/rekeningen
    heen zoals meegegeven. Toont ook posities die intussen netto 0 zijn.

    Bedrag- en aantalkolommen blijven numeriek (float) — enkel de weergave wordt via
    column_config geformatteerd. Zo sorteert een klik op de kolomkop numeriek i.p.v.
    alfabetisch (wat gebeurde toen deze kolommen al opgemaakte '€'-strings waren)."""
    names = names if names is not None else asset_name_map()
    if not realized_list:
        st.info(empty_msg)
        return
    rows = []
    for g in sorted(realized_list, key=lambda x: x["date"], reverse=True):
        rows.append({
            "W/V":           sign_icon(g["gain_loss"]),
            "Datum":         g["date"][:10],
            "Activum":       asset_label(g["ticker"], names),
            "Rekening":      g.get("account") or "—",
            "Aantal":        g["quantity"],
            "Opbrengst (€)": g["sell_total"],
            "Kostbasis (€)": g["cost_basis"],
            "W/V (€)":       g["gain_loss"],
        })
    show_df(pd.DataFrame(rows), width='stretch', hide_index=True, column_config={
        "Aantal":        st.column_config.NumberColumn(format="%.10g"),
        "Opbrengst (€)": st.column_config.NumberColumn(format="€ %.10g"),
        "Kostbasis (€)": st.column_config.NumberColumn(format="€ %.10g"),
        "W/V (€)":       st.column_config.NumberColumn(format="€ %.10g"),
    })
    tot = sum(g["gain_loss"] for g in realized_list)
    st.caption(f"Totaal gerealiseerde W/V (deze selectie, alle jaren): **{eur(tot)}**")


def fx_lookup(currency: str, date_str: str) -> tuple[float | None, str]:
    """(koers, bron) voor native -> EUR op een datum.

    bron: 'eur' | 'historisch' | 'actueel' (historische koers niet beschikbaar,
    benaderd met de koers van vandaag) | 'onbekend'.

    Waarom dit bestaat: hier zat de TOB-bug. De oude code deed
    `get_historical_exchange_rate(...) or 1.0`. Faalde die lookup (netwerkhapering),
    dan werd de koers stilzwijgend 1,0 en was het 'EUR-bedrag' gewoon het bedrag in
    USD — waarna de TOB van 0,35% op dat USD-bedrag werd berekend. Een koers van 1,0
    is voor géén enkele vreemde munt een verdedigbare terugval. Nu wordt er nooit
    stilzwijgend 1,0 gebruikt: lukt de historische koers niet, dan gebruiken we de
    actuele koers (en zeggen we dat), en lukt ook dat niet, dan geven we None terug
    zodat de aanroeper om een eigen koers moet vragen."""
    if not currency or currency == "EUR":
        return 1.0, "eur"
    rate = md.get_historical_exchange_rate(currency, str(date_str), "EUR")
    if rate:
        return float(rate), "historisch"
    rate = md.get_exchange_rate(currency, "EUR")
    if rate:
        logger.warning(f"fx_lookup({currency},{date_str}): historische koers niet beschikbaar — "
                       "benaderd met de actuele koers. Geef bij voorkeur je eigen koers in.")
        return float(rate), "actueel"
    logger.warning(f"fx_lookup({currency},{date_str}): geen enkele wisselkoers beschikbaar.")
    return None, "onbekend"


def compute_eur(amount: float, currency: str, date_str: str,
                fx_override: float | None = None) -> tuple[float | None, float | None]:
    """(fx_rate, eur_bedrag) op transactiedatum. fx_override (je eigen brokerkoers) heeft
    altijd voorrang. Geeft (None, None) als er geen enkele koers te vinden is — zie
    fx_lookup voor waarom er nooit stilzwijgend op 1,0 wordt teruggevallen."""
    if not amount or currency == "EUR":
        return 1.0, float(amount or 0.0)
    if fx_override:
        return float(fx_override), float(amount) * float(fx_override)
    rate, _src = fx_lookup(currency, date_str)
    if rate is None:
        return None, None
    return rate, float(amount) * rate


@st.cache_data(ttl=5, show_spinner=False)
def _ui_state() -> dict:
    try:
        raw = db.get_setting("ui_state", "")
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


def _ui_save(key: str, value):
    """Bewaar één widgetwaarde; schrijft enkel weg als ze effectief wijzigde."""
    try:
        state = dict(_ui_state())
        if state.get(key) == value:
            return
        state[key] = value
        db.set_setting("ui_state", json.dumps(state))
        _ui_state.clear()
    except Exception as exc:
        logger.warning(f"_ui_save({key}): {exc}")


def sticky(key: str, fallback, options=None):
    """Beginwaarde voor een widget met deze key: de bewaarde keuze, anders 'fallback'.

    Roep dit aan VÓÓR de widget. De widget zelf zet st.session_state[key]; die waarde
    lezen we na afloop terug met sticky_save(). options (indien gegeven) filtert waarden
    weg die intussen niet meer bestaan — bv. een rekening die je verwijderd hebt."""
    if key in st.session_state:
        return st.session_state[key]
    val = _ui_state().get(key, fallback)
    if options is not None:
        if isinstance(val, list):
            val = [v for v in val if v in options]
        elif val not in options:
            val = fallback
    st.session_state[key] = val
    return val


def sticky_save(key: str):
    """Bewaar de huidige waarde van de widget met deze key."""
    if key in st.session_state:
        v = st.session_state[key]
        _ui_save(key, list(v) if isinstance(v, (tuple, set)) else v)


def sticky_select(label, options, key, fallback=None, widget="selectbox", **kw):
    """selectbox / radio / multiselect die zijn keuze onthoudt over een herlaad heen."""
    fb = fallback if fallback is not None else ([] if widget == "multiselect" else options[0])
    sticky(key, fb, options)
    fn = {"selectbox": st.selectbox, "radio": st.radio,
          "multiselect": st.multiselect}[widget]
    out = fn(label, options, key=key, **kw)
    sticky_save(key)
    return out


def account_filter_widget(key: str):
    """Multiselect van rekeningen. Lege selectie = alle rekeningen.
    Retourneert een tuple (cachebaar) of None. De keuze wordt onthouden over een
    herlaad van de app heen."""
    opts = db.get_accounts()
    sticky(key, [], opts)
    sel = st.multiselect("Rekeningen", opts, key=key, placeholder="Alle rekeningen")
    sticky_save(key)
    return tuple(sel) if sel else None


def df_row_select(df, key: str):
    """Toon een dataframe met klikbare enkelvoudige rijselectie en geef de index van de
    geselecteerde rij terug (positie in df), of None. Defensief tegen oudere Streamlit-
    versies en testomgevingen die geen selectie-object teruggeven."""
    ev = show_df(df, width="stretch", hide_index=True, key=key,
                      on_select="rerun", selection_mode="single-row")
    rows = None
    try:
        rows = ev.selection.rows
    except Exception:
        try:
            rows = ev["selection"]["rows"]
        except Exception:
            rows = None
    if isinstance(rows, (list, tuple)) and rows and isinstance(rows[0], int):
        idx = rows[0]
        # Na filteren kan een eerder bewaarde selectie-index buiten de (kortere) lijst
        # vallen -> negeer die i.p.v. een IndexError te veroorzaken.
        if 0 <= idx < len(df):
            return idx
    return None


def _cell_eq(a, b) -> bool:
    """Vergelijk een tabelcel (bewerkt vs origineel), robuust voor None/NaN en floats."""
    an = a is None or (isinstance(a, float) and pd.isna(a))
    bn = b is None or (isinstance(b, float) and pd.isna(b))
    if an and bn:
        return True
    if an or bn:
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return str(a) == str(b)


def _recompute_dividend_chain(divs, rv_rate: float, include_manual: bool = False,
                              dry_run: bool = False) -> list[dict]:
    """(Her)bouw de dividendketen op vanaf ① bruto: buitenlandse bronbelasting uit het
    land van het activum EN het tarief van het jaar van het dividend, Belgische RV uit
    de instellingen.

    Zelfherstellend en idempotent: lijnen waarvan de opgeslagen keten al klopt worden
    overgeslagen; lijnen die niet meer overeenkomen — bv. nadat je het land van een
    activum hebt gecorrigeerd — worden opnieuw berekend vanaf het brutobedrag.
    Interest en securities lending blijven ongemoeid.

    include_manual=False (standaard): lijnen die JIJ handmatig hebt gecorrigeerd
    (manual_override) blijven ongemoeid. Een herberekening mag je eigen correcties niet
    stilzwijgend overschrijven — dat is precies waarvoor je ze hebt ingevoerd.
    dry_run=True: niets wegschrijven, enkel teruggeven wát er zou wijzigen.

    Geeft een lijst wijzigingen terug: per lijn de oude en nieuwe ②/🇧🇪RV/④/netto-EUR."""
    a_by = {a["ticker"]: a for a in db.get_assets()}
    changes: list[dict] = []

    def _close(x, y, tol=0.02):
        xv, yv = (x or 0.0), (y or 0.0)
        return abs(xv - yv) <= tol

    for d in divs:
        if (d.get("kind") or "dividend") != "dividend":
            continue
        if d.get("manual_override") and not include_manual:
            continue   # handmatig gecorrigeerd -> met rust laten
        # Anker = ① bruto vóór bronbelasting; val terug op ③ of de opgeslagen bruto.
        A = d.get("gross_before_wht")
        if A is None:
            A = d.get("gross_after_wht")
        if A is None:
            A = d.get("gross_amount")
        if A is None:
            continue
        cur  = d.get("currency") or "EUR"
        ndat = d["date"][:10]
        ctry = (a_by.get(d["ticker"], {}).get("country") or "BE").upper()
        # Tarief van het JAAR VAN HET DIVIDEND, niet van vandaag: bronbelastingen
        # wijzigen over de jaren en een dividend uit 2024 moet met het tarief van 2024
        # herberekend worden.
        dyear = tax_mod.year_of(ndat)
        wht  = tax_mod.get_wht_rate(ctry, dyear) if ctry != "BE" else 0.0
        # Volledige keten opnieuw opbouwen vanaf ① (B/C/D leeg → uit de tarieven)
        res  = tax_mod.resolve_dividend_chain(A, None, None, None,
                                              rv_rate=rv_rate, wht_rate=wht)
        rA, rB, rC, rD, rRV = res["a"], res["b"], res["c"], res["d"], res["rv"]

        # EUR-tegenwaarden + cash-boeking op basis van de (her)berekende keten.
        # Een EIGEN wisselkoers blijft behouden: die komt van je brokerafschrift en
        # mag nooit door de historische marktkoers vervangen worden. De bedragen
        # zelf worden wél opnieuw opgebouwd — beschermd tegen overschrijven is niet
        # hetzelfde als uitgesloten van controle.
        _own_fx = div_fx_override(d)

        def _te(v):
            return None if v is None else compute_eur(v, cur, ndat, _own_fx)[1]
        a_eur, c_eur, d_eur = _te(rA), _te(rC), _te(rD)
        gross_eur = a_eur if a_eur is not None else (c_eur if c_eur is not None else d_eur)
        net_eur   = d_eur if d_eur is not None else c_eur
        if gross_eur is None or net_eur is None:
            continue
        wh_eur = max(0.0, gross_eur - net_eur)
        cbk = d.get("cash_basis") or "net"
        if cbk == "none":
            # Uitkering in aandelen (stockdividend): per definitie geen cash-boeking.
            # Let op de valkuil: 0.0 is 'falsy', dus de dict-lookup met 'or'-terugval
            # hieronder zou 0.0 stilzwijgend door het netto vervangen.
            cash_eur = 0.0
        else:
            cash_eur = {"gross_before": a_eur, "gross_after": c_eur, "net": net_eur}.get(cbk)
            if cash_eur is None:
                cash_eur = net_eur

        # Idempotent: enkel overslaan als zowel de keten áls de EUR/cash-velden al
        # kloppen. Zo herstelt een klik ook een stale cash-boeking (bv. na een eerdere
        # herberekening die net_eur/cash_eur niet mee bijwerkte) zonder de tabel te wijzigen.
        if (_close(rB, d.get("foreign_wht_amt")) and
                _close(rRV, d.get("belgian_rv_amt")) and
                _close(rD, d.get("net_received")) and
                _close(net_eur, d.get("net_eur")) and
                _close(cash_eur, d.get("cash_eur")) and
                _close(gross_eur, d.get("gross_eur"))):
            continue

        changes.append({
            "id":        d["id"],
            "datum":     ndat,
            "ticker":    d["ticker"],
            "land":      ctry,
            "jaar":      dyear,
            "wht_pct":   round(wht * 100, 3),
            "handmatig": bool(d.get("manual_override")),
            "eigen_fx":  bool(_own_fx),
            "oud_wht":   d.get("foreign_wht_amt"),
            "nieuw_wht": rB,
            "oud_rv":    d.get("belgian_rv_amt"),
            "nieuw_rv":  rRV,
            "oud_netto": d.get("net_received"),
            "nieuw_netto": rD,
            "oud_netto_eur":   d.get("net_eur"),
            "nieuw_netto_eur": net_eur,
            "munt":      cur,
        })
        if dry_run:
            continue

        prim = rA if rA is not None else (rC if rC is not None else rD)
        fx_prim = _own_fx or (compute_eur(prim, cur, ndat)[0] or 1.0)
        db.update_dividend(
            d["id"], gross_amount=prim, withholding_tax=round(wh_eur / fx_prim, 2),
            fx_rate=fx_prim, gross_eur=gross_eur, withholding_eur=wh_eur, net_eur=net_eur,
            foreign_wht_withheld=1 if (rB and rB > 0) else 0,
            belgian_rv_withheld=1 if (rRV and rRV > 0) else 0,
            gross_before_wht=rA, gross_before_wht_cur=cur if rA is not None else None,
            foreign_wht_amt=rB, foreign_wht_cur=cur if rB is not None else None,
            gross_after_wht=rC, gross_after_wht_cur=cur if rC is not None else None,
            belgian_rv_amt=rRV, net_received=rD, net_received_cur=cur if rD is not None else None,
            cash_basis=cbk, cash_eur=cash_eur,
            # Herberekende lijn is per definitie niet langer een handmatige correctie.
            manual_override=0)
    return changes


def _recompute_tob_preview(txns: list[dict], ainfo: dict) -> tuple[list[dict], int]:
    """Welke transacties hebben een verkeerde EUR-tegenwaarde en/of TOB?

    Per transactie wordt de EUR-tegenwaarde en de TOB daarop herberekend en
    vergeleken met wat er opgeslagen staat.

    WELKE WISSELKOERS?
      • Lijnen met een EIGEN wisselkoers (fx_manual) behouden JOUW koers — die heb je
        bewust ingegeven omdat je broker ze zo afgerekend heeft, en ze wordt hier dus
        nooit door de marktkoers vervangen. Maar de TOB wordt er wél opnieuw op
        berekend: de beurstaks is een percentage van de EUR-tegenwaarde, dus een
        andere koers betekent per definitie een andere TOB. Werd de koers achteraf
        aangepast (of stond de EUR-tegenwaarde nog op de oude koers), dan bleef die
        TOB vroeger op het oude bedrag staan — precies wat hier rechtgezet wordt.
      • Alle andere lijnen krijgen de historische marktkoers van de transactiedatum.

    Lijnen met een HANDMATIGE TOB (tob_manual) en toekenningen (performance shares,
    geen TOB) blijven altijd ongemoeid.

    'verdacht' markeert de oude fout expliciet: de opgeslagen TOB komt (bijna) exact
    overeen met het tarief toegepast op het bedrag in VREEMDE MUNT i.p.v. op de
    EUR-tegenwaarde. Dat gebeurde wanneer de koers stilzwijgend 1,0 werd.
    Geeft (wijzigingen, aantal_verdacht) terug; schrijft niets weg."""
    changes, suspect = [], 0
    for t in txns:
        if t.get("tob_manual") or t.get("is_performance_share") or t.get("is_stock_dividend"):
            continue
        cur = t.get("currency") or "EUR"
        if cur == "EUR":
            continue   # zonder vreemde munt kan de FX-fout niet optreden

        eigen_fx = bool(t.get("fx_manual"))
        if eigen_fx:
            new_fx = float(t.get("fx_rate") or 0) or None
            if not new_fx or new_fx <= 0:
                continue   # 'eigen koers' aangevinkt maar geen bruikbare koers: niets te doen
        else:
            new_fx, _src = fx_lookup(cur, t["date"])
            if not new_fx:
                continue   # geen koers beschikbaar: niets om mee te herberekenen

        native = float(t["total_amount"])
        new_eur = round(native * new_fx, 2)
        info = ainfo.get(t["ticker"], {})
        new_tob = tax_mod.calculate_tob(info.get("asset_type", "stock"),
                                        info.get("etf_subtype", "distributing"), new_eur,
                                        bool(info.get("belgian_registered", 1)),
                                        txn_date=t["date"])
        old_tob = round(float(t.get("tob_tax") or 0), 2)
        old_eur = round(float(t.get("total_amount_eur") or native), 2)
        old_fx = round(float(t.get("fx_rate") or 1.0), 6)
        if abs(new_tob - old_tob) < 0.01 and abs(new_eur - old_eur) < 0.01:
            continue

        # Verdacht = de TOB is berekend op het NATIVE bedrag (de oude bug)
        tob_on_native = tax_mod.calculate_tob(info.get("asset_type", "stock"),
                                              info.get("etf_subtype", "distributing"), native,
                                              bool(info.get("belgian_registered", 1)),
                                              txn_date=t["date"])
        verdacht = abs(old_tob - tob_on_native) < 0.01 and abs(tob_on_native - new_tob) >= 0.01
        if verdacht:
            suspect += 1
        changes.append({
            "id": t["id"], "datum": t["date"][:10], "ticker": t["ticker"], "munt": cur,
            "oud_fx": old_fx, "nieuw_fx": round(new_fx, 6),
            "oud_eur": old_eur, "nieuw_eur": new_eur,
            "oud_tob": old_tob, "nieuw_tob": new_tob,
            "verdacht": verdacht, "eigen_fx": eigen_fx,
        })
    return changes, suspect


def _date_or_none(s: str):
    """'JJJJ-MM-DD' (of dd/mm/jjjj) -> date, anders None."""
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _undo_banner(c=None):
    """Toon meteen na een verwijdering een knop om ze terug te draaien.

    Een bevestigingsvraag beschermt tegen de verkeerde klik, maar niet tegen de
    verkeerde beslissing: dat je het verkeerde item koos, zie je meestal pas nadat het
    weg is. Vandaar deze knop, en daarnaast een blijvende prullenbak."""
    c = c or st
    grp = st.session_state.get("undo_group")
    if not grp:
        return
    lbl = st.session_state.get("undo_label", "de vorige verwijdering")
    b1, b2 = c.columns([3, 1])
    b1.success(f"🗑️ {lbl} verwijderd — naar de prullenbak verplaatst.")
    with b2:
        if st.button("↩️ Ongedaan maken", key=f"undo_{grp}", width="stretch"):
            items = db.last_trash_group(grp)
            res = db.restore_trash([i["id"] for i in items])
            st.session_state.pop("undo_group", None)
            st.session_state.pop("undo_label", None)
            clear_cache()
            if res["errors"]:
                st.error("Niet alles kon terug: " + "; ".join(res["errors"][:3]))
            else:
                st.session_state["undo_done"] = f"{res['restored']} rij(en) teruggezet."
            st.rerun()
    if st.session_state.get("undo_done"):
        c.info("↩️ " + st.session_state.pop("undo_done"))


def multiselect_delete(state_key, options_map, do_delete_one, noun="rij",
                       extra_warning="", container=None):
    """Multiselect om meerdere rijen te kiezen + wis-knop met EXPLICIETE bevestiging.
    options_map: dict {id: label} (invoegvolgorde = weergavevolgorde).
    do_delete_one(id): verwijdert één item."""
    c = container or st
    _undo_banner(c)
    ids = list(options_map.keys())
    sel = c.multiselect(f"Selecteer {noun}(en) om te verwijderen", ids,
                        format_func=lambda i: options_map.get(i, str(i)),
                        key=f"{state_key}_ms", placeholder=f"Kies één of meerdere {noun}(en)…")
    pending = st.session_state.get(state_key)
    if pending:
        labels = [options_map.get(i, str(i)) for i in pending if i in options_map] or \
                 [str(i) for i in pending]
        preview = "; ".join(labels[:6]) + (f"  … (+{len(labels) - 6})" if len(labels) > 6 else "")
        st.warning(f"⚠️ {len(pending)} {noun}(en) verwijderen?\n\n{preview}"
                   + (f"\n\n{extra_warning}" if extra_warning else "")
                   + "\n\nDe rijen gaan naar de prullenbak (⚙️ Instellingen → 🗃️ Data) "
                     "en blijven daar terug te halen.")
        cc1, cc2 = st.columns(2)
        if cc1.button("✅ Ja, verwijderen", key=f"{state_key}_yes", width="stretch"):
            # Groepssleutel: alles wat in één klik verdwijnt, hoort bij elkaar en komt
            # met één klik ook weer terug.
            grp = f"{state_key}-{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
            for i in pending:
                try:
                    do_delete_one(i, group=grp)
                except TypeError:
                    # Verwijderfuncties die (nog) geen groep kennen: gewoon uitvoeren.
                    do_delete_one(i)
            st.session_state.pop(state_key, None)
            st.session_state["undo_group"] = grp
            st.session_state["undo_label"] = f"{len(pending)} {noun}(en)"
            clear_cache()
            st.rerun()
        if cc2.button("✖️ Annuleren", key=f"{state_key}_no", width="stretch"):
            st.session_state.pop(state_key, None)
            st.rerun()
    else:
        if c.button(f"🗑️ Wis geselecteerde ({len(sel)})", key=f"{state_key}_btn",
                    disabled=not sel, width="stretch"):
            st.session_state[state_key] = list(sel)
            st.rerun()


def delete_with_confirm(btn_label, state_key, target_id, warning, do_delete, btn_container=None):
    """Wis-knop met expliciete bevestigingsstap. do_delete() draait pas na bevestiging.
    Voorkomt dat één klik onmiddellijk (onomkeerbaar) data wist."""
    container = btn_container if btn_container is not None else st
    if st.session_state.get(state_key) == target_id:
        st.warning(warning)
        cc1, cc2 = st.columns(2)
        if cc1.button("✅ Ja, definitief verwijderen", key=f"{state_key}_yes", width="stretch"):
            do_delete()
            st.session_state.pop(state_key, None)
            clear_cache()
            st.rerun()
        if cc2.button("✖️ Annuleren", key=f"{state_key}_no", width="stretch"):
            st.session_state.pop(state_key, None)
            st.rerun()
        return True   # bevestiging staat open
    if container.button(btn_label, key=f"{state_key}_btn", width="stretch"):
        st.session_state[state_key] = target_id
        st.rerun()
    return False


def _div_fx_widget(currency: str, on_date, key_prefix: str,
                   context: str = "dit bedrag") -> tuple[int, float | None]:
    """Blok 'eigen wisselkoers' voor de dividendformulieren.

    Geeft (fx_manual, fx_override) terug. Bij EUR verschijnt er niets en is er
    niets om te kiezen. Dezelfde redenering als bij transacties: een broker rekent
    vaak met zijn eigen koers, en die hoort bij het bedrag zoals hij het afgerekend
    heeft — niet bij de marktkoers van die dag. Wordt de koers hier vastgelegd, dan
    laat elke latere herberekening ze staan."""
    if currency == "EUR":
        return 0, None
    mkt, src = fx_lookup(currency, on_date)
    if src == "historisch":
        st.caption(f"💱 Marktkoers op {on_date}: **1 {currency} = {mkt:.6g} EUR**")
    elif src == "actueel":
        st.warning(f"💱 De historische koers voor {on_date} is niet beschikbaar; de app "
                   f"gebruikt de **actuele** koers (1 {currency} = {mkt:.6g} EUR) als "
                   "benadering. Geef hieronder liever de koers van je broker in.")
    else:
        st.error(f"💱 Geen enkele wisselkoers gevonden voor {currency}. Geef hieronder je "
                 f"eigen koers in, anders kan de EUR-tegenwaarde van {context} niet "
                 "berekend worden.")

    fx_manual = int(st.checkbox(
        "💱 Eigen wisselkoers gebruiken (koers van je broker)",
        value=(mkt is None), key=f"{key_prefix}_fxman",
        help="Brokers rekenen dividenden in vreemde munt vaak om tegen hun eigen koers, "
             "die je op het afschrift terugvindt. Vul die hier in, dan blijft ze voorgoed "
             "aan deze lijn hangen en wordt ze nooit overschreven door een herberekening "
             "met de marktkoers."))
    if not fx_manual:
        return 0, None

    f1, f2 = st.columns([1, 2])
    with f1:
        val = st.number_input(f"1 {currency} = ? EUR", min_value=0.0, format="%.10g",
                              value=float(mkt) if mkt else 0.0, step=0.0001,
                              key=f"{key_prefix}_fxval")
    with f2:
        if mkt and val:
            spread = (val - mkt) / mkt * 100
            st.caption(f"Afwijking t.o.v. de marktkoers: **{pct(spread)}**"
                       + ("  (jouw koers is ongunstiger — typisch een wisselmarge)"
                          if spread < 0 else ""))
    return 1, (val or None)


def div_fx_override(d: dict) -> float | None:
    """De eigen wisselkoers van een dividend, of None wanneer er geen is.

    Net als bij transacties rekent een broker vaak met zijn eigen koers. Staat
    fx_manual aan, dan is fx_rate JOUW koers en mag geen enkele herberekening ze
    door de historische marktkoers vervangen. Een koers van 0 of ontbrekend telt
    niet als eigen koers — dan zou de omrekening stilzwijgend op nul uitkomen."""
    if not d.get("fx_manual"):
        return None
    try:
        fx = float(d.get("fx_rate") or 0)
    except (TypeError, ValueError):
        return None
    return fx if fx > 0 else None


def backfill_eur(force: bool = False) -> int:
    """Reken bestaande transacties + dividenden om naar EUR (historische koers).
    Voor dividenden worden álle EUR-velden herberekend — ook net_eur en de
    cash-boeking (cash_eur) — zodat het cash-grootboek mee wordt bijgewerkt."""
    n = 0
    for t in db.get_transactions():
        need = (t.get("total_amount_eur") is None) or (force and t["currency"] != "EUR")
        if not need and t.get("costs_eur") is None and (t.get("costs") or 0) > 0:
            need = True
        if not need:
            continue
        fx, tot_eur  = compute_eur(t["total_amount"], t["currency"], t["date"])
        _, costs_eur = compute_eur(t.get("costs") or 0, t.get("costs_currency") or "EUR", t["date"])
        db.set_transaction_eur(t["id"], fx, tot_eur, costs_eur)
        n += 1
    for d in db.get_dividends():
        if d.get("gross_eur") is not None and not (force and d["currency"] != "EUR"):
            continue
        cur  = d.get("currency") or "EUR"
        ndat = d["date"][:10]
        # Eigen brokerkoers heeft altijd voorrang — ook bij een geforceerde backfill.
        _own = div_fx_override(d)
        fx   = _own if _own else (compute_eur(1.0, cur, ndat)[0] or 1.0)
        A, C, Dv = d.get("gross_before_wht"), d.get("gross_after_wht"), d.get("net_received")
        if any(v is not None for v in (A, C, Dv)):
            # Native keten aanwezig: de bedragen blijven, enkel hun EUR-tegenwaarde wijzigt.
            prim       = A if A is not None else (C if C is not None else Dv)
            net_native = Dv if Dv is not None else (C if C is not None else prim)
            cbk        = d.get("cash_basis") or "net"
            if cbk == "none":
                cash_native = 0.0
            else:
                cash_native = {"gross_before": A, "gross_after": C, "net": net_native}.get(cbk)
                if cash_native is None:
                    cash_native = net_native
            gross_eur = (prim or 0.0) * fx
            net_eur   = (net_native or 0.0) * fx
            cash_eur  = (cash_native or 0.0) * fx
            wh_eur    = max(0.0, gross_eur - net_eur)
        else:
            # Oude rij zonder keten: val terug op bruto/ingehouden.
            gross_eur = (d["gross_amount"] or 0.0) * fx
            wh_eur    = (d["withholding_tax"] or 0.0) * fx
            net_eur   = gross_eur - wh_eur
            cash_eur  = net_eur
        db.update_dividend(d["id"], fx_rate=fx, gross_eur=gross_eur, withholding_eur=wh_eur,
                           net_eur=net_eur, cash_eur=cash_eur)
        n += 1
    return n
