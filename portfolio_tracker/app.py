"""
app.py — Portfolio Tracker — Streamlit hoofdapplicatie
Belgische beleggingsportefeuille met belastingtracking en AI-advies.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import date, datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import ai_advisor
import belgian_tax as tax_mod
import bulk_import as bulk
import database as db
import market_data as md

# ── Logging ───────────────────────────────────────────────────────────────────
# Streamlit draait als een apart proces van scheduler.py en configureerde tot nu
# toe geen logging: warnings/info van market_data/database (bv. bij 'Info ophalen'
# of 'Ophalen 31/12/2025') kwamen daardoor ongeformatteerd (geen tijdstip/niveau)
# in de add-on-log terecht via Pythons kale 'lastResort'-handler. Consistent met
# scheduler.py, zodat alle logregels — ongeacht welk proces ze produceert — een
# tijdstip en niveau tonen. basicConfig() is een no-op als er al handlers actief
# zijn, dus dit is veilig om bij elke Streamlit-rerun opnieuw aan te roepen.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("app")

# ── Pagina-configuratie ───────────────────────────────────────────────────────

st.set_page_config(
    page_title="Portfolio Tracker 🇧🇪",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
div[data-testid="metric-container"] {
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 10px;
    padding: 0.8rem 1rem;
}
div[data-testid="stDataFrame"] { border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ── Database initialiseren ────────────────────────────────────────────────────
# Streamlit voert dit script bij ELKE interactie opnieuw uit; init_db (alle
# CREATE TABLE's + migratiechecks met PRAGMA table_info per tabel) hoeft maar
# een keer per proces te draaien. cache_resource onthoudt dat over reruns en
# sessies heen zolang het proces leeft.
@st.cache_resource(show_spinner=False)
def _init_db_once() -> bool:
    db.init_db()
    return True


_init_db_once()

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
    return overview, assets, prices


def clear_cache():
    get_overview.clear()


def daily_pl(pv: dict) -> dict:
    """Dagelijkse winst/verlies per positie.

    Referentie is de laatste koers die vóór vandaag in price_history staat (de
    scheduler schrijft elke 5 minuten weg, dus dat is in de praktijk de slotkoers
    van de vorige beursdag). Alles komt uit de database: geen netwerkcalls.

    Per ticker: {prev, price, change_pct, pl_eur, quantity}. De omrekening naar EUR
    gebeurt met de wisselkoers die al in de positie zit (huidige waarde gedeeld door
    aantal x koers), zodat er geen aparte FX-call nodig is. Tickers zonder koers van
    een vorige dag ontbreken in het resultaat (bv. net toegevoegd, of de scheduler
    draait nog geen volledige dag)."""
    if not pv:
        return {}
    today = datetime.now().strftime("%Y-%m-%d")
    prev_map = db.get_previous_closes(list(pv.keys()), today)
    out = {}
    for ticker, pos in pv.items():
        prev_row = prev_map.get(ticker.upper())
        price = pos.get("current_price")
        qty = pos.get("quantity") or 0
        if not prev_row or not price or not qty:
            continue
        prev = prev_row["price"]
        if not prev:
            continue
        cur_val = pos.get("current_value")
        fx = (cur_val / (qty * price)) if (cur_val and qty and price) else 1.0
        out[ticker] = {
            "prev":       prev,
            "price":      price,
            "quantity":   qty,
            "change_pct": (price - prev) / prev * 100,
            "pl_eur":     (price - prev) * qty * fx,
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


def dividend_net_eur(d: dict) -> float:
    """Netto ontvangen dividend in EUR (na alle voorheffingen)."""
    if d.get("net_eur") is not None:
        return d["net_eur"]
    g = d.get("gross_eur") if d.get("gross_eur") is not None else d["gross_amount"]
    w = d.get("withholding_eur") if d.get("withholding_eur") is not None else d["withholding_tax"]
    return g - w


def dividends_net_eur(divs, accounts=None) -> float:
    """Som van netto dividenden (EUR), optioneel gefilterd op een set rekeningen."""
    tot = 0.0
    for d in divs:
        if accounts is not None and (d.get("account") or db.DEFAULT_ACCOUNT) not in accounts:
            continue
        tot += dividend_net_eur(d)
    return tot


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


# ── Filters en keuzes onthouden over een herlaad heen ────────────────────────
# Streamlit gooit session_state weg bij een refresh van de pagina. Filters (rekening,
# jaar, type, ...) en keuzes (zienswijze, taartbasis, ...) worden daarom in de database
# bewaard onder de sleutel 'ui_state' en bij het opbouwen van de widget opnieuw als
# beginwaarde gezet. Zo staat de app na een herlaad nog precies zoals je ze had.

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

        # EUR-tegenwaarden + cash-boeking op basis van de (her)berekende keten
        def _te(v):
            return None if v is None else compute_eur(v, cur, ndat)[1]
        a_eur, c_eur, d_eur = _te(rA), _te(rC), _te(rD)
        gross_eur = a_eur if a_eur is not None else (c_eur if c_eur is not None else d_eur)
        net_eur   = d_eur if d_eur is not None else c_eur
        if gross_eur is None or net_eur is None:
            continue
        wh_eur = max(0.0, gross_eur - net_eur)
        cbk = d.get("cash_basis") or "net"
        cash_eur = {"gross_before": a_eur, "gross_after": c_eur, "net": net_eur}.get(cbk) or net_eur

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
        fx_prim = compute_eur(prim, cur, ndat)[0] or 1.0
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

    Herberekent per transactie de wisselkoers (historisch), de EUR-tegenwaarde en de TOB
    daarop, en vergelijkt met wat er opgeslagen staat. Lijnen met een EIGEN wisselkoers
    (fx_manual) of een HANDMATIGE TOB (tob_manual) worden overgeslagen — die heb je
    bewust zo gezet.

    'verdacht' markeert de oude fout expliciet: de opgeslagen TOB komt (bijna) exact
    overeen met het tarief toegepast op het bedrag in VREEMDE MUNT i.p.v. op de
    EUR-tegenwaarde. Dat gebeurde wanneer de koers stilzwijgend 1,0 werd.
    Geeft (wijzigingen, aantal_verdacht) terug; schrijft niets weg."""
    changes, suspect = [], 0
    for t in txns:
        if t.get("fx_manual") or t.get("tob_manual") or t.get("is_performance_share"):
            continue
        cur = t.get("currency") or "EUR"
        if cur == "EUR":
            continue   # zonder vreemde munt kan de FX-fout niet optreden
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
            "verdacht": verdacht,
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


def multiselect_delete(state_key, options_map, do_delete_one, noun="rij",
                       extra_warning="", container=None):
    """Multiselect om meerdere rijen te kiezen + wis-knop met EXPLICIETE bevestiging.
    options_map: dict {id: label} (invoegvolgorde = weergavevolgorde).
    do_delete_one(id): verwijdert één item."""
    c = container or st
    ids = list(options_map.keys())
    sel = c.multiselect(f"Selecteer {noun}(en) om te verwijderen", ids,
                        format_func=lambda i: options_map.get(i, str(i)),
                        key=f"{state_key}_ms", placeholder=f"Kies één of meerdere {noun}(en)…")
    pending = st.session_state.get(state_key)
    if pending:
        labels = [options_map.get(i, str(i)) for i in pending if i in options_map] or \
                 [str(i) for i in pending]
        preview = "; ".join(labels[:6]) + (f"  … (+{len(labels) - 6})" if len(labels) > 6 else "")
        st.warning(f"⚠️ {len(pending)} {noun}(en) definitief verwijderen? Dit kan niet ongedaan "
                   f"gemaakt worden.\n\n{preview}" + (f"\n\n{extra_warning}" if extra_warning else ""))
        cc1, cc2 = st.columns(2)
        if cc1.button("✅ Ja, definitief verwijderen", key=f"{state_key}_yes", width="stretch"):
            for i in pending:
                do_delete_one(i)
            st.session_state.pop(state_key, None)
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
        fx   = compute_eur(1.0, cur, ndat)[0] or 1.0
        A, C, Dv = d.get("gross_before_wht"), d.get("gross_after_wht"), d.get("net_received")
        if any(v is not None for v in (A, C, Dv)):
            # Native keten aanwezig: de bedragen blijven, enkel hun EUR-tegenwaarde wijzigt.
            prim       = A if A is not None else (C if C is not None else Dv)
            net_native = Dv if Dv is not None else (C if C is not None else prim)
            cbk        = d.get("cash_basis") or "net"
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


# ── PAGINA: Dashboard ─────────────────────────────────────────────────────────

def page_dashboard():
    st.title("📊 Dashboard")

    fc1, fc2 = st.columns([2, 3])
    with fc1:
        acct = account_filter_widget("dash_acct")
    with fc2:
        period = st.radio("Periode", ["YTD (dit jaar)", "Sinds start (all-time)"],
                          horizontal=True, key="dash_period", label_visibility="collapsed")
    all_time = period.startswith("Sinds")
    # Zienswijze performance shares (3 modi) — enkel zinvol, en dus enkel zichtbaar,
    # wanneer de GESELECTEERDE rekening(en) effectief producten met personenbelasting
    # bevatten. Bij 'alle rekeningen' (acct leeg) telt de hele portefeuille mee.
    has_inctax = has_income_tax(acct)
    pmode = perf_mode()
    if has_inctax:
        cur_i = PERF_MODES.index(pmode)
        pmode = st.radio(
            "🎁 Zienswijze performance shares (personenbelasting)", PERF_MODES, index=cur_i,
            format_func=lambda m: PERF_MODE_LABELS[m], key="dash_perf_mode",
            help="Bepaalt hoe de bij toekenning betaalde personenbelasting doorwerkt in totaal "
                 "geïnvesteerd, de ongerealiseerde W/V en de kostenweergave. Beïnvloedt enkel de "
                 "weergave van je rendement, niet de meerwaardebelasting.")
        if pmode != db.get_setting("perf_display_mode", "invested"):
            db.set_setting("perf_display_mode", pmode)
    if acct:
        st.caption(f"📂 Gefilterd op: **{', '.join(acct)}** — belastingcijfers blijven globaal (vrijstelling geldt per persoon).")

    year = datetime.now().year
    overview, assets, prices = get_overview(year, acct)
    pv = overview["position_values"]
    sel_realized = overview.get("selection_realized_gains", [])

    if not pv and not sel_realized:
        st.info("👋 Welkom! Voeg activa toe via **🏢 Activa** en daarna transacties via **➕ Transacties**.")
        return
    if not pv and sel_realized:
        st.info("ℹ️ Geen open posities voor deze selectie, maar er is wel een gerealiseerde historiek "
                "(bv. een rekening die je hebt afgesloten). Die zie je hieronder.")

    total_val  = overview["total_portfolio_value"]
    total_cost = overview["total_cost_basis"]
    unreal_gl  = overview["unrealized_gl"]
    real_gl    = overview["total_realized_gl"]
    tax_due    = overview["tax_due"]
    exemption  = overview["annual_exemption"]
    remaining  = overview["remaining_exemption"]

    # Periode-afhankelijke cijfers
    accset = set(acct) if acct else None

    # Performance-share aanpassingen op de aangehouden posities (afhankelijk van de modus)
    _ph = perf_held_summary(accset) if has_inctax else {"held_vesting": 0.0, "held_tax": 0.0, "total_tax": 0.0}
    inv_adj = wv_adj = pb_cost = 0.0
    if pmode == "invested":
        inv_adj = -_ph["held_vesting"] + _ph["held_tax"]   # kostbasis: vesting -> belasting
        wv_adj  = _ph["held_vesting"] - _ph["held_tax"]
    elif pmode == "cost":
        inv_adj = -_ph["held_vesting"]                      # kostbasis -> 0
        wv_adj  = _ph["held_vesting"]
        pb_cost = _ph["held_tax"]                           # personenbelasting als kost
    total_cost = (total_cost or 0) + inv_adj
    unreal_gl  = (unreal_gl or 0) + wv_adj
    divs_period = db.get_dividends(year=None if all_time else year)
    div_net = dividends_net_eur(divs_period, accset)
    realized_period = (overview.get("selection_realized_total", 0.0) if all_time
                       else overview.get("selection_realized_year", 0.0))
    period_lbl = "sinds start" if all_time else "YTD"

    # ── KPI-rij ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💼 Portefeuillewaarde", eur(total_val),
              delta=eur(unreal_gl), delta_color=delta_color(unreal_gl))
    c2.metric("💸 Totaal geïnvesteerd", eur(total_cost))
    c3.metric(f"📊 Gerealiseerde W/V ({period_lbl})", eur(realized_period),
              delta_color=delta_color(realized_period))
    _dben = tax_mod.dividend_tax_benefit(None if all_time else year, accset)
    div_benefit = _dben["total_benefit"]
    c4.metric(f"💰 Netto dividenden ({period_lbl})", eur(div_net),
              delta=(f"+{eur(div_benefit)} recup." if div_benefit else None),
              help="Netto ontvangen dividenden. De delta is de recupereerbare roerende voorheffing "
                   "(vrijstelling €833 p.p.) plus eventuele FBB voor Franse aandelen die je via de "
                   "belastingaangifte kunt terugkrijgen — zie 🧾 Belgische Belasting voor de uitwerking.")
    _kosten = overview.get("selection_costs", 0) + overview.get("account_costs_selection", 0) + pb_cost
    _klabel = "🧾 Kosten (txn + rekening" + (" + personenbel.)" if pb_cost else ")")
    c5.metric(_klabel, eur(_kosten),
              help="Transactiekosten + algemene rekeningkosten (bv. beheerskosten)"
                   + (", plus de personenbelasting op performance shares (die je in deze modus als kost telt)."
                      if pb_cost else ". Apart gehouden, niet in de meerwaardeberekening."))

    # ── Resultaat: ongerealiseerd + gerealiseerd + totaal (over de rekeningen heen) ──
    totale_wv = realized_period + (unreal_gl or 0)
    st.markdown(f"#### 📊 Resultaat ({period_lbl}, over alle geselecteerde rekeningen)")
    rc1, rc2, rc3 = st.columns(3)
    rc1.metric("Ongerealiseerde W/V", eur(unreal_gl), delta_color=delta_color(unreal_gl),
               help="Lopende winst/verlies op de posities die je nu aanhoudt (geselecteerde rekeningen).")
    rc2.metric("Gerealiseerde W/V", eur(realized_period), delta_color=delta_color(realized_period),
               help="Winst/verlies uit verkopen, over alle geselecteerde rekeningen heen — "
                    "ook van posities die elders heraangekocht zijn.")
    rc3.metric("Totale W/V (gereal. + ongereal.)", eur(totale_wv), delta_color=delta_color(totale_wv))
    _cash_avail = db.compute_cash_positions(accset)["totals"]["available"]
    st.caption(f"💶 **Beschikbare cash** (deze selectie): **{eur(_cash_avail)}** — om aandelen mee te "
               "kopen. Stortingen/opnames beheer je op de **💶 Cash**-pagina.")

    st.divider()

    # ── Dagresultaat per positie ─────────────────────────────────────────────
    st.subheader("📆 Dagresultaat vandaag")
    dpl = daily_pl(pv)
    if not dpl:
        st.info("Nog geen dagresultaat: daarvoor is minstens één koers van een vorige dag nodig. "
                "De achtergrondplanner legt elke 5 minuten koersen vast — morgen staat dit hier.")
    else:
        day_total = sum(d["pl_eur"] for d in dpl.values())
        base_val = sum((pv[t]["current_value"] or 0) - dpl[t]["pl_eur"] for t in dpl)
        day_pct = (day_total / base_val * 100) if base_val else 0.0
        winners = sum(1 for d in dpl.values() if d["pl_eur"] > 0)
        losers = sum(1 for d in dpl.values() if d["pl_eur"] < 0)

        d1, d2, d3 = st.columns([2, 1, 2])
        d1.metric("Dagresultaat portefeuille", eur(day_total), delta=pct(day_pct),
                  delta_color=delta_color(day_total),
                  help="Som van de dagelijkse winst/verlies van alle open posities in deze "
                       "selectie, t.o.v. de laatste koers van de vorige (beurs)dag.")
        d2.metric("Stijgers / dalers", f"{winners} / {losers}", delta_color="off")
        _best = max(dpl.items(), key=lambda kv: kv[1]["pl_eur"])
        _worst = min(dpl.items(), key=lambda kv: kv[1]["pl_eur"])
        _nm = asset_name_map()
        d3.markdown(f"🏆 **Beste vandaag:** {_nm.get(_best[0], _best[0])} "
                    f"({pct(_best[1]['change_pct'])}, {eur(_best[1]['pl_eur'])})  \n"
                    f"🐌 **Zwakste vandaag:** {_nm.get(_worst[0], _worst[0])} "
                    f"({pct(_worst[1]['change_pct'])}, {eur(_worst[1]['pl_eur'])})")

        names_dp = asset_name_map()
        # Tijdstip van de laatst vastgelegde koers per ticker (uit price_history) — dit
        # is wat de achtergrondplanner het recentst wegschreef. Zo zie je meteen of een
        # koers (bv. een US-aandeel) écht recent is of al dagen stilstaat.
        _last_ts = db.get_latest_prices(list(dpl))
        drows = []
        for t in sorted(dpl, key=lambda x: dpl[x]["pl_eur"], reverse=True):
            d = dpl[t]
            drows.append({
                "": sign_icon(d["pl_eur"]),
                "Activum":        asset_label(t, names_dp),
                "Aantal":         d["quantity"],
                "Vorige slot":    d["prev"],
                "Koers nu":       d["price"],
                "Δ vandaag (%)":  d["change_pct"],
                "Dag-P/L (€)":    d["pl_eur"],
                "Huidige waarde": pv[t]["current_value"],
                "Laatste update": _short_ts((_last_ts.get(t.upper()) or {}).get("timestamp")),
            })
        show_df(pd.DataFrame(drows), width="stretch", hide_index=True, column_config={
            "Aantal":         st.column_config.NumberColumn(format="%.10g"),
            "Vorige slot":    st.column_config.NumberColumn(format="%.10g"),
            "Koers nu":       st.column_config.NumberColumn(format="%.10g"),
            "Δ vandaag (%)":  st.column_config.NumberColumn(format="%+.10g%%"),
            "Dag-P/L (€)":    st.column_config.NumberColumn(format="€ %+.10g"),
            "Huidige waarde": st.column_config.NumberColumn(format="€ %.10g"),
            "Laatste update": st.column_config.TextColumn(
                help="Tijdstip (DD/MM UU:MM, Brusselse tijd) van de laatst vastgelegde koers "
                     "voor dit activum. Staat dit ver in het verleden, dan is de koers niet "
                     "meer ververst — bv. een tickerwijziging of een instrument dat geen enkele "
                     "bron nog terugvindt."),
        })
        _missing = [t for t in pv if t not in dpl]
        cap = ("Referentie = de laatste vastgelegde koers van de vorige (beurs)dag. Koersen en "
               "vorige slotkoersen staan in de native munt; de dag-P/L staat in euro. "
               "'Laatste update' = wanneer de planner de koers het recentst vastlegde.")
        if _missing:
            cap += (f"  ·  Geen vorige koers voor: {', '.join(names_dp.get(t, t) for t in _missing)} "
                    "(nog te weinig koershistoriek).")
        st.caption(cap)

    st.divider()

    # AI-ratingsynthese + wijzigingen sinds de vorige ronde (gedeeld door beide kolommen)
    dash_synth   = ai_advisor.rating_synthesis(list(pv.keys()), n_batches=9) if pv else {}
    dash_changes = ai_advisor.rating_changes(list(pv.keys())) if pv else {}

    col_l, col_r = st.columns([3, 2])

    with col_l:
        if not pv:
            st.caption("Geen open posities om grafisch te tonen voor deze selectie.")
        # Taartdiagram: verdeling op huidige waarde óf op geïnvesteerd kapitaal
        PIE_VALUE, PIE_COST = "💰 Huidige waarde", "📥 Geïnvesteerd kapitaal"
        sticky("dash_pie_basis", PIE_VALUE, [PIE_VALUE, PIE_COST])
        pie_basis = st.radio("Verdeling volgens", [PIE_VALUE, PIE_COST], horizontal=True,
                             key="dash_pie_basis", label_visibility="collapsed",
                             help="Huidige waarde = wat de posities vandaag waard zijn (dus mee "
                                  "bepaald door koersbewegingen). Geïnvesteerd kapitaal = de "
                                  "kostbasis, dus hoe je je geld effectief hebt verdeeld.")
        sticky_save("dash_pie_basis")
        on_cost = pie_basis == PIE_COST

        names_map = {a["ticker"]: a.get("name", a["ticker"]) for a in assets}
        labels = list(pv.keys())
        _pt = _ph.get("per_ticker", {}) if has_inctax else {}

        def _invested(t: str) -> float:
            """Geïnvesteerd kapitaal (EUR) voor één positie, in dezelfde zienswijze als de
            KPI 'Totaal geïnvesteerd' — anders zouden taart en cijfers elkaar tegenspreken."""
            base = pv[t].get("total_cost") or 0.0
            p = _pt.get(t)
            if p:
                if pmode == "invested":      # kostbasis: vestingwaarde -> betaalde belasting
                    base = base - p["vesting"] + p["tax"]
                elif pmode == "cost":        # kostbasis -> 0 (aandelen 'gratis')
                    base = base - p["vesting"]
            return max(0.0, base)

        raw = {t: (_invested(t) if on_cost else (pv[t]["current_value"] or 0)) for t in labels}
        labels = [t for t in labels if raw[t] > 0]   # posities met 0 vertekenen de taart niet
        values = [raw[t] for t in labels]
        names = [names_map.get(t, t) for t in labels]

        if not labels:
            st.caption("Geen bedragen om te tonen voor deze weergave.")
        else:
            _title = ("Samenstelling portefeuille — geïnvesteerd kapitaal" if on_cost
                      else "Samenstelling portefeuille — huidige waarde")
            fig_pie = go.Figure(go.Pie(
                labels=names, values=values,
                hole=0.45, textinfo="label+percent",
                hovertemplate="<b>%{label}</b><br>€%{value:,.2f}<extra></extra>",
            ))
            fig_pie.update_layout(
                title=_title,
                height=300, margin=dict(t=40, b=0, l=0, r=0),
                paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
            )
            st.plotly_chart(fig_pie, width='stretch')
            _tot = sum(values)
            if on_cost:
                st.caption(f"Totaal geïnvesteerd (deze selectie): **{eur(_tot)}** — de verdeling "
                           "van je inleg, los van koersbewegingen. Vergelijk met de huidige waarde "
                           "om te zien welke posities zwaarder of lichter zijn gaan wegen."
                           + ("  Performance shares volgen de gekozen zienswijze hierboven."
                              if _pt else ""))
            else:
                st.caption(f"Totale huidige waarde (deze selectie): **{eur(_tot)}** — het gewicht "
                           "van elke positie vandaag, inclusief koerswinst en -verlies.")

        # Staafdiagram: netto resultaat per activum (W/V + dividenden − kosten)
        names = asset_name_map()
        result = per_asset_result(overview, year=None if all_time else year, accounts=accset)
        if result:
            tickers_sorted = sorted(result.keys(), key=lambda t: perf_net(result[t], pmode))
            net_vals  = [perf_net(result[t], pmode) for t in tickers_sorted]
            wv_vals   = [result[t]["total"] for t in tickers_sorted]
            div_vals  = [result[t]["dividends"] for t in tickers_sorted]
            cost_vals = [result[t]["costs"] for t in tickers_sorted]
            tax_vals  = [result[t]["income_tax"] for t in tickers_sorted]
            labels    = [names.get(t, t) for t in tickers_sorted]
            colors    = ["#00b894" if v >= 0 else "#d63031" for v in net_vals]
            customdata = list(zip(tickers_sorted, wv_vals, div_vals, cost_vals, tax_vals))

            fig_bar = go.Figure(go.Bar(
                x=labels, y=net_vals, marker_color=colors,
                customdata=customdata,
                text=[f"€{v:,.0f}" for v in net_vals], textposition="outside",
                hovertemplate="<b>%{x}</b> (%{customdata[0]})<br>Netto resultaat: €%{y:,.2f}"
                              "<br>W/V (gereal.+ongereal.): €%{customdata[1]:,.2f}"
                              "<br>Dividenden: €%{customdata[2]:,.2f}"
                              "<br>Kosten (txn + TOB): −€%{customdata[3]:,.2f}"
                              "<br>Personenbelasting: −€%{customdata[4]:,.2f}<extra></extra>",
            ))
            fig_bar.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.3)")
            fig_bar.update_layout(
                title=f"Netto resultaat per activum ({period_lbl})",
                height=300, showlegend=False,
                margin=dict(t=40, b=30, l=20, r=20),
                plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(fig_bar, width='stretch')
            tot_inctax = sum(r["income_tax"] for r in result.values())
            tot_net    = sum(perf_net(r, pmode) for r in result.values())
            if tot_inctax and pmode == "grant":
                cap = "Performance shares gerekend aan de toekenningswaarde (zuivere meerwaarde)."
            elif tot_inctax:
                cap = ("Performance shares gerekend aan de betaalde personenbelasting "
                       "(reële winst = huidige waarde − belasting).")
            else:
                cap = "Netto = ongerealiseerde + gerealiseerde W/V + dividenden − kosten (txn + TOB)."
            st.caption(cap + f"  **Totaal netto: {eur(tot_net)}**"
                       + (f"  ·  betaalde personenbelasting: {eur(tot_inctax)}" if tot_inctax else ""))

    with col_r:
        # Belastingstatus
        st.subheader(f"🧾 Belasting {year}")
        taxable_gl = overview.get("total_taxable_gl", real_gl)
        pct_used = min(100.0, taxable_gl / exemption * 100) if exemption > 0 else 0
        color_lbl = "🟢" if pct_used < 60 else ("🟡" if pct_used < 90 else "🔴")

        st.metric("Netto gerealiseerde W/V", eur(real_gl),
                  delta_color=delta_color(real_gl))
        if overview.get("fotomoment_applied") and abs(taxable_gl - real_gl) > 0.005:
            st.caption(f"📸 Belastbare basis na fotomoment (31/12/2025): **{eur(taxable_gl)}** "
                       "— de winst van vóór 2026 is vrijgesteld.")
        st.progress(max(0.0, min(1.0, pct_used / 100)),
                    text=f"{color_lbl} {pct_used:.1f}% van vrijstelling (€{exemption:,.0f})")

        if tax_due > 0:
            st.error(f"💰 Geschatte meerwaardebelasting: **{eur(tax_due)}**")
        else:
            st.success(f"✅ Nog {eur(remaining)} vrije ruimte")

        st.divider()

        # AI-advies: enkel de kooptips (zonder uitleg) + link naar de AI-pagina
        st.subheader("🤖 AI-kooptips")
        names_d = asset_name_map()
        buy_tips = [tk for tk in pv
                    if dash_synth.get(tk, {}).get("consensus") in ("strong_buy", "buy")]
        if buy_tips:
            buy_tips.sort(key=lambda tk: 0 if dash_synth[tk]["consensus"] == "strong_buy" else 1)
            for tk in buy_tips:
                cons = dash_synth[tk]["consensus"]
                st.markdown(f"- {RATING_BADGE[cons]} — **{asset_label(tk, names_d)}**"
                            f"{change_arrow(dash_changes.get(tk))}")
        else:
            st.caption("Geen actuele kooptips. Genereer/actualiseer het advies via 🤖 AI Advisor.")

        if dash_changes:
            ups = [tk for tk, c in dash_changes.items() if c["up"]]
            downs = [tk for tk, c in dash_changes.items() if not c["up"]]
            parts = []
            if ups:
                parts.append("🔺 opgewaardeerd: " + ", ".join(names_d.get(t, t) for t in ups))
            if downs:
                parts.append("🔻 afgewaardeerd: " + ", ".join(names_d.get(t, t) for t in downs))
            st.caption("**Advieswijzigingen sinds de vorige ronde** — " + "  ·  ".join(parts))

        if st.button("➡️ Naar AI Advisor", key="dash_to_ai", width="stretch"):
            st.session_state["nav_goto"] = "🤖 AI Advisor"
            st.rerun()

    st.divider()
    st.subheader("📊 Gerealiseerde meer-/minwaarden (historiek)")
    if acct:
        st.caption(f"Rekeningen **{', '.join(acct)}** — ook zichtbaar wanneer de huidige positie 0 is "
                   "(bv. een afgesloten rekening).")
    else:
        st.caption("Over alle rekeningen heen, alle jaren — inclusief winst/verlies uit "
                   "verkochte en elders heraangekochte posities.")
    render_realized_history(overview.get("selection_realized_gains", []), asset_name_map())


# ── PAGINA: Portefeuille ───────────────────────────────────────────────────────

def page_portfolio():
    st.title("💼 Portefeuille")

    col_btn, col_acct, _ = st.columns([1, 2, 3])
    if col_btn.button("🔄 Ververs prijzen"):
        clear_cache()
        md._CACHE.clear()
        # Eenmalig live ophalen forceren: get_overview leest anders gewoon de
        # opgeslagen scheduler-koersen terug (DB-first sinds 0.30.0).
        st.session_state["force_live_prices"] = True
        st.rerun()
    with col_acct:
        acct = account_filter_widget("port_acct")

    year = datetime.now().year
    live = bool(st.session_state.pop("force_live_prices", False))
    if live:
        with st.spinner("Actuele koersen live ophalen..."):
            overview, assets, prices = get_overview(year, acct, live=True)
    else:
        overview, assets, prices = get_overview(year, acct)
    pv = overview["position_values"]

    if not pv:
        if overview.get("selection_realized_gains"):
            st.info("Geen open posities voor deze selectie, maar er is wel een gerealiseerde "
                    "historiek (bv. verkocht en elders heraangekocht). Die zie je hieronder.")
            st.subheader("📊 Gerealiseerde meer-/minwaarden (historiek)")
            render_realized_history(overview["selection_realized_gains"], asset_name_map())
        else:
            st.info("Geen open posities. Voeg transacties toe via ➕ Transacties.")
        return

    assets_map = {a["ticker"]: a for a in assets}
    divs_net = {}
    for d in db.get_dividends():
        if d.get("net_eur") is not None:
            n = d["net_eur"]
        else:
            g = d.get("gross_eur") if d.get("gross_eur") is not None else d["gross_amount"]
            w = d.get("withholding_eur") if d.get("withholding_eur") is not None else d["withholding_tax"]
            n = g - w
        divs_net[d["ticker"]] = divs_net.get(d["ticker"], 0) + n

    # Koersdoelen: activum-niveau (ingesteld bij toevoegen) heeft voorrang — dat is
    # de meest bewuste, actuele keuze. Anders het laatste transactie-koersdoel, en
    # als allerlaatste terugval het AI-koersdoel.
    price_targets = {}
    for a in db.get_assets():
        if a.get("price_target") is not None:
            price_targets[a["ticker"]] = a["price_target"]
    for t in db.get_transactions():           # ASC op datum -> laatste wint
        if t.get("price_target") is not None and t["ticker"] not in price_targets:
            price_targets[t["ticker"]] = t["price_target"]
    for tk in pv:
        if tk not in price_targets:
            pt = db.get_latest_price_target(tk)
            if pt:
                price_targets[tk] = pt["price_target"]

    accset = set(acct) if acct else None
    nmap = asset_name_map()

    # AI-ratingsynthese + wijzigingen t.o.v. de vorige ronde
    synth   = ai_advisor.rating_synthesis(list(pv.keys()), n_batches=9)
    changes = ai_advisor.rating_changes(list(pv.keys()))
    n_rounds = len(db.get_recent_rating_batches(9))

    # ── Renderblokken (volgorde wordt onderaan bepaald) ───────────────────────

    def render_per_asset():
        _pm = perf_mode()
        st.subheader("📊 Totaal resultaat per activum")
        _mnote = {"cost": "personenbelasting als kost (kostbasis €0)",
                  "invested": "reële winst = huidige waarde − personenbelasting",
                  "grant": "meerwaarde t.o.v. de toekenningsprijs (personenbelasting genegeerd)"}[_pm]
        st.caption("Per activum: ongerealiseerde + gerealiseerde W/V, ontvangen dividenden, gelinkte "
                   "kosten (transactiekosten + TOB) en de personenbelasting op performance shares. "
                   f"Zienswijze performance shares: **{_mnote}** (in te stellen op het dashboard).")
        result = per_asset_result(overview, year=None, accounts=accset)
        if not result:
            st.info("Nog geen posities of historiek voor deze selectie.")
            return
        any_inctax = any(r["income_tax"] for r in result.values())
        rrows = []
        for t in sorted(result.keys(), key=lambda x: perf_net(result[x], _pm), reverse=True):
            r = result[t]
            rec = synth.get(t, {}).get("consensus")
            net = perf_net(r, _pm)
            # In modus 'cost' toont de kostenkolom de personenbelasting mee
            kosten_disp = r["costs"] + (r["income_tax"] if _pm == "cost" else 0)
            row = {
                "W/V":                 sign_icon(net),
                "Activum":             asset_label(t, nmap),
                "Aantal (nu)":         r["quantity"] or 0.0,
                "Huidige waarde":      r["current_value"],
                "Ongerealiseerd":      r["unrealized"] + (r["perf_basis"] if _pm == "cost"
                                           else (r["perf_basis"] - r["income_tax"]) if _pm == "invested" else 0),
                "Gerealiseerd":        r["realized"],
                "Dividenden":          r["dividends"],
                "Kosten":              kosten_disp,
            }
            if any_inctax:
                row["Personenbel."] = r["income_tax"] or 0.0
            row["Netto resultaat"] = net
            row["AI-advies"]       = ai_badge(rec, changes.get(t))
            rrows.append(row)
        _rr_cfg = {
            "Aantal (nu)":    st.column_config.NumberColumn(format="%.10g"),
            "Huidige waarde": st.column_config.NumberColumn(format="€ %.10g"),
            "Ongerealiseerd": st.column_config.NumberColumn(format="€ %.10g"),
            "Gerealiseerd":   st.column_config.NumberColumn(format="€ %.10g"),
            "Dividenden":     st.column_config.NumberColumn(format="€ %.10g"),
            "Kosten":         st.column_config.NumberColumn(format="€ %.10g"),
            "Netto resultaat": st.column_config.NumberColumn(format="€ %.10g"),
        }
        if any_inctax:
            _rr_cfg["Personenbel."] = st.column_config.NumberColumn(format="€ %.10g")
        show_df(pd.DataFrame(rrows), width="stretch", hide_index=True, column_config=_rr_cfg)
        tu = sum(r["unrealized"] for r in result.values())
        tr = sum(r["realized"] for r in result.values())
        tdv = sum(r["dividends"] for r in result.values())
        tc = sum(r["costs"] for r in result.values())
        tpb = sum(r["income_tax"] for r in result.values())
        net_all = sum(perf_net(r, _pm) for r in result.values())
        extra = (f"  Personenbelasting performance shares: {eur(tpb)} "
                 f"({'als kost' if _pm=='cost' else 'als kostbasis' if _pm=='invested' else 'genegeerd'})." if tpb else "")
        st.caption(f"**Totaal netto resultaat: {eur(net_all)}**  ·  "
                   "🟢 = positief, 🔴 = negatief.  🔺/🔻 = advies gewijzigd sinds de vorige ronde." + extra)

    def render_positions():
        st.subheader("📋 Open posities")
        rows = []
        for ticker, pos in pv.items():
            asset = assets_map.get(ticker, {})
            div = divs_net.get(ticker, 0)
            total_return = (pos["unrealized_gain_loss"] or 0) + div
            tgt = price_targets.get(ticker)
            upside = None
            if tgt and pos["current_price"]:
                upside = (tgt - pos["current_price"]) / pos["current_price"] * 100
            rec = synth.get(ticker, {}).get("consensus")
            rows.append({
                "":             sign_icon(pos["unrealized_gain_loss"]),
                "Ticker":       ticker,
                "Naam":         (asset.get("name") or ticker)[:20],
                "Munt":         pos["current_price_currency"] or "EUR",
                "Aantal":       pos["quantity"],
                "Gem.kostpr.(€)":  pos["avg_cost"],
                "Koers (native)":  pos["current_price"] if pos["current_price"] else None,
                "Koersdoel":    tgt,
                "Potentieel":   upside,
                "Huidige waarde": pos["current_value"],
                "W/V (%)":      pos["unrealized_gain_loss_pct"],
                "Dividend":     div,
                "Tot. rendement": total_return,
                "AI-advies":    ai_badge(rec, changes.get(ticker)),
            })
        show_df(pd.DataFrame(rows), width="stretch", hide_index=True, height=420, column_config={
            "Aantal":           st.column_config.NumberColumn(format="%.10g"),
            "Gem.kostpr.(€)":   st.column_config.NumberColumn(format="%.10g"),
            "Koers (native)":   st.column_config.NumberColumn(format="%.10g"),
            "Koersdoel":        st.column_config.NumberColumn(format="%.10g"),
            "Potentieel":       st.column_config.NumberColumn(format="%+.10g%%"),
            "Huidige waarde":   st.column_config.NumberColumn(format="€ %.10g"),
            "W/V (%)":          st.column_config.NumberColumn(format="%+.10g%%"),
            "Dividend":         st.column_config.NumberColumn(format="€ %.10g"),
            "Tot. rendement":   st.column_config.NumberColumn(format="€ %.10g"),
        })

        total_val  = overview["total_portfolio_value"]
        total_cost = overview["total_cost_basis"]
        tot_gl     = overview["unrealized_gl"]
        tot_div    = dividends_net_eur(db.get_dividends(), accset)   # all-time, rekening-bewust
        txn_costs  = overview.get("selection_costs", 0)
        acct_costs = overview.get("account_costs_selection", 0)
        all_costs  = txn_costs + acct_costs
        net_return = tot_gl + tot_div - all_costs
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Totaal geïnvesteerd", eur(total_cost))
        c2.metric("Totale waarde",       eur(total_val))
        c3.metric("Ongerealiseerde W/V", eur(tot_gl),
                  delta=pct(tot_gl / total_cost * 100 if total_cost else 0),
                  delta_color=delta_color(tot_gl))
        c4.metric("Netto dividenden (all-time)", eur(tot_div))
        c5.metric("Kosten (txn + rekening)", eur(all_costs),
                  help="Transactiekosten + algemene rekeningkosten (bv. beheerskosten). "
                       "Drukken het nettorendement, los van de meerwaardeberekening.")
        st.caption(f"💡 Nettorendement na kosten: **{eur(net_return)}**  "
                   f"(ongerealiseerde W/V + dividenden − kosten). "
                   f"Waarvan transactiekosten {eur(txn_costs)} en rekeningkosten {eur(acct_costs)}.")
        _cash = db.compute_cash_positions(accset)["totals"]["available"]
        st.caption(f"💶 **Beschikbare cash** (deze selectie): **{eur(_cash)}** — beheer stortingen en "
                   "opnames via de **💶 Cash**-pagina.")

    def render_realized():
        st.subheader("📊 Gerealiseerde meer-/minwaarden (historiek)")
        if acct:
            st.caption(f"Rekeningen **{', '.join(acct)}**.")
        else:
            st.caption("Alle rekeningen, alle jaren — zo zie je de volledige historiek van een "
                       "activum, ook als het op de ene rekening verkocht en op een andere heraangekocht is.")
        render_realized_history(overview.get("selection_realized_gains", []), nmap)

    def render_ai_synth():
        sc1, sc2 = st.columns([3, 1])
        sc1.subheader(f"🤖 AI-advies — synthese ({n_rounds} dag(en))")
        with sc2:
            if st.button("🔄 Genereer advies", key="gen_ratings",
                         help="Genereert het volledige dagelijkse portefeuilleadvies (tekst + ratings)."):
                if not db.get_setting("openai_api_key", ""):
                    st.warning("Geen OpenAI-sleutel — stel die in via ⚙️ Instellingen.")
                else:
                    with st.spinner("AI beoordeelt je portefeuille..."):
                        res = ai_advisor.generate_daily_portfolio_advice()
                    if res.get("error"):
                        st.error(res["error"])
                    else:
                        if res.get("truncated"):
                            st.warning(f"⚠️ Antwoord afgekapt: {res['stored']} van de "
                                       f"{res.get('expected', '?')} posities kregen een rating.")
                        else:
                            st.success(f"✅ Advies gegenereerd ({res['stored']} ratings).")
                        st.rerun()

        # Tekstadvies uit het laatste dagelijkse advies
        latest = db.get_ai_evaluations("daily_advice", limit=1)
        if latest and (latest[0].get("content") or "").strip():
            ev = latest[0]
            with st.expander("📝 Volledig tekstadvies (laatste dag)", expanded=False):
                st.caption(f"📅 {ev['created_at'][:16]}")
                st.markdown(ev["content"])

        if synth:
            srows = []
            for tk in pv:
                s = synth.get(tk)
                ch = changes.get(tk)
                delta = "🔺" if (ch and ch["up"]) else ("🔻" if ch else "")
                if not s:
                    srows.append({"Ticker": tk, "Consensus": "—", "Δ": "", "Laatste": "—",
                                  "Sterk kopen": 0, "Kopen": 0, "Behouden": 0,
                                  "Verkopen": 0, "Sterk verkopen": 0, "Koersdoel": "—"})
                    continue
                c = s["counts"]
                srows.append({
                    "Ticker":         tk,
                    "Consensus":      RATING_BADGE.get(s["consensus"], "—"),
                    "Δ":              delta,
                    "Laatste":        ai_advisor.RATING_LABELS.get(s["latest"], "—"),
                    "Sterk kopen":    c["strong_buy"],
                    "Kopen":          c["buy"],
                    "Behouden":       c["hold"],
                    "Verkopen":       c["sell"],
                    "Sterk verkopen": c["strong_sell"],
                    "Koersdoel":      f"{s['latest_target']:.2f} {s['currency']}" if s.get("latest_target") else "—",
                })
            show_df(pd.DataFrame(srows), width="stretch", hide_index=True)
            st.caption(f"Synthese van de ratings uit de laatste {n_rounds} (max 9) dagelijkse adviezen per ticker. "
                       "Consensus = meest voorkomende rating. Δ 🔺/🔻 = bullisher/bearisher dan de vorige dag. "
                       "Het advies wordt elke werkdag automatisch gegenereerd; met de knop kun je het meteen vernieuwen.")
        else:
            st.info("Nog geen AI-advies. Klik op '🔄 Genereer advies' voor het eerste dagelijkse advies "
                    "(of wacht op de automatische dagelijkse run).")

    def render_price_history():
        st.subheader("📈 Prijsgeschiedenis")
        tickers = list(pv.keys())
        sel = st.selectbox("Selecteer positie:", tickers,
                           format_func=lambda t: asset_label(t, nmap))
        days = st.slider("Aantal dagen:", 1, 90, 14)
        hist = db.get_price_history(sel, days=days)
        if hist:
            df_h = pd.DataFrame(hist)
            df_h["timestamp"] = pd.to_datetime(df_h["timestamp"])
            avg_cost = pv[sel]["avg_cost"]
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_h["timestamp"], y=df_h["price"],
                mode="lines", line=dict(color="#74b9ff", width=2),
                fill="tozeroy", fillcolor="rgba(116,185,255,0.08)",
                name=nmap.get(sel, sel),
            ))
            fig.add_hline(y=avg_cost, line_dash="dash", line_color="#fdcb6e",
                          annotation_text=f"Gem. kostprijs {num(avg_cost, 2)}")
            fig.update_layout(
                title=f"{asset_label(sel, nmap)} — {days} dagen",
                height=340, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=40, b=30, l=20, r=20),
            )
            st.plotly_chart(fig, width="stretch")
        else:
            st.info("Nog geen prijsgeschiedenis. De scheduler slaat elke 5 minuten koersen op.")

    # Volgorde: totaal per activum → open posities → gerealiseerde historiek → AI-synthese → prijsgeschiedenis
    render_per_asset()
    st.divider()
    render_positions()
    st.divider()
    render_realized()
    st.divider()
    render_ai_synth()
    st.divider()
    render_price_history()


