"""
app.py — Portfolio Tracker — Streamlit hoofdapplicatie
Belgische beleggingsportefeuille met belastingtracking en AI-advies.
"""
from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import ai_advisor
import belgian_tax as tax_mod
import database as db
import market_data as md

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
db.init_db()

# ── Hulpfuncties ──────────────────────────────────────────────────────────────

def eur(val: float | None, decimals: int = 2) -> str:
    if val is None:
        return "—"
    return f"€{val:,.{decimals}f}"


def pct(val: float | None) -> str:
    if val is None:
        return "—"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def sign_icon(val: float | None) -> str:
    if val is None:
        return "⚪"
    return "🟢" if val >= 0 else "🔴"


def delta_color(val: float | None) -> str:
    if val is None or val == 0:
        return "off"
    return "normal" if val >= 0 else "inverse"


@st.cache_data(ttl=60, show_spinner=False)
def get_overview(year: int, account: str | None = None) -> dict:
    """Gecachte portfolioverzicht (60 s TTL). account=None -> alle rekeningen."""
    assets = db.get_assets()
    tickers = [a["ticker"] for a in assets]
    prices = md.get_prices_for_tickers(tickers)
    overview = tax_mod.calculate_tax_overview(year=year, current_prices=prices,
                                              account=account)
    return overview, assets, prices


def clear_cache():
    get_overview.clear()


def compute_eur(amount: float, currency: str, date_str: str) -> tuple[float, float]:
    """(fx_rate, eur_bedrag) op transactiedatum. Valt terug op 1.0 bij EUR/fout."""
    if not amount or currency == "EUR":
        return 1.0, float(amount or 0.0)
    rate = md.get_historical_exchange_rate(currency, str(date_str), "EUR") or 1.0
    return rate, float(amount) * rate


def account_filter_widget(key: str) -> str | None:
    """Dropdown 'Alle rekeningen' + gedefinieerde rekeningen. None = alle."""
    opts = ["📂 Alle rekeningen"] + db.get_accounts()
    sel = st.selectbox("Rekening", opts, key=key)
    return None if sel.startswith("📂") else sel


def backfill_eur(force: bool = False) -> int:
    """Reken bestaande transacties + dividenden om naar EUR (historische koers)."""
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
        fx, gross_eur = compute_eur(d["gross_amount"], d["currency"], d["date"])
        _, wh_eur     = compute_eur(d["withholding_tax"], d["currency"], d["date"])
        db.set_dividend_eur(d["id"], fx, gross_eur, wh_eur)
        n += 1
    return n


# ── PAGINA: Dashboard ─────────────────────────────────────────────────────────

