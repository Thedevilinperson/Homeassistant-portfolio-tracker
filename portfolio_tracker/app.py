"""
app.py — Portfolio Tracker — Streamlit hoofdapplicatie
Belgische beleggingsportefeuille met belastingtracking en AI-advies.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime

import streamlit as st

import belgian_tax as tax_mod
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

# ── Pagina's ──────────────────────────────────────────────────────────────────
# Elke pagina is een eigen module in views/. De gedeelde bouwstenen (opmaak, de
# gecachete portefeuilleweergave, blijvende filters, herberekeningen) staan in
# views/common.py. Dit bestand doet nog maar drie dingen: de app opzetten, de
# zijbalk tekenen en de gekozen pagina aanroepen.
#
# De map heet bewust 'views' en niet 'pages': Streamlit bouwt uit een map met de
# naam 'pages' automatisch een eigen navigatiemenu, wat botst met de zijbalk
# hieronder.
from views.common import eur, pct                      # noqa: E402  (na set_page_config)
from views import (                                    # noqa: E402
    ai, assets, cash, dashboard, dividends, docs, evolution, portfolio,
    settings, simulation, status, tax, transactions,
)

PAGES = {
    "📊 Dashboard":            dashboard.page_dashboard,
    "💼 Portefeuille":         portfolio.page_portfolio,
    "💶 Cash":                 cash.page_cash,
    "📈 Evolutie":             evolution.page_evolution,
    "🏢 Activa":               assets.page_assets,
    "➕ Transacties":          transactions.page_transactions,
    "💰 Dividenden":           dividends.page_dividends,
    "🧮 Simulatie":            simulation.page_simulation,
    "🧾 Belgische Belasting":  tax.page_tax,
    "🤖 AI Advisor":           ai.page_ai_advisor,
    "🩺 Status":               status.page_status,
    "⚙️ Instellingen":         settings.page_settings,
    "📖 Handleiding":          docs.page_docs,
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