# ── PAGINA: Activa ────────────────────────────────────────────────────────────

def page_assets():
    st.title("🏢 Activa beheren")

    CUR = ["EUR", "USD", "GBP", "CHF"]
    _asec = _section_radio("assets_section",
        ["➕ Activum toevoegen", "📋 Overzicht", "🔀 Splitsingen"])

    if _asec == "➕ Activum toevoegen":
        n = st.session_state.get("as_nonce", 0)
        def k(name): return f"as_{name}_{n}"

        st.caption("Tip: vul de ticker in en klik op **🔍 Info ophalen** — naam, munt, type, beurs en ISIN "
                   "worden dan ingevuld in het formulier, zodat je ze kunt nakijken vóór je opslaat.")
        c1, c2 = st.columns(2)
        with c1:
            ticker = st.text_input("Ticker *", placeholder="bv. AAPL, VWCE.AS", key=k("ticker"))
            if st.button("🔍 Info ophalen via Yahoo Finance", key=k("fetch")):
                if not ticker.strip():
                    st.warning("Vul eerst een ticker in.")
                else:
                    with st.spinner("Info ophalen via Yahoo Finance..."):
                        info = md.get_stock_info(ticker.strip().upper())
                    _tk = ticker.strip().upper()
                    if not info.get("found") and md._isin_valid(_tk):
                        # Geen Yahoo-notering, maar het is een geldige ISIN (bv. een warrant).
                        # Vul naam/type/beurs/land in en probeer de munt/koers via externe bronnen.
                        with st.spinner("ISIN testen op externe bronnen..."):
                            _p, _c, _src = md.probe_isin(_tk)
                            _meta = md.probe_isin_meta(_tk)
                        st.session_state[k("isin")] = _tk
                        st.session_state[k("country")] = _tk[:2]
                        st.session_state[k("cur")] = _c or "EUR"
                        st.session_state[k("isin_only_src")] = _src or ""
                        if _meta.get("name"):
                            st.session_state[k("name")] = _meta["name"]
                        if _meta.get("type"):
                            st.session_state[k("type")] = _meta["type"]
                        if _meta.get("exchange"):
                            st.session_state[k("exch")] = _meta["exchange"]
                        st.session_state[k("fetched")] = True
                        st.rerun()
                    elif not info.get("found"):
                        st.error(
                            f"❌ Yahoo Finance vond geen gegevens voor '{_tk}'. "
                            "Controleer de ticker — Europese beurzen vereisen een suffix "
                            "(bv. .PA Parijs, .AS Amsterdam, .BR Brussel, .DE Xetra, .MI Milaan, .L Londen). "
                            "Heeft dit effect geen ticker maar wél een ISIN (bv. een warrant)? "
                            "Vul dan de ISIN in het Ticker-veld in.")
                    else:
                        st.session_state[k("name")] = info.get("name", "") or ""
                        st.session_state[k("cur")]  = info.get("currency", "EUR") or "EUR"
                        st.session_state[k("type")] = info.get("type", "stock") or "stock"
                        st.session_state[k("exch")] = info.get("exchange", "") or ""
                        st.session_state[k("isin")] = info.get("isin", "") or ""
                        _isin = (info.get("isin") or "").strip().upper()
                        if len(_isin) >= 2 and _isin[:2].isalpha():
                            st.session_state[k("country")] = _isin[:2]
                        st.session_state[k("fetched")] = True
                        if not (info.get("isin") or "").strip():
                            st.session_state[k("isin_missing")] = True
                        else:
                            st.session_state.pop(k("isin_missing"), None)
                        st.rerun()
            if st.session_state.get(k("isin_missing")):
                st.warning("ℹ️ Yahoo gaf voor deze ticker geen ISIN mee (komt vaak voor bij "
                           ".BR/.DE-listings). Vul de ISIN hieronder handmatig in — je vindt ze op "
                           "de website van de uitgever, op justETF, of op de beurspagina.")
            name = st.text_input("Naam *", key=k("name"),
                                 placeholder="bv. Vanguard FTSE All-World")
            cur_val  = st.session_state.get(k("cur"), "EUR")
            cur_opts = CUR if cur_val in CUR else CUR + [cur_val]
            currency = st.selectbox("Munt", cur_opts, key=k("cur"))
        with c2:
            asset_type = st.radio("Type", ["stock", "etf", "bond"],
                                  format_func=lambda x: {"stock": "📊 Aandeel", "etf": "🧺 ETF/fonds", "bond": "📈 Obligatie"}[x],
                                  key=k("type"))
            etf_subtype = "distributing"
            belg_reg = True
            if asset_type == "etf":
                etf_subtype = st.radio("ETF-type", ["distributing", "accumulating"],
                                       format_func=lambda x: "📤 Uitkerend (distributie)" if x == "distributing" else "📦 Kapitaliserend",
                                       help="Samen met de registratie bepaalt dit de TOB.", key=k("sub"))
                belg_reg = st.checkbox("🇧🇪 In België aangeboden / geregistreerd (FSMA)",
                                       value=st.session_state.get(k("breg"), True), key=k("breg"),
                                       help="Vink AAN voor in België aangeboden fondsen (TOB 0,12% uitkerend / 1,32% kapitaliserend). "
                                            "Vink UIT voor niet in België aangeboden trackers/ETC's (bv. G2XJ.DE): dan geldt 0,35%.")
            exchange = st.text_input("Beurs", key=k("exch"), placeholder="bv. NMS, AMS")
            isin     = st.text_input("ISIN", key=k("isin"), placeholder="bv. IE00BK5BQT80")
            _clist = list(tax_mod.COUNTRY_NAMES.keys())
            # Default via session state (géén index-parameter): de fetch-flows zetten
            # het land ook via st.session_state, en Streamlit staat niet toe dat een
            # widget zowel een default als een session-state-waarde krijgt.
            st.session_state.setdefault(k("country"), "BE")
            if st.session_state[k("country")] not in _clist:
                _clist = _clist + [st.session_state[k("country")]]
            country = st.selectbox("Land van herkomst", _clist, key=k("country"),
                                   format_func=lambda c: f"{c} — {tax_mod.COUNTRY_NAMES.get(c, c)}",
                                   help="Bepaalt het tarief van de buitenlandse bronbelasting bij "
                                        "dividenden (zie ⚙️ Instellingen). Tip: het land van de "
                                        "uitgever, vaak herkenbaar aan de eerste 2 letters van de ISIN.")

        # TOB-indicatie tonen
        _tob_rate = tax_mod.calculate_tob(asset_type, etf_subtype, 10000, belg_reg) / 10000 * 100
        st.caption(f"➡️ TOB-tarief voor dit activum: **{_tob_rate:.2f}%**".replace(".", ","))

        # Fotomoment (slotkoers 31/12/2025) — voor de meerwaardebelasting op vóór-2026 stukken
        st.session_state.setdefault(k("snap_stage"), None)
        st.session_state.setdefault("as_snap_nonce", 0)
        snn = st.session_state["as_snap_nonce"]
        fm1, fm2 = st.columns([2, 1])
        with fm1:
            snap_val = st.number_input(
                f"📸 Fotomomentwaarde 31/12/2025 ({currency}/stuk) — optioneel",
                min_value=0.0, step=0.01, format="%.10g",
                value=st.session_state[k("snap_stage")], key=f"as_snap_{n}_{snn}",
                help="Slotkoers op 31/12/2025. Voor stukken die je vóór 2026 kocht vertrekt de "
                     "belastbare meerwaarde van de hoogste van (werkelijke aankoopprijs, fotomomentwaarde). "
                     "Laat leeg voor activa die je pas vanaf 2026 koopt.")
        with fm2:
            st.write(""); st.write("")
            if st.button("📸 Ophalen 31/12/2025", key=k("snapfetch")):
                if not ticker.strip():
                    st.warning("Vul eerst een ticker in.")
                else:
                    with st.spinner("Slotkoers 31/12/2025 ophalen..."):
                        p = md.get_close_on_date(ticker.strip().upper(), tax_mod.SNAPSHOT_DATE)
                    if p is None:
                        st.error(
                            "Geen slotkoers gevonden voor 31/12/2025. Kocht je dit activum pas "
                            "**vanaf 2026**? Dan heb je geen fotomomentwaarde nodig — laat het "
                            "veld gewoon leeg (zie tip hierboven). Effecten die pas in 2026 "
                            "uitgegeven of verhandeld werden (zoals sommige warrants/certificaten) "
                            "hadden op 31/12/2025 uiteraard nog geen koers. Bezat je dit al vóór "
                            "2026, vul de koers dan handmatig in.")
                    else:
                        st.session_state[k("snap_stage")] = float(p)
                        st.session_state["as_snap_nonce"] = snn + 1
                        st.rerun()
        if snap_val and snap_val > 0 and currency != "EUR":
            _fxs, _snap_eur_prev = compute_eur(snap_val, currency, tax_mod.SNAPSHOT_DATE)
            st.caption(f"≈ €{num(_snap_eur_prev, 2)}/stuk (koers 31/12/2025: {_fxs:.4f})")

        # Koersdoel meteen bij het toevoegen instellen (i.p.v. pas bij een transactie).
        # Staging analoog aan het koersdoel in het transactieformulier, maar met eigen
        # keys (as_pt_*) zodat beide formulieren elkaars widgetstatus niet delen.
        st.session_state.setdefault(k("pt_stage"), 0.0)
        st.session_state.setdefault("as_pt_nonce", 0)
        ptn = st.session_state["as_pt_nonce"]
        ptc1, ptc2 = st.columns([2, 1])
        with ptc1:
            price_target = st.number_input(
                f"🎯 Koersdoel (optioneel, {currency})", min_value=0.0, step=0.01,
                format="%.10g", value=float(st.session_state[k("pt_stage")]),
                key=f"as_pt_input_{n}_{ptn}",
                help="Je koersdoel voor dit activum — verschijnt op het dashboard en wordt "
                     "gebruikt bij het AI-advies. Kan later nog aangepast worden via een "
                     "transactie of in het overzicht hieronder.")
        with ptc2:
            st.write(""); st.write("")
            if st.button("🤖 Bepaal via AI", key=k("ai_pt")):
                if not ticker.strip():
                    st.warning("Vul eerst een ticker in.")
                elif not db.get_setting("openai_api_key", ""):
                    st.warning("Geen OpenAI-sleutel — stel die in via ⚙️ Instellingen.")
                else:
                    with st.spinner("AI bepaalt koersdoel..."):
                        res = ai_advisor.suggest_price_target(ticker.strip().upper())
                    if res.get("error"):
                        st.error(res["error"])
                    else:
                        st.session_state[k("pt_stage")] = float(res["price_target"])
                        st.session_state["as_pt_nonce"] = ptn + 1
                        st.session_state[k("pt_info")] = (
                            f"🎯 AI-koersdoel {res['price_target']:.2f} {res['currency']} "
                            f"(model {res.get('model','?')}). {res.get('rationale','')} {res.get('scenario','')}")
                        st.rerun()
        if st.session_state.get(k("pt_info")):
            st.caption(st.session_state.pop(k("pt_info")))

        if st.session_state.get(k("fetched")):
            _src = st.session_state.get(k("isin_only_src"))
            if _src is not None:
                # ISIN-only activum (geen Yahoo-notering, bv. een warrant)
                _name_found = bool(st.session_state.get(k("name")))
                if _src and _name_found:
                    st.success(f"✅ ISIN herkend — naam ingevuld en automatische koers beschikbaar "
                               f"via **{_src}**. Controleer de velden en klik op Toevoegen.")
                elif _src:
                    st.success(f"✅ ISIN herkend — automatische koers beschikbaar via **{_src}**, "
                               "maar geen naam gevonden. Vul zelf een **naam** in en klik op Toevoegen.")
                elif _name_found:
                    st.info("ℹ️ Naam gevonden, maar (nog) geen automatische koers. Controleer de "
                            "velden en klik op Toevoegen — de app blijft koersen proberen via de "
                            "ISIN (onvista, Börse Frankfurt, Tradegate, Lang & Schwarz). Lukt dat "
                            "niet, zet dan een **handmatige koers** in het overzicht als laatste redmiddel.")
                else:
                    st.info("ℹ️ Deze ISIN staat niet op Yahoo en er werd (nog) geen naam of externe koers "
                            "gevonden. Vul zelf een **naam** in en klik op Toevoegen — de app blijft koersen "
                            "proberen via de ISIN (onvista, Börse Frankfurt, Tradegate, Lang & Schwarz). "
                            "Lukt dat niet, zet dan een **handmatige koers** in het overzicht als laatste "
                            "redmiddel.")
            else:
                st.success("✨ Velden ingevuld via Yahoo Finance — controleer en pas aan waar nodig, en klik daarna op Toevoegen.")

        if st.button("✅ Activum toevoegen", type="primary", key=k("save")):
            if not ticker.strip():
                st.error("Vul een ticker in.")
            elif not name.strip():
                st.error("Vul een naam in (verplicht). Gebruik eventueel '🔍 Info ophalen' om die automatisch in te vullen.")
            else:
                t = ticker.strip().upper()
                db.add_asset(t, name.strip(), asset_type, etf_subtype,
                             currency, exchange.strip() or None, isin.strip() or None,
                             belgian_registered=int(belg_reg), country=country,
                             price_target=(price_target or None),
                             price_target_currency=(currency if price_target else None))
                if snap_val and snap_val > 0:
                    _fx, snap_eur = compute_eur(snap_val, currency, tax_mod.SNAPSHOT_DATE)
                    db.set_asset_snapshot(t, float(snap_val), snap_eur)
                clear_cache()
                st.session_state["as_nonce"] = n + 1   # formulier leegmaken
                st.session_state["as_pt_nonce"] = ptn + 1
                st.success(f"✅ {t} — {name.strip()} toegevoegd!")
                st.rerun()

    if _asec == "📋 Overzicht":
        st.session_state.pop("edit_asset", None)  # inline bewerken vervangt het oude formulier

        assets = db.get_assets()
        if not assets:
            st.info("Nog geen activa geregistreerd.")
            return

        f_asset = st.text_input("🔎 Filter op naam of ticker", key="asset_filter",
                                placeholder="bv. Apple, VWCE, STMPA.PA")
        if f_asset.strip():
            q = f_asset.strip().lower()
            assets = [a for a in assets
                      if q in (a.get("name") or "").lower() or q in a["ticker"].lower()]
        if not assets:
            st.info("Geen activa gevonden voor deze filter.")
            return
        st.caption(f"{len(assets)} activum/activa")
        a_names = {a["ticker"]: (a.get("name") or a["ticker"]) for a in assets}
        TYPE_LBL = {"stock": "Aandeel", "etf": "ETF", "bond": "Obligatie"}
        TYPE_KEY = {v: k for k, v in TYPE_LBL.items()}
        SUB_LBL  = {"distributing": "uitkerend", "accumulating": "kapitaliserend", "": "—"}
        SUB_KEY  = {v: k for k, v in SUB_LBL.items()}
        ACUR = ["EUR", "USD", "GBP", "CHF"]
        clist = list(tax_mod.COUNTRY_NAMES.keys())
        rows = []
        for a in assets:
            lp = db.get_latest_price(a["ticker"])
            mp = a.get("manual_price")
            sub = a.get("etf_subtype") if a["asset_type"] == "etf" else ""
            cur = a["currency"] if a["currency"] in ACUR else "EUR"
            ctry = (a.get("country") or "BE").upper()
            rows.append({
                "Ticker":     a["ticker"],
                "Naam":       a.get("name") or "",
                "Type":       TYPE_LBL.get(a["asset_type"], a["asset_type"]),
                "ETF-type":   SUB_LBL.get(sub, "—"),
                "BE":         bool(a.get("belgian_registered")),
                "Munt":       cur,
                "Land":       ctry if ctry in clist else "BE",
                "Beurs":      a.get("exchange") or "",
                "ISIN":       a.get("isin") or "",
                "Gevonden ticker": a.get("resolved_symbol") or "",
                "Koersdoel":  round(a["price_target"], 4) if a.get("price_target") is not None else None,
                "Fotomoment": round(a["snapshot_price"], 4) if a.get("snapshot_price") is not None else None,
                "Handmatige koers": round(mp, 4) if mp is not None else None,
                "Enkel handm.": bool(a.get("manual_only")),
                "Mislukt": int(a.get("price_fail_count") or 0),
                "Laatste koers": round(mp, 4) if mp is not None else (round(lp["price"], 4) if lp else None),
            })
        cc = st.column_config
        edited = st.data_editor(
            pd.DataFrame(rows), width="stretch", hide_index=True, key="asset_editor",
            num_rows="fixed",
            column_config={
                "Ticker":     cc.TextColumn(disabled=True,
                                            help="Ticker corrigeren doe je onderaan (verhuist transacties mee)."),
                "Naam":       cc.TextColumn(),
                "Type":       cc.SelectboxColumn(options=list(TYPE_LBL.values())),
                "ETF-type":   cc.SelectboxColumn(options=list(SUB_LBL.values()),
                                                 help="Enkel relevant voor ETF's (bepaalt mee de TOB)."),
                "BE":         cc.CheckboxColumn(help="In België aangeboden/geregistreerd (FSMA)."),
                "Munt":       cc.SelectboxColumn(options=ACUR),
                "Land":       cc.SelectboxColumn(options=clist,
                                                 help="Land van herkomst — bepaalt de buitenlandse bronbelasting."),
                "Beurs":      cc.TextColumn(),
                "ISIN":       cc.TextColumn(help="De ISIN is de bron van waarheid voor koersopzoeking — "
                                                  "uniek per effect, i.t.t. een Yahoo-ticker die door "
                                                  "beurssuffixen ambigu kan zijn. Vul ze in voor de meest "
                                                  "betrouwbare koersen."),
                "Gevonden ticker": cc.TextColumn(disabled=True,
                                                 help="Het Yahoo-symbool dat laatst via de ISIN gevonden werd "
                                                      "(informatief). De ISIN blijft de bron van waarheid; "
                                                      "dit veld is enkel een gemakskolom."),
                "Koersdoel":  cc.NumberColumn(min_value=0.0, format="%.10g",
                                             help="Je koersdoel (native munt) — verschijnt op het dashboard "
                                                  "en bij het AI-advies. Leeg = geen koersdoel op activumniveau "
                                                  "(dan geldt het laatste transactie- of AI-koersdoel)."),
                "Fotomoment": cc.NumberColumn(min_value=0.0, format="%.10g",
                                              help="Slotkoers 31/12/2025 (native). Leeg = geen fotomoment."),
                "Handmatige koers": cc.NumberColumn(min_value=0.0, format="%.10g",
                                              help="Laatste redmiddel: enkel gebruikt als geen enkele onlinebron "
                                                   "(Yahoo, onvista, Börse Frankfurt, Tradegate, Lang & Schwarz) een koers "
                                                   "vindt. Zet de ISIN correct in — dan werken de meeste warrants "
                                                   "automatisch. Leeg = volledig automatisch."),
                "Mislukt": cc.NumberColumn(
                    disabled=True, format="%d",
                    help=f"Aantal mislukte koersophalingen op rij. Vanaf "
                         f"{md.MAX_PRICE_FAILURES} stopt de app met proberen voor dit activum "
                         "(geen nutteloze netwerkcalls en logruis meer). Heractiveer hieronder "
                         "of zet een handmatige koers."),
                "Enkel handm.": cc.CheckboxColumn(
                    help="Sla ALLE onlinebronnen over voor dit effect en gebruik enkel de "
                         "handmatige koers. Aanzetten voor effecten die nergens publiek "
                         "genoteerd zijn: dat scheelt vijf mislukte netwerkcalls en evenveel "
                         "foutregels in de log bij elke koersverversing (om de 5 minuten)."),
                "Laatste koers": cc.NumberColumn(disabled=True, format="%.10g"),
            })
        st.caption("✏️ Bewerk rechtstreeks in de tabel en klik op 'Wijzigingen opslaan'. TOB-tarief, "
                   "buitenlandse bronbelasting en de EUR-fotomomentwaarde volgen automatisch. "
                   "Staat een effect niet op Yahoo (bv. een warrant)? Vul de **ISIN** in — koersen "
                   "worden dan via de ISIN opgehaald (Yahoo, onvista, Euronext, Tradegate, L&S, "
                   "Börse Frankfurt). Vindt geen enkele bron het effect, zet dan een "
                   "**handmatige koers** én vink **Enkel handm.** aan — dat stopt ook de "
                   "foutmeldingen in de log.")

        _open_t, _closed_t = tax_mod.open_position_tickers()
        if _closed_t:
            st.caption(
                f"⏭️ **Geen koersen meer voor {len(_closed_t)} gesloten positie(s):** "
                + ", ".join(asset_label(t, a_names) for t in _closed_t)
                + ".  Dit zijn de activa waarvan de app denkt dat je ze volledig verkocht hebt "
                  "(zelfde FIFO-berekening als het dashboard). Staat hier iets tussen dat je nog "
                  "wél bezit, dan ontbreekt er een transactie — controleer de aankopen/verkopen "
                  "op de 💰 Transacties-pagina.")

        _stuck = [a for a in assets
                  if int(a.get("price_fail_count") or 0) >= md.MAX_PRICE_FAILURES
                  and not a.get("manual_only")]
        if _stuck:
            st.warning(
                f"⏸️ Koersophaling **gestopt** voor {len(_stuck)} activum/activa na "
                f"{md.MAX_PRICE_FAILURES} mislukte pogingen op rij: "
                + ", ".join(asset_label(a["ticker"], a_names) for a in _stuck)
                + ".  Vijf bronnen die tien keer na elkaar niets vinden, wijst op een effect dat "
                  "nergens genoteerd staat — verdere pogingen zijn dan enkel verspilde "
                  "netwerkcalls. Zet een **handmatige koers** (en vink **Enkel handm.** aan), of "
                  "heractiveer hieronder als je denkt dat het een tijdelijke storing was.")
            rc1, rc2 = st.columns([3, 1])
            _rsel = rc1.multiselect("Heractiveren", [a["ticker"] for a in _stuck],
                                    default=[a["ticker"] for a in _stuck],
                                    format_func=lambda t: asset_label(t, a_names),
                                    key="reactivate_sel", label_visibility="collapsed")
            if rc2.button("🔄 Heractiveer", key="reactivate_btn") and _rsel:
                for t in _rsel:
                    db.reset_price_failures(t)
                    md._GIVEN_UP_LOGGED.discard(t)
                clear_cache()
                st.success(f"✅ Koersophaling opnieuw actief voor {len(_rsel)} activum/activa.")
                st.rerun()

        with st.expander("🔬 Bronnen diagnose — waarom vindt de app geen koers?"):
            st.caption("Vraagt élke koersbron apart wat ze van deze ISIN weet en toont het "
                       "antwoord. Zo zie je of een effect ergens gekend is, in plaats van enkel "
                       "'alle bronnen faalden'.")
            _isins = [(a["ticker"], a.get("isin") or "") for a in assets if (a.get("isin") or "")]
            if not _isins:
                st.info("Geen enkel activum heeft een ISIN ingevuld.")
            else:
                _dsel = st.selectbox("Activum", _isins,
                                     format_func=lambda p: f"{asset_label(p[0], a_names)} — {p[1]}",
                                     key="diag_sel")
                if st.button("🔬 Diagnose uitvoeren", key="diag_run"):
                    with st.spinner("Alle koersbronnen bevragen..."):
                        res = md.diagnose_isin(_dsel[1])
                    show_df(pd.DataFrame([{
                        "": "✅" if r["ok"] else "❌",
                        "Bron": r["bron"],
                        "Koers": r["koers"],
                        "Munt": r["munt"] or "",
                        "Antwoord": r["detail"],
                    } for r in res]), width="stretch", hide_index=True, column_config={
                        "Koers": st.column_config.NumberColumn(format="%.10g"),
                    })
                    if not any(r["ok"] for r in res):
                        st.warning(
                            "**Geen enkele bron kent dit effect** — ook Euronext niet, en dat is "
                            "de beurs waar Nederlandse en Belgische gestructureerde producten "
                            "noteren. Dat wijst er sterk op dat dit instrument **niet publiek "
                            "beursgenoteerd** is (bv. een warrant uit een werkgeversplan, die wel "
                            "een ISIN heeft maar niet verhandeld wordt op een beurs). Er is dan "
                            "geen koers om op te halen: vul een **handmatige koers** in en vink "
                            "**Enkel handm.** aan.")

        if st.button("💾 Wijzigingen opslaan", type="primary", key="asset_save_inline"):
            n_upd, problems = 0, []
            try:
                for i, a in enumerate(assets):
                    r = edited.iloc[i]
                    orig = rows[i]
                    if all(_cell_eq(r[k], orig[k]) for k in
                           ("Naam", "Type", "ETF-type", "BE", "Munt", "Land", "Beurs", "ISIN",
                            "Koersdoel", "Fotomoment", "Handmatige koers", "Enkel handm.")):
                        continue
                    atype = TYPE_KEY.get(str(r["Type"]), a["asset_type"])
                    asub  = SUB_KEY.get(str(r["ETF-type"]), a.get("etf_subtype") or "distributing") or "distributing"
                    ncur  = str(r["Munt"]) if r["Munt"] in ACUR else (a.get("currency") or "EUR")
                    ctry  = str(r["Land"]) if r["Land"] in clist else "BE"
                    tgt = r["Koersdoel"]
                    has_tgt = not (tgt is None or pd.isna(tgt) or float(tgt) <= 0)
                    db.update_asset(a["ticker"], name=(str(r["Naam"]).strip() or a["ticker"]),
                                    asset_type=atype, etf_subtype=asub, currency=ncur,
                                    exchange=(str(r["Beurs"]).strip() or ""),
                                    isin=(str(r["ISIN"]).strip() or ""),
                                    belgian_registered=int(bool(r["BE"])), country=ctry,
                                    price_target=(float(tgt) if has_tgt else None),
                                    price_target_currency=(ncur if has_tgt else None),
                                    clear_price_target=(not has_tgt))
                    snap = r["Fotomoment"]
                    if snap is None or pd.isna(snap) or float(snap) <= 0:
                        db.set_asset_snapshot(a["ticker"], None, None)
                    else:
                        _fx, snap_eur = compute_eur(float(snap), ncur, tax_mod.SNAPSHOT_DATE)
                        db.set_asset_snapshot(a["ticker"], float(snap), snap_eur)
                    mpv = r["Handmatige koers"]
                    if mpv is None or pd.isna(mpv) or float(mpv) <= 0:
                        db.set_manual_price(a["ticker"], None, None)
                    else:
                        db.set_manual_price(a["ticker"], float(mpv), ncur)
                    db.set_manual_only(a["ticker"], bool(r["Enkel handm."]))
                    n_upd += 1
            except Exception as exc:
                problems.append(f"Onverwachte fout: {exc}")
            for p in problems:
                st.warning("⚠️ " + p)
            if n_upd:
                clear_cache()
                st.success(f"✅ {n_upd} activum/activa bijgewerkt.")
                st.rerun()
            elif not problems:
                st.info("Geen wijzigingen gevonden.")

        fmc1, fmc2 = st.columns([3, 1])
        fmc1.caption("📸 Fotomoment = slotkoers 31/12/2025 (native munt), gebruikt voor de "
                     "meerwaardebelasting op stukken gekocht vóór 2026. Je kunt de waarde in de "
                     "tabel intypen, of hiernaast automatisch ophalen voor activa zonder waarde.")
        if fmc2.button("📸 Ophalen (ontbrekende)", key="snap_fetch_all", width="stretch"):
            n_ok, n_fail = 0, 0
            with st.spinner("Slotkoersen 31/12/2025 ophalen..."):
                for a in assets:
                    if a.get("snapshot_price") is not None:
                        continue
                    p = md.get_close_on_date(a["ticker"], tax_mod.SNAPSHOT_DATE)
                    if p:
                        _fx, p_eur = compute_eur(p, a["currency"], tax_mod.SNAPSHOT_DATE)
                        db.set_asset_snapshot(a["ticker"], p, p_eur)
                        n_ok += 1
                    else:
                        n_fail += 1
            clear_cache()
            if n_ok:
                st.success(f"✅ {n_ok} fotomoment(en) opgehaald." + (f" {n_fail} niet gevonden." if n_fail else ""))
                st.rerun()
            else:
                st.info("Geen ontbrekende fotomomenten gevonden of geen koersen beschikbaar.")

        # Ticker corrigeren (verhuist transacties, dividenden en koershistoriek mee)
        missing_snap = [a for a in assets if a.get("snapshot_price") is None]
        if missing_snap:
            if st.button(f"📸 Fotomoment ophalen (ontbrekende: {len(missing_snap)})",
                         key="fetch_snaps",
                         help=f"Haalt de slotkoers van {tax_mod.SNAPSHOT_DATE} op voor alle activa "
                              "zonder fotomoment. Handig na het toevoegen van nieuwe activa."):
                got = 0
                for a in missing_snap:
                    px = md.get_close_on_date(a["ticker"], tax_mod.SNAPSHOT_DATE)
                    if px:
                        _fx, px_eur = compute_eur(px, a.get("currency") or "EUR", tax_mod.SNAPSHOT_DATE)
                        db.set_asset_snapshot(a["ticker"], px, px_eur)
                        got += 1
                clear_cache()
                if got:
                    st.success(f"✅ Fotomoment opgehaald voor {got} activum/activa.")
                else:
                    st.warning("Geen koersen gevonden (mogelijk niet op Yahoo genoteerd — vul de "
                               "fotomomentwaarde dan handmatig in de tabel in).")
                st.rerun()

        with st.expander("🔧 Ticker corrigeren"):
            rc1, rc2, rc3 = st.columns([2, 2, 1])
            old_tk = rc1.selectbox("Huidige ticker", [a["ticker"] for a in assets], key="rename_old")
            new_tk = rc2.text_input("Nieuwe ticker", key="rename_new",
                                    placeholder="bv. STMPA → STMPA.PA").strip().upper()
            rc3.write(""); rc3.write("")
            if rc3.button("Hernoem", key="rename_btn", width="stretch"):
                if not new_tk:
                    st.warning("Vul een nieuwe ticker in.")
                elif new_tk == old_tk:
                    st.info("Dezelfde ticker.")
                elif db.rename_ticker(old_tk, new_tk):
                    clear_cache()
                    st.success(f"✅ {old_tk} → {new_tk} (transacties/dividenden/koersen verhuisd). "
                               "Ververs de koersen op de Portefeuille-pagina.")
                    st.rerun()
                else:
                    st.error(f"'{new_tk}' bestaat al — kies een andere ticker.")

        # Verwijderen (meerdere tegelijk, met bevestiging — incl. transacties!)
        st.divider()
        adel_opts = {a["ticker"]: f"{asset_label(a['ticker'], a_names)}" for a in assets}
        multiselect_delete(
            "confirm_del_asset", adel_opts,
            lambda tk: db.delete_asset(tk), noun="activum",
            extra_warning="⚠️ Dit wist óók ALLE transacties, dividenden en splitsingen van de "
                          "geselecteerde activa.")

    if _asec == "🔀 Splitsingen":
        st.subheader("🔀 Aandelensplitsingen")
        st.caption("Registreer een splitsing (bv. NVIDIA 1 → 10) of een omgekeerde splitsing "
                   "(bv. 10 → 1). Transacties van vóór de splitsdatum worden automatisch omgerekend "
                   "(aantal × ratio, prijs ÷ ratio); je kostbasis blijft gelijk. Yahoo-koersen zijn al "
                   "split-gecorrigeerd, zodat je posities en waarde correct blijven.")
        all_assets = db.get_assets()
        if not all_assets:
            st.info("Voeg eerst activa toe.")
        else:
            s_tickers = [a["ticker"] for a in all_assets]
            s_names = {a["ticker"]: (a.get("name") or a["ticker"]) for a in all_assets}
            with st.form("split_form", clear_on_submit=True):
                sc1, sc2, sc3, sc4 = st.columns(4)
                with sc1:
                    s_tk = st.selectbox("Activum", s_tickers,
                                        format_func=lambda t: asset_label(t, s_names))
                with sc2:
                    s_date = st.date_input("Splitsdatum", value=date.today(), min_value=date(2000,1,1), max_value=date.today())
                with sc3:
                    s_from = st.number_input("Van (oude aandelen)", min_value=1, value=1, step=1)
                with sc4:
                    s_to = st.number_input("Naar (nieuwe aandelen)", min_value=1, value=2, step=1)
                ratio = s_to / s_from if s_from else 1
                st.caption(f"Ratio = {s_to}/{s_from} = **{ratio:g}** "
                           f"(1 aandeel wordt {ratio:g} aandelen; prijs gedeeld door {ratio:g})")
                if st.form_submit_button("✅ Splitsing registreren", type="primary"):
                    db.add_split(s_tk, str(s_date), ratio)
                    clear_cache()
                    st.success(f"✅ Splitsing {s_from}→{s_to} voor {s_tk} op {s_date} geregistreerd!")
                    st.rerun()

            splits = db.get_splits()
            if splits:
                st.divider()
                sp_rows = [{
                    "ID":      sp["id"],
                    "Datum":   sp["split_date"][:10],
                    "Activum": f"{sp['ticker']} — {s_names.get(sp['ticker'], sp['ticker'])}",
                    "Ratio":   f"{sp['ratio']:g}",
                } for sp in splits]
                show_df(pd.DataFrame(sp_rows), width="stretch", hide_index=True)
                sp_opts = {sp["id"]: f"#{sp['id']} · {sp['split_date'][:10]} · {sp['ticker']} · ratio {sp['ratio']:g}"
                           for sp in splits}
                multiselect_delete("confirm_del_split", sp_opts,
                                   lambda i: db.delete_split(i), noun="splitsing",
                                   extra_warning="De transacties van vóór de splitsdatum worden weer "
                                                 "zonder deze ratio getoond.")
            else:
                st.info("Nog geen splitsingen geregistreerd.")