def page_dashboard():
    st.title("📊 Dashboard")

    fc1, fc2 = st.columns([1, 4])
    with fc1:
        acct = account_filter_widget("dash_acct")
    if acct:
        st.caption(f"📂 Gefilterd op rekening: **{acct}** — belastingcijfers blijven globaal (vrijstelling geldt per persoon).")

    year = datetime.now().year
    overview, assets, prices = get_overview(year, acct)
    pv = overview["position_values"]

    if not pv:
        st.info("👋 Welkom! Voeg activa toe via **🏢 Activa** en daarna transacties via **➕ Transacties**.")
        return

    total_val  = overview["total_portfolio_value"]
    total_cost = overview["total_cost_basis"]
    unreal_gl  = overview["unrealized_gl"]
    real_gl    = overview["total_realized_gl"]
    tax_due    = overview["tax_due"]
    exemption  = overview["annual_exemption"]
    remaining  = overview["remaining_exemption"]

    # ── KPI-rij ──────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("💼 Portefeuillewaarde", eur(total_val),
              delta=eur(unreal_gl), delta_color=delta_color(unreal_gl))
    c2.metric("💸 Totaal geïnvesteerd", eur(total_cost))
    c3.metric("📈 Ongerealiseerde W/V",
              pct(unreal_gl / total_cost * 100 if total_cost else None),
              delta=eur(unreal_gl), delta_color=delta_color(unreal_gl))
    c4.metric("💰 Netto dividenden YTD", eur(overview["total_dividends_net"]))
    c5.metric("🧾 Transactiekosten", eur(overview.get("selection_costs", 0)),
              help="Aankoop-/verkoopkosten (excl. TOB). Apart gehouden, niet in de meerwaardeberekening.")

    st.divider()

    col_l, col_r = st.columns([3, 2])

    with col_l:
        # Taarttaart samenstelling
        labels = list(pv.keys())
        values = [pv[t]["current_value"] or 0 for t in labels]
        names_map = {a["ticker"]: a.get("name", a["ticker"]) for a in assets}
        names = [names_map.get(t, t) for t in labels]

        fig_pie = go.Figure(go.Pie(
            labels=names, values=values,
            hole=0.45, textinfo="label+percent",
            hovertemplate="<b>%{label}</b><br>€%{value:,.2f}<extra></extra>",
        ))
        fig_pie.update_layout(
            title="Samenstelling portefeuille",
            height=300, margin=dict(t=40, b=0, l=0, r=0),
            paper_bgcolor="rgba(0,0,0,0)", showlegend=False,
        )
        st.plotly_chart(fig_pie, use_container_width=True)

        # Staafdiagram W/V per positie
        tickers_sorted = sorted(pv.keys(), key=lambda t: pv[t]["unrealized_gain_loss"] or 0)
        gl_vals = [pv[t]["unrealized_gain_loss"] or 0 for t in tickers_sorted]
        colors  = ["#00b894" if v >= 0 else "#d63031" for v in gl_vals]

        fig_bar = go.Figure(go.Bar(
            x=tickers_sorted, y=gl_vals, marker_color=colors,
            text=[f"€{v:,.0f}" for v in gl_vals], textposition="outside",
            hovertemplate="<b>%{x}</b><br>€%{y:,.2f}<extra></extra>",
        ))
        fig_bar.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.3)")
        fig_bar.update_layout(
            title="Ongerealiseerde winst/verlies per positie",
            height=280, showlegend=False,
            margin=dict(t=40, b=30, l=20, r=20),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col_r:
        # Belastingstatus
        st.subheader(f"🧾 Belasting {year}")
        pct_used = min(100.0, real_gl / exemption * 100) if exemption > 0 else 0
        color_lbl = "🟢" if pct_used < 60 else ("🟡" if pct_used < 90 else "🔴")

        st.metric("Netto gerealiseerde W/V", eur(real_gl),
                  delta_color=delta_color(real_gl))
        st.progress(min(1.0, pct_used / 100),
                    text=f"{color_lbl} {pct_used:.1f}% van vrijstelling (€{exemption:,.0f})")

        if tax_due > 0:
            st.error(f"💰 Geschatte meerwaardebelasting: **{eur(tax_due)}**")
        else:
            st.success(f"✅ Nog {eur(remaining)} vrije ruimte")

        st.divider()

        # Laatste AI-advies
        st.subheader("🤖 Laatste AI-advies")
        latest = db.get_ai_evaluations("tax_optimization", limit=1)
        if latest:
            ev = latest[0]
            st.caption(f"📅 {ev['created_at'][:16]}")
            preview = ev["content"][:350]
            st.markdown(preview + ("…" if len(ev["content"]) > 350 else ""))
        else:
            st.caption("Nog geen advies. Genereer het via 🤖 AI Advisor.")


# ── PAGINA: Portefeuille ───────────────────────────────────────────────────────

def page_portfolio():
    st.title("💼 Portefeuille")

    col_btn, col_acct, _ = st.columns([1, 2, 3])
    if col_btn.button("🔄 Ververs prijzen"):
        clear_cache()
        md._CACHE.clear()
        st.rerun()
    with col_acct:
        acct = account_filter_widget("port_acct")

    year = datetime.now().year
    overview, assets, prices = get_overview(year, acct)
    pv = overview["position_values"]

    if not pv:
        st.info("Geen open posities. Voeg transacties toe via ➕ Transacties.")
        return

    assets_map = {a["ticker"]: a for a in assets}
    divs_net = {}
    for d in db.get_dividends():
        divs_net[d["ticker"]] = divs_net.get(d["ticker"], 0) + (
            d["gross_amount"] - d["withholding_tax"])

    rows = []
    for ticker, pos in pv.items():
        asset = assets_map.get(ticker, {})
        div = divs_net.get(ticker, 0)
        total_return = (pos["unrealized_gain_loss"] or 0) + div
        rows.append({
            "":             sign_icon(pos["unrealized_gain_loss"]),
            "Ticker":       ticker,
            "Naam":         (asset.get("name") or ticker)[:22],
            "Type":         (asset.get("asset_type") or "—").upper(),
            "Munt":         pos["current_price_currency"] or "EUR",
            "Aantal":       f"{pos['quantity']:.4f}",
            "Gem.kostpr.(€)":  f"{pos['avg_cost']:.4f}",
            "Koers (native)":  f"{pos['current_price']:.4f}" if pos["current_price"] else "—",
            "Geïnvesteerd": eur(pos["total_cost"]),
            "Huidige waarde": eur(pos["current_value"]),
            "W/V (€)":      eur(pos["unrealized_gain_loss"]),
            "W/V (%)":      pct(pos["unrealized_gain_loss_pct"]),
            "Dividend":     eur(div),
            "Tot. rendement": eur(total_return),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True, height=420)

    # Totaalrij
    total_val  = overview["total_portfolio_value"]
    total_cost = overview["total_cost_basis"]
    tot_gl     = overview["unrealized_gl"]
    tot_div    = overview["total_dividends_net"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Totaal geïnvesteerd", eur(total_cost))
    c2.metric("Totale waarde",       eur(total_val))
    c3.metric("Ongerealiseerde W/V", eur(tot_gl),
              delta=pct(tot_gl / total_cost * 100 if total_cost else 0),
              delta_color=delta_color(tot_gl))
    c4.metric("Netto dividenden",    eur(tot_div))

    st.divider()
    st.subheader("📈 Prijsgeschiedenis")
    tickers = list(pv.keys())
    sel = st.selectbox("Selecteer positie:", tickers)
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
            name=sel,
        ))
        fig.add_hline(y=avg_cost, line_dash="dash", line_color="#fdcb6e",
                      annotation_text=f"Gem. kostprijs {avg_cost:.4f}")
        fig.update_layout(
            title=f"{sel} — {days} dagen",
            height=340, plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=40, b=30, l=20, r=20),
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Nog geen prijsgeschiedenis. De scheduler slaat elke 5 minuten koersen op.")


# ── PAGINA: Activa ────────────────────────────────────────────────────────────

def page_assets():
    st.title("🏢 Activa beheren")

    tab_add, tab_list = st.tabs(["➕ Activum toevoegen", "📋 Overzicht"])

    with tab_add:
        with st.form("asset_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                ticker = st.text_input("Ticker *", placeholder="bv. AAPL, VWCE.AS")
                name   = st.text_input("Naam (optioneel)", placeholder="bv. Vanguard FTSE All-World")
                currency = st.selectbox("Munt", ["EUR", "USD", "GBP", "CHF"])
            with c2:
                asset_type  = st.radio("Type", ["stock", "etf"],
                                       format_func=lambda x: "📊 Aandeel" if x == "stock" else "🧺 ETF")
                etf_subtype = "distributing"
                if asset_type == "etf":
                    etf_subtype = st.radio("ETF-type", ["distributing", "accumulating"],
                                           format_func=lambda x: "📤 Distribuerend" if x == "distributing" else "📦 Kapitaliseerend",
                                           help="Bepaalt de TOB-berekening (0,12% / 1,32%)")
                exchange = st.text_input("Beurs (optioneel)", placeholder="bv. Euronext, NYSE")

            auto_fill = st.checkbox("✨ Info automatisch ophalen via Yahoo Finance", value=True)
            submitted = st.form_submit_button("✅ Activum toevoegen", type="primary")

            if submitted:
                if not ticker.strip():
                    st.error("Vul een ticker in.")
                else:
                    t = ticker.strip().upper()
                    n = name.strip()
                    if auto_fill and not n:
                        with st.spinner("Info ophalen via Yahoo Finance..."):
                            info = md.get_stock_info(t)
                            n        = info.get("name", t)
                            currency = info.get("currency", currency)
                            detected = info.get("type", asset_type)
                            if detected == "etf" and asset_type == "stock":
                                asset_type = "etf"
                    db.add_asset(t, n or t, asset_type, etf_subtype, currency, exchange or None)
                    clear_cache()
                    st.success(f"✅ {t} — {n} toegevoegd!")
                    st.rerun()

    with tab_list:
        assets = db.get_assets()
        if not assets:
            st.info("Nog geen activa geregistreerd.")
            return
        for a in assets:
            c1, c2, c3 = st.columns([5, 2, 1])
            with c1:
                subtype_lbl = f" ({a['etf_subtype']})" if a["asset_type"] == "etf" else ""
                st.markdown(f"**{a['ticker']}** — {a.get('name') or '—'}")
                st.caption(f"{a['asset_type'].upper()}{subtype_lbl} | {a['currency']} | {a.get('exchange') or '—'}")
            with c2:
                lp = db.get_latest_price(a["ticker"])
                if lp:
                    st.metric("Laatste koers", f"{lp['price']:.4f} {lp['currency']}",
                              label_visibility="collapsed")
                else:
                    st.caption("Geen koers")
            with c3:
                if st.button("🗑️", key=f"del_asset_{a['ticker']}",
                             help=f"Verwijder {a['ticker']} (inclusief alle transacties)"):
                    db.delete_asset(a["ticker"])
                    clear_cache()
                    st.rerun()
            st.divider()


# ── PAGINA: Transacties ───────────────────────────────────────────────────────

def page_transactions():
    st.title("➕ Transacties")

    assets = db.get_assets()
    if not assets:
        st.warning("Voeg eerst activa toe via 🏢 Activa.")
        return

    asset_tickers = [a["ticker"] for a in assets]
    assets_map    = {a["ticker"]: a for a in assets}

    tab_add, tab_view = st.tabs(["📝 Nieuwe transactie", "📋 Overzicht"])

    with tab_add:
        with st.form("txn_form", clear_on_submit=True):
            c1, c2 = st.columns(2)
            with c1:
                ticker   = st.selectbox("Activum *", asset_tickers)
                txn_date = st.date_input("Datum *", value=date.today())
                txn_type = st.radio("Type *", ["buy", "sell"],
                                    format_func=lambda x: "🟢 Aankoop" if x == "buy" else "🔴 Verkoop",
                                    horizontal=True)
                account  = st.selectbox("Rekening *", db.get_accounts(),
                                        help="Beheer rekeningen via ⚙️ Instellingen → Rekeningen")
            with c2:
                quantity    = st.number_input("Aantal *", min_value=0.0001, step=0.001,
                                               format="%.4f", value=1.0)
                price_unit  = st.number_input("Prijs per stuk *", min_value=0.0001,
                                               step=0.01, format="%.4f", value=1.0)
                currency    = st.selectbox("Munt", ["EUR", "USD", "GBP", "CHF"],
                                           index=["EUR", "USD", "GBP", "CHF"].index(
                                               assets_map.get(ticker, {}).get("currency", "EUR")))

            total_amount = quantity * price_unit

            # Kosten (in munt naar keuze, los van TOB)
            ck1, ck2 = st.columns([2, 1])
            with ck1:
                costs = st.number_input("Transactiekosten (optioneel)", min_value=0.0,
                                        step=0.01, format="%.2f", value=0.0,
                                        help="Broker-/beurskosten e.d. — apart gehouden, niet in de meerwaardeberekening.")
            with ck2:
                costs_currency = st.selectbox("Kostenmunt", ["EUR", "USD", "GBP", "CHF"],
                                              key="costs_cur")

            # TOB auto-berekening
            asset_info  = assets_map.get(ticker, {})
            tob_amount  = tax_mod.calculate_tob(
                asset_info.get("asset_type", "stock"),
                asset_info.get("etf_subtype", "distributing"),
                total_amount,
            )
            # EUR-voorbeeld tonen
            _fx_prev, _eur_prev = compute_eur(total_amount, currency, txn_date)
            eur_hint = "" if currency == "EUR" else f" ≈ **€{_eur_prev:,.2f}** (koers {_fx_prev:.4f})"
            st.info(f"**Totaalwaarde:** {currency} {total_amount:,.4f}{eur_hint} | **TOB:** {currency} {tob_amount:,.2f}")

            manual_tob = st.checkbox("TOB manueel aanpassen")
            if manual_tob:
                tob_amount = st.number_input("TOB (€)", min_value=0.0, value=tob_amount,
                                              step=0.01, format="%.2f")

            notes = st.text_area("Notities (optioneel)", height=60)
            submitted = st.form_submit_button("✅ Transactie toevoegen", type="primary")

            if submitted:
                if quantity <= 0 or price_unit <= 0:
                    st.error("Aantal en prijs moeten positief zijn.")
                else:
                    fx_rate, tot_eur = compute_eur(total_amount, currency, txn_date)
                    _, costs_eur = compute_eur(costs, costs_currency, txn_date)
                    proceed = True
                    if txn_type == "sell":
                        # Beschikbaarheid controleren BINNEN de gekozen rekening
                        acct_txns = db.get_transactions(ticker=ticker, account=account)
                        positions, _ = tax_mod.build_fifo_positions(acct_txns)
                        available = positions.get(ticker, {}).get("total_quantity", 0)
                        if quantity > available + 1e-9:
                            st.error(f"Onvoldoende positie op rekening '{account}'. Beschikbaar: {available:.4f}")
                            proceed = False
                    if proceed:
                        db.add_transaction(ticker, txn_type, str(txn_date), quantity,
                                           price_unit, total_amount, currency, tob_amount,
                                           notes or None, account=account, costs=costs,
                                           costs_currency=costs_currency, fx_rate=fx_rate,
                                           total_amount_eur=tot_eur, costs_eur=costs_eur)
                        clear_cache()
                        st.success(f"✅ {'Aankoop' if txn_type == 'buy' else 'Verkoop'} van "
                                   f"{quantity:.4f} × {ticker} op {account} toegevoegd!")
                        st.rerun()

    with tab_view:
        c1, c2, c3, c4 = st.columns(4)
        f_tick = c1.text_input("Filter ticker")
        f_type = c2.selectbox("Type", ["Alle", "Aankoop", "Verkoop"])
        f_year = c3.selectbox("Jaar", ["Alle"] + [str(y) for y in range(datetime.now().year, 2019, -1)])
        f_acct = c4.selectbox("Rekening", ["Alle"] + db.get_accounts())

        txns = db.get_transactions(
            ticker=f_tick.upper() if f_tick else None,
            year=int(f_year) if f_year != "Alle" else None,
            txn_type=("buy" if f_type == "Aankoop" else "sell" if f_type == "Verkoop" else None),
            account=(f_acct if f_acct != "Alle" else None),
        )

        if not txns:
            st.info("Geen transacties gevonden.")
            return

        # Totalen
        total_tob   = sum(t["tob_tax"] or 0 for t in txns)
        total_costs = sum(t.get("costs_eur") or 0 for t in txns)
        st.caption(f"{len(txns)} transactie(s) | Totale TOB: {eur(total_tob)} | Kosten: {eur(total_costs)}")

        accounts = db.get_accounts()
        for t in reversed(txns):  # Nieuwste eerst
            icon  = "🟢" if t["transaction_type"] == "buy" else "🔴"
            label = "Aankoop" if t["transaction_type"] == "buy" else "Verkoop"
            c_info, c_val, c_acct, c_del = st.columns([4, 3, 2, 1])
            with c_info:
                st.markdown(f"{icon} **{t['ticker']}** — {label}")
                st.caption(f"📅 {t['date']}")
                if t.get("notes"):
                    st.caption(f"📝 {t['notes']}")
            with c_val:
                st.markdown(f"{t['quantity']:.4f} × {t['currency']} {t['price_per_unit']:.4f}")
                eur_tot = t.get("total_amount_eur")
                eur_str = f" (€{eur_tot:,.2f})" if eur_tot is not None and t["currency"] != "EUR" else ""
                st.caption(f"Totaal: {t['currency']} {t['total_amount']:,.2f}{eur_str}")
                st.caption(f"TOB: {eur(t['tob_tax'])} | Kosten: {eur(t.get('costs_eur') or 0)}")
            with c_acct:
                cur_acct = t.get("account") or db.DEFAULT_ACCOUNT
                idx = accounts.index(cur_acct) if cur_acct in accounts else 0
                new_acct = st.selectbox("Rekening", accounts, index=idx,
                                        key=f"acct_{t['id']}", label_visibility="collapsed")
                if new_acct != cur_acct:
                    db.update_transaction_account(t["id"], new_acct)
                    clear_cache()
                    st.rerun()
            with c_del:
                if st.button("🗑️", key=f"del_t_{t['id']}"):
                    db.delete_transaction(t["id"])
                    clear_cache()
                    st.rerun()
            st.divider()


# ── PAGINA: Dividenden ────────────────────────────────────────────────────────

def page_dividends():
    st.title("💰 Dividenden")

    assets = db.get_assets()

    tab_add, tab_view = st.tabs(["📝 Dividend toevoegen", "📋 Overzicht"])

    with tab_add:
        tickers = [a["ticker"] for a in assets]
        if not tickers:
            st.warning("Voeg eerst activa toe via 🏢 Activa.")
        else:
            wh_default = float(db.get_setting("withholding_tax_rate", "0.30"))
            with st.form("div_form", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    d_ticker   = st.selectbox("Activum *", tickers)
                    d_date     = st.date_input("Datum *", value=date.today())
                    d_currency = st.selectbox("Munt", ["EUR", "USD", "GBP"])
                with c2:
                    gross  = st.number_input("Bruto dividend (€) *", min_value=0.01, step=0.01, format="%.2f")
                    wh_pct = st.number_input("Roerende voorheffing (%)", min_value=0.0,
                                              max_value=100.0, value=wh_default * 100, step=0.5)
                    wh_amt = gross * wh_pct / 100
                    net    = gross - wh_amt
                    st.info(f"**Netto ontvangen:** {d_currency} {net:,.2f} (RV: {d_currency} {wh_amt:,.2f})")
                notes = st.text_area("Notities (optioneel)", height=60)
                if st.form_submit_button("✅ Dividend toevoegen", type="primary"):
                    fx_rate, gross_eur = compute_eur(gross, d_currency, d_date)
                    _, wh_eur = compute_eur(wh_amt, d_currency, d_date)
                    db.add_dividend(d_ticker, str(d_date), gross, wh_amt, d_currency, notes or None,
                                    fx_rate=fx_rate, gross_eur=gross_eur, withholding_eur=wh_eur)
                    clear_cache()
                    st.success(f"✅ Dividend {d_currency} {net:.2f} netto voor {d_ticker} toegevoegd!")
                    st.rerun()

    with tab_view:
        f_year = st.selectbox("Jaar:", ["Alle"] + [str(y) for y in range(datetime.now().year, 2019, -1)],
                              key="div_year")
        divs = db.get_dividends(year=int(f_year) if f_year != "Alle" else None)

        if not divs:
            st.info("Geen dividenden gevonden.")
            return

        total_gross = sum(d["gross_amount"] for d in divs)
        total_wh    = sum(d["withholding_tax"] for d in divs)
        total_net   = total_gross - total_wh

        c1, c2, c3 = st.columns(3)
        c1.metric("Bruto", eur(total_gross))
        c2.metric("Roerende voorheffing", eur(total_wh))
        c3.metric("Netto ontvangen", eur(total_net))
        st.divider()

        for d in divs:
            net = d["gross_amount"] - d["withholding_tax"]
            c_info, c_val, c_del = st.columns([5, 3, 1])
            with c_info:
                st.markdown(f"🎁 **{d['ticker']}**")
                st.caption(f"📅 {d['date']}")
                if d.get("notes"):
                    st.caption(f"📝 {d['notes']}")
            with c_val:
                st.markdown(f"Bruto: **{d['currency']} {d['gross_amount']:,.2f}**")
                st.caption(f"RV: {d['currency']} {d['withholding_tax']:,.2f} | Netto: {d['currency']} {net:,.2f}")
            with c_del:
                if st.button("🗑️", key=f"del_d_{d['id']}"):
                    db.delete_dividend(d["id"])
                    clear_cache()
                    st.rerun()
            st.divider()


# ── PAGINA: Belgische belasting ────────────────────────────────────────────────

def page_tax():
    st.title("🧾 Belgische Meerwaardebelasting")
    st.caption("⚖️ *Schattingen — raadpleeg een erkend belastingconsulent voor uw situatie.*")

    cur_year  = datetime.now().year
    sel_year  = st.selectbox("Boekjaar:", list(range(cur_year, cur_year - 6, -1)))
    overview, assets, prices = get_overview(sel_year)

    pv          = overview["position_values"]
    real_gl     = overview["total_realized_gl"]
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
    c1.metric("Gerealiseerde W/V", eur(real_gl), delta_color=delta_color(real_gl))
    c2.metric("Jaarlijkse vrijstelling", eur(exemption))
    c3.metric("Belastbaar bedrag", eur(taxable))
    c4.metric("Geschatte belasting (10%)", eur(tax_due),
              delta_color="inverse" if tax_due > 0 else "off")
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
        pct_used = min(100.0, real_gl / exemption * 100) if exemption > 0 else 0
        color_lbl = "🟢" if pct_used < 60 else ("🟡" if pct_used < 90 else "🔴")
        st.subheader("Vrijstelling gebruik")
        st.progress(max(0.0, min(1.0, pct_used / 100)),
                    text=f"{color_lbl} {pct_used:.1f}% gebruikt ({eur(real_gl)} / {eur(exemption)})")

        st.markdown(f"""
| | Bedrag |
|---|---|
| Gerealiseerde meerwaarden | **{eur(real_gl)}** |
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
            "Aantal":      f"{g['quantity']:.4f}",
            "Kostbasis":   eur(g["cost_basis"]),
            "Verkoopwaarde": eur(g["sell_total"]),
            "Winst/Verlies": eur(g["gain_loss"]),
        } for g in sorted(year_gains, key=lambda x: x["date"], reverse=True)]
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
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
            "Transactiewaarde": eur(t["total_amount"]),
            "TOB":    eur(t["tob_tax"]),
        } for t in txns_year if t["tob_tax"]]
        if tob_rows:
            with st.expander("TOB-detail per transactie"):
                st.dataframe(pd.DataFrame(tob_rows), use_container_width=True, hide_index=True)


# ── PAGINA: AI Advisor ────────────────────────────────────────────────────────

def page_ai_advisor():
    st.title("🤖 AI Beleggingsadviseur")

    api_key = db.get_setting("openai_api_key", "")
    if not api_key:
        st.warning("⚠️ Voeg uw OpenAI API-sleutel toe in **⚙️ Instellingen** om AI-functies te gebruiken.")
        return

    tab_tax, tab_open, tab_mid, tab_close = st.tabs([
        "💡 Belastingoptimalisatie",
        "🔔 Marktopening",
        "☀️ Middag",
        "🔕 Slotring",
    ])

    def render_eval_tab(eval_type: str, timing_filter: str | None,
                        button_label: str, manual_args: dict):
        evals = db.get_ai_evaluations(eval_type, limit=10)
        if timing_filter:
            evals = [e for e in evals if e.get("timing") == timing_filter]

        latest = evals[0] if evals else None
        if latest:
            st.caption(f"📅 Gegenereerd op: {latest['created_at'][:16]}")
            if latest.get("tickers"):
                st.caption(f"📊 Tickers: {latest['tickers']}")
            st.markdown(latest["content"])
        else:
            st.info("Nog geen evaluatie beschikbaar. Klik op de knop hieronder of wacht op de dagelijkse scheduler.")

        st.divider()
        if st.button(button_label, type="primary", key=f"gen_{eval_type}_{timing_filter}"):
            with st.spinner("GPT analyseert uw portefeuille..."):
                if eval_type == "tax_optimization":
                    ai_advisor.generate_tax_optimization()
                else:
                    ai_advisor.generate_market_evaluation(
                        manual_args["timing"], manual_args["exchanges"])
            clear_cache()
            st.rerun()

        if len(evals) > 1:
            with st.expander("📚 Historiek"):
                for ev in evals[1:]:
                    st.caption(f"📅 {ev['created_at'][:16]}")
                    st.markdown(ev["content"])
                    st.divider()

    with tab_tax:
        st.subheader("💡 Dagelijks belastingoptimalisatieadvies")
        st.caption("Automatisch gegenereerd op werkdagen om 08:00. Gebaseerd op actuele portefeuille en Belgische fiscale regels.")
        render_eval_tab("tax_optimization", None,
                        "💡 Genereer belastingadvies nu",
                        {})

    with tab_open:
        st.subheader("🔔 Evaluatie bij marktopening")
        st.caption("Euronext: 09:05 | NYSE/NASDAQ: 15:35 (Brussels Time)")
        render_eval_tab("market_evaluation", "open",
                        "🔔 Genereer opening-evaluatie nu",
                        {"timing": "open", "exchanges": ["Euronext", "NYSE", "NASDAQ"]})

    with tab_mid:
        st.subheader("☀️ Evaluatie midden van de beursdag")
        st.caption("Euronext: 13:15 | NYSE/NASDAQ: 18:45 (Brussels Time)")
        render_eval_tab("market_evaluation", "midday",
                        "☀️ Genereer middag-evaluatie nu",
                        {"timing": "midday", "exchanges": ["Euronext", "NYSE", "NASDAQ"]})

    with tab_close:
        st.subheader("🔕 Evaluatie bij slotring")
        st.caption("Euronext: 17:35 | NYSE/NASDAQ: 22:05 (Brussels Time)")
        render_eval_tab("market_evaluation", "close",
                        "🔕 Genereer slotring-evaluatie nu",
                        {"timing": "close", "exchanges": ["Euronext", "NYSE", "NASDAQ"]})


# ── PAGINA: Instellingen ──────────────────────────────────────────────────────

def page_settings():
    st.title("⚙️ Instellingen")

    tab_api, tab_acct, tab_tax, tab_tob, tab_data = st.tabs(
        ["🔑 API-sleutel", "🏦 Rekeningen", "🧾 Meerwaardebelasting", "🏛️ TOB-tarieven", "🗃️ Data"])

    with tab_api:
        st.subheader("OpenAI API")
        current = db.get_setting("openai_api_key", "")
        new_key = st.text_input("API-sleutel", value=current, type="password",
                                help="Beschikbaar via platform.openai.com/api-keys")
        model = st.selectbox("Model", ["gpt-4.1-mini", "gpt-4.1", "gpt-4.1-nano"],
                             index=["gpt-4.1-mini", "gpt-4.1", "gpt-4.1-nano"].index(
                                 db.get_setting("openai_model", "gpt-4.1-mini")))
        if st.button("💾 Opslaan", key="save_api"):
            db.set_setting("openai_api_key", new_key.strip())
            db.set_setting("openai_model", model)
            st.success("✅ API-sleutel opgeslagen!")
        if current:
            st.success("✅ API-sleutel is geconfigureerd.")
        else:
            st.warning("⚠️ Geen API-sleutel — AI-functies niet beschikbaar.")

    with tab_acct:
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

    with tab_tax:
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

    with tab_tob:
        st.subheader("Taks op Beursverrichtingen (TOB)")
        c1, c2 = st.columns(2)
        with c1:
            r_s  = st.number_input("Aandelen tarief (%)", value=float(db.get_setting("tob_rate_stocks", "0.0035"))*100, step=0.001, format="%.4f")
            r_ed = st.number_input("ETF distribuerend (%)", value=float(db.get_setting("tob_rate_etf_distributing", "0.0012"))*100, step=0.001, format="%.4f")
            r_ea = st.number_input("ETF kapitaliseerend (%)", value=float(db.get_setting("tob_rate_etf_accumulating", "0.0132"))*100, step=0.001, format="%.4f")
        with c2:
            m_s  = st.number_input("Aandelen maximum (€)", value=float(db.get_setting("tob_max_stocks", "1600")), step=100.0)
            m_ed = st.number_input("ETF distr. maximum (€)", value=float(db.get_setting("tob_max_etf_distributing", "1300")), step=100.0)
            m_ea = st.number_input("ETF kap. maximum (€)", value=float(db.get_setting("tob_max_etf_accumulating", "4000")), step=100.0)
        wh = st.number_input("Roerende voorheffing (%)",
                              value=float(db.get_setting("withholding_tax_rate", "0.30"))*100,
                              step=0.5)
        if st.button("💾 Opslaan", key="save_tob"):
            db.set_setting("tob_rate_stocks", str(r_s/100))
            db.set_setting("tob_rate_etf_distributing", str(r_ed/100))
            db.set_setting("tob_rate_etf_accumulating", str(r_ea/100))
            db.set_setting("tob_max_stocks", str(m_s))
            db.set_setting("tob_max_etf_distributing", str(m_ed))
            db.set_setting("tob_max_etf_accumulating", str(m_ea))
            db.set_setting("withholding_tax_rate", str(wh/100))
            st.success("✅ TOB-instellingen opgeslagen!")

    with tab_data:
        st.subheader("Databeheer")
        assets = db.get_assets()
        txns   = db.get_transactions()
        divs   = db.get_dividends()
        c1, c2, c3 = st.columns(3)
        c1.metric("Activa", len(assets))
        c2.metric("Transacties", len(txns))
        c3.metric("Dividenden", len(divs))
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
    st.plotly_chart(fig_val, use_container_width=True)

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
    st.plotly_chart(fig_pct, use_container_width=True)

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
            "Kostenbasis":    eur(s["cost_basis"]),
            "Huidige waarde": eur(s["current_value"]),
            "W/V (€)":        eur(s["gain_loss"]),
            "W/V (%)":        pct(s["gain_loss_pct"]),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
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
        st.plotly_chart(fig_cmp, use_container_width=True)


# ── Navigatie ─────────────────────────────────────────────────────────────────

PAGES = {
    "📊 Dashboard":            page_dashboard,
    "💼 Portefeuille":         page_portfolio,
    "📈 Evolutie":             page_evolution,
    "🏢 Activa":               page_assets,
    "➕ Transacties":          page_transactions,
    "💰 Dividenden":           page_dividends,
    "🧾 Belgische Belasting":  page_tax,
    "🤖 AI Advisor":           page_ai_advisor,
    "⚙️ Instellingen":         page_settings,
}

with st.sidebar:
    st.title("📈 Portfolio Tracker")
    st.caption("Belgische belegger 🇧🇪")

    selected = st.radio("Menu", list(PAGES.keys()), label_visibility="collapsed")

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

    st.divider()
    now = datetime.now()
    st.caption(f"📅 {now.strftime('%d/%m/%Y %H:%M')}")
    st.caption("⏱️ Koersen: elke 5 min")
    st.caption("🤖 AI: 3× per dag + 08:00")

PAGES[selected]()