# ── PAGINA: Transacties ───────────────────────────────────────────────────────

def page_transactions():
    st.title("➕ Transacties")

    assets = db.get_assets()
    if not assets:
        st.warning("Voeg eerst activa toe via 🏢 Activa.")
        return

    asset_tickers = [a["ticker"] for a in assets]
    assets_map    = {a["ticker"]: a for a in assets}
    names         = {a["ticker"]: (a.get("name") or a["ticker"]) for a in assets}
    fmt           = lambda t: asset_label(t, names)

    _tsec = _section_radio("txn_section",
        ["📝 Nieuwe transactie", "📋 Overzicht", "🏦 Rekeningkosten"])

    CUR = ["EUR", "USD", "GBP", "CHF"]

    if _tsec == "📝 Nieuwe transactie":
        # Bevestiging tonen na een geslaagde toevoeging (na reset/rerun)
        if st.session_state.get("txn_added_msg"):
            st.success(st.session_state.pop("txn_added_msg"))

        # Formulier-brede nonce: bij een geslaagde toevoeging bumpen we deze,
        # waardoor alle velden verse (lege) widgets worden.
        txn_n = st.session_state.get("txn_add_nonce", 0)
        kk = lambda s: f"add_{s}_{txn_n}"

        c1, c2 = st.columns(2)
        with c1:
            ticker   = st.selectbox("Activum *", asset_tickers, key=kk("ticker"),
                                     format_func=fmt)
            txn_date = st.date_input("Datum *", value=date.today(), min_value=date(2000,1,1), max_value=date.today(), key=kk("date"))
            txn_type = st.radio("Type *", ["buy", "sell"],
                                format_func=lambda x: "🟢 Aankoop" if x == "buy" else "🔴 Verkoop",
                                horizontal=True, key=kk("type"))
            account  = st.selectbox("Rekening *", db.get_accounts(), key=kk("acct"),
                                    help="Beheer rekeningen via ⚙️ Instellingen → Rekeningen")
        with c2:
            # Bij een verkoop: toon de beschikbare positie OP de verkoopdatum en bied
            # 'volledige positie verkopen' aan (voorkomt gedoe met fractionele aandelen).
            sell_avail = None
            sell_all = False
            if txn_type == "sell":
                _acct_txns = db.get_transactions(ticker=ticker, account=account)
                _upto = [t for t in _acct_txns if t["date"][:10] <= str(txn_date)]
                _posd, _ = tax_mod.build_fifo_positions(_upto)
                sell_avail = round(_posd.get(ticker, {}).get("total_quantity", 0.0), 6)
                sell_all = st.checkbox(
                    f"🔻 Volledige positie verkopen ({sell_avail:.4f} beschikbaar op {txn_date})",
                    key=kk("sellall"),
                    help="Verkoopt exact je volledige positie op de gekozen datum — handig bij "
                         "fractionele aandelen. Vink uit om zelf een aantal in te geven.")
            if txn_type == "sell" and sell_all:
                quantity = float(sell_avail or 0.0)
                st.number_input("Aantal *", min_value=0.0, value=quantity,
                                format="%.10g", key=kk("qty_locked"), disabled=True)
            else:
                quantity = st.number_input("Aantal *", min_value=0.0, step=0.0001,
                                           format="%.10g", value=None, key=kk("qty"))
            price_unit = st.number_input("Prijs per stuk *", min_value=0.0,
                                         step=0.01, format="%.10g", value=None,
                                         key=kk("price"))
            # Munt volgt automatisch het gekozen activum (per ticker een eigen widget)
            asset_cur = assets_map.get(ticker, {}).get("currency", "EUR")
            cur_opts  = CUR if asset_cur in CUR else CUR + [asset_cur]
            currency  = st.selectbox("Munt", cur_opts, index=cur_opts.index(asset_cur),
                                     key=f"add_cur_{ticker}_{txn_n}")

        total_amount = (quantity or 0) * (price_unit or 0)

        # Koersdoel + AI-bepaling (aparte staging-variabele, wisselende key).
        st.session_state.setdefault("pt_staged", 0.0)
        st.session_state.setdefault("pt_nonce", 0)
        ptn = st.session_state["pt_nonce"]
        pc1, pc2 = st.columns([2, 1])
        with pc1:
            price_target = st.number_input("Koersdoel (optioneel, native munt)",
                                           min_value=0.0, step=0.01, format="%.10g",
                                           value=float(st.session_state["pt_staged"]),
                                           key=f"pt_input_{ptn}")
        with pc2:
            st.write("")
            st.write("")
            if st.button("🤖 Bepaal via AI", key="ai_pt"):
                if not db.get_setting("openai_api_key", ""):
                    st.warning("Geen OpenAI-sleutel — stel die in via ⚙️ Instellingen.")
                else:
                    with st.spinner("AI bepaalt koersdoel..."):
                        res = ai_advisor.suggest_price_target(ticker, account)
                    if res.get("error"):
                        st.error(res["error"])
                    else:
                        st.session_state["pt_staged"] = float(res["price_target"])
                        st.session_state["pt_nonce"]  = ptn + 1
                        st.session_state["pt_info"] = (
                            f"🎯 AI-koersdoel {res['price_target']:.2f} {res['currency']} "
                            f"(model {res.get('model','?')}). {res.get('rationale','')} {res.get('scenario','')}")
                        st.rerun()
        if st.session_state.get("pt_info"):
            st.caption(st.session_state["pt_info"])

        # Kosten (in munt naar keuze, los van TOB)
        ck1, ck2 = st.columns([2, 1])
        with ck1:
            costs = st.number_input("Transactiekosten (optioneel)", min_value=0.0,
                                    step=0.01, format="%.10g", value=None,
                                    key=kk("costs"),
                                    help="Broker-/beurskosten — apart gehouden, niet in de meerwaardeberekening.")
        with ck2:
            costs_currency = st.selectbox("Kostenmunt", cur_opts,
                                          index=cur_opts.index("EUR") if "EUR" in cur_opts else 0,
                                          key=kk("costs_cur"))
        costs = costs or 0.0

        # Performance shares (vesting): gekregen i.p.v. gekocht. Kostbasis = waarde bij
        # toekenning (waarop je al personenbelasting betaalde); geen TOB, geen cash.
        is_perf = False
        income_tax_eur = 0.0
        if txn_type == "buy":
            is_perf = st.checkbox(
                "🎁 Toegekend als loon of gratis gekregen (warrants, RSU, gratis/bonus aandelen)", key=kk("perf"),
                help="Effecten die je kreeg i.p.v. kocht (warrants, performance shares/RSU, gratis of "
                     "bonusaandelen uit een werknemersplan). Voer het aantal en de waarde per stuk op de "
                     "toekenningsdatum in — die basiswaarde wordt je kostbasis voor de meerwaarde. Geen "
                     "TOB, geen cash. Voor een écht gratis aandeel zonder belasting: vink hieronder "
                     "'Écht gratis' aan; de waarde per stuk mag dan 0 zijn.")
            if is_perf:
                _, _vest_eur = compute_eur(total_amount, currency, txn_date)
                tax_free = st.checkbox(
                    "🆓 Écht gratis aandeel — geen personenbelasting", key=kk("perf_free"),
                    help="Vink aan voor gratis/bonusaandelen waarop je géén personenbelasting betaalt. "
                         "De prijs/waarde per stuk mag dan 0 zijn en er wordt geen personenbelasting "
                         "bijgehouden. De kostbasis voor een latere meerwaarde is gelijk aan de opgegeven "
                         "waarde (€0 bij een volledig gratis aandeel).")
                if tax_free:
                    income_tax_eur = 0.0
                    st.caption(f"📌 Gratis aandeel — kostbasis ≈ **€{_vest_eur:,.2f}**, "
                               "**geen personenbelasting**, geen TOB, geen cash-uitgave.")
                else:
                    pb_pct = st.number_input(
                        "Personenbelasting bij toekenning (%)", min_value=0.0, max_value=100.0,
                        value=53.5, step=0.5, key=kk("perf_pct"),
                        help="Marginaal tarief waartegen de toekenning als beroepsinkomen belast werd "
                             "(vaak ± 53,5%). Dit bedrag wordt apart bijgehouden als personenbelasting.")
                    income_tax_eur = round(_vest_eur * pb_pct / 100, 2)
                    if st.checkbox("Bedrag personenbelasting manueel ingeven", key=kk("perf_man")):
                        income_tax_eur = st.number_input(
                            "Personenbelasting (€)", min_value=0.0, value=income_tax_eur,
                            step=0.01, format="%.10g", key=kk("perf_taxval"))
                    st.caption(f"📌 Kostbasis ≈ **€{_vest_eur:,.2f}** | personenbelasting "
                               f"**€{income_tax_eur:,.2f}** (apart bijgehouden, toggle op dashboard). "
                               "Geen TOB, geen cash-uitgave.")

        asset_info = assets_map.get(ticker, {})

        # ── Wisselkoers ──────────────────────────────────────────────────────
        # De TOB is een Belgische heffing op de EUR-tegenwaarde, dus de koers bepaalt
        # rechtstreeks hoeveel TOB je betaalt. Brokers hanteren vaak hun EIGEN koers
        # (soms met een auto-FX-marge erin verwerkt); die hoort bij de transactie.
        fx_manual = 0
        fx_override = None
        if currency != "EUR":
            _mkt_fx, _fx_src = fx_lookup(currency, txn_date)
            if _fx_src == "historisch":
                st.caption(f"💱 Marktkoers op {txn_date}: **1 {currency} = "
                           f"{_mkt_fx:.6g} EUR**")
            elif _fx_src == "actueel":
                st.warning(f"💱 De historische koers voor {txn_date} is niet beschikbaar; "
                           f"de app gebruikt de **actuele** koers (1 {currency} = "
                           f"{_mkt_fx:.6g} EUR) als benadering. Geef hieronder liever de koers "
                           "van je broker in — dat is toch de koers die je écht betaald hebt.")
            else:
                st.error(f"💱 Geen enkele wisselkoers gevonden voor {currency}. Geef hieronder "
                         "je eigen koers in, anders kunnen de EUR-tegenwaarde en de TOB niet "
                         "correct berekend worden.")

            fx_manual = int(st.checkbox(
                "💱 Eigen wisselkoers gebruiken (koers van je broker)",
                value=(_mkt_fx is None), key=kk("fx_man"),
                help="Brokers rekenen vaak met hun eigen wisselkoers. Vul die hier in, dan "
                     "blijft ze voorgoed aan deze transactie hangen en wordt ze nooit "
                     "overschreven door een herberekening met de marktkoers."))
            if fx_manual:
                fxc1, fxc2 = st.columns([1, 2])
                with fxc1:
                    fx_override = st.number_input(
                        f"1 {currency} = ? EUR", min_value=0.0, format="%.10g",
                        value=float(_mkt_fx) if _mkt_fx else 0.0,
                        step=0.0001, key=kk("fx_val"))
                with fxc2:
                    if _mkt_fx and fx_override:
                        _spread = (fx_override - _mkt_fx) / _mkt_fx * 100
                        st.caption(f"Afwijking t.o.v. de marktkoers: **{pct(_spread)}**"
                                   + ("  (jouw koers is ongunstiger — typisch een auto-FX-marge)"
                                      if _spread < 0 else ""))
                st.warning(
                    "⚠️ **Tel de auto-FX-kosten niet dubbel.** Zit de wisselkostenmarge van je "
                    "broker al **verwerkt in deze koers** (auto-FX), voeg ze dan **niet** ook "
                    "nog eens toe bij *Transactiekosten* hierboven — anders trek je ze twee keer "
                    "af van je rendement. Rekent je broker de wisselkost als een **aparte lijn** "
                    "aan (en gebruikt hij de zuivere marktkoers), zet ze dan wél bij de kosten "
                    "en gebruik hier de marktkoers.")
                fx_override = fx_override or None

        _fx_prev, _eur_prev = compute_eur(total_amount, currency, txn_date, fx_override)
        if _fx_prev is None:
            st.error("Zonder wisselkoers kan deze transactie niet correct opgeslagen worden. "
                     "Vink 'Eigen wisselkoers gebruiken' aan en vul de koers in.")
            _fx_prev, _eur_prev = 0.0, 0.0
        if is_perf:
            tob_amount = 0.0
            st.info(f"**Waarde bij toekenning:** {currency} {num(total_amount, 2)}"
                    f"{'' if currency == 'EUR' else f' ≈ €{_eur_prev:,.2f}'} | **TOB:** €0,00 (toekenning)")
        else:
            tob_amount = tax_mod.calculate_tob(asset_info.get("asset_type", "stock"),
                                               asset_info.get("etf_subtype", "distributing"),
                                               _eur_prev,
                                               bool(asset_info.get("belgian_registered", 1)),
                                               txn_date=txn_date)
            eur_hint = "" if currency == "EUR" else f" ≈ **€{_eur_prev:,.2f}** (koers {_fx_prev:.4f})"
            st.info(f"**Totaalwaarde:** {currency} {num(total_amount, 2)}{eur_hint} | **TOB:** €{tob_amount:,.2f}")
            if st.checkbox("TOB manueel aanpassen", key=kk("tob_man")):
                tob_amount = st.number_input("TOB (€)", min_value=0.0, value=tob_amount,
                                             step=0.01, format="%.10g", key=kk("tob_val"))
        notes = st.text_area("Notities (optioneel)", height=60, key=kk("notes"))

        if st.button("✅ Transactie toevoegen", type="primary", key=kk("submit")):
            if not quantity or quantity <= 0:
                st.error("Vul een geldig aantal in (groter dan 0).")
            elif not is_perf and (not price_unit or price_unit <= 0):
                st.error("Vul een geldige prijs per stuk in (groter dan 0). "
                         "Een gratis aandeel voer je in met '🎁 Toegekend als loon of gratis gekregen'.")
            else:
                price_unit = price_unit or 0.0
                fx_rate, tot_eur = compute_eur(total_amount, currency, txn_date, fx_override)
                _, costs_eur = compute_eur(costs, costs_currency, txn_date)
                proceed = True
                if fx_rate is None or costs_eur is None:
                    st.error("Geen wisselkoers beschikbaar — vul je eigen koers in "
                             "('Eigen wisselkoers gebruiken'). Zonder koers zouden de "
                             "EUR-tegenwaarde en de TOB fout zijn.")
                    proceed = False
                if txn_type == "sell":
                    acct_txns = db.get_transactions(ticker=ticker, account=account)
                    # Positie beschikbaar OP de verkoopdatum (een verkoop kan niet vóór
                    # de bijhorende aankoop liggen — anders klopt de FIFO/portefeuille niet).
                    upto = [t for t in acct_txns if t["date"][:10] <= str(txn_date)]
                    positions, _ = tax_mod.build_fifo_positions(upto)
                    available = positions.get(ticker, {}).get("total_quantity", 0.0)
                    positions_all, _ = tax_mod.build_fifo_positions(acct_txns)
                    available_all = positions_all.get(ticker, {}).get("total_quantity", 0.0)
                    # Fractionele tolerantie: exact de volledige positie verkopen mag.
                    if quantity - available > 1e-6:
                        if available_all - quantity > -1e-6 and available < available_all - 1e-9:
                            st.error(
                                f"Op {txn_date} had je slechts **{available:.4f}** stuk(s) op '{account}'. "
                                f"Je bezit in totaal wel {available_all:.4f}, maar de verkoopdatum ligt "
                                "wellicht vóór je aankoop. Een verkoop kan niet vóór de aankoop liggen — "
                                "corrigeer de **verkoopdatum**.")
                        else:
                            st.error(f"Onvoldoende positie op '{account}' op {txn_date}. "
                                     f"Beschikbaar: {available:.4f}.")
                        proceed = False
                if proceed:
                    db.add_transaction(ticker, txn_type, str(txn_date), quantity,
                                       price_unit, total_amount, currency, tob_amount,
                                       notes or None, account=account, costs=costs,
                                       costs_currency=costs_currency, fx_rate=fx_rate,
                                       total_amount_eur=tot_eur, costs_eur=costs_eur,
                                       price_target=(price_target or None),
                                       is_performance_share=int(is_perf),
                                       income_tax_eur=income_tax_eur,
                                       fx_manual=fx_manual,
                                       tob_manual=int(bool(st.session_state.get(kk("tob_man")))))
                    clear_cache()
                    # Volledige reset: bump formulier-nonce + koersdoel-staging leeg
                    st.session_state["txn_add_nonce"] = txn_n + 1
                    st.session_state["pt_staged"] = 0.0
                    st.session_state["pt_nonce"] = st.session_state.get("pt_nonce", 0) + 1
                    st.session_state.pop("pt_info", None)
                    st.session_state["txn_added_msg"] = (
                        f"✅ {'Aankoop' if txn_type == 'buy' else 'Verkoop'} van "
                        f"{quantity:.4f} × {fmt(ticker)} op {account} toegevoegd! Het formulier is leeggemaakt.")
                    st.rerun()

    if _tsec == "📋 Overzicht":
        st.session_state.pop("edit_txn", None)  # inline bewerken vervangt het oude formulier


        c1, c2, c3, c4 = st.columns(4)
        _o_asset = ["Alle"] + asset_tickers
        _o_year  = ["Alle"] + [str(y) for y in range(datetime.now().year, 2019, -1)]
        _o_acct  = ["Alle"] + db.get_accounts()
        with c1:
            f_asset = sticky_select("Activum", _o_asset, "txn_f_asset", "Alle",
                                    format_func=lambda t: "Alle" if t == "Alle" else fmt(t))
        with c2:
            f_type = sticky_select("Type", ["Alle", "Aankoop", "Verkoop"], "txn_f_type", "Alle")
        with c3:
            f_year = sticky_select("Jaar", _o_year, "txn_f_year", "Alle")
        with c4:
            f_acct = sticky_select("Rekening", _o_acct, "txn_f_acct", "Alle")

        txns = db.get_transactions(
            ticker=(f_asset if f_asset != "Alle" else None),
            year=int(f_year) if f_year != "Alle" else None,
            txn_type=("buy" if f_type == "Aankoop" else "sell" if f_type == "Verkoop" else None),
            account=(f_acct if f_acct != "Alle" else None),
            adjusted=False,
        )
        if not txns:
            st.info("Geen transacties gevonden.")
            return

        total_tob   = sum(t["tob_tax"] or 0 for t in txns)
        total_costs = sum(t.get("costs_eur") or 0 for t in txns)
        st.caption(f"{len(txns)} transactie(s) | Totale TOB: {eur(total_tob)} | Kosten: {eur(total_costs)}")

        ordered = list(reversed(txns))
        ainfo = {a["ticker"]: a for a in db.get_assets()}
        accounts = db.get_accounts()
        TYPE_LBL = {"buy": "🟢 Aankoop", "sell": "🔴 Verkoop"}
        TYPE_KEY = {v: k for k, v in TYPE_LBL.items()}
        TCUR = ["EUR", "USD", "GBP", "CHF"]
        rows = []
        for t in ordered:
            cur = t["currency"] if t["currency"] in TCUR else "EUR"
            rows.append({
                "ID":       t["id"],
                "Datum":    t["date"][:10],
                "Type":     TYPE_LBL.get(t["transaction_type"], t["transaction_type"]),
                "Activum":  asset_label(t["ticker"], names),
                "Aantal":   round(t["quantity"], 4),
                "Prijs":    round(t["price_per_unit"], 4),
                "Munt":     cur,
                "Rekening": t.get("account") or db.DEFAULT_ACCOUNT,
                "Kosten €": round(t.get("costs_eur") or 0, 2),
                "Koersdoel": t.get("price_target"),
                "Perf?":    bool(t.get("is_performance_share")),
                "Personenbel. €": round(t.get("income_tax_eur") or 0, 2),
                "FX-koers": round(float(t.get("fx_rate") or 1.0), 6),
                "FX eigen": bool(t.get("fx_manual")),
                "€ Totaal": round(t.get("total_amount_eur") or t["total_amount"], 2),
                "TOB €":    round(t.get("tob_tax") or 0, 2),
                "TOB eigen": bool(t.get("tob_manual")),
                "Notities": t.get("notes") or "",
            })
        cc = st.column_config
        edited = st.data_editor(
            pd.DataFrame(rows), width="stretch", hide_index=True, key="txn_editor",
            num_rows="fixed",
            column_config={
                "ID":        cc.NumberColumn(disabled=True, width="small"),
                "Datum":     cc.TextColumn(help="JJJJ-MM-DD"),
                "Type":      cc.SelectboxColumn(options=list(TYPE_LBL.values())),
                "Activum":   cc.TextColumn(disabled=True,
                                           help="Ticker wijzigen doe je via 🏢 Activa (ticker corrigeren)."),
                "Aantal":    cc.NumberColumn(min_value=0.0, format="%.10g"),
                "Prijs":     cc.NumberColumn(min_value=0.0, format="%.10g"),
                "Munt":      cc.SelectboxColumn(options=TCUR),
                "Rekening":  cc.SelectboxColumn(options=accounts),
                "Kosten €":  cc.NumberColumn(min_value=0.0, format="%.10g"),
                "Koersdoel": cc.NumberColumn(min_value=0.0, format="%.10g"),
                "Perf?":     cc.CheckboxColumn(help="Performance shares (toekenning): geen TOB."),
                "Personenbel. €": cc.NumberColumn(min_value=0.0, format="%.10g",
                                                  help="Personenbelasting bij toekenning (enkel bij Perf?)."),
                "€ Totaal":  cc.NumberColumn(disabled=True, format="%.10g"),
                "FX-koers":  cc.NumberColumn(
                    format="%.10g",
                    help="1 eenheid van de munt in EUR. Vink 'FX eigen' aan om je EIGEN koers "
                         "(die van je broker) te bewaren; ze wordt dan nooit overschreven door "
                         "een herberekening met de marktkoers."),
                "FX eigen":  cc.CheckboxColumn(
                    help="Aan = de koers hiernaast is JOUW koers en blijft voorgoed bij deze "
                         "transactie. Let op: zit de auto-FX-marge van je broker al in die koers "
                         "verwerkt, tel ze dan niet nóg eens bij 'Kosten €'."),
                "TOB €":     cc.NumberColumn(
                    format="%.10g",
                    help="Beurstaks in EUR. Pas je hem aan, dan wordt 'TOB eigen' automatisch "
                         "aangevinkt en laat de herberekening deze lijn met rust."),
                "TOB eigen": cc.CheckboxColumn(
                    help="Aan = handmatig ingestelde TOB; wordt niet herberekend."),
                "Notities":  cc.TextColumn(),
            })
        st.caption("✏️ Bewerk rechtstreeks in de tabel (datum, type, aantal, prijs, munt, rekening, "
                   "kosten, koersdoel, performance shares, notities) en klik op 'Wijzigingen opslaan'. "
                   "Totaal, EUR-tegenwaarde en TOB worden bij het opslaan herberekend.")

        if st.button("💾 Wijzigingen opslaan", type="primary", key="txn_save_inline"):
            n_upd, problems = 0, []
            try:
                for i, t in enumerate(ordered):
                    r = edited.iloc[i]
                    orig = rows[i]
                    if all(_cell_eq(r[k], orig[k]) for k in
                           ("Datum", "Type", "Aantal", "Prijs", "Munt", "Rekening",
                            "Kosten €", "Koersdoel", "Perf?", "Personenbel. €", "Notities",
                            "FX-koers", "FX eigen", "TOB €", "TOB eigen")):
                        continue
                    nd = _date_or_none(str(r["Datum"]))
                    if nd is None:
                        problems.append(f"#{t['id']}: datum '{r['Datum']}' ongeldig (JJJJ-MM-DD).")
                        continue
                    ttype = TYPE_KEY.get(str(r["Type"]), t["transaction_type"])
                    try:
                        qty = float(r["Aantal"]); price = float(r["Prijs"])
                    except (TypeError, ValueError):
                        problems.append(f"#{t['id']}: aantal/prijs ongeldig."); continue
                    if qty <= 0 or price < 0:
                        problems.append(f"#{t['id']}: aantal moet > 0 en prijs ≥ 0 zijn."); continue
                    ncur = str(r["Munt"]) if r["Munt"] in TCUR else (t.get("currency") or "EUR")
                    total = qty * price

                    # ── Wisselkoers ──────────────────────────────────────────
                    # Zelf ingevulde koers (of 'FX eigen' aangevinkt) = die van je broker:
                    # die blijft bij de transactie en wordt nooit door de marktkoers vervangen.
                    fx_edited = not _cell_eq(r["FX-koers"], orig["FX-koers"])
                    fx_man = int(bool(r["FX eigen"]) or fx_edited)
                    fx_val = None
                    if fx_man:
                        try:
                            fx_val = float(r["FX-koers"])
                        except (TypeError, ValueError):
                            fx_val = None
                        if not fx_val or fx_val <= 0:
                            problems.append(f"#{t['id']}: 'FX eigen' staat aan maar de FX-koers "
                                            "is leeg of 0.")
                            continue
                    fx, tot_eur = compute_eur(total, ncur, nd, fx_val)
                    if fx is None:
                        problems.append(f"#{t['id']}: geen wisselkoers voor {ncur} op {nd}. "
                                        "Vink 'FX eigen' aan en vul de koers van je broker in — "
                                        "zonder koers zouden het EUR-bedrag en de TOB fout zijn.")
                        continue

                    perf = bool(r["Perf?"])
                    inctax = 0.0 if not perf else float(r["Personenbel. €"] or 0)
                    info = ainfo.get(t["ticker"], {})

                    # ── TOB ──────────────────────────────────────────────────
                    # Zelf aangepast = handmatig: laten staan. Anders herberekenen op de
                    # EUR-tegenwaarde (nooit op het bedrag in vreemde munt).
                    tob_edited = not _cell_eq(r["TOB €"], orig["TOB €"])
                    tob_man = int(bool(r["TOB eigen"]) or tob_edited)
                    if perf:
                        tob, tob_man = 0.0, 0
                    elif tob_man:
                        tob = float(r["TOB €"] or 0)
                    else:
                        tob = tax_mod.calculate_tob(info.get("asset_type", "stock"),
                                                    info.get("etf_subtype", "distributing"), tot_eur,
                                                    bool(info.get("belgian_registered", 1)), txn_date=nd)
                    costs_v = float(r["Kosten €"] or 0)
                    tgt = float(r["Koersdoel"]) if not (r["Koersdoel"] is None or pd.isna(r["Koersdoel"])) else None
                    db.update_transaction(
                        t["id"], transaction_type=ttype, date=str(nd), quantity=qty,
                        price_per_unit=price, total_amount=total, currency=ncur, tob_tax=tob,
                        notes=(str(r["Notities"]) or None) if not pd.isna(r["Notities"]) else None,
                        account=str(r["Rekening"]), costs=costs_v, costs_currency="EUR",
                        fx_rate=fx, total_amount_eur=tot_eur, costs_eur=costs_v,
                        price_target=tgt, is_performance_share=int(perf), income_tax_eur=inctax,
                        fx_manual=fx_man, tob_manual=tob_man)
                    n_upd += 1
            except Exception as exc:
                problems.append(f"Onverwachte fout: {exc}")
            for p in problems:
                st.warning("⚠️ " + p)
            if n_upd:
                clear_cache()
                st.success(f"✅ {n_upd} transactie(s) bijgewerkt.")
                st.rerun()
            elif not problems:
                st.info("Geen wijzigingen gevonden.")

        # ── TOB en EUR-tegenwaarde herberekenen ──────────────────────────────
        st.divider()
        with st.expander("🔄 TOB en EUR-tegenwaarde controleren/herberekenen"):
            st.caption(
                "De TOB is een Belgische heffing op de **EUR-tegenwaarde**. In oudere versies kon "
                "de wisselkoers stilzwijgend op 1,0 blijven staan wanneer de historische koers "
                "niet opgehaald raakte — dan werd het tarief (bv. 0,35%) op het bedrag in **vreemde "
                "munt** toegepast, en was de TOB fout. Deze controle herberekent de EUR-tegenwaarde "
                "met de juiste koers en de TOB daarop. Lijnen met een **eigen wisselkoers** of een "
                "**handmatige TOB** blijven ongemoeid.")
            rt_changes, rt_suspect = _recompute_tob_preview(txns, ainfo)
            if not rt_changes:
                st.success("✅ Alle transacties in deze selectie kloppen — niets te herberekenen.")
            else:
                _dtob = sum(c["nieuw_tob"] - c["oud_tob"] for c in rt_changes)
                st.warning(
                    f"**{len(rt_changes)} transactie(s)** zouden wijzigen"
                    + (f", waarvan **{rt_suspect}** met een TOB die duidelijk op de vréémde munt "
                       "berekend lijkt" if rt_suspect else "")
                    + f". Verschil in totale TOB: **{eur(_dtob)}**.")
                show_df(pd.DataFrame([{
                    "": "🚩" if c["verdacht"] else "",
                    "ID": c["id"], "Datum": c["datum"],
                    "Activum": asset_label(c["ticker"], names),
                    "Munt": c["munt"],
                    "Koers nu": c["oud_fx"], "Koers wordt": c["nieuw_fx"],
                    "€ nu": c["oud_eur"], "€ wordt": c["nieuw_eur"],
                    "TOB nu": c["oud_tob"], "TOB wordt": c["nieuw_tob"],
                    "Δ TOB": c["nieuw_tob"] - c["oud_tob"],
                } for c in rt_changes]), width="stretch", hide_index=True, column_config={
                    "ID": st.column_config.NumberColumn(format="%d", width="small"),
                    "Koers nu": st.column_config.NumberColumn(format="%.10g"),
                    "Koers wordt": st.column_config.NumberColumn(format="%.10g"),
                    "€ nu": st.column_config.NumberColumn(format="€ %.10g"),
                    "€ wordt": st.column_config.NumberColumn(format="€ %.10g"),
                    "TOB nu": st.column_config.NumberColumn(format="€ %.10g"),
                    "TOB wordt": st.column_config.NumberColumn(format="€ %.10g"),
                    "Δ TOB": st.column_config.NumberColumn(format="€ %+.10g"),
                })
                st.caption("🚩 = de opgeslagen TOB komt overeen met het tarief toegepast op het "
                           "bedrag in vréémde munt — dat is precies de oude fout.")
                # Nonce in de key: Streamlit verbiedt het overschrijven van een widget-key
                # nadat de widget is aangemaakt (StreamlitAPIException). Door de key te
                # veranderen is het een NIEUWE checkbox, die vanzelf leeg begint — zo
                # blijft het vinkje na een herberekening niet aangevinkt staan.
                _tobn = st.session_state.get("tob_rc_nonce", 0)
                if st.checkbox("Ja, herbereken deze transacties", key=f"tob_rc_confirm_{_tobn}"):
                    if st.button("🔄 Herberekening uitvoeren", type="primary", key="tob_rc_do"):
                        for c in rt_changes:
                            db.update_transaction(c["id"], fx_rate=c["nieuw_fx"],
                                                  total_amount_eur=c["nieuw_eur"],
                                                  tob_tax=c["nieuw_tob"])
                        clear_cache()
                        st.session_state["tob_rc_nonce"] = _tobn + 1   # geen widget-key
                        st.success(f"✅ {len(rt_changes)} transactie(s) herberekend.")
                        st.rerun()

        # Verwijderen (meerdere tegelijk, met bevestiging)
        st.divider()
        tdel_opts = {t["id"]: f"#{t['id']} · {t['date'][:10]} · "
                              f"{'Aankoop' if t['transaction_type']=='buy' else 'Verkoop'} · "
                              f"{asset_label(t['ticker'], names)} · {t['quantity']:g}" for t in ordered}
        multiselect_delete("confirm_del_txn", tdel_opts,
                           lambda i: db.delete_transaction(i), noun="transactie")

    if _tsec == "🏦 Rekeningkosten":
        st.subheader("🏦 Algemene rekeningkosten")
        st.caption("Kosten die niet aan een specifiek aandeel hangen (bv. beheerskosten, bewaarloon). "
                   "Ze drukken het totale rendement van de rekening, maar niet de individuele posities of de meerwaardeberekening.")
        with st.form("acct_cost_form", clear_on_submit=True):
            a1, a2, a3 = st.columns(3)
            with a1:
                ac_acct = st.selectbox("Rekening *", db.get_accounts())
                ac_date = st.date_input("Datum *", value=date.today(), min_value=date(2000,1,1), max_value=date.today())
            with a2:
                ac_amount = st.number_input("Bedrag *", min_value=0.0, step=0.01, format="%.10g")
                ac_cur    = st.selectbox("Munt", CUR)
            with a3:
                ac_desc = st.text_input("Omschrijving", placeholder="bv. jaarlijks bewaarloon")
            if st.form_submit_button("✅ Kost toevoegen", type="primary"):
                if ac_amount <= 0:
                    st.error("Bedrag moet positief zijn.")
                else:
                    fx, amt_eur = compute_eur(ac_amount, ac_cur, ac_date)
                    db.add_account_cost(ac_acct, str(ac_date), ac_amount, ac_cur,
                                        ac_desc or None, fx_rate=fx, amount_eur=amt_eur)
                    clear_cache()
                    st.success("✅ Rekeningkost toegevoegd!")
                    st.rerun()

        costs = db.get_account_costs()
        if costs:
            st.divider()
            st.caption(f"Totaal rekeningkosten: {eur(db.total_account_costs_eur())}")
            acc_all = db.get_accounts()
            crows = [{
                "ID":           c["id"],
                "Datum":        c["date"][:10],
                "Rekening":     c["account"],
                "Omschrijving": c.get("description") or "",
                "Bedrag":       c["amount"],
                "Munt":         c.get("currency") or "EUR",
                "EUR":          round(c.get("amount_eur") or 0.0, 2),
            } for c in costs]
            ccg = st.column_config
            cedited = st.data_editor(
                pd.DataFrame(crows), width="stretch", hide_index=True, key="acct_cost_editor",
                num_rows="fixed",
                column_config={
                    "ID":           ccg.NumberColumn(disabled=True, width="small"),
                    "Datum":        ccg.TextColumn(help="JJJJ-MM-DD"),
                    "Rekening":     ccg.SelectboxColumn(options=acc_all),
                    "Omschrijving": ccg.TextColumn(),
                    "Bedrag":       ccg.NumberColumn(min_value=0.0, format="%.10g"),
                    "Munt":         ccg.SelectboxColumn(options=CUR),
                    "EUR":          ccg.NumberColumn(disabled=True, format="%.10g"),
                })
            st.caption("✏️ Bewerk rechtstreeks in de tabel en klik op 'Wijzigingen opslaan'. "
                       "Het EUR-bedrag wordt bij het opslaan herberekend (historische wisselkoers).")
            if st.button("💾 Wijzigingen opslaan", key="acct_cost_save"):
                n_upd, problems = 0, []
                try:
                    for i, c in enumerate(costs):
                        r = cedited.iloc[i]
                        orig = crows[i]
                        if all(r[k] == orig[k] for k in ("Datum", "Rekening", "Omschrijving", "Bedrag", "Munt")):
                            continue
                        nd = _date_or_none(str(r["Datum"]))
                        amt = None
                        try:
                            amt = float(r["Bedrag"])
                        except (TypeError, ValueError):
                            pass
                        if nd is None:
                            problems.append(f"#{c['id']}: datum '{r['Datum']}' ongeldig (JJJJ-MM-DD).")
                            continue
                        if amt is None or amt < 0:
                            problems.append(f"#{c['id']}: bedrag ongeldig.")
                            continue
                        ncur = str(r["Munt"]) if r["Munt"] in CUR else (c.get("currency") or "EUR")
                        fx, amt_eur = compute_eur(amt, ncur, nd)
                        db.update_account_cost(c["id"], account=str(r["Rekening"]), date=str(nd),
                                               description=(str(r["Omschrijving"]) or None),
                                               amount=amt, currency=ncur,
                                               fx_rate=fx, amount_eur=amt_eur)
                        n_upd += 1
                except Exception as exc:
                    problems.append(f"Onverwachte fout: {exc}")
                for p in problems:
                    st.warning("⚠️ " + p)
                if n_upd:
                    clear_cache()
                    st.success(f"✅ {n_upd} rekeningkost(en) bijgewerkt.")
                    st.rerun()
                elif not problems:
                    st.info("Geen wijzigingen gevonden.")

            # Verwijderen (meerdere tegelijk, met bevestiging)
            st.divider()
            cd_opts = {c["id"]: f"#{c['id']} · {c['date'][:10]} · {c['account']} · "
                                f"{c.get('description') or 'kost'} · {eur(c.get('amount_eur') or 0)}"
                       for c in costs}
            multiselect_delete("confirm_del_acct_cost", cd_opts,
                               lambda i: db.delete_account_cost(i), noun="rekeningkost")


# ── PAGINA: Dividenden ────────────────────────────────────────────────────────

def page_dividends():
    st.title("💰 Dividenden")

    assets = db.get_assets()

    _div_section = st.radio(
        "Weergave", ["📝 Dividend toevoegen", "📋 Overzicht"],
        key="div_section", horizontal=True, label_visibility="collapsed")

    if _div_section == "📝 Dividend toevoegen":
        tickers = [a["ticker"] for a in assets]
        div_names = {a["ticker"]: (a.get("name") or a["ticker"]) for a in assets}
        amap = {a["ticker"]: a for a in assets}
        if not tickers:
            st.warning("Voeg eerst activa toe via 🏢 Activa.")
        else:
            if st.session_state.get("div_added_msg"):
                st.success(st.session_state.pop("div_added_msg"))
            dn = st.session_state.get("div_amt_nonce", 0)
            dk = lambda s: f"div_{s}_{dn}"
            # Stabiele keys (géén nonce): activum/datum/rekening/soort/munt/cash-keuze
            # mogen NIET resetten wanneer 'Vul lege velden in' de bedragvelden ververst
            # — enkel de bedragvelden zelf (A/B/C/D, RV%, eenvoudige bruto/ingehouden)
            # gebruiken de nonce-key, zodat ze via 'pre' opnieuw ingevuld kunnen worden.
            sk = lambda s: f"div_stable_{s}"
            CURS = ["EUR", "USD", "GBP", "CHF"]

            _KIND_LBL = {"dividend": "💰 Dividend", "interest": "🏦 Interest",
                         "securities_lending": "🔁 Securities lending"}
            _kinds = list(_KIND_LBL.keys())
            d_kind = st.radio("Soort inkomst", _kinds, horizontal=True, key=sk("kind"),
                              format_func=lambda k: _KIND_LBL[k],
                              help="Dividend telt mee voor de vrijstelling van €833 p.p.; interest en "
                                   "securities lending niet (die hebben hun eigen fiscale regels).")

            # Interest is meestal cash-rekeninginterest (niet aan één specifiek
            # activum gekoppeld); securities lending is dat niet noodzakelijk
            # (kan een vergoeding voor de hele portefeuille zijn). Dividend blijft
            # altijd aan een activum gekoppeld — dat IS letterlijk waarvoor het
            # uitgekeerd wordt.
            if d_kind != "dividend":
                _no_asset = st.checkbox(
                    "Niet gekoppeld aan een specifiek activum (bv. algemene "
                    "cash-rekeninginterest)", value=True, key=sk("no_asset"),
                    help="Standaard aan voor interest/securities lending, aangezien dit meestal "
                         "een algemene rekeningvergoeding is. Vink uit als dit bedrag wél bij één "
                         "specifiek activum hoort (bv. securities-lendingvergoeding voor een "
                         "uitgeleende positie).")
            else:
                _no_asset = False

            cc1, cc2, cc3 = st.columns(3)
            if _no_asset:
                cc1.text_input("Activum", value="— Algemeen (niet gekoppeld) —", disabled=True,
                               key=sk("tkr_disabled"))
                d_ticker = None
            else:
                d_ticker = cc1.selectbox("Activum *", tickers, key=sk("tkr"),
                                         format_func=lambda t: asset_label(t, div_names))
            d_date    = cc2.date_input("Datum *", value=date.today(), min_value=date(2000,1,1), max_value=date.today(), key=sk("date"))
            d_account = cc3.selectbox("Rekening *", db.get_accounts(), key=sk("acct"),
                                      help="De rekening waarop dit bedrag is uitgekeerd. "
                                           "Hetzelfde bedrag op een andere rekening voer je als een aparte lijn in.")
            asset_cur = amap.get(d_ticker, {}).get("currency", "EUR") if d_ticker else "EUR"
            cur_opts  = CURS if asset_cur in CURS else CURS + [asset_cur]

            mode = st.radio("Invoerwijze", ["Eenvoudig", "Gedetailleerd (bronbelasting + RV)"],
                            horizontal=True, key="div_mode")

            if mode == "Eenvoudig":
                sc1, sc2 = st.columns(2)
                with sc1:
                    gross    = st.number_input("Bruto dividend *", min_value=0.0, step=0.01,
                                               format="%.10g", value=None, key=dk("s_gross"))
                    currency = st.selectbox("Munt", cur_opts, index=cur_opts.index(asset_cur),
                                            key=sk(f"s_cur_{d_ticker}"))
                with sc2:
                    wh_amt = st.number_input("Ingehouden voorheffing (bedrag)", min_value=0.0,
                                             step=0.01, format="%.10g", value=None, key=dk("s_wh"))
                notes = st.text_area("Notities (optioneel)", height=60, key=dk("s_notes"))
                g = gross or 0.0
                w = wh_amt or 0.0
                st.info(f"**Netto:** {currency} {g - w:,.2f}")
                if st.button("✅ Dividend toevoegen", type="primary", key=dk("s_submit")):
                    if not gross or gross <= 0:
                        st.error("Vul een bruto dividend in.")
                    else:
                        fx_rate, gross_eur = compute_eur(g, currency, d_date)
                        _, wh_eur = compute_eur(w, currency, d_date)
                        db.add_dividend(d_ticker, str(d_date), g, w, currency, notes or None,
                                        fx_rate=fx_rate, gross_eur=gross_eur, withholding_eur=wh_eur,
                                        belgian_rv_withheld=1 if w > 0 else 0, account=d_account,
                                        details={"kind": d_kind, "net_eur": gross_eur - wh_eur})
                        clear_cache()
                        st.session_state["div_amt_nonce"] = dn + 1
                        _lbl = d_ticker or "algemeen (niet gekoppeld)"
                        st.session_state["div_added_msg"] = (
                            f"✅ Dividend {currency} {g - w:.2f} netto voor {_lbl} op {d_account} toegevoegd!")
                        st.rerun()

            else:  # Gedetailleerd
                a_country = (amap.get(d_ticker, {}).get("country") or "BE").upper()
                wht_pct_default = tax_mod.get_wht_rates(tax_mod.year_of(str(d_date))).get(a_country, 0.0)
                is_foreign = a_country != "BE"
                cname = tax_mod.COUNTRY_NAMES.get(a_country, a_country)
                st.caption(f"Vul in wat je weet — lege velden worden automatisch berekend en ingevuld. "
                           f"Land van dit activum: **{cname}**"
                           + (f" (bronbelasting {wht_pct_default:g}%)." if is_foreign else " (geen buitenlandse bronbelasting)."))

                # Prefill (gezet door de aanvul-knop) — nonce zorgt voor verse widgets
                pre = st.session_state.pop("div_prefill", {})
                rv_pct = st.number_input(
                    "🇧🇪 Roerende voorheffing (%)", min_value=0.0, max_value=100.0,
                    value=float(pre.get("rv_pct", 30.0)), step=0.5, key=dk("rvpct"),
                    help="Belgische roerende voorheffing op dividenden — standaard 30%. Pas aan bij "
                         "een afwijkend tarief (bv. VVPR-bis 15%). Gebruikt om ④ uit ③ te berekenen "
                         "(of omgekeerd) wanneer een van beide leeg is.")

                # Munt-widgets keyen op het activum: bij een ander activum verschijnen
                # verse muntvelden met de juiste standaardmunt.
                def cur_box_t(col, keyname):
                    return col.selectbox("Munt", cur_opts, index=cur_opts.index(asset_cur),
                                         key=sk(f"{keyname}_{d_ticker}"), label_visibility="collapsed")

                r1a, r1b = st.columns([3, 1])
                A = r1a.number_input("① Bruto dividend (vóór buitenlandse bronbelasting)",
                                     min_value=0.0, step=0.01, format="%.10g",
                                     value=pre.get("A"), key=dk("A"),
                                     help="Het brutobedrag vóór eender welke inhouding. Enkel invullen "
                                          "bij een BUITENLANDS activum (bv. VS, Nederland, Frankrijk); "
                                          "voor Belgische aandelen laat je dit leeg en start je bij ③.")
                A_cur = cur_box_t(r1b, "Acur")
                r2a, r2b = st.columns([3, 1])
                B = r2a.number_input("② Buitenlandse bronbelasting",
                                     min_value=0.0, step=0.01, format="%.10g",
                                     value=pre.get("B"), key=dk("B"),
                                     help="Wordt automatisch berekend uit ① × het heffingstarief van het "
                                          f"land van het activum ({cname}: {wht_pct_default:g}% — zie ⚙️ "
                                          "Instellingen). Klopt het ingehouden bedrag niet (bv. ander "
                                          "verdragstarief), pas het hier aan.")
                B_cur = cur_box_t(r2b, "Bcur")
                r3a, r3b = st.columns([3, 1])
                C = r3a.number_input("③ Bruto na bronbelasting / vóór Belgische RV",
                                     min_value=0.0, step=0.01, format="%.10g",
                                     value=pre.get("C"), key=dk("C"),
                                     help="Het bedrag waarop de Belgische roerende voorheffing wordt "
                                          "berekend. Voor BELGISCHE aandelen is dit het brutodividend: "
                                          "vul het hier in en laat ① en ② leeg.")
                C_cur = cur_box_t(r3b, "Ccur")
                r4a, r4b = st.columns([3, 1])
                D = r4a.number_input("④ Netto dividend (na alle voorheffingen)",
                                     min_value=0.0, step=0.01, format="%.10g",
                                     value=pre.get("D"), key=dk("D"),
                                     help="Wat er uiteindelijk overblijft na ALLE belastingen: eventuele "
                                          "buitenlandse bronbelasting én de Belgische roerende voorheffing. "
                                          "Dit is doorgaans wat je broker daadwerkelijk uitkeert.")
                D_cur = cur_box_t(r4b, "Dcur")
                notes = st.text_area("Notities (optioneel)", height=60, key=dk("d_notes"))

                # Keten aanvullen met de tarieven (land + RV%)
                res = tax_mod.resolve_dividend_chain(
                    A, B, C, D,
                    rv_rate=(rv_pct / 100.0),
                    wht_rate=(wht_pct_default / 100.0) if (is_foreign and d_kind == "dividend") else 0.0)
                rA, rB, rC, rD, rRV = res["a"], res["b"], res["c"], res["d"], res["rv"]
                def _f(v, cur): return "—" if v is None else f"{cur} {v:,.2f}"
                st.markdown(
                    f"**Afgeleide keten:** ① {_f(rA, A_cur)}  →  ② bronbelasting {_f(rB, B_cur)}  →  "
                    f"③ {_f(rC, C_cur)}  →  🇧🇪 RV {_f(rRV, C_cur)}  →  ④ netto {_f(rD, D_cur)}")

                # Omgekeerde controle (④ → ③ → ② → ①) met tolerantie voor afronding
                filled = [v for v in (A, B, C, D) if v is not None]
                if len(filled) >= 2:
                    issues = tax_mod.verify_dividend_chain(rA, rB, rC, rD, tol=0.02)
                    if issues:
                        for i in issues:
                            st.warning("⚠️ Controle (④→③→②→①): " + i)
                    else:
                        st.caption("✅ Omgekeerde controle (④→③→②→①) klopt binnen de afrondingstolerantie (± €0,02).")

                bc1, bc2 = st.columns([1, 2])
                if bc1.button("🪄 Vul lege velden in", key=dk("fill"),
                              help="Zet de automatisch berekende bedragen in de lege invoervelden, "
                                   "zodat je ze kunt nakijken en zo nodig aanpassen vóór het opslaan."):
                    st.session_state["div_prefill"] = {
                        "A": rA, "B": rB, "C": rC, "D": rD, "rv_pct": rv_pct,
                        "cash_basis": st.session_state.get(sk("cashbasis"), "④ Netto"),
                    }
                    st.session_state["div_amt_nonce"] = dn + 1
                    st.rerun()

                cash_choice = bc2.radio(
                    "Cash-boeking op basis van", ["④ Netto", "③ Bruto na bronbelasting", "① Bruto vóór bronbelasting"],
                    horizontal=True, key=sk("cashbasis"),
                    index=["④ Netto", "③ Bruto na bronbelasting", "① Bruto vóór bronbelasting"].index(pre["cash_basis"]) if pre.get("cash_basis") in ("④ Netto", "③ Bruto na bronbelasting", "① Bruto vóór bronbelasting") else 0,
                    help="Welk bedrag als dividend in het cash-grootboek (💶 Cash) geboekt wordt. "
                         "Standaard het netto (④) — wat je broker effectief stort. Kies ③ of ① als je "
                         "broker bruto uitkeert en de belasting later apart afhoudt. Er kan er maar één "
                         "gekozen worden.")

                if st.button("✅ Dividend toevoegen", type="primary", key=dk("d_submit")):
                    # EUR per veld (elk in zijn eigen munt op de dividenddatum)
                    def to_eur(v, cur):
                        if v is None: return None
                        return compute_eur(v, cur, d_date)[1]
                    a_eur = to_eur(rA, A_cur); b_eur = to_eur(rB, B_cur)
                    c_eur = to_eur(rC, C_cur); d_eur = to_eur(rD, D_cur)
                    gross_eur = a_eur if a_eur is not None else (c_eur if c_eur is not None else d_eur)
                    net_eur   = d_eur if d_eur is not None else (c_eur if c_eur is not None else
                                (a_eur - b_eur if (a_eur is not None and b_eur is not None) else None))
                    if gross_eur is None or net_eur is None:
                        st.error("Geef minstens een bruto- én een nettowaarde in (of voldoende velden om ze te berekenen).")
                    else:
                        wh_eur = max(0.0, gross_eur - net_eur)
                        # Cash-boeking op basis van het gekozen veld
                        if cash_choice.startswith("①"):
                            cash_basis, cash_eur_v = "gross_before", (a_eur if a_eur is not None else net_eur)
                        elif cash_choice.startswith("③"):
                            cash_basis, cash_eur_v = "gross_after", (c_eur if c_eur is not None else net_eur)
                        else:
                            cash_basis, cash_eur_v = "net", net_eur
                        # Native rollup (voor weergave/compat): primair veld = ① of ③ of ④
                        prim_v, prim_cur = ((rA, A_cur) if rA is not None else
                                            (rC, C_cur) if rC is not None else (rD, D_cur))
                        fx_prim = compute_eur(prim_v, prim_cur, d_date)[0] or 1.0
                        wh_native = round(wh_eur / fx_prim, 2)
                        details = {
                            "gross_before_wht": rA, "gross_before_wht_cur": A_cur if rA is not None else None,
                            "foreign_wht_amt":  rB, "foreign_wht_cur":      B_cur if rB is not None else None,
                            "gross_after_wht":  rC, "gross_after_wht_cur":  C_cur if rC is not None else None,
                            "belgian_rv_amt":   rRV,
                            "net_received":     rD, "net_received_cur":     D_cur if rD is not None else None,
                            "net_eur":          net_eur,
                            "cash_basis":       cash_basis,
                            "cash_eur":         cash_eur_v,
                            "kind":             d_kind,
                        }
                        db.add_dividend(d_ticker, str(d_date), prim_v, wh_native, prim_cur, notes or None,
                                        fx_rate=fx_prim, gross_eur=gross_eur, withholding_eur=wh_eur,
                                        foreign_wht_withheld=1 if (rB and rB > 0) else 0,
                                        belgian_rv_withheld=1 if (rRV and rRV > 0) else 0,
                                        account=d_account, details=details)
                        clear_cache()
                        st.session_state["div_amt_nonce"] = dn + 1
                        _lbl = d_ticker or "algemeen (niet gekoppeld)"
                        st.session_state["div_added_msg"] = (
                            f"✅ Dividend voor {_lbl} op {d_account} toegevoegd (netto ≈ {eur(net_eur)}; "
                            f"cash-boeking: {cash_choice}).")
                        st.rerun()

    else:  # 📋 Overzicht
        st.session_state.pop("edit_div", None)  # oude bewerkstaat opruimen
        fcol1, fcol2 = st.columns(2)
        f_year = fcol1.selectbox("Jaar:", ["Alle"] + [str(y) for y in range(datetime.now().year, 2019, -1)],
                                 key="div_year")
        f_acct = fcol2.selectbox("Rekening:", ["Alle rekeningen"] + db.get_accounts(), key="div_acct")
        divs = db.get_dividends(
            year=int(f_year) if f_year != "Alle" else None,
            account=(f_acct if f_acct != "Alle rekeningen" else None))

        if not divs:
            st.info("Geen dividenden gevonden.")
            return

        def _geur(d): return d.get("gross_eur") if d.get("gross_eur") is not None else d["gross_amount"]
        def _neur(d):
            if d.get("net_eur") is not None: return d["net_eur"]
            return _geur(d) - (d.get("withholding_eur") if d.get("withholding_eur") is not None else d["withholding_tax"])
        total_gross = sum(_geur(d) for d in divs)
        total_net   = sum(_neur(d) for d in divs)
        total_wh    = total_gross - total_net

        c1, c2, c3 = st.columns(3)
        c1.metric("Bruto (EUR)", eur(total_gross))
        c2.metric("Ingehouden voorheffingen", eur(total_wh))
        c3.metric("Netto ontvangen", eur(total_net))

        # Fiscaal recupereerbaar (833-vrijstelling + FBB) voor de huidige selectie
        _acc = (f_acct if f_acct != "Alle rekeningen" else None)
        _ben = tax_mod.dividend_tax_benefit(int(f_year) if f_year != "Alle" else None, _acc)
        if _ben["total_benefit"] > 0:
            st.success(f"💡 Fiscaal recupereerbaar via de aangifte: **{eur(_ben['total_benefit'])}** "
                       f"(RV-vrijstelling {eur(_ben['total_reclaimable_rv'])}"
                       + (f" + FBB {eur(_ben['total_fbb'])}" if _ben["total_fbb"] else "")
                       + "). Volledige uitwerking op de **🧾 Belgische Belasting**-pagina.")

        # Netto per rekening (EUR) — handig wanneer eenzelfde activum op meerdere rekeningen uitkeert
        if f_acct == "Alle rekeningen":
            per_acct = {}
            for d in divs:
                a = d.get("account") or db.DEFAULT_ACCOUNT
                per_acct[a] = per_acct.get(a, 0.0) + _neur(d)
            if len(per_acct) > 1:
                st.caption("**Netto per rekening:** " +
                           "  ·  ".join(f"{a}: {eur(v)}" for a, v in sorted(per_acct.items())))
        st.divider()

        names_map = asset_name_map()
        a_by_tk   = {a["ticker"]: a for a in db.get_assets()}
        CASH_LBL  = {"net": "④ Netto", "gross_after": "③ Bruto na", "gross_before": "① Bruto vóór"}
        CASH_KEY  = {v: k for k, v in CASH_LBL.items()}
        KIND_LBL  = {"dividend": "Dividend", "interest": "Interest", "securities_lending": "Securities lending"}
        KIND_KEY  = {v: k for k, v in KIND_LBL.items()}
        accounts_all = db.get_accounts()
        rows = []
        for d in divs:
            rows.append({
                "ID":       d["id"],
                "Datum":    d["date"][:10],
                "Activum":  asset_label(d["ticker"], names_map),
                "Soort":    KIND_LBL.get(d.get("kind") or "dividend", "Dividend"),
                "Rekening": d.get("account") or db.DEFAULT_ACCOUNT,
                "① Bruto":  d.get("gross_before_wht"),
                "② Bronbel.": d.get("foreign_wht_amt"),
                "③ Na bronbel.": d.get("gross_after_wht"),
                "🇧🇪 RV":   d.get("belgian_rv_amt"),
                "④ Netto":  d.get("net_received") if d.get("net_received") is not None
                            else round(d["gross_amount"] - d["withholding_tax"], 2),
                "Munt":     d.get("net_received_cur") or d.get("gross_before_wht_cur") or d["currency"],
                "Cash":     CASH_LBL.get(d.get("cash_basis") or "net", "④ Netto"),
                "Netto €":  round(_neur(d), 2),
                "🔒 Handmatig": bool(d.get("manual_override")),
                "Notities": d.get("notes") or "",
            })
        cc = st.column_config
        CUR_OPTS = ["EUR", "USD", "GBP", "CHF"]
        edited = st.data_editor(
            pd.DataFrame(rows), width="stretch", hide_index=True, key="div_editor",
            num_rows="fixed",
            column_config={
                "ID":            cc.NumberColumn(disabled=True, format="%d", width="small",
                                                 help="Uniek dividend-ID — handig om een lijn te selecteren voor verwijdering."),
                "Datum":         cc.TextColumn(help="JJJJ-MM-DD"),
                "Activum":       cc.TextColumn(disabled=True),
                "Soort":         cc.SelectboxColumn(options=list(KIND_LBL.values()),
                                                    help="Dividend telt mee voor de 833-vrijstelling; "
                                                         "interest en securities lending niet."),
                "Rekening":      cc.SelectboxColumn(options=accounts_all),
                "① Bruto":       cc.NumberColumn(min_value=0.0, format="%.10g",
                                                 help="Bruto vóór buitenlandse bronbelasting (enkel buitenlandse aandelen)."),
                "② Bronbel.":    cc.NumberColumn(min_value=0.0, format="%.10g",
                                                 help="Laat leeg om automatisch te berekenen uit het land."),
                "③ Na bronbel.": cc.NumberColumn(min_value=0.0, format="%.10g",
                                                 help="Grondslag Belgische RV. Voor Belgische aandelen begin je hier."),
                "🇧🇪 RV":        cc.NumberColumn(disabled=True, format="%.10g",
                                                 help="Belgische roerende voorheffing (berekend)."),
                "④ Netto":       cc.NumberColumn(min_value=0.0, format="%.10g",
                                                 help="Laat leeg om automatisch te berekenen (③ × (1 − RV%))."),
                "Munt":          cc.SelectboxColumn(options=CUR_OPTS),
                "Cash":          cc.SelectboxColumn(options=list(CASH_LBL.values()),
                                                    help="Welk veld naar het cash-grootboek gaat."),
                "Netto €":       cc.NumberColumn(disabled=True, format="%.10g"),
                "🔒 Handmatig":  cc.CheckboxColumn(
                    help="Deze lijn is door jou handmatig gecorrigeerd. De knop 'keten "
                         "herberekenen' laat ze dan met rust. Wordt automatisch aangevinkt zodra "
                         "je een bedrag (①-④) aanpast; vink af om de lijn weer automatisch te "
                         "laten herberekenen."),
                "Notities":      cc.TextColumn(),
            })
        st.caption("✏️ Bewerk rechtstreeks in de tabel. Laat ② en ④ leeg om ze automatisch te laten "
                   "berekenen (bronbelasting uit het land van het activum, RV uit de instellingen). "
                   "De keten, RV, EUR-bedragen en cash-boeking worden bij het opslaan herberekend en gecontroleerd.")

        _rvrate = float(db.get_setting("withholding_tax_rate", "0.30"))
        if st.button("💾 Wijzigingen opslaan", type="primary", key="div_save_inline"):
            n_upd, problems = 0, []
            try:
                for i, d in enumerate(divs):
                    r = edited.iloc[i]
                    orig = rows[i]
                    if all(r[k] == orig[k] or (pd.isna(r[k]) and orig[k] is None)
                           for k in ("Datum", "Soort", "Rekening", "① Bruto", "② Bronbel.", "③ Na bronbel.",
                                     "④ Netto", "Munt", "Cash", "Notities", "🔒 Handmatig")):
                        continue
                    nd = _date_or_none(str(r["Datum"]))
                    if nd is None:
                        problems.append(f"#{d['id']}: datum '{r['Datum']}' ongeldig (JJJJ-MM-DD).")
                        continue
                    def _num(v):
                        try:
                            return None if v is None or pd.isna(v) else float(v)
                        except (TypeError, ValueError):
                            return None
                    nA, nB = _num(r["① Bruto"]), _num(r["② Bronbel."])
                    nC, nD = _num(r["③ Na bronbel."]), _num(r["④ Netto"])
                    ncur   = str(r["Munt"]) if r["Munt"] in CUR_OPTS else (d.get("currency") or "EUR")
                    kind   = KIND_KEY.get(str(r["Soort"]), "dividend")
                    # Tarieven toepassen: bronbelasting uit het land, RV uit de instellingen
                    ctry = (a_by_tk.get(d["ticker"], {}).get("country") or "BE").upper()
                    _wht = (tax_mod.get_wht_rate(ctry, tax_mod.year_of(d["date"]))
                            if (kind == "dividend" and ctry != "BE") else 0.0)
                    res = tax_mod.resolve_dividend_chain(nA, nB, nC, nD, rv_rate=_rvrate, wht_rate=_wht)
                    rA, rB, rC, rD, rRV = res["a"], res["b"], res["c"], res["d"], res["rv"]
                    def _te(v):
                        return None if v is None else compute_eur(v, ncur, nd)[1]
                    a_eur, c_eur, d_eur = _te(rA), _te(rC), _te(rD)
                    gross_eur = a_eur if a_eur is not None else (c_eur if c_eur is not None else d_eur)
                    net_eur   = d_eur if d_eur is not None else c_eur
                    if gross_eur is None or net_eur is None:
                        problems.append(f"#{d['id']}: minstens een bruto- en nettowaarde nodig.")
                        continue
                    issues = tax_mod.verify_dividend_chain(rA, rB, rC, rD, tol=0.02)
                    if issues:
                        problems.append(f"#{d['id']}: " + "; ".join(issues) + " — niet opgeslagen.")
                        continue
                    cbk = CASH_KEY.get(str(r["Cash"]), "net")
                    cash_eur_v = {"gross_before": a_eur, "gross_after": c_eur, "net": net_eur}.get(cbk)
                    if cash_eur_v is None:
                        cash_eur_v = net_eur
                    wh_eur = max(0.0, gross_eur - net_eur)
                    prim_v = rA if rA is not None else (rC if rC is not None else rD)
                    fx_prim = compute_eur(prim_v, ncur, nd)[0] or 1.0
                    db.update_dividend(
                        d["id"], date=str(nd), account=str(r["Rekening"]),
                        notes=(str(r["Notities"]) or None) if not pd.isna(r["Notities"]) else None,
                        currency=ncur, gross_amount=prim_v,
                        withholding_tax=round(wh_eur / fx_prim, 2), fx_rate=fx_prim,
                        gross_eur=gross_eur, withholding_eur=wh_eur, net_eur=net_eur,
                        foreign_wht_withheld=1 if (rB and rB > 0) else 0,
                        belgian_rv_withheld=1 if (rRV and rRV > 0) else 0,
                        gross_before_wht=rA, gross_before_wht_cur=ncur if rA is not None else None,
                        foreign_wht_amt=rB, foreign_wht_cur=ncur if rB is not None else None,
                        gross_after_wht=rC, gross_after_wht_cur=ncur if rC is not None else None,
                        belgian_rv_amt=rRV, net_received=rD,
                        net_received_cur=ncur if rD is not None else None,
                        cash_basis=cbk, cash_eur=cash_eur_v, kind=kind,
                        # Bedragen zelf aangepast? Dan is dit een HANDMATIGE CORRECTIE en
                        # laat de knop 'keten herberekenen' deze lijn voortaan met rust.
                        # (Enkel de datum/rekening/notities wijzigen telt niet als correctie.)
                        manual_override=1 if any(
                            not _cell_eq(r[k], orig[k])
                            for k in ("① Bruto", "② Bronbel.", "③ Na bronbel.", "④ Netto")
                        ) else (1 if bool(r["🔒 Handmatig"]) else 0))
                    n_upd += 1
            except Exception as exc:
                problems.append(f"Onverwachte fout: {exc}")
            for p in problems:
                st.warning("⚠️ " + p)
            if n_upd:
                clear_cache()
                st.success(f"✅ {n_upd} lijn(en) bijgewerkt.")
                st.rerun()
            elif not problems:
                st.info("Geen wijzigingen gevonden.")

        # ── Keten herberekenen: eerst tonen wát er zou wijzigen, dan pas uitvoeren ──
        st.divider()
        st.markdown("#### 🔄 Keten herberekenen")
        st.caption("Herbouwt de keten vanaf ① bruto met de bronbelasting van het **land** van het "
                   "activum **en van het jaar van het dividend**, plus de RV uit de instellingen "
                   "(inclusief EUR-bedragen en cash-boeking). Lijnen die al kloppen blijven "
                   "ongemoeid. **Handmatig gecorrigeerde lijnen (🔒) worden standaard niet "
                   "aangeraakt** — je ziet hieronder eerst wat er precies zou wijzigen.")

        _n_manual = sum(1 for d in divs
                        if d.get("manual_override") and (d.get("kind") or "dividend") == "dividend")
        RC_SAFE = "🔒 Handmatig gecorrigeerde lijnen overslaan (aanbevolen)"
        RC_ALL  = "⚠️ Ook handmatig gecorrigeerde lijnen overschrijven"
        rc_scope = st.radio("Bereik", [RC_SAFE, RC_ALL], key="div_rc_scope",
                            index=0, label_visibility="collapsed",
                            help="Bij 'overschrijven' worden ook je eigen correcties vervangen door "
                                 "de theoretisch berekende waarden. Dat kan zinvol zijn na een "
                                 "tariefcorrectie, maar je verliest dan de handmatige waarden.")
        _incl = rc_scope == RC_ALL
        if _n_manual:
            st.caption(f"🔒 **{_n_manual}** lijn(en) staan als handmatig gecorrigeerd gemarkeerd."
                       + ("  Die worden nu **wél** overschreven." if _incl
                          else "  Die blijven ongemoeid."))

        _preview = _recompute_dividend_chain(divs, _rvrate, include_manual=_incl, dry_run=True)
        if not _preview:
            st.success("✅ Alle lijnen kloppen al met de tarieven — er valt niets te herberekenen.")
        else:
            _dnet = sum((c["nieuw_netto_eur"] or 0) - (c["oud_netto_eur"] or 0) for c in _preview)
            _nman = sum(1 for c in _preview if c["handmatig"])
            st.warning(f"**{len(_preview)} lijn(en)** zouden wijzigen"
                       + (f", waarvan **{_nman} handmatig gecorrigeerd**" if _nman else "")
                       + f". Impact op het totale netto: **{eur(_dnet)}**.")
            show_df(pd.DataFrame([{
                "": "🔒" if c["handmatig"] else "",
                "ID":        c["id"],
                "Datum":     c["datum"],
                "Activum":   asset_label(c["ticker"], names_map),
                "Land/jaar": f"{c['land']} {c['jaar']} ({c['wht_pct']:g}%)",
                "② Bronbel. nu":  c["oud_wht"],
                "② wordt":        c["nieuw_wht"],
                "④ Netto nu":     c["oud_netto"],
                "④ wordt":        c["nieuw_netto"],
                "Δ netto €":      (c["nieuw_netto_eur"] or 0) - (c["oud_netto_eur"] or 0),
            } for c in _preview]), width="stretch", hide_index=True, column_config={
                "ID":            st.column_config.NumberColumn(format="%d", width="small"),
                "② Bronbel. nu": st.column_config.NumberColumn(format="%.10g"),
                "② wordt":       st.column_config.NumberColumn(format="%.10g"),
                "④ Netto nu":    st.column_config.NumberColumn(format="%.10g"),
                "④ wordt":       st.column_config.NumberColumn(format="%.10g"),
                "Δ netto €":     st.column_config.NumberColumn(format="€ %+.10g"),
            })
            _conf_lbl = ("Ja, overschrijf ook mijn handmatige correcties" if (_incl and _nman)
                         else "Ja, voer deze herberekening uit")
            # Zelfde valkuil als bij de TOB: een widget-key mag niet overschreven worden
            # nadat de widget is aangemaakt. Nonce in de key i.p.v. de waarde resetten.
            _divn = st.session_state.get("div_rc_nonce", 0)
            if st.checkbox(_conf_lbl, key=f"div_rc_confirm_{_divn}"):
                if st.button("🔄 Herberekening uitvoeren", type="primary", key="div_recompute"):
                    done = _recompute_dividend_chain(divs, _rvrate, include_manual=_incl)
                    clear_cache()
                    st.session_state["div_rc_nonce"] = _divn + 1   # geen widget-key
                    st.success(f"✅ {len(done)} lijn(en) herberekend.")
                    st.rerun()

        # Verwijderen (meerdere tegelijk, met bevestiging)
        st.divider()
        del_opts = {d["id"]: f"#{d['id']} · {d['date'][:10]} · {asset_label(d['ticker'], names_map)} "
                             f"· netto {eur(_neur(d))}" for d in divs}
        multiselect_delete("confirm_del_div", del_opts,
                           lambda i: db.delete_dividend(i), noun="dividend")


# ── PAGINA: Belgische belasting ────────────────────────────────────────────────

def page_tax():
    st.title("🧾 Belgische Meerwaardebelasting")
    st.caption("⚖️ *Schattingen — raadpleeg een erkend belastingconsulent voor uw situatie.*")

    cur_year  = datetime.now().year
    sel_year  = st.selectbox("Boekjaar:", list(range(cur_year, cur_year - 6, -1)))
    overview, assets, prices = get_overview(sel_year)

    pv          = overview["position_values"]
    real_gl     = overview["total_realized_gl"]
    taxable_gl  = overview.get("total_taxable_gl", real_gl)
    foto        = overview.get("fotomoment_applied") and abs(taxable_gl - real_gl) > 0.005
    exemption   = overview["annual_exemption"]
    remaining   = overview["remaining_exemption"]
    taxable     = overview["taxable_amount"]
    tax_rate    = overview["tax_rate"]
    tax_due     = overview["tax_due"]
    unreal_gl   = overview["unrealized_gl"]
    total_val   = overview["total_portfolio_value"]
    total_cost  = overview["total_cost_basis"]

    # ── Metrics ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Belastbare W/V" if foto else "Gerealiseerde W/V", eur(taxable_gl),
              delta_color=delta_color(taxable_gl))
    c2.metric("Jaarlijkse vrijstelling", eur(exemption))
    c3.metric("Belastbaar bedrag", eur(taxable))
    c4.metric("Geschatte belasting (10%)", eur(tax_due),
              delta_color="inverse" if tax_due > 0 else "off")
    if foto:
        st.caption(f"📸 Fotomoment toegepast: economische W/V **{eur(real_gl)}**, maar fiscaal belastbaar "
                   f"**{eur(taxable_gl)}** — de meerwaarde opgebouwd vóór 2026 (referentie 31/12/2025) is vrijgesteld.")
    cnt       = overview.get("exemption_count", 1)
    carry_eff = overview.get("carry_exemption", 0.0)
    base_eff  = overview.get("base_exemption_effective", exemption)
    if cnt == 2 or carry_eff > 0:
        basis_txt = (f"2 × €{overview['base_exemption']:,.0f}" if cnt == 2
                     else f"€{overview['base_exemption']:,.0f}")
        opbouw_txt = f" + €{carry_eff:,.0f} opgebouwde overdracht" if carry_eff > 0 else ""
        partner_txt = " Elke partner heeft een eigen vrijstelling (gemeenschap van goederen)." if cnt == 2 else ""
        st.caption(f"ℹ️ Vrijstelling = {basis_txt} basis{opbouw_txt} = **€{exemption:,.0f}**.{partner_txt}")

    st.divider()
    col_l, col_r = st.columns([3, 2])

    with col_l:
        pct_used = min(100.0, taxable_gl / exemption * 100) if exemption > 0 else 0
        color_lbl = "🟢" if pct_used < 60 else ("🟡" if pct_used < 90 else "🔴")
        st.subheader("Vrijstelling gebruik")
        st.progress(max(0.0, min(1.0, pct_used / 100)),
                    text=f"{color_lbl} {pct_used:.1f}% gebruikt ({eur(taxable_gl)} / {eur(exemption)})")

        _econ_row = f"| Gerealiseerde W/V (economisch) | {eur(real_gl)} |\n" if foto else ""
        _basis_lbl = "Belastbare meerwaarden (na fotomoment)" if foto else "Gerealiseerde meerwaarden"
        st.markdown(f"""
| | Bedrag |
|---|---|
{_econ_row}| {_basis_lbl} | **{eur(taxable_gl)}** |
| Basisvrijstelling | {eur(overview.get('base_exemption_effective', exemption))} |
| Opgebouwde overdracht | {eur(overview.get('carry_exemption', 0))} |
| **Totale vrijstelling** | **{eur(exemption)}** |
| Resterend vrij | {eur(remaining)} |
| Belastbaar bedrag | **{eur(taxable)}** |
| Tarief | {tax_rate*100:.0f}% |
| **Geschatte belasting** | **{eur(tax_due)}** |
        """)

        if tax_due > 0:
            st.error(f"⚠️ Geschatte meerwaardebelasting {sel_year}: **{eur(tax_due)}**")
        else:
            st.success(f"✅ Geen meerwaardebelasting verschuldigd ({eur(remaining)} ruimte over).")

    with col_r:
        st.subheader("Totale portefeuille")
        st.metric("Huidige waarde", eur(total_val))
        st.metric("Kostbasis",      eur(total_cost))
        st.metric("Ongerealiseerde W/V", eur(unreal_gl),
                  delta=pct(unreal_gl / total_cost * 100 if total_cost else None),
                  delta_color=delta_color(unreal_gl))
        st.metric("Totale W/V (gerealiseerd + ongerealiseerd)",
                  eur(real_gl + unreal_gl),
                  delta_color=delta_color(real_gl + unreal_gl))

        st.divider()
        with st.expander("ℹ️ Fiscale wetgeving"):
            st.markdown(f"""
**Meerwaardebelasting België {sel_year}** (De Wever-hervorming)

- **Tarief:** 10% op netto gerealiseerde meerwaarden
- **Vrijstelling:** eerste **{eur(overview.get('base_exemption', exemption))}** per belastingplichtige per jaar{' — bij gemeenschap van goederen telt dit per partner, samen ' + eur(exemption) if overview.get('exemption_count', 1) == 2 else ''}
- **Opbouw:** ongebruikt deel (max €1.000/jaar) overdraagbaar tot 5 jaar → max €15.000 p.p.
- **Minwaarden** compenseren meerwaarden binnen hetzelfde boekjaar
- **Methode:** FIFO (first in, first out)
- **TOB:** apart berekend per transactie (reeds afgehouden)
- **Dividenden:** onderhevig aan 30% roerende voorheffing (apart stelsel)

*Raadpleeg een erkend belastingconsulent (accountant / fiscaal adviseur) voor uw specifieke situatie.*
            """)

    # ── Gerealiseerde transacties ──────────────────────────────────────────
    year_gains = overview["realized_gains"]
    if year_gains:
        st.divider()
        st.subheader(f"📋 Gerealiseerde transacties {sel_year}")
        rows = [{
            sign_icon(g["gain_loss"]): sign_icon(g["gain_loss"]),
            "Ticker":      g["ticker"],
            "Verkoopdatum": g["date"],
            "Aantal":      g["quantity"],
            "Kostbasis":   g["cost_basis"],
            "Verkoopwaarde": g["sell_total"],
            "Winst/Verlies": g["gain_loss"],
        } for g in sorted(year_gains, key=lambda x: x["date"], reverse=True)]
        show_df(pd.DataFrame(rows), width='stretch', hide_index=True, column_config={
            "Aantal":        st.column_config.NumberColumn(format="%.10g"),
            "Kostbasis":     st.column_config.NumberColumn(format="€ %.10g"),
            "Verkoopwaarde": st.column_config.NumberColumn(format="€ %.10g"),
            "Winst/Verlies": st.column_config.NumberColumn(format="€ %.10g"),
        })
    else:
        st.info(f"Geen gerealiseerde transacties in {sel_year}.")

    # TOB overzicht
    st.divider()
    st.subheader(f"🏛️ TOB betaald {sel_year}")
    txns_year = db.get_transactions(year=sel_year)
    total_tob = sum(t["tob_tax"] or 0 for t in txns_year)
    st.metric("Totale TOB betaald", eur(total_tob))
    if txns_year:
        tob_rows = [{
            "Ticker": t["ticker"],
            "Type":   "Aankoop" if t["transaction_type"] == "buy" else "Verkoop",
            "Datum":  t["date"],
            "Transactiewaarde": t["total_amount"],
            "TOB":    t["tob_tax"],
        } for t in txns_year if t["tob_tax"]]
        if tob_rows:
            with st.expander("TOB-detail per transactie"):
                show_df(pd.DataFrame(tob_rows), width='stretch', hide_index=True, column_config={
                    "Transactiewaarde": st.column_config.NumberColumn(format="€ %.10g"),
                    "TOB":              st.column_config.NumberColumn(format="€ %.10g"),
                })

    # ── Dividendfiscaliteit ───────────────────────────────────────────────────
    st.divider()
    st.subheader(f"💰 Dividendfiscaliteit {sel_year} (personenbelasting)")
    ben = tax_mod.dividend_tax_benefit(sel_year)
    yd = ben["per_year"].get(sel_year)
    persons = ben["persons"]
    if not yd or (yd["qualifying_gross"] <= 0 and yd["excluded_gross"] <= 0 and yd["fbb_base_fr"] <= 0):
        st.info("Geen dividenden geregistreerd voor dit jaar.")
    else:
        st.caption(f"Vrijstelling: **€{ben['exemption_per_person']:,.0f} per persoon** × {persons} persoon(en) "
                   f"= **€{ben['cap_amount']:,.0f}** vrijgestelde 'gewone' aandelendividenden. "
                   f"RV-tarief {ben['rv_rate']*100:.0f}%. Enkel individuele aandelen tellen mee "
                   "(fondsen/ETF's niet).")
        m1, m2, m3 = st.columns(3)
        m1.metric("In aanmerking komende dividenden", eur(yd["qualifying_gross"]),
                  help="Bruto (na eventuele buitenlandse bronheffing) van individuele aandelen.")
        m2.metric("Recupereerbare roerende voorheffing", eur(yd["reclaimable_rv"]),
                  help=f"Via codes 1437/2437. Max €{ben['exemption_per_person']*0.30*persons:,.2f} "
                       f"({persons}× €{ben['exemption_per_person']*0.30:,.2f}).")
        m3.metric("FBB Franse aandelen" + ("" if ben["fbb_enabled"] else " (uit)"),
                  eur(yd["fbb"]),
                  help="15% van het netto na Franse bronheffing. In/uit te schakelen in ⚙️ Instellingen.")

        st.markdown(f"**Totaal fiscaal voordeel {sel_year}: {eur(yd['total_benefit'])}**")
        # Uitwerking / optimalisatie
        lines = []
        if yd["qualifying_gross"] > yd["cap_amount"]:
            lines.append(f"Je in aanmerking komende dividenden ({eur(yd['qualifying_gross'])}) overschrijden "
                         f"de vrijstellingskorf ({eur(yd['cap_amount'])}). Vraag de vrijstelling aan voor de "
                         "dividenden met het **hoogste** RV-tarief eerst; je recupereert dan het maximum "
                         f"van {eur(yd['reclaimable_rv'])}.")
        else:
            lines.append(f"Al je in aanmerking komende dividenden ({eur(yd['qualifying_gross'])}) passen binnen "
                         f"de korf ({eur(yd['cap_amount'])}); de volledige ingehouden RV van "
                         f"{eur(yd['reclaimable_rv'])} is recupereerbaar.")
        if yd["excluded_gross"] > 0:
            lines.append(f"€{yd['excluded_gross']:,.2f} aan fonds-/ETF-dividenden komt **niet** in aanmerking "
                         "voor deze vrijstelling.")
        if ben["fbb_enabled"] and yd["fbb"] > 0:
            lines.append(f"Voor je Franse aandelen kun je daarnaast een FBB van {eur(yd['fbb'])} verrekenen "
                         "(vak VII, rubriek F) — dit is betwiste materie, bewaar bewijsstukken.")
        elif yd["fbb_base_fr"] > 0 and not ben["fbb_enabled"]:
            lines.append(f"Je hebt Franse aandelendividenden (basis {eur(yd['fbb_base_fr'])}); zet de FBB aan "
                         "in ⚙️ Instellingen om die mogelijke verrekening te zien.")
        if persons == 1:
            lines.append("Ben je gehuwd/wettelijk samenwonend? Zet het huwelijksstelsel op 'gemeenschap van "
                         "goederen' om de korf te verdubbelen.")
        for ln in lines:
            st.markdown("- " + ln)
        st.caption("ℹ️ Vermeld in de aangifte de **ingehouden roerende voorheffing** (niet het dividendbedrag) "
                   "onder de codes **1437/2437**. Dit is een schatting; bewaar je rekeninguittreksels als bewijs.")


# ── PAGINA: AI Advisor ────────────────────────────────────────────────────────

def render_market_opportunities():
    """Luik 2: koopopportuniteiten uit de wereldwijde markt + de opvolging ervan
    over 7 dagen, 1 maand en 3 maanden (met het gemiddelde advies per periode)."""
    st.subheader("② 🌍 Marktopportuniteiten — buiten je portefeuille")
    st.caption("Elke werkdag (07:45, vóór de opening) speurt de AI de wereldwijde markt af naar "
               "**nieuwe** koopideeën op basis van bedrijfsprestaties, vooruitzichten, "
               "macro-economie, geopolitiek en financiële berichtgeving: **2 defensieve** "
               "(groei + eventueel dividend), **2 matig speculatieve** en **2 sterk speculatieve** "
               "aandelen — elk met onderbouwing, katalysatoren en risico's.")

    if not ai_advisor.ai_function_enabled("market"):
        st.warning("Deze functie staat uit. Schakel ze in via ⚙️ Instellingen → AI.")
    if not ai_advisor.market_websearch_enabled():
        st.warning("🔌 Live websearch staat uit: de AI put enkel uit haar trainingskennis en kent "
                   "de berichtgeving van vandaag dus niet. Zet ze aan via ⚙️ Instellingen → AI.")

    if st.button("🌍 Zoek nu marktopportuniteiten", type="primary", key="gen_market"):
        with st.spinner("AI doorzoekt de wereldwijde markt (dit kan een halve minuut duren)..."):
            res = ai_advisor.generate_market_opportunities()
        if res.get("error"):
            st.error(res["error"])
        else:
            src = "met live websearch" if res.get("websearch") else \
                  "zonder websearch (enkel trainingskennis)"
            st.success(f"✅ {res['stored']} koopidee(ën) gegenereerd {src}.")
        st.rerun()

    # ── De ideeën van de laatste ronde ───────────────────────────────────────
    batch = db.get_latest_idea_batch()
    if not batch:
        st.info("Nog geen marktopportuniteiten. Klik hierboven of wacht op de dagelijkse run.")
        return

    ideas = db.get_market_ideas(batch_id=batch)
    note = db.get_ai_evaluations("market_ideas", limit=1)
    st.markdown(f"#### 📅 Ideeën van {ideas[0]['idea_date']}")
    if note and (note[0].get("content") or "").strip():
        st.markdown("**🌐 Marktbeeld**")
        st.markdown(note[0]["content"])

    by_bucket = {}
    for it in ideas:
        by_bucket.setdefault(it["bucket"], []).append(it)

    for bucket in ai_advisor.MARKET_BUCKETS:
        rows = by_bucket.get(bucket, [])
        st.markdown(f"##### {ai_advisor.BUCKET_LABELS[bucket]}")
        if not rows:
            st.caption("Geen idee in deze klasse voor deze ronde.")
            continue
        cols = st.columns(len(rows))
        for col, it in zip(cols, rows):
            with col:
                with st.container(border=True):
                    st.markdown(f"**{it.get('name') or it['ticker']}** · `{it['ticker']}`")
                    meta = [it.get("exchange") or "", it.get("currency") or ""]
                    st.caption(" · ".join(m for m in meta if m))
                    m1, m2 = st.columns(2)
                    m1.metric("Advies", ai_advisor.RATING_LABELS.get(it.get("rating"), "—"))
                    if it.get("price_target"):
                        up = None
                        if it.get("price_at_advice"):
                            up = (it["price_target"] - it["price_at_advice"]) / it["price_at_advice"] * 100
                        m2.metric("Koersdoel 12m", f"{it['price_target']:.2f}",
                                  delta=pct(up) if up is not None else None,
                                  delta_color=delta_color(up))
                    facts = []
                    if it.get("price_at_advice"):
                        facts.append(f"Koers bij advies: **{it['price_at_advice']:.2f} "
                                     f"{it.get('currency') or ''}**")
                    if it.get("dividend_yield"):
                        facts.append(f"Dividendrendement: **{it['dividend_yield']:.2f}%**")
                    if it.get("horizon"):
                        facts.append(f"Horizon: **{it['horizon']}**")
                    if facts:
                        st.caption("  ·  ".join(facts))
                    if it.get("rationale"):
                        st.markdown(f"**Onderbouwing** — {it['rationale']}")
                    if it.get("catalysts"):
                        st.markdown(f"**⚡ Katalysatoren** — {it['catalysts']}")
                    if it.get("risks"):
                        st.markdown(f"**⚠️ Risico's** — {it['risks']}")

    # ── Opvolging: gemiddeld advies per periode ──────────────────────────────
    st.divider()
    st.markdown("#### 📈 Opvolging van de adviezen")
    st.caption("Elk voorgesteld aandeel wordt bijgehouden. Per periode zie je het **gemiddelde "
               "advies** (het gemiddelde van alle ratings die dat aandeel in die periode kreeg), "
               "hoe vaak het werd voorgesteld en het rendement sinds het eerste advies.")

    plabels = {lbl: days for _, lbl, days in ai_advisor.MARKET_PERIODS}
    sel = _section_radio("market_period", list(plabels.keys()))
    days = plabels[sel]
    synth = ai_advisor.market_idea_synthesis(days)

    if not synth:
        st.info(f"Nog geen adviezen in de laatste {sel.lower()}.")
        return

    rets = [r["rendement_pct"] for r in synth if r["rendement_pct"] is not None]
    s1, s2, s3 = st.columns(3)
    s1.metric(f"Voorgestelde aandelen ({sel.lower()})", str(len(synth)))
    s2.metric("Totaal adviezen", str(sum(r["n"] for r in synth)))
    if rets:
        avg_ret = sum(rets) / len(rets)
        s3.metric("Gem. rendement sinds 1e advies", pct(avg_ret),
                  delta_color=delta_color(avg_ret),
                  help="Gemiddeld koersrendement (native munt) van de voorgestelde aandelen, "
                       "gemeten vanaf de koers op het moment van hun eerste advies.")
    else:
        s3.metric("Gem. rendement sinds 1e advies", "—",
                  help="Nog geen opgevolgde koersen. De planner legt de koers van elk voorgesteld "
                       "aandeel dagelijks vast; morgen staat hier een cijfer.")

    srows = []
    for r in synth:
        srows.append({
            "":                  sign_icon(r["rendement_pct"]) if r["rendement_pct"] is not None else "⚪",
            "Aandeel":           f"{r['naam']} ({r['ticker']})",
            "Klasse":            " + ".join(ai_advisor.BUCKET_SHORT[b] for b in r["buckets"]),
            "Adviezen":          r["n"],
            "Gemiddeld advies":  ai_badge(r["avg_rating"]),
            "Score":             r["avg_score"],
            "Laatste advies":    ai_badge(r["latest_rating"]),
            "1e advies":         r["eerste_advies"],
            "Startkoers":        r["startkoers"],
            "Koers nu":          r["huidige_koers"],
            "Rendement":         r["rendement_pct"],
            "Koersdoel 12m":     r["koersdoel"],
        })
    show_df(pd.DataFrame(srows), width="stretch", hide_index=True, column_config={
        "Adviezen":      st.column_config.NumberColumn(format="%d"),
        "Score":         st.column_config.NumberColumn(
                             format="%+.10g",
                             help="Gemiddelde ratingscore: +2 sterk kopen, +1 kopen, 0 behouden, "
                                  "−1 verkopen, −2 sterk verkopen."),
        "Startkoers":    st.column_config.NumberColumn(format="%.10g"),
        "Koers nu":      st.column_config.NumberColumn(format="%.10g"),
        "Rendement":     st.column_config.NumberColumn(format="%+.10g%%"),
        "Koersdoel 12m": st.column_config.NumberColumn(format="%.10g"),
    })
    st.caption("Koersen in de native munt van elk aandeel. Het rendement is een zuiver "
               "koersrendement (geen dividenden, geen wisselkoerseffect) en is dus geen "
               "gerealiseerd resultaat — het meet enkel hoe het advies het sindsdien doet. "
               "Dit is geen gepersonaliseerd financieel advies.")


def page_ai_advisor():
    st.title("🤖 AI Beleggingsadviseur")

    api_key = db.get_setting("openai_api_key", "")
    if not api_key:
        st.warning("⚠️ Voeg uw OpenAI API-sleutel toe in **⚙️ Instellingen** om AI-functies te gebruiken.")
        return

    # ── AI-kosten ─────────────────────────────────────────────────────────────
    usage = db.get_ai_usage_summary()
    if usage["total_calls"]:
        try:
            tot_eur = md.convert_to_eur(usage["total_cost_usd"], "USD")
            mon_eur = md.convert_to_eur(usage["month_cost_usd"], "USD")
        except Exception:
            tot_eur = mon_eur = None
        k1, k2, k3 = st.columns(3)
        k1.metric("💵 AI-kosten totaal",
                  f"${usage['total_cost_usd']:.4f}",
                  help="Geschat op basis van tokengebruik en richtprijzen. De exacte factuur staat op je OpenAI-dashboard.")
        k2.metric("📅 Deze maand", f"${usage['month_cost_usd']:.4f}",
                  delta=f"{usage['month_calls']} oproep(en)", delta_color="off")
        k3.metric("🔢 Totaal oproepen", str(usage["total_calls"]),
                  delta=(f"≈ {eur(tot_eur)}" if tot_eur is not None else None), delta_color="off")
        with st.expander("📊 Uitsplitsing AI-kosten"):
            if usage["by_model"]:
                st.caption("Per model")
                show_df(pd.DataFrame([{
                    "Model": r["model"],
                    "Oproepen": r["n"],
                    "Input-tokens": r["pt"],
                    "Output-tokens": r["ct"],
                    "Kost (USD)": r["c"],
                } for r in usage["by_model"]]), width='stretch', hide_index=True, column_config={
                    "Input-tokens":  st.column_config.NumberColumn(format="%d"),
                    "Output-tokens": st.column_config.NumberColumn(format="%d"),
                    "Kost (USD)":    st.column_config.NumberColumn(format="$ %.4f"),
                })
            if usage["by_function"]:
                st.caption("Per functie")
                func_labels = {"tax_optimization": "Belastingadvies",
                               "daily_advice": "① Portefeuilleadvies",
                               "market_ideas": "② Marktopportuniteiten",
                               "market_evaluation": "Marktevaluatie (oud)",
                               "portfolio_ratings": "Portefeuille-ratings (oud)",
                               "price_target": "Koersdoel", "chat": "Overig",
                               "price_refresh": "Prijsverversing"}
                show_df(pd.DataFrame([{
                    "Functie": func_labels.get(r["function"], r["function"]),
                    "Oproepen": r["n"],
                    "Kost (USD)": r["c"],
                } for r in usage["by_function"]]), width='stretch', hide_index=True, column_config={
                    "Kost (USD)": st.column_config.NumberColumn(format="$ %.4f"),
                })

            st.divider()
            pr1, pr2 = st.columns([3, 1])
            last = db.get_setting("ai_pricing_last_refresh", "")
            pr1.caption("Richtprijzen per model (USD per 1M tokens). Worden maandelijks automatisch "
                        "ververst." + (f" Laatste verversing: {last}." if last else ""))
            if pr2.button("💲 Ververs nu", key="refresh_prices"):
                if not db.get_setting("openai_api_key", ""):
                    st.warning("Geen OpenAI-sleutel — stel die in via ⚙️ Instellingen.")
                else:
                    with st.spinner("Actuele modelprijzen opzoeken via AI..."):
                        res = ai_advisor.refresh_model_prices()
                    if res.get("error"):
                        st.error(res["error"])
                    else:
                        st.success(f"✅ {len(res['updated'])} prijs(en) bijgewerkt "
                                   f"({', '.join(res['updated']) or 'geen wijziging'}).")
                        st.rerun()
            pricing = ai_advisor.get_model_pricing()
            show_df(pd.DataFrame([{
                "Model": m, "Input ($/1M)": p[0], "Output ($/1M)": p[1],
            } for m, p in pricing.items()]), width='stretch', hide_index=True, column_config={
                "Input ($/1M)":  st.column_config.NumberColumn(format="%.10g"),
                "Output ($/1M)": st.column_config.NumberColumn(format="%.10g"),
            })
            st.caption("ℹ️ Richtprijzen medio 2026; werkelijke kosten kunnen afwijken. "
                       "Controleer je OpenAI-dashboard voor de exacte factuur.")
        st.divider()

    # Actieve privacymodus tonen
    _plvl = ai_advisor.privacy_level()
    if _plvl != "off":
        _pl = "bedragen verborgen (percentages)" if _plvl == "amounts" else "volledig anoniem (ook tickers)"
        st.caption(f"🔒 Privacymodus actief: **{_pl}**. Pas aan via ⚙️ Instellingen → AI.")

    st.info("Het **dagelijkse advies bestaat uit twee luiken**:  \n"
            "**① Portefeuilleadvies** — (sterk) kopen / behouden / (sterk) verkopen op wat je "
            "**nu al bezit**.  \n"
            "**② Marktopportuniteiten** — nieuwe koopideeën uit de **wereldwijde markt**, "
            "los van je portefeuille: elke dag 2 defensieve, 2 matig speculatieve en "
            "2 sterk speculatieve aandelen.")

    _aisec = _section_radio("ai_section", [
        "① 📋 Portefeuilleadvies (dagelijks)",
        "② 🌍 Marktopportuniteiten (dagelijks)",
        "💡 Belastingoptimalisatie (maandelijks)",
    ])

    if _aisec == "💡 Belastingoptimalisatie (maandelijks)":
        st.subheader("💡 Belastingoptimalisatieadvies")
        st.caption("Automatisch gegenereerd op de 1e van de maand om 08:00. Gebaseerd op je actuele "
                   "portefeuille en de Belgische fiscale regels.")
        if not ai_advisor.ai_function_enabled("tax"):
            st.warning("Deze functie staat uit. Schakel ze in via ⚙️ Instellingen → AI.")
        evals = db.get_ai_evaluations("tax_optimization", limit=10)
        if evals:
            st.caption(f"📅 Laatste: {evals[0]['created_at'][:16]}")
            st.markdown(evals[0]["content"])
        else:
            st.info("Nog geen belastingadvies. Klik hieronder of wacht op de maandelijkse run.")
        if st.button("💡 Genereer belastingadvies nu", type="primary", key="gen_tax"):
            with st.spinner("AI analyseert je portefeuille..."):
                ai_advisor.generate_tax_optimization()
            clear_cache()
            st.rerun()
        if len(evals) > 1:
            with st.expander("📚 Historiek"):
                for ev in evals[1:]:
                    st.caption(f"📅 {ev['created_at'][:16]}")
                    st.markdown(ev["content"])
                    st.divider()

    if _aisec == "② 🌍 Marktopportuniteiten (dagelijks)":
        render_market_opportunities()

    if _aisec == "① 📋 Portefeuilleadvies (dagelijks)":
        st.subheader("① 📋 Portefeuilleadvies — enkel je bestaande posities")
        st.caption("Eén advies per werkdag (18:00) over de aandelen die je **nu al bezit**: "
                   "(sterk) kopen, behouden of (sterk) verkopen. Levert zowel dit tekstadvies als "
                   "de ratings die de tabellen op de **💼 Portefeuille**-pagina en het dashboard "
                   "voeden. Nieuwe aandelen buiten je portefeuille komen bewust niet hier aan bod "
                   "— die vind je in luik ② Marktopportuniteiten.")
        if not ai_advisor.ai_function_enabled("daily"):
            st.warning("Deze functie staat uit. Schakel ze in via ⚙️ Instellingen → AI.")
        devals = db.get_ai_evaluations("daily_advice", limit=10)
        if devals and (devals[0].get("content") or "").strip():
            st.caption(f"📅 Laatste: {devals[0]['created_at'][:16]}")
            st.markdown(devals[0]["content"])
        else:
            st.info("Nog geen dagelijks advies. Klik hieronder of wacht op de dagelijkse run.")
        if st.button("🤖 Genereer dagelijks advies nu", type="primary", key="gen_daily"):
            with st.spinner("AI beoordeelt je portefeuille..."):
                res = ai_advisor.generate_daily_portfolio_advice()
            if res.get("error"):
                st.error(res["error"])
            elif res.get("truncated"):
                st.warning(f"⚠️ Advies gegenereerd, maar het AI-antwoord was afgekapt: "
                           f"{res['stored']} van de {res.get('expected', '?')} posities kregen "
                           "een rating. Het bruikbare deel is bewaard. Probeer opnieuw, of kies "
                           "een model met een ruimere uitvoerlimiet (⚙️ Instellingen → AI).")
            else:
                st.success(f"✅ Advies gegenereerd ({res['stored']} ratings). "
                           "De portefeuille-tabellen zijn bijgewerkt.")
            clear_cache()
            st.rerun()
        if len(devals) > 1:
            with st.expander("📚 Historiek"):
                for ev in devals[1:]:
                    if not (ev.get("content") or "").strip():
                        continue
                    st.caption(f"📅 {ev['created_at'][:16]}")
                    st.markdown(ev["content"])
                    st.divider()


# ── PAGINA: Instellingen ──────────────────────────────────────────────────────

def page_settings():
    st.title("⚙️ Instellingen")

    _ssec = _section_radio("settings_section",
        ["🔑 API-sleutel", "🏦 Rekeningen", "🧾 Meerwaardebelasting", "🏛️ TOB & bronbelasting", "🗃️ Data"])

    if _ssec == "🔑 API-sleutel":
        st.subheader("OpenAI API & AI-instellingen")
        current = db.get_setting("openai_api_key", "")
        new_key = st.text_input("API-sleutel", value=current, type="password",
                                help="Beschikbaar via platform.openai.com/api-keys")

        model_keys = list(ai_advisor.AVAILABLE_MODELS.keys())
        def _model_idx(setting, default):
            cur = db.get_setting(setting, default) or default
            return model_keys.index(cur) if cur in model_keys else 0

        m1, m2, m3 = st.columns(3)
        with m1:
            model = st.selectbox("① Model voor portefeuilleadvies", model_keys,
                                 index=_model_idx("openai_model", "gpt-5.6-terra"),
                                 format_func=lambda k: ai_advisor.AVAILABLE_MODELS[k],
                                 help="Gebruikt voor luik 1 (dagelijks portefeuilleadvies) en het "
                                      "maandelijkse belastingadvies.")
        with m2:
            mk_model = st.selectbox("② Model voor marktopportuniteiten", model_keys,
                                    index=_model_idx("openai_market_model", "gpt-5.6-terra"),
                                    format_func=lambda k: ai_advisor.AVAILABLE_MODELS[k],
                                    help="Apart model voor luik 2. Marktonderzoek met live "
                                         "websearch vraagt vaak meer redeneervermogen dan het "
                                         "beoordelen van je eigen posities — hier kan je dus een "
                                         "sterker (of net goedkoper) model kiezen dan voor luik 1.")
        with m3:
            pt_model = st.selectbox("Model voor koersdoelbepaling", model_keys,
                                    index=_model_idx("openai_price_target_model", "gpt-5.6-sol"),
                                    format_func=lambda k: ai_advisor.AVAILABLE_MODELS[k],
                                    help="Mag een sterker (duurder) model zijn dan voor het reguliere advies.")

        # ── Geraamde kost per oproep, per model ──────────────────────────────
        with st.expander("💵 Wat kost één oproep? — raming per model"):
            _ws = db.get_setting("ai_market_websearch", "1") != "0"
            st.caption("Geraamde kost van ÉÉN oproep, per model en per functie. Zodra een functie "
                       "een keer gedraaid heeft, wordt het **gemeten** gemiddelde tokengebruik "
                       "gebruikt (anders een richtwaarde). Voor luik ② is de kost van de "
                       "websearch-oproep en de opgehaalde zoekinhoud meegerekend"
                       + (" (websearch staat AAN)." if _ws else " — maar websearch staat nu UIT.")
                       + " Het blijft een raming: de echte factuur staat op je OpenAI-dashboard.")
            _cost_rows, _measured = [], set()
            for _mk in model_keys:
                _d1 = ai_advisor.estimate_call_cost("daily_advice", _mk)
                _d2 = ai_advisor.estimate_call_cost("market_ideas", _mk, websearch=_ws)
                _dt = ai_advisor.estimate_call_cost("tax_optimization", _mk)
                if _d1["measured"]: _measured.add("① portefeuilleadvies")
                if _d2["measured"]: _measured.add("② marktopportuniteiten")
                if _dt["measured"]: _measured.add("belastingadvies")
                _cost_rows.append({
                    "Model":                     ai_advisor.AVAILABLE_MODELS[_mk],
                    "in $/1M":                   ai_advisor.get_model_pricing().get(_mk, (0, 0))[0],
                    "uit $/1M":                  ai_advisor.get_model_pricing().get(_mk, (0, 0))[1],
                    "① Portefeuilleadvies ($)":  _d1["total"],
                    "② Marktopportuniteiten ($)": _d2["total"],
                    "Belastingadvies ($)":       _dt["total"],
                    "Per maand ($)":             _d1["total"] * 21 + _d2["total"] * 21 + _dt["total"],
                })
            show_df(pd.DataFrame(_cost_rows), column_config={
                "in $/1M":                    st.column_config.NumberColumn(format="$ %.10g"),
                "uit $/1M":                   st.column_config.NumberColumn(format="$ %.10g"),
                "① Portefeuilleadvies ($)":   st.column_config.NumberColumn(format="$ %.4f"),
                "② Marktopportuniteiten ($)": st.column_config.NumberColumn(format="$ %.4f"),
                "Belastingadvies ($)":        st.column_config.NumberColumn(format="$ %.4f"),
                "Per maand ($)":              st.column_config.NumberColumn(
                    format="$ %.2f",
                    help="Ruwe maandraming: 21 werkdagen x (luik ① + luik ②) + 1 belastingadvies."),
            }, dec=4)
            st.caption(("Gemeten tokengebruik gebruikt voor: " + ", ".join(sorted(_measured))
                        + ". De rest is een richtwaarde.") if _measured
                       else "Nog geen historiek: alle bedragen zijn richtwaarden. Na de eerste "
                            "oproepen wordt dit vanzelf accurater.")

        st.markdown("**Investeringsvolume (particuliere belegger)**")
        st.caption("Helpt de AI realistische, op jouw budget afgestemde koopvoorstellen te doen.")
        v1, v2 = st.columns(2)
        with v1:
            vol_m = st.number_input("Geschat bedrag per maand (€)", min_value=0.0, step=50.0,
                                    value=float(db.get_setting("investment_volume_month", "0") or 0))
        with v2:
            vol_y = st.number_input("Geschat bedrag per jaar (€)", min_value=0.0, step=500.0,
                                    value=float(db.get_setting("investment_volume_year", "0") or 0))

        st.divider()
        st.markdown("**🔒 Privacy & AI-functies**")
        st.caption("Bepaal hoeveel van je financiële data naar OpenAI gestuurd wordt en welke "
                   "AI-functies actief zijn. OpenAI gebruikt API-invoer standaard niet om modellen "
                   "te trainen; deze instellingen beperken de data extra.")
        priv_opts = ["off", "amounts", "full"]
        priv_lbl = {"off": "Uit — volledige data (tickers + bedragen)",
                    "amounts": "Bedragen verbergen — enkel gewichten in %, tickers blijven",
                    "full": "Volledig anoniem — ook tickers/namen vervangen door POS1, POS2, ..."}
        cur_priv = db.get_setting("ai_privacy_mode", "off")
        privacy = st.selectbox("Privacymodus", priv_opts,
                               index=priv_opts.index(cur_priv) if cur_priv in priv_opts else 0,
                               format_func=lambda k: priv_lbl[k])
        st.caption("Bij 'volledig anoniem' krijgt de AI geen tickers, namen of bedragen — enkel type, "
                   "profiel en gewicht. Het advies blijft bruikbaar maar is iets minder specifiek; de "
                   "ratings worden achteraf weer aan je echte aandelen gekoppeld.")
        en1, en2, en3 = st.columns(3)
        enable_tax = en1.checkbox("Maandelijks belastingadvies actief",
                                  value=db.get_setting("ai_enable_tax", "1") != "0")
        enable_daily = en2.checkbox("① Dagelijks portefeuilleadvies actief",
                                    value=db.get_setting("ai_enable_daily", "1") != "0")
        enable_market = en3.checkbox("② Dagelijkse marktopportuniteiten actief",
                                     value=db.get_setting("ai_enable_market", "1") != "0",
                                     help="Luik 2: elke werkdag 6 koopideeën uit de wereldwijde "
                                          "markt (2 defensief, 2 matig speculatief, 2 sterk "
                                          "speculatief).")
        enable_ws = st.checkbox("🌐 Live websearch voor de marktopportuniteiten",
                                value=db.get_setting("ai_market_websearch", "1") != "0",
                                help="Laat de AI zelf actuele koersen, resultaten en "
                                     "berichtgeving opzoeken via de websearch-tool van OpenAI. "
                                     "Zonder dit put ze enkel uit haar trainingskennis en kent ze "
                                     "het nieuws van vandaag niet. Kost iets meer per oproep; valt "
                                     "automatisch terug op gewoon advies als je model de tool niet "
                                     "ondersteunt.")

        if st.button("💾 Opslaan", key="save_api"):
            db.set_setting("openai_api_key", new_key.strip())
            db.set_setting("openai_model", model)
            db.set_setting("openai_market_model", mk_model)
            db.set_setting("openai_price_target_model", pt_model)
            db.set_setting("investment_volume_month", str(vol_m))
            db.set_setting("investment_volume_year", str(vol_y))
            db.set_setting("ai_privacy_mode", privacy)
            db.set_setting("ai_enable_tax", "1" if enable_tax else "0")
            db.set_setting("ai_enable_daily", "1" if enable_daily else "0")
            db.set_setting("ai_enable_market", "1" if enable_market else "0")
            db.set_setting("ai_market_websearch", "1" if enable_ws else "0")
            st.success("✅ Instellingen opgeslagen!")
        if current:
            st.success("✅ API-sleutel is geconfigureerd.")
        else:
            st.warning("⚠️ Geen API-sleutel — AI-functies niet beschikbaar.")

    if _ssec == "🏦 Rekeningen":
        st.subheader("Rekeningen / oorsprong")
        st.caption("Definieer je rekeningen (bv. Bolero, Degiro, Saxo). Je kiest er één bij elke transactie en kunt erop filteren in het Dashboard, de Portefeuille en de Evolutie-pagina.")
        current = [a for a in db.get_accounts() if a != db.DEFAULT_ACCOUNT]
        txt = st.text_area("Eén rekening per regel", value="\n".join(current), height=140,
                           help="De rekening 'Niet toegewezen' bestaat altijd als vangnet voor oude transacties.")
        if st.button("💾 Rekeningen opslaan", key="save_accts"):
            db.set_accounts([line.strip() for line in txt.splitlines() if line.strip()])
            clear_cache()
            st.success("✅ Rekeningen opgeslagen!")
        used = db.get_used_accounts()
        if used:
            st.caption("Momenteel in gebruik: " + ", ".join(used))

        st.divider()
        st.markdown("**Beleggingsprofiel per rekening**")
        st.caption("Bepaalt hoe de AI-adviseur de aanbevelingen per rekening afstemt.")
        prof_keys = list(ai_advisor.PROFILE_LABELS.keys())
        profiles = db.get_account_profiles()
        accts_now = [a for a in db.get_accounts() if a != db.DEFAULT_ACCOUNT]
        if not accts_now:
            st.info("Voeg eerst rekeningen toe om een profiel in te stellen.")
        for acct in accts_now:
            cur_prof = profiles.get(acct, "neutral")
            sel = st.selectbox(
                f"🏦 {acct}", prof_keys,
                index=prof_keys.index(cur_prof) if cur_prof in prof_keys else prof_keys.index("neutral"),
                format_func=lambda k: ai_advisor.PROFILE_LABELS[k],
                key=f"profile_{acct}")
            if sel != cur_prof:
                db.set_account_profile(acct, sel)
                st.toast(f"Profiel '{acct}' bijgewerkt", icon="✅")

    if _ssec == "🧾 Meerwaardebelasting":
        st.subheader("Meerwaardebelasting (opt-out stelsel)")
        rate  = st.number_input("Belastingtarief (%)",
                                min_value=0.0, max_value=100.0,
                                value=float(db.get_setting("capital_gains_tax_rate", "0.10")) * 100,
                                step=0.5)
        exemp = st.number_input("Jaarlijkse vrijstelling per persoon (€)",
                                min_value=0.0, value=float(db.get_setting("annual_exemption", "10000")),
                                step=500.0)

        regimes = {
            "single":    "Alleenstaand / 1 belastingplichtige  →  1× vrijstelling",
            "community": "Gehuwd of wettelijk samenwonend, gemeenschap van goederen  →  2× vrijstelling",
        }
        keys = list(regimes.keys())
        cur_regime = db.get_setting("household_regime", "single")
        regime = st.selectbox("Belastingsituatie / huwelijksstelsel", keys,
                              index=keys.index(cur_regime) if cur_regime in keys else 0,
                              format_func=lambda k: regimes[k])
        if regime == "community":
            st.info(f"💑 Bij gemeenschap van goederen heeft **elke partner** recht op de jaarlijkse vrijstelling — ook als een effectenrekening op naam van één partner staat. "
                    f"De gezamenlijke meerwaarde wordt verminderd met een effectieve vrijstelling van **€{exemp*2:,.0f}**.")
        st.caption("⚖️ Schatting op basis van een gelijke (50/50) toerekening van de meerwaarde aan beide partners. "
                   "De meerjarige opbouw van ongebruikte vrijstelling (max €1.000/jaar, tot €15.000 p.p. over 5 jaar) "
                   "wordt automatisch berekend uit je transactiegeschiedenis vanaf 2026. Raadpleeg een fiscalist voor je concrete situatie.")

        if st.button("💾 Opslaan", key="save_tax"):
            db.set_setting("capital_gains_tax_rate", str(rate / 100))
            db.set_setting("annual_exemption", str(exemp))
            db.set_setting("household_regime", regime)
            clear_cache()
            st.success("✅ Belastinginstellingen opgeslagen!")

        st.divider()
        st.subheader("💰 Dividendvrijstelling (personenbelasting)")
        st.caption("De eerste schijf 'gewone' aandelendividenden per belastingplichtige is vrijgesteld "
                   "van roerende voorheffing; je recupereert die RV via de aangifte (codes 1437/2437). "
                   "Geldt niet voor dividenden van fondsen/ETF's. Het bedrag is sinds 2025 niet "
                   "geïndexeerd (t/m aanslagjaar 2030).")
        div_exemp = st.number_input("Vrijgestelde dividenden per persoon (€)",
                                    min_value=0.0, value=float(db.get_setting("dividend_exemption_per_person", "833")),
                                    step=1.0,
                                    help="Inkomstenjaar 2025/2026: €833 p.p. (max €249,90 recupereerbare RV p.p.). "
                                         "Het aantal personen volgt uit het huwelijksstelsel hierboven.")
        fbb_on = st.checkbox("FBB voor Franse aandelen toepassen",
                             value=db.get_setting("fbb_enabled", "0") == "1",
                             help="Forfaitair gedeelte buitenlandse belasting (verdrag BE-FR): 15% van het "
                                  "nettobedrag na Franse bronheffing. De fiscus aanvaardt dit na rechtspraak "
                                  "(Hof van Cassatie), maar het blijft betwist — raadpleeg een fiscalist.")
        fbb_r = st.number_input("FBB-tarief (%)", min_value=0.0, max_value=100.0,
                                value=float(db.get_setting("fbb_rate", "0.15")) * 100, step=0.5,
                                disabled=not fbb_on)
        if st.button("💾 Dividendvrijstelling opslaan", key="save_div_tax"):
            db.set_setting("dividend_exemption_per_person", str(div_exemp))
            db.set_setting("fbb_enabled", "1" if fbb_on else "0")
            db.set_setting("fbb_rate", str(fbb_r / 100))
            clear_cache()
            st.success("✅ Dividendvrijstelling opgeslagen!")

    if _ssec == "🏛️ TOB & bronbelasting":
        st.subheader("Taks op Beursverrichtingen (TOB)")
        c1, c2 = st.columns(2)
        with c1:
            r_s  = st.number_input("Aandelen tarief (%)", value=float(db.get_setting("tob_rate_stocks", "0.0035"))*100, step=0.001, format="%.10g")
            r_ed = st.number_input("ETF distribuerend (%)", value=float(db.get_setting("tob_rate_etf_distributing", "0.0012"))*100, step=0.001, format="%.10g")
            r_ea = st.number_input("ETF kapitaliseerend (%)", value=float(db.get_setting("tob_rate_etf_accumulating", "0.0132"))*100, step=0.001, format="%.10g")
        with c2:
            m_s  = st.number_input("Aandelen maximum (€)", value=float(db.get_setting("tob_max_stocks", "1600")), step=100.0)
            m_ed = st.number_input("ETF distr. maximum (€)", value=float(db.get_setting("tob_max_etf_distributing", "1300")), step=100.0)
            m_ea = st.number_input("ETF kap. maximum (€)", value=float(db.get_setting("tob_max_etf_accumulating", "4000")), step=100.0)
        wh = st.number_input("Roerende voorheffing (%)",
                              value=float(db.get_setting("withholding_tax_rate", "0.30"))*100,
                              step=0.5)
        _tob_start = db.get_setting("tob_start_date", "2017-01-01")
        try:
            _tob_start_d = datetime.strptime(_tob_start[:10], "%Y-%m-%d").date()
        except Exception:
            _tob_start_d = date(2017, 1, 1)
        tob_start = st.date_input(
            "TOB van toepassing vanaf", value=_tob_start_d,
            min_value=date(1990, 1, 1), max_value=date.today(),
            help="Transacties vóór deze datum krijgen geen TOB. Voor beleggers via een "
                 "buitenlandse tussenpersoon (bv. DEGIRO) geldt de TOB-plicht pas sinds 1/1/2017. "
                 "Gebruik je (ook) een Belgische broker die vroeger al TOB inhield, pas de datum dan aan.")
        if st.button("💾 Opslaan", key="save_tob"):
            db.set_setting("tob_rate_stocks", str(r_s/100))
            db.set_setting("tob_rate_etf_distributing", str(r_ed/100))
            db.set_setting("tob_rate_etf_accumulating", str(r_ea/100))
            db.set_setting("tob_max_stocks", str(m_s))
            db.set_setting("tob_max_etf_distributing", str(m_ed))
            db.set_setting("tob_max_etf_accumulating", str(m_ea))
            db.set_setting("tob_start_date", str(tob_start))
            db.set_setting("withholding_tax_rate", str(wh/100))
            st.success("✅ TOB-instellingen opgeslagen!")

        st.divider()
        st.subheader("🌍 Buitenlandse bronbelasting op dividenden — per jaar")
        st.caption("Tarief per land van herkomst (het land stel je in per activum op de 🏢 Activa-pagina), "
                   "**per jaar**. Bronbelastingen wijzigen over de jaren, en een dividend hoort belast te "
                   "worden tegen het tarief dat gold **op dat moment** — niet tegen het tarief van vandaag. "
                   "Tarieven **schuiven door**: stel je 2024 in, dan geldt dat ook voor 2025, 2026, ... tot "
                   "je voor een van die jaren iets anders instelt. Je registreert dus enkel de "
                   "**wijzigingen**. Standaardtarieven zijn indicatief — verdragstarieven kunnen afwijken.")

        # Dekking: voor elk jaar met dividenden moet er een tarief gekend zijn
        _dyears = sorted({tax_mod.year_of(d["date"]) for d in db.get_dividends()
                          if (d.get("kind") or "dividend") == "dividend"
                          and tax_mod.year_of(d["date"])})
        _tyears = sorted({tax_mod.year_of(t["date"]) for t in db.get_transactions()
                          if tax_mod.year_of(t["date"])})
        _years_needed = sorted(set(_dyears) | set(_tyears) | {datetime.now().year})
        _cfg = tax_mod.configured_years()
        if _cfg:
            _uncovered = [y for y in _years_needed if y < min(_cfg)]
            if _uncovered:
                st.warning(f"⚠️ Voor {', '.join(map(str, _uncovered))} is er geen jaartabel: die "
                           f"jaren vallen terug op de standaardtarieven. Het vroegst ingestelde jaar "
                           f"is {min(_cfg)}. Stel het oudste jaar in dat je nodig hebt — alle latere "
                           "jaren erven dat automatisch.")
            else:
                st.success(f"✅ Alle jaren met transacties of dividenden ({_years_needed[0]}–"
                           f"{_years_needed[-1]}) zijn gedekt. Ingestelde jaren: "
                           f"{', '.join(map(str, _cfg))}.")
        else:
            st.info("Nog geen jaartabel ingesteld — alles gebruikt voorlopig de standaardtarieven. "
                    "Sla hieronder een jaar op om de historiek vast te leggen.")

        _yopts = sorted(set(_years_needed) | set(_cfg) | {datetime.now().year + 1})
        wy = st.selectbox("Jaar", _yopts, index=_yopts.index(datetime.now().year),
                          key="wht_year",
                          format_func=lambda y: (f"{y} · eigen tarieven ingesteld" if y in _cfg
                                                 else f"{y} · erft van "
                                                      f"{max([c for c in _cfg if c <= y], default='de standaard')}"))
        rates_now = tax_mod.get_wht_rates(wy)
        wrows = [{"Land": c, "Naam": tax_mod.COUNTRY_NAMES.get(c, c), "Tarief (%)": rates_now[c]}
                 for c in sorted(rates_now.keys())]
        wcg = st.column_config
        wedit = st.data_editor(
            pd.DataFrame(wrows), width="stretch", hide_index=True, key=f"wht_editor_{wy}",
            num_rows="dynamic",
            column_config={
                "Land":       wcg.TextColumn(help="Landcode (2 letters, bv. US)", max_chars=2),
                "Naam":       wcg.TextColumn(disabled=True),
                "Tarief (%)": wcg.NumberColumn(min_value=0.0, max_value=100.0, format="%.10g"),
            })
        wb1, wb2, _ = st.columns([2, 2, 3])
        if wb1.button(f"💾 Tarieven {wy} opslaan", key="save_wht", type="primary"):
            try:
                new_rates = {}
                for _, r in wedit.iterrows():
                    code = str(r["Land"] or "").strip().upper()
                    if len(code) == 2 and code.isalpha() and not pd.isna(r["Tarief (%)"]):
                        new_rates[code] = float(r["Tarief (%)"])
                tax_mod.save_year_rates(wy, new_rates)
                clear_cache()
                st.success(f"✅ {len(new_rates)} tarieven opgeslagen voor **{wy}** (en voor alle "
                           "latere jaren zonder eigen tabel). Bestaande dividenden worden hierdoor "
                           "niet herberekend — gebruik daarvoor de knop op de 💰 Dividenden-pagina.")
            except Exception as exc:
                st.error(f"Kon de tarieven niet opslaan: {exc}")
        if wy in _cfg and wb2.button(f"🗑️ Jaartabel {wy} wissen", key="del_wht_year"):
            tax_mod.delete_year_rates(wy)
            clear_cache()
            st.success(f"Jaartabel {wy} gewist — dat jaar erft nu weer van het vorige jaar.")
            st.rerun()
        with st.expander("📅 Overzicht van de ingestelde jaren"):
            if not _cfg:
                st.caption("Nog geen enkel jaar ingesteld.")
            else:
                _codes = sorted({c for y in _cfg for c in tax_mod._year_rate_table()[y]})
                _ov = [{"Land": c, "Naam": tax_mod.COUNTRY_NAMES.get(c, c),
                        **{str(y): tax_mod.get_wht_rates(y).get(c) for y in _cfg}}
                       for c in _codes]
                show_df(pd.DataFrame(_ov), width="stretch", hide_index=True)
                st.caption("Elk jaar toont het tarief dat er effectief geldt (dus inclusief wat het "
                           "van een vorig jaar erft).")

    if _ssec == "🗃️ Data":
        st.subheader("Databeheer")
        assets = db.get_assets()
        txns   = db.get_transactions()
        divs   = db.get_dividends()
        c1, c2, c3 = st.columns(3)
        c1.metric("Activa", len(assets))
        c2.metric("Transacties", len(txns))
        c3.metric("Dividenden", len(divs))
        st.divider()

        st.subheader("📥 Bulk-import via Excel")
        st.caption("Laad transacties, dividenden en rekeningkosten in bulk op. Download eerst de "
                   "template, vul ze in en upload ze. Onbekende activa worden automatisch aangemaakt "
                   "(vul naam/type/munt in voor een correcte TOB).")
        try:
            st.download_button("⬇️ Download Excel-template", data=bulk.build_template(),
                               file_name="portfolio_import_template.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="dl_template")
        except Exception as exc:
            st.error(f"Kon de template niet genereren: {exc}")

        up = st.file_uploader("Upload ingevulde Excel", type=["xlsx"], key="bulk_upload")
        if up is not None:
            try:
                parsed = bulk.parse_workbook(up)
            except Exception as exc:
                parsed = None
                st.error(f"Kon het bestand niet verwerken: {exc}")
            if parsed is not None:
                n_t = len(parsed["transacties"]); n_d = len(parsed["dividenden"])
                n_k = len(parsed["kosten"]);      n_a = len(parsed["new_assets"])
                pc1, pc2, pc3, pc4 = st.columns(4)
                pc1.metric("Transacties", n_t)
                pc2.metric("Dividenden", n_d)
                pc3.metric("Kosten", n_k)
                pc4.metric("Nieuwe activa", n_a)
                if parsed["errors"]:
                    with st.expander(f"⚠️ {len(parsed['errors'])} rij(en) overgeslagen — bekijk de fouten",
                                     expanded=True):
                        for e in parsed["errors"]:
                            st.write("• " + e)
                if n_a:
                    st.caption("Nieuw aan te maken activa: "
                               + ", ".join(f"{tk} ({i['asset_type']})" for tk, i in parsed["new_assets"].items())
                               + ". Controleer nadien het type/ETF-subtype op de Activa-pagina.")
                total = n_t + n_d + n_k
                if total == 0:
                    st.warning("Geen geldige rijen gevonden om te importeren.")
                elif st.button(f"✅ Importeer {total} rij(en)", type="primary", key="do_bulk_import"):
                    with st.spinner("Importeren..."):
                        summ = bulk.apply_import(parsed)
                        clear_cache()
                    st.success(f"✅ Geïmporteerd: {summ['transacties']} transacties, "
                               f"{summ['dividenden']} dividenden, {summ['kosten']} kosten, "
                               f"{summ['assets']} nieuwe activa aangemaakt.")
                    st.caption("Tip: draai eventueel '💱 Herbereken EUR-bedragen' hieronder als je "
                               "vreemde munten zonder fx_koers importeerde.")
        st.divider()

        if st.button("🔄 Prijzen nu ophalen en opslaan"):
            with st.spinner("Koersen ophalen..."):
                tickers = [a["ticker"] for a in assets]
                prices  = md.get_prices_for_tickers(tickers)
                for ticker, info in prices.items():
                    if info["price"] is not None:
                        db.save_price(ticker, info["price"], info.get("currency", "EUR"))
                clear_cache()
                md._CACHE.clear()
            st.success(f"✅ Koersen opgeslagen voor {len(prices)} ticker(s).")
        st.divider()
        st.subheader("💱 EUR-omrekening")
        st.caption("Reken bestaande transacties en dividenden om naar EUR met de wisselkoers op hun eigen datum. Nodig na de migratie of na het importeren van oude (USD/GBP/…) data.")
        force = st.checkbox("Ook reeds-omgerekende, niet-EUR rijen opnieuw berekenen", value=False)
        if st.button("💱 Herbereken EUR-bedragen"):
            with st.spinner("Historische wisselkoersen ophalen..."):
                n = backfill_eur(force=force)
                clear_cache()
                md._CACHE.clear()
            st.success(f"✅ {n} rij(en) omgerekend naar EUR.")
        st.divider()
        keep = st.number_input("Prijsgeschiedenis bewaren (dagen)", min_value=7,
                                max_value=365, value=90)
        if st.button("🗑️ Oude prijsdata opruimen"):
            db.cleanup_old_prices(keep_days=keep)
            st.success(f"✅ Prijsdata ouder dan {keep} dagen verwijderd.")




# ── PAGINA: Evolutie ──────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _evolution_df(sig: str):
    """Reconstrueer de historische waarde/kostenbasis per rekening (1800s cache)."""
    txns = db.get_transactions()
    assets = db.get_assets()
    if not txns:
        return None
    ticker_currency = {a["ticker"]: a.get("currency", "EUR") for a in assets}
    start = min(t["date"] for t in txns)[:10]
    price_map, fx_map, currencies = {}, {}, set()
    for a in assets:
        s = md.get_price_series(a["ticker"], start)
        if s is not None:
            price_map[a["ticker"]] = s
        currencies.add(a.get("currency", "EUR"))
    for cur in currencies:
        if cur != "EUR":
            fx_map[cur] = md.get_fx_series(cur, start)
    return tax_mod.reconstruct_portfolio_evolution(txns, price_map, fx_map, ticker_currency)


def _koersdoel_historiek_section():
    """Punt 8: evolutie van de koersdoelen per activum (handmatig én AI), met de
    mogelijkheid om het koersdoel opnieuw te bepalen. Toont per activum een tijdlijn
    van wanneer welk koersdoel is vastgelegd of gewijzigd."""
    st.divider()
    st.subheader("🎯 Koersdoel-historiek")

    hist_tickers = db.get_tickers_with_target_history()
    names = asset_name_map()

    if not hist_tickers:
        st.caption("Nog geen koersdoelen vastgelegd. Zodra je een koersdoel instelt "
                   "(handmatig bij een activum/transactie of via een AI-advies), verschijnt "
                   "de evolutie hier per activum.")
        return

    sel = st.selectbox("Activum", hist_tickers,
                       format_func=lambda t: f"{names.get(t, t)} ({t})",
                       key="pt_hist_ticker")
    hist = db.get_price_target_history(sel)   # chronologisch (oudste eerst)
    if not hist:
        st.caption("Geen koersdoelen voor dit activum.")
        return

    SRC_LBL = {"manual": "✍️ Handmatig", "ai": "🤖 AI"}

    # ── Tabel: nieuwste eerst, met wijziging t.o.v. het vorige koersdoel ──────
    rows = []
    for i, h in enumerate(hist):
        prev = hist[i - 1]["target"] if i > 0 else None
        delta = (h["target"] - prev) if prev is not None else None
        note = h.get("note")
        label = SRC_LBL.get(h["source"], h["source"])
        if h["source"] == "ai" and note:
            label += f" ({note})"
        elif note and note != "huidig koersdoel (migratie)":
            label += f" · {note}"
        rows.append({
            "Vastgelegd op": _short_ts(h["set_at"]),
            "Koersdoel":     h["target"],
            "Munt":          h["currency"],
            "Δ t.o.v. vorige": delta,
            "Bron":          label,
        })
    rows.reverse()   # nieuwste bovenaan
    show_df(pd.DataFrame(rows), width="stretch", hide_index=True, column_config={
        "Koersdoel":       st.column_config.NumberColumn(format="%.10g"),
        "Δ t.o.v. vorige": st.column_config.NumberColumn(format="%+.10g"),
    })

    # ── Grafiek: koersdoel-evolutie (trapjeslijn) + werkelijke koers ─────────
    try:
        xs = [datetime.strptime(str(h["set_at"])[:19], "%Y-%m-%d %H:%M:%S") for h in hist]
    except (ValueError, TypeError):
        xs = None
    if xs and len(xs) >= 1:
        fig = go.Figure()
        # Werkelijke koers als achtergrond (native munt), indien beschikbaar.
        try:
            start = min(xs).strftime("%Y-%m-%d")
            series = md.get_price_series(sel, start)
            if series is not None and len(series):
                fig.add_trace(go.Scatter(
                    x=list(series.index), y=list(series.values), mode="lines",
                    name="Koers", line=dict(color="rgba(160,160,160,0.55)", width=1.5)))
        except Exception:
            pass
        # Koersdoel als trapjeslijn tot vandaag doorgetrokken.
        tx = xs + [datetime.now()]
        ty = [h["target"] for h in hist] + [hist[-1]["target"]]
        fig.add_trace(go.Scatter(
            x=tx, y=ty, mode="lines", name="Koersdoel",
            line=dict(color="#fdcb6e", width=2, shape="hv")))
        # Markers per bron (kleur = handmatig vs AI).
        for src, col, nm in (("manual", "#0984e3", "Handmatig"), ("ai", "#00b894", "AI")):
            pts = [(x, h["target"]) for x, h in zip(xs, hist) if h["source"] == src]
            if pts:
                fig.add_trace(go.Scatter(
                    x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers",
                    name=nm, marker=dict(color=col, size=9,
                                         line=dict(color="white", width=1))))
        fig.update_layout(height=320, margin=dict(t=30, b=30, l=20, r=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", yanchor="bottom", y=1.0,
                                      xanchor="right", x=1.0),
                          title=f"Koersdoel-evolutie — {names.get(sel, sel)} ({hist[-1]['currency']})")
        st.plotly_chart(fig, width="stretch")

    st.caption("De trapjeslijn toont het geldende koersdoel over de tijd; elk bolletje is een "
               "moment waarop een koersdoel werd vastgelegd of gewijzigd (blauw = handmatig, "
               "groen = AI). De grijze lijn is de werkelijke koers, indien beschikbaar.")

    # ── Koersdoel opnieuw bepalen (handmatig) ────────────────────────────────
    with st.expander("🎯 Koersdoel opnieuw bepalen"):
        _cur_default = hist[-1]["currency"] or "EUR"
        hc1, hc2, hc3 = st.columns([2, 1, 1])
        new_tgt = hc1.number_input(f"Nieuw koersdoel ({_cur_default})", min_value=0.0,
                                   step=0.01, value=float(hist[-1]["target"]),
                                   key=f"pt_new_{sel}")
        new_cur = hc2.text_input("Munt", value=_cur_default, key=f"pt_cur_{sel}").strip().upper()
        hc3.markdown("&nbsp;")
        if hc3.button("Vastleggen", key=f"pt_set_{sel}", type="primary"):
            if new_tgt and new_tgt > 0:
                db.update_asset(sel, price_target=float(new_tgt),
                                price_target_currency=(new_cur or _cur_default))
                clear_cache()
                st.success(f"🎯 Nieuw koersdoel {num(new_tgt, 2)} {new_cur or _cur_default} "
                           f"vastgelegd voor {names.get(sel, sel)}.")
                st.rerun()
            else:
                st.warning("Geef een koersdoel groter dan 0 in.")
        st.caption("Het nieuwe koersdoel wordt het actieve doel op het activum én komt als "
                   "handmatige wijziging in de historiek hierboven.")


def page_evolution():
    st.title("📈 Waarde-evolutie & vergelijking per rekening")

    txns = db.get_transactions()
    if not txns:
        st.info("Nog geen transacties. Voeg ze toe via ➕ Transacties.")
        return

    sig = f"{len(txns)}:{max(t['id'] for t in txns)}:{min(t['date'] for t in txns)[:10]}"
    with st.spinner("Historische koersen ophalen en portefeuille reconstrueren..."):
        df = _evolution_df(sig)

    if df is None or df.empty:
        st.warning("Kon geen historische reeks opbouwen — koersdata (yfinance) niet beschikbaar voor deze tickers.")
        _koersdoel_historiek_section()
        return

    acct_cols = sorted(c[len("value::"):] for c in df.columns
                       if c.startswith("value::") and c != "value::TOTAL")

    cfg1, cfg2 = st.columns([3, 2])
    with cfg1:
        sel = st.multiselect("Rekeningen", acct_cols, default=acct_cols)
    with cfg2:
        months = st.select_slider("Periode", options=[1, 3, 6, 12, 24, 60], value=12,
                                  format_func=lambda m: f"{m} mnd" if m < 24 else f"{m//12} jaar")
    if not sel:
        st.info("Selecteer minstens één rekening.")
        return

    cutoff = df.index.max() - pd.Timedelta(days=30 * months)
    d = df[df.index >= cutoff]

    # ── Grafiek 1: absolute waarde-evolutie (EUR) ─────────────────────────────
    st.subheader("💼 Waarde-evolutie (EUR)")
    fig_val = go.Figure()
    palette = ["#74b9ff", "#00b894", "#fdcb6e", "#e17055", "#a29bfe", "#fd79a8"]
    for i, acct in enumerate(sel):
        col = f"value::{acct}"
        if col in d:
            fig_val.add_trace(go.Scatter(
                x=d.index, y=d[col], mode="lines", name=acct,
                line=dict(width=2, color=palette[i % len(palette)]),
            ))
    if len(sel) > 1:
        cols = [f"value::{a}" for a in sel if f"value::{a}" in d]
        tot = d[cols].sum(axis=1)
        fig_val.add_trace(go.Scatter(x=d.index, y=tot, mode="lines", name="Totaal (selectie)",
                                     line=dict(width=3, color="#ffffff", dash="dot")))
    fig_val.update_layout(height=360, margin=dict(t=20, b=30, l=20, r=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", y=-0.15), hovermode="x unified")
    fig_val.update_yaxes(tickprefix="€")
    st.plotly_chart(fig_val, width='stretch')

    # ── Grafiek 2: procentuele meer-/minwaarde t.o.v. aankoopprijs ────────────
    st.subheader("📊 Procentuele meer-/minwaarde t.o.v. aankoopprijs")
    st.caption("Per rekening: (huidige waarde − kostenbasis) / kostenbasis. Toont het rendement op het belegde geld, niet het absolute bedrag.")
    fig_pct = go.Figure()
    for i, acct in enumerate(sel):
        vcol, ccol = f"value::{acct}", f"cost::{acct}"
        if vcol in d and ccol in d:
            pct_series = (d[vcol] - d[ccol]) / d[ccol].replace(0, float("nan")) * 100
            fig_pct.add_trace(go.Scatter(
                x=d.index, y=pct_series, mode="lines", name=acct,
                line=dict(width=2, color=palette[i % len(palette)]),
            ))
    fig_pct.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.4)")
    fig_pct.update_layout(height=360, margin=dict(t=20, b=30, l=20, r=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", y=-0.15), hovermode="x unified")
    fig_pct.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig_pct, width='stretch')

    # ── Huidige momentopname per rekening ─────────────────────────────────────
    st.divider()
    st.subheader("📌 Huidige stand per rekening")
    assets = db.get_assets()
    prices = md.get_prices_for_tickers([a["ticker"] for a in assets])
    summ = tax_mod.account_summary(db.get_transactions(), prices)
    rows = []
    for acct in sorted(summ):
        s = summ[acct]
        rows.append({
            "Rekening":       acct,
            "Posities":       s["n_positions"],
            "Kostenbasis":    s["cost_basis"],
            "Huidige waarde": s["current_value"],
            "W/V (€)":        s["gain_loss"],
            "W/V (%)":        s["gain_loss_pct"],
        })
    if rows:
        show_df(pd.DataFrame(rows), width='stretch', hide_index=True, column_config={
            "Kostenbasis":    st.column_config.NumberColumn(format="€ %.10g"),
            "Huidige waarde": st.column_config.NumberColumn(format="€ %.10g"),
            "W/V (€)":        st.column_config.NumberColumn(format="€ %.10g"),
            "W/V (%)":        st.column_config.NumberColumn(format="%+.10g%%"),
        })
        fig_cmp = go.Figure(go.Bar(
            x=[r["Rekening"] for r in rows],
            y=[summ[r["Rekening"]]["gain_loss_pct"] for r in rows],
            marker_color=["#00b894" if summ[r["Rekening"]]["gain_loss_pct"] >= 0 else "#d63031" for r in rows],
            text=[pct(summ[r["Rekening"]]["gain_loss_pct"]) for r in rows],
            textposition="outside",
        ))
        fig_cmp.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.3)")
        fig_cmp.update_layout(title="Rendement per rekening (%)", height=300,
                              margin=dict(t=40, b=30, l=20, r=20), showlegend=False,
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig_cmp.update_yaxes(ticksuffix="%")
        st.plotly_chart(fig_cmp, width='stretch')

    _koersdoel_historiek_section()


# ── Navigatie ─────────────────────────────────────────────────────────────────

# ── PAGINA: Cash-grootboek ────────────────────────────────────────────────────

def page_cash():
    st.title("💶 Cash")
    st.caption("Volwaardig cash-grootboek per rekening. **Beschikbare cash** = stortingen − opnames "
               "+ verkopen − aankopen + dividenden − rekeningkosten. Toekenningen (performance shares) "
               "kosten geen brokergeld en tellen hier voor €0.")

    _csec = _section_radio("cash_section", ["📊 Posities", "➕ Storting / opname", "📜 Bewegingen"])

    if _csec == "📊 Posities":
        pos = db.compute_cash_positions()
        per, tot = pos["per_account"], pos["totals"]
        c1, c2, c3 = st.columns(3)
        c1.metric("💰 Totaal gestort (cash in)", eur(tot["deposits"]))
        c2.metric("🏧 Totaal opgenomen (cash out)", eur(tot["withdrawals"]))
        c3.metric("🟢 Beschikbare cash", eur(tot["available"]),
                  help="Cash die je nu beschikbaar hebt om aandelen mee te kopen (over alle rekeningen).")
        if not per:
            st.info("Nog geen cashbewegingen. Begin met een storting via '➕ Storting / opname'.")
        else:
            rows = []
            for a, r in sorted(per.items()):
                rows.append({
                    "Rekening":       a,
                    "Stortingen":     r["deposits"],
                    "Opnames":        -r["withdrawals"],
                    "Aankopen":       -r["buys"],
                    "Verkopen":       r["sells"],
                    "Dividenden":     r["dividends"],
                    "Rekeningkosten": -r["costs"],
                    "Beschikbaar":    r["available"],
                })
            _money_cfg = {c: st.column_config.NumberColumn(format="€ %.10g") for c in
                         ("Stortingen", "Opnames", "Aankopen", "Verkopen",
                          "Dividenden", "Rekeningkosten", "Beschikbaar")}
            show_df(pd.DataFrame(rows), width="stretch", hide_index=True, column_config=_money_cfg)
            st.caption("Aankopen en rekeningkosten verlagen de cash (−); verkopen en dividenden verhogen ze (+). "
                       "Een negatieve beschikbare cash betekent dat er meer is uitgegeven dan gestort — "
                       "registreer dan je ontbrekende stortingen. Betaalde je de personenbelasting op "
                       "performance shares vanaf je beleggingsrekening, boek die dan als een opname.")

    if _csec == "➕ Storting / opname":
        accts = db.get_accounts()
        if not accts:
            st.warning("Maak eerst een rekening aan via ⚙️ Instellingen.")
        else:
            with st.form("cash_form", clear_on_submit=True):
                cc1, cc2, cc3 = st.columns(3)
                cm_acct = cc1.selectbox("Rekening", accts)
                cm_type = cc2.selectbox("Type", ["Storting (cash in)", "Opname (cash out)"])
                cm_date = cc3.date_input("Datum", value=date.today(),
                                         min_value=date(2000, 1, 1), max_value=date.today())
                cc4, cc5 = st.columns(2)
                cm_amt = cc4.number_input("Bedrag", min_value=0.0, step=0.01, format="%.10g", value=None)
                cm_cur = cc5.selectbox("Munt", ["EUR", "USD", "GBP", "CHF"])
                cm_note = st.text_input("Notitie (optioneel)",
                                        placeholder="bv. startkapitaal, winstopname, bijstorting")
                if st.form_submit_button("✅ Toevoegen", type="primary"):
                    if not cm_amt or cm_amt <= 0:
                        st.error("Vul een bedrag groter dan 0 in.")
                    else:
                        fx, eur_amt = compute_eur(cm_amt, cm_cur, cm_date)
                        mtype = "deposit" if cm_type.startswith("Storting") else "withdrawal"
                        db.add_cash_movement(cm_acct, str(cm_date), mtype, cm_amt, cm_cur,
                                             fx, eur_amt, cm_note or None)
                        clear_cache()
                        st.success(f"✅ {cm_type.split(' ')[0]} van {cm_cur} {cm_amt:,.2f} "
                                   f"op {cm_acct} toegevoegd!")
                        st.rerun()
        st.info("💡 Aankopen, verkopen, dividenden en rekeningkosten hoef je hier **niet** in te geven — "
                "die worden automatisch uit je transacties, dividenden en kosten afgeleid. Registreer hier "
                "enkel echte geldstortingen en -opnames.")

    if _csec == "📜 Bewegingen":
        laccts = db.get_accounts()
        lsel = st.multiselect("Rekeningen", laccts, default=[], key="cash_log_acct",
                              placeholder="Alle rekeningen")
        ledger = db.cash_ledger(tuple(lsel) if lsel else None)
        if not ledger:
            st.info("Nog geen cashbewegingen. Voeg een storting toe of registreer transacties.")
        else:
            lbl = {"Storting": "🟢 Storting", "Opname": "🔴 Opname", "Aankoop": "🔻 Aankoop",
                   "Verkoop": "🔺 Verkoop", "Dividend": "💰 Dividend",
                   "Interest": "🏦 Interest", "Securities lending": "🔁 Securities lending",
                   "Rekeningkost": "🧾 Rekeningkost", "Toekenning": "🎁 Toekenning"}
            rows = [{
                "Datum":    it["date"],
                "Rekening": it["account"],
                "Type":     lbl.get(it["label"], it["label"]),
                "Omschrijving": it["desc"],
                "Mutatie":  it["delta"],
                "Saldo":    it["balance"],
            } for it in reversed(ledger)]   # nieuwste bovenaan
            show_df(pd.DataFrame(rows), width="stretch", hide_index=True, column_config={
                "Mutatie": st.column_config.NumberColumn(format="€ %.10g"),
                "Saldo":   st.column_config.NumberColumn(format="€ %.10g"),
            })
            st.caption("Volledig grootboek: stortingen/opnames samen met de automatisch afgeleide "
                       "bewegingen uit aankopen (−), verkopen (+), dividenden (+) en rekeningkosten (−). "
                       "'Saldo' is het lopende cashsaldo per rekening. Toekenningen (performance shares) "
                       "staan als €0 (geen cash).")

            # Enkel handmatige bewegingen kunnen verwijderd worden
            manual = [it for it in ledger if it["source"] == "manual"]
            if manual:
                st.divider()
                opts = {it["ref"]: f"#{it['ref']} · {it['date']} · {it['account']} · {it['label']} · {eur(it['delta'])}"
                        for it in reversed(manual)}
                multiselect_delete("confirm_del_cash", opts,
                                   lambda i: db.delete_cash_movement(i),
                                   noun="storting/opname")


def page_simulation():
    st.title("🧮 Simulatie meerwaardebelasting")
    st.caption("Schat vooraf in hoe de Belgische meerwaardebelasting uitdraait wanneer je posities "
               "(geheel of gedeeltelijk) verkoopt en eventueel meteen terug aankoopt. De belasting is "
               "globaal per persoon; de jaarlijkse vrijstelling, de opbouw en het fotomoment (slotkoers "
               "31/12/2025) worden mee verrekend. Er wordt niets opgeslagen of uitgevoerd.")

    assets = db.get_assets()
    if not assets:
        st.info("Nog geen activa om te simuleren.")
        return
    a_info    = {a["ticker"]: a for a in assets}
    a_names   = {a["ticker"]: (a.get("name") or a["ticker"]) for a in assets}
    snapshots = {a["ticker"]: a["snapshot_price_eur"] for a in assets
                 if a.get("snapshot_price_eur") is not None}
    tickers   = [a["ticker"] for a in assets]
    prices    = md.get_prices_for_tickers(tickers)

    pos_by_key, _, _ = tax_mod._fifo_core(db.get_transactions(), snapshots)
    held = {k: v for k, v in pos_by_key.items() if v["total_quantity"] > 1e-9}
    if not held:
        st.info("Geen open posities om te simuleren.")
        return

    sim_date = st.date_input("Simulatiedatum", value=date.today(),
                             min_value=date(2000, 1, 1), max_value=date(2035, 12, 31),
                             help="Datum van de hypothetische verkopen/heraankopen. Bepaalt het boekjaar "
                                  "en de fotomoment-behandeling.")

    rows, keys = [], []
    for (tk, acct), pos in sorted(held.items()):
        qty    = pos["total_quantity"]
        avg    = pos["total_cost"] / qty if qty else 0.0
        pinfo  = prices.get(tk, {})
        native = pinfo.get("price")
        cur    = pinfo.get("currency") or a_info.get(tk, {}).get("currency", "EUR")
        keys.append((tk, acct, cur))
        rows.append({
            "Activum":            a_names.get(tk, tk),
            "Rekening":           acct,
            "Aantal":             round(qty, 4),
            "Gem. kostprijs (€)": round(avg, 2),
            "Huidige koers":      round(native, 4) if native is not None else 0.0,
            "Munt":               cur,
            "Verkoop aantal":     0.0,
            "Verkoopprijs":       round(native, 4) if native is not None else 0.0,
            "Heraankoop aantal":  0.0,
            "Heraankoopprijs":    round(native, 4) if native is not None else 0.0,
        })
    df = pd.DataFrame(rows)
    cc = st.column_config
    edited = st.data_editor(
        df, width="stretch", hide_index=True, key="sim_editor",
        column_config={
            "Activum":            cc.TextColumn(disabled=True),
            "Rekening":           cc.TextColumn(disabled=True),
            "Aantal":             cc.NumberColumn(disabled=True, format="%.10g"),
            "Gem. kostprijs (€)": cc.NumberColumn(disabled=True, format="%.10g"),
            "Huidige koers":      cc.NumberColumn(disabled=True, format="%.10g"),
            "Munt":               cc.TextColumn(disabled=True),
            "Verkoop aantal":     cc.NumberColumn(min_value=0.0, step=1.0, format="%.10g"),
            "Verkoopprijs":       cc.NumberColumn(min_value=0.0, step=0.01, format="%.10g"),
            "Heraankoop aantal":  cc.NumberColumn(min_value=0.0, step=1.0, format="%.10g"),
            "Heraankoopprijs":    cc.NumberColumn(min_value=0.0, step=0.01, format="%.10g"),
        })
    st.caption("Vul 'Verkoop aantal' in (geheel of gedeeltelijk). Optioneel: 'Heraankoop aantal' om "
               "meteen terug te kopen (bv. om de kostbasis te resetten of voor tax-loss harvesting). "
               "Prijzen staan standaard op de huidige koers; pas ze aan voor een scenario.")

    if st.button("🧮 Bereken simulatie", type="primary", key="run_sim"):
        extra, warnings = [], []
        sells_eur = buys_eur = tob_total = 0.0
        n_sell = n_buy = 0
        for i, (tk, acct, cur) in enumerate(keys):
            r        = edited.iloc[i]
            held_qty = float(df.iloc[i]["Aantal"])
            sqty     = float(r["Verkoop aantal"] or 0)
            sprice   = float(r["Verkoopprijs"] or 0)
            bqty     = float(r["Heraankoop aantal"] or 0)
            bprice   = float(r["Heraankoopprijs"] or 0)
            info     = a_info.get(tk, {})
            if sqty > 0:
                if sqty > held_qty + 1e-9:
                    warnings.append(f"{a_names.get(tk, tk)}: verkoop {sqty:g} > beschikbaar {held_qty:g} — afgekapt.")
                    sqty = held_qty
                fx, eur_amt = compute_eur(sprice * sqty, cur, str(sim_date))
                tob = tax_mod.calculate_tob(info.get("asset_type", "stock"),
                                            info.get("etf_subtype", "distributing"), eur_amt,
                                            bool(info.get("belgian_registered", 1)), txn_date=sim_date)
                extra.append({"ticker": tk, "account": acct, "transaction_type": "sell",
                              "date": f"{sim_date} 10:00:00", "quantity": sqty, "price_per_unit": sprice,
                              "total_amount": sprice * sqty, "currency": cur, "fx_rate": fx,
                              "total_amount_eur": eur_amt, "costs_eur": 0.0, "tob_tax": tob})
                sells_eur += eur_amt; tob_total += tob; n_sell += 1
            if bqty > 0:
                fx2, eur2 = compute_eur(bprice * bqty, cur, str(sim_date))
                tob2 = tax_mod.calculate_tob(info.get("asset_type", "stock"),
                                             info.get("etf_subtype", "distributing"), eur2,
                                             bool(info.get("belgian_registered", 1)), txn_date=sim_date)
                extra.append({"ticker": tk, "account": acct, "transaction_type": "buy",
                              "date": f"{sim_date} 11:00:00", "quantity": bqty, "price_per_unit": bprice,
                              "total_amount": bprice * bqty, "currency": cur, "fx_rate": fx2,
                              "total_amount_eur": eur2, "costs_eur": 0.0, "tob_tax": tob2})
                buys_eur += eur2; tob_total += tob2; n_buy += 1

        if not extra:
            st.warning("Vul minstens één 'Verkoop aantal' of 'Heraankoop aantal' in.")
            return
        for w in warnings:
            st.warning("⚠️ " + w)

        year    = sim_date.year
        ov_base = tax_mod.calculate_tax_overview(year, prices)
        ov_sim  = tax_mod.calculate_tax_overview(year, prices, extra_transactions=extra)

        d_real    = ov_sim["total_realized_gl"]  - ov_base["total_realized_gl"]
        d_tax     = ov_sim["tax_due"]            - ov_base["tax_due"]
        net       = sells_eur - buys_eur - d_tax - tob_total

        st.divider()
        st.subheader("📊 Resultaat van de simulatie")
        m1, m2, m3 = st.columns(3)
        m1.metric("Gerealiseerde meerwaarde", eur(d_real),
                  help="Economische meer-/minwaarde van de gesimuleerde verkopen (kostbasis via FIFO).")
        m2.metric("Extra meerwaardebelasting", eur(d_tax),
                  help="Toename van de meerwaardebelasting dit boekjaar door de simulatie (10% boven de vrijstelling).")
        m3.metric("TOB (verkopen + heraankopen)", eur(tob_total))
        m4, m5, m6 = st.columns(3)
        m4.metric("Verkoopopbrengst (bruto)", eur(sells_eur))
        m5.metric("Heraankoopkost", eur(buys_eur))
        m6.metric("Netto na belasting + TOB", eur(net), delta_color=delta_color(net))

        st.caption(
            f"**Boekjaar {year}** · jaarlijkse vrijstelling {eur(ov_sim['annual_exemption'])}.  "
            f"Belastbare basis (fiscaal): {eur(ov_base['total_taxable_gl'])} → **{eur(ov_sim['total_taxable_gl'])}**.  "
            f"Belast deel na vrijstelling: {eur(ov_base['taxable_amount'])} → **{eur(ov_sim['taxable_amount'])}**.  "
            f"Totale meerwaardebelasting dit jaar: {eur(ov_base['tax_due'])} → **{eur(ov_sim['tax_due'])}**.")
        if ov_sim.get("fotomoment_applied"):
            st.caption("ℹ️ Voor loten gekocht vóór 2026 is het fotomoment (slotkoers 31/12/2025) toegepast "
                       "op de belastbare basis — winst van vóór 2026 blijft buiten schot.")
        st.info(f"{n_sell} verkoop/verkopen en {n_buy} heraankoop/heraankopen gesimuleerd. "
                "Dit is een schatting — er wordt niets opgeslagen of uitgevoerd. Bij een heraankoop "
                "wordt de kostbasis voor toekomstige meerwaarden de heraankoopprijs.")


def page_status():
    st.title("🩺 Status & waarschuwingen")
    st.caption("De gezondheid van je koersdata op één plek: verouderde koersen, dagen zonder "
               "koersbeweging, tickerwijzigingen of meerdere producten onder één ISIN, "
               "niet-geregistreerde aandelensplits en naamsafwijkingen (mogelijke fusie of "
               "rebranding).")

    last = db.get_setting("status_last_run")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🔄 Nu controleren", type="primary", width="stretch"):
            with st.spinner("Statuscontrole uitvoeren (koersdata + online bronnen)..."):
                summary = db.run_status_checks(online=True)
            st.session_state["status_last_summary"] = summary
            clear_cache()
            st.rerun()
    with c2:
        if last:
            st.caption(f"Laatste controle: {_short_ts(last)} · draait ook automatisch elke dag "
                       "om 22:45.")
        else:
            st.caption("Nog geen automatische controle uitgevoerd — klik op 'Nu controleren' of "
                       "wacht op de dagelijkse run (22:45).")

    summ = st.session_state.get("status_last_summary")
    if summ:
        st.info(f"Laatste run: {summ.get('checked', 0)} activa gecontroleerd · "
                f"{summ.get('new', 0)} nieuw · {summ.get('resolved', 0)} opgelost · "
                f"{summ.get('open', 0)} open"
                + (f" · {summ['errors']} netwerkfout(en)" if summ.get('errors') else "")
                + ("" if summ.get("online") else " · (offline: enkel koersdata-checks)"))

    events = db.get_status_events()
    if not events:
        st.success("✅ Geen openstaande waarschuwingen. Je koersdata ziet er gezond uit.")
        st.caption("Tip: staat een US-aandeel op 0% dagwinst, kijk dan op het Dashboard naar de "
                   "kolom 'Laatste update'. Is die recent, dan is 0% normaal (markt gesloten); "
                   "staat ze dagen terug, dan verschijnt hier een waarschuwing 'Verouderde koers'.")
        return

    names = asset_name_map()
    SEV = {"error": "🔴", "warning": "🟠", "info": "🔵"}
    KIND = {"stale_price": "Verouderde koers", "flat_price": "Geen koersbeweging",
            "ticker_change": "Tickerwijziging", "split": "Aandelensplit",
            "name_change": "Naamsafwijking"}

    n_warn = sum(1 for e in events if e["severity"] in ("warning", "error"))
    n_info = sum(1 for e in events if e["severity"] == "info")
    st.markdown(f"**{len(events)} openstaande waarschuwing(en)** — {n_warn} ter opvolging, "
                f"{n_info} informatief.")
    st.divider()

    for e in events:
        icon = SEV.get(e["severity"], "⚪")
        nm = names.get(e["ticker"], e["ticker"])
        d = e.get("detail") or {}
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                ack = " · ✓ gezien" if e.get("acknowledged") else ""
                st.markdown(f"{icon} **{nm}** ({e['ticker']}) · *{KIND.get(e['kind'], e['kind'])}*{ack}")
                st.write(e["message"])
                meta = f"Sinds {_short_ts(e['detected_at'])}"
                if e.get("isin"):
                    meta += f" · ISIN {e['isin']}"
                if e["kind"] == "ticker_change" and d.get("candidates"):
                    meta += f" · kandidaten: {', '.join(d['candidates'])}"
                if e["kind"] == "name_change" and d.get("yahoo"):
                    meta += f" · bron: '{d['yahoo']}'"
                if e["kind"] == "ticker_change" and d.get("new"):
                    meta += " · 'Gevonden ticker' is automatisch bijgewerkt"
                st.caption(meta)
            with right:
                if e["kind"] == "split" and d.get("splits"):
                    if st.button("Split registreren", key=f"sp_{e['id']}", width="stretch"):
                        for d_, r_ in d["splits"]:
                            db.add_split(e["ticker"], d_, float(r_))
                        db.resolve_status_event_by_id(e["id"])
                        clear_cache()
                        st.rerun()
                if not e.get("acknowledged"):
                    if st.button("✓ Gezien", key=f"ack_{e['id']}", width="stretch"):
                        db.acknowledge_status_event(e["id"])
                        st.rerun()
                if st.button("Sluiten", key=f"cl_{e['id']}", width="stretch"):
                    db.resolve_status_event_by_id(e["id"])
                    st.rerun()

    st.caption("'Sluiten' verbergt een waarschuwing; blijft de toestand bestaan, dan verschijnt "
               "ze bij de volgende controle opnieuw. Een aandelensplit wordt NIET automatisch "
               "toegepast — pas na 'Split registreren' worden je transacties en kostbasis "
               "aangepast (FIFO). Een gedetecteerde tickerwijziging werkt de kolom 'Gevonden "
               "ticker' meteen bij en selecteert voortaan het actieve symbool.")


PAGES = {
    "📊 Dashboard":            page_dashboard,
    "💼 Portefeuille":         page_portfolio,
    "💶 Cash":                 page_cash,
    "📈 Evolutie":             page_evolution,
    "🏢 Activa":               page_assets,
    "➕ Transacties":          page_transactions,
    "💰 Dividenden":           page_dividends,
    "🧮 Simulatie":            page_simulation,
    "🧾 Belgische Belasting":  page_tax,
    "🤖 AI Advisor":           page_ai_advisor,
    "🩺 Status":               page_status,
    "⚙️ Instellingen":         page_settings,
}

with st.sidebar:
    st.title("📈 Portfolio Tracker")
    st.caption("Belgische belegger 🇧🇪")

    # Programmatische paginawissel (bv. via knop): toepassen VÓÓR de radio bestaat,
    # anders werpt Streamlit een fout (widgetstate na instantiatie wijzigen).
    if st.session_state.get("nav_goto") in PAGES:
        st.session_state["nav_menu"] = st.session_state.pop("nav_goto")
    selected = st.radio("Menu", list(PAGES.keys()), label_visibility="collapsed", key="nav_menu")

    st.divider()
    # Snelle stats
    try:
        assets = db.get_assets()
        if assets:
            tickers = [a["ticker"] for a in assets]
            prices  = md.get_prices_for_tickers(tickers)
            all_txns = db.get_transactions()
            positions, _ = tax_mod.build_fifo_positions(all_txns)
            pos_vals = tax_mod.get_position_values(positions, prices)
            total_v = sum(p["current_value"] for p in pos_vals.values() if p["current_value"])
            total_c = sum(p["total_cost"]    for p in pos_vals.values())
            gl = total_v - total_c
            icon = "🟢" if gl >= 0 else "🔴"
            st.metric("💼 Waarde", eur(total_v))
            st.caption(f"{icon} {eur(gl)} ({pct(gl/total_c*100 if total_c else 0)})")
    except Exception:
        pass

    try:
        _ai = db.get_ai_usage_summary()
        st.metric("🤖 AI-kosten totaal", f"${_ai['total_cost_usd']:,.2f}",
                  help=f"Deze maand: ${_ai['month_cost_usd']:,.2f} · {_ai['total_calls']} oproepen. "
                       "Details op de AI Advisor-pagina.")
    except Exception:
        pass

    st.divider()
    now = datetime.now()
    st.caption(f"📅 {now.strftime('%d/%m/%Y %H:%M')}")
    st.caption("⏱️ Koersen: elke 5 min")
    st.caption("🤖 AI: 1× per werkdag (18:00) + belastingadvies maandelijks")

PAGES[selected]()