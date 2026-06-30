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
import streamlit.components.v1 as components

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
def get_overview(year: int, account=None) -> dict:
    """Gecachte portfolioverzicht (60 s TTL). account=None -> alle rekeningen;
    mag ook een tuple van rekeningnamen zijn (multiselect)."""
    assets = db.get_assets()
    tickers = [a["ticker"] for a in assets]
    prices = md.get_prices_for_tickers(tickers)
    overview = tax_mod.calculate_tax_overview(year=year, current_prices=prices,
                                              account=account)
    return overview, assets, prices


def clear_cache():
    get_overview.clear()


def asset_name_map() -> dict:
    """{ticker: naam} voor alle geregistreerde activa."""
    return {a["ticker"]: (a.get("name") or a["ticker"]) for a in db.get_assets()}


def asset_label(ticker: str, names: dict | None = None) -> str:
    """Toon 'Naam (TICKER)'; valt terug op enkel de ticker als er geen naam is."""
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


def perf_net(r: dict, real_model: bool = True) -> float:
    """Netto resultaat van een activum volgens de gekozen zienswijze voor performance shares.
    real_model=True: reële winst (huidige waarde − betaalde personenbelasting).
    real_model=False: zuivere meerwaarde t.o.v. de toekenningswaarde."""
    return r["net_real"] if real_model else r["net_total"]


def render_realized_history(realized_list, names=None, empty_msg="Nog geen gerealiseerde meer-/minwaarden."):
    """Tabel met gerealiseerde meer-/minwaarden (verkopen), over alle jaren/rekeningen
    heen zoals meegegeven. Toont ook posities die intussen netto 0 zijn."""
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
            "Aantal":        f"{g['quantity']:.4f}",
            "Opbrengst (€)": eur(g["sell_total"]),
            "Kostbasis (€)": eur(g["cost_basis"]),
            "W/V (€)":       eur(g["gain_loss"]),
        })
    st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
    tot = sum(g["gain_loss"] for g in realized_list)
    st.caption(f"Totaal gerealiseerde W/V (deze selectie, alle jaren): **{eur(tot)}**")


def compute_eur(amount: float, currency: str, date_str: str) -> tuple[float, float]:
    """(fx_rate, eur_bedrag) op transactiedatum. Valt terug op 1.0 bij EUR/fout."""
    if not amount or currency == "EUR":
        return 1.0, float(amount or 0.0)
    rate = md.get_historical_exchange_rate(currency, str(date_str), "EUR") or 1.0
    return rate, float(amount) * rate


def account_filter_widget(key: str):
    """Multiselect van rekeningen. Lege selectie = alle rekeningen.
    Retourneert een tuple (cachebaar) of None."""
    opts = db.get_accounts()
    sel = st.multiselect("Rekeningen", opts, default=[], key=key,
                         placeholder="Alle rekeningen")
    return tuple(sel) if sel else None


def df_row_select(df, key: str):
    """Toon een dataframe met klikbare enkelvoudige rijselectie en geef de index van de
    geselecteerde rij terug (positie in df), of None. Defensief tegen oudere Streamlit-
    versies en testomgevingen die geen selectie-object teruggeven."""
    ev = st.dataframe(df, width="stretch", hide_index=True, key=key,
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
        return rows[0]
    return None


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

    fc1, fc2 = st.columns([2, 3])
    with fc1:
        acct = account_filter_widget("dash_acct")
    with fc2:
        period = st.radio("Periode", ["YTD (dit jaar)", "Sinds start (all-time)"],
                          horizontal=True, key="dash_period", label_visibility="collapsed")
    all_time = period.startswith("Sinds")
    # Toggle: hoe performance shares meetellen in het resultaat
    has_inctax = any((t.get("income_tax_eur") or 0) > 0 for t in db.get_transactions())
    real_perf = True
    if has_inctax:
        real_perf = st.checkbox(
            "Performance shares doorrekenen aan betaalde personenbelasting",
            value=True, key="dash_real_perf",
            help="AAN: reële winst = huidige waarde − betaalde personenbelasting (de toekenningswaarde "
                 "telt niet als kost; je investeerde in feite enkel de belasting). UIT: zuivere "
                 "meerwaarde t.o.v. de toekenningswaarde. Beïnvloedt enkel de weergave, niet de meerwaardebelasting.")
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
    c4.metric(f"💰 Netto dividenden ({period_lbl})", eur(div_net))
    _kosten = overview.get("selection_costs", 0) + overview.get("account_costs_selection", 0)
    c5.metric("🧾 Kosten (txn + rekening)", eur(_kosten),
              help="Transactiekosten + algemene rekeningkosten (bv. beheerskosten). "
                   "Apart gehouden, niet in de meerwaardeberekening.")

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

    # AI-ratingsynthese + wijzigingen sinds de vorige ronde (gedeeld door beide kolommen)
    dash_synth   = ai_advisor.rating_synthesis(list(pv.keys()), n_batches=9) if pv else {}
    dash_changes = ai_advisor.rating_changes(list(pv.keys())) if pv else {}

    col_l, col_r = st.columns([3, 2])

    with col_l:
        if not pv:
            st.caption("Geen open posities om grafisch te tonen voor deze selectie.")
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
        st.plotly_chart(fig_pie, width='stretch')

        # Staafdiagram: netto resultaat per activum (W/V + dividenden − kosten)
        names = asset_name_map()
        result = per_asset_result(overview, year=None if all_time else year, accounts=accset)
        if result:
            tickers_sorted = sorted(result.keys(), key=lambda t: perf_net(result[t], real_perf))
            net_vals  = [perf_net(result[t], real_perf) for t in tickers_sorted]
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
            tot_net    = sum(perf_net(r, real_perf) for r in result.values())
            if tot_inctax and real_perf:
                cap = ("Performance shares gerekend aan de betaalde personenbelasting "
                       "(reële winst = huidige waarde − belasting).")
            elif tot_inctax:
                cap = "Performance shares gerekend aan de toekenningswaarde (zuivere meerwaarde)."
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
        st.rerun()
    with col_acct:
        acct = account_filter_widget("port_acct")

    year = datetime.now().year
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

    # Koersdoelen (laatste per ticker uit transacties; anders AI-koersdoel)
    price_targets = {}
    for t in db.get_transactions():           # ASC op datum -> laatste wint
        if t.get("price_target") is not None:
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
        st.subheader("📊 Totaal resultaat per activum")
        st.caption("Per activum: ongerealiseerde + gerealiseerde W/V, ontvangen dividenden, gelinkte "
                   "kosten (transactiekosten + TOB) en — voor performance shares — de betaalde "
                   "personenbelasting. Voor performance shares is het 'Netto resultaat' de reële winst: "
                   "huidige waarde − betaalde personenbelasting (de toekenningswaarde telt niet als kost).")
        result = per_asset_result(overview, year=None, accounts=accset)
        if not result:
            st.info("Nog geen posities of historiek voor deze selectie.")
            return
        any_inctax = any(r["income_tax"] for r in result.values())
        rrows = []
        for t in sorted(result.keys(), key=lambda x: result[x]["net_real"], reverse=True):
            r = result[t]
            rec = synth.get(t, {}).get("consensus")
            net = r["net_real"]
            row = {
                "W/V":                 sign_icon(net),
                "Activum":             asset_label(t, nmap),
                "Aantal (nu)":         f"{r['quantity']:.4f}" if r["quantity"] else "0",
                "Huidige waarde":      eur(r["current_value"]),
                "Ongerealiseerd":      eur(r["unrealized"]),
                "Gerealiseerd":        eur(r["realized"]),
                "Dividenden":          eur(r["dividends"]),
                "Kosten":              eur(r["costs"]),
            }
            if any_inctax:
                row["Personenbel."] = eur(r["income_tax"]) if r["income_tax"] else "—"
            row["Netto resultaat"] = eur(net)
            row["AI-advies"]       = ai_badge(rec, changes.get(t))
            rrows.append(row)
        st.dataframe(pd.DataFrame(rrows), width="stretch", hide_index=True)
        tu = sum(r["unrealized"] for r in result.values())
        tr = sum(r["realized"] for r in result.values())
        tdv = sum(r["dividends"] for r in result.values())
        tc = sum(r["costs"] for r in result.values())
        tpb = sum(r["income_tax"] for r in result.values())
        net_all = sum(r["net_real"] for r in result.values())
        extra = (f"  Voor performance shares geldt: reële winst = huidige waarde − personenbelasting "
                 f"(totaal betaalde personenbelasting {eur(tpb)})." if tpb else "")
        st.caption(f"**Totaal netto resultaat: {eur(net_all)}** "
                   f"(ongerealiseerd {eur(tu)} + gerealiseerd {eur(tr)} + dividenden {eur(tdv)} − kosten {eur(tc)}"
                   + (" + performance-aanpassing" if tpb else "") + ").  "
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
                "Aantal":       f"{pos['quantity']:.4f}",
                "Gem.kostpr.(€)":  f"{pos['avg_cost']:.4f}",
                "Koers (native)":  f"{pos['current_price']:.4f}" if pos["current_price"] else "—",
                "Koersdoel":    f"{tgt:.2f}" if tgt else "—",
                "Potentieel":   pct(upside) if upside is not None else "—",
                "Huidige waarde": eur(pos["current_value"]),
                "W/V (%)":      pct(pos["unrealized_gain_loss_pct"]),
                "Dividend":     eur(div),
                "Tot. rendement": eur(total_return),
                "AI-advies":    ai_badge(rec, changes.get(ticker)),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=420)

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
            st.dataframe(pd.DataFrame(srows), width="stretch", hide_index=True)
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
                          annotation_text=f"Gem. kostprijs {avg_cost:.4f}")
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
    tab_add, tab_list, tab_splits = st.tabs(
        ["➕ Activum toevoegen", "📋 Overzicht", "🔀 Splitsingen"])

    with tab_add:
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
                    if not info.get("found"):
                        st.error(
                            f"❌ Yahoo Finance vond geen gegevens voor '{ticker.strip().upper()}'. "
                            "Controleer de ticker — Europese beurzen vereisen een suffix "
                            "(bv. .PA Parijs, .AS Amsterdam, .BR Brussel, .DE Xetra, .MI Milaan, .L Londen).")
                    else:
                        st.session_state[k("name")] = info.get("name", "") or ""
                        st.session_state[k("cur")]  = info.get("currency", "EUR") or "EUR"
                        st.session_state[k("type")] = info.get("type", "stock") or "stock"
                        st.session_state[k("exch")] = info.get("exchange", "") or ""
                        st.session_state[k("isin")] = info.get("isin", "") or ""
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
                min_value=0.0, step=0.01, format="%.4f",
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
                        st.error("Geen slotkoers gevonden voor 31/12/2025 — vul ze handmatig in.")
                    else:
                        st.session_state[k("snap_stage")] = float(p)
                        st.session_state["as_snap_nonce"] = snn + 1
                        st.rerun()
        if snap_val and snap_val > 0 and currency != "EUR":
            _fxs, _snap_eur_prev = compute_eur(snap_val, currency, tax_mod.SNAPSHOT_DATE)
            st.caption(f"≈ €{_snap_eur_prev:,.4f}/stuk (koers 31/12/2025: {_fxs:.4f})")

        if st.session_state.get(k("fetched")):
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
                             belgian_registered=int(belg_reg))
                if snap_val and snap_val > 0:
                    _fx, snap_eur = compute_eur(snap_val, currency, tax_mod.SNAPSHOT_DATE)
                    db.set_asset_snapshot(t, float(snap_val), snap_eur)
                clear_cache()
                st.session_state["as_nonce"] = n + 1   # formulier leegmaken
                st.success(f"✅ {t} — {name.strip()} toegevoegd!")
                st.rerun()

    with tab_list:
        # ── Bewerkformulier (bij klik op ✏️) ──────────────────────────────────
        edit_tk = st.session_state.get("edit_asset")
        if edit_tk:
            ea = db.get_asset(edit_tk)
            if ea:
                st.markdown(f"### ✏️ {edit_tk} bewerken")
                sfc1, sfc2 = st.columns([3, 1])
                sfc1.caption("📸 Fotomoment = slotkoers 31/12/2025, gebruikt voor de meerwaardebelasting "
                             "op stukken die je vóór 2026 kocht.")
                if sfc2.button("📸 Ophalen 31/12/2025", key=f"esnapfetch_{edit_tk}"):
                    with st.spinner("Slotkoers 31/12/2025 ophalen..."):
                        p = md.get_close_on_date(edit_tk, tax_mod.SNAPSHOT_DATE)
                    if p is None:
                        st.warning("Geen slotkoers gevonden voor 31/12/2025 — vul ze handmatig in.")
                    else:
                        st.session_state[f"esnap_{edit_tk}"] = float(p)
                        st.rerun()
                with st.form("edit_asset_form"):
                    e1, e2 = st.columns(2)
                    with e1:
                        e_ticker = st.text_input("Ticker", value=edit_tk,
                                                 help="Pas aan als de ticker fout is (bv. STMPA → STMPA.PA). "
                                                      "Transacties, dividenden en koershistoriek verhuizen mee.")
                        e_name = st.text_input("Naam", value=ea.get("name") or "")
                        e_cur_val = ea.get("currency") or "EUR"
                        e_cur_opts = CUR if e_cur_val in CUR else CUR + [e_cur_val]
                        e_cur = st.selectbox("Munt", e_cur_opts,
                                             index=e_cur_opts.index(e_cur_val))
                        e_isin = st.text_input("ISIN", value=ea.get("isin") or "")
                    with e2:
                        _types = ["stock", "etf", "bond"]
                        e_type = st.radio("Type", _types,
                                          index=_types.index(ea.get("asset_type")) if ea.get("asset_type") in _types else 0,
                                          format_func=lambda x: {"stock": "📊 Aandeel", "etf": "🧺 ETF/fonds", "bond": "📈 Obligatie"}[x])
                        e_sub = ea.get("etf_subtype") or "distributing"
                        e_breg = bool(ea.get("belgian_registered", 1))
                        if e_type == "etf":
                            e_sub = st.radio("ETF-type", ["distributing", "accumulating"],
                                             index=0 if e_sub == "distributing" else 1,
                                             format_func=lambda x: "📤 Uitkerend (distributie)" if x == "distributing" else "📦 Kapitaliserend")
                            e_breg = st.checkbox("🇧🇪 In België aangeboden / geregistreerd (FSMA)",
                                                 value=e_breg,
                                                 help="Uit = niet in België aangeboden tracker/ETC (bv. G2XJ.DE) → TOB 0,35%.")
                        e_exch = st.text_input("Beurs", value=ea.get("exchange") or "")
                        e_snap = st.number_input(
                            f"📸 Fotomomentwaarde 31/12/2025 ({e_cur}/stuk)",
                            min_value=0.0, step=0.01, format="%.4f",
                            value=float(st.session_state.get(f"esnap_{edit_tk}",
                                                             ea.get("snapshot_price") or 0.0)),
                            help="Slotkoers op 31/12/2025. Laat 0 voor activa die je pas vanaf 2026 koopt. "
                                 "Gebruik de knop hierboven om ze automatisch op te halen.")
                    _etr = tax_mod.calculate_tob(e_type, e_sub, 10000, e_breg) / 10000 * 100
                    st.caption(f"➡️ TOB-tarief: **{_etr:.2f}%**".replace(".", ",") +
                               "  ·  💡 Na het corrigeren van een ticker: klik op '🔄 Ververs prijzen' op de Portefeuille-pagina.")
                    s1, s2 = st.columns(2)
                    if s1.form_submit_button("💾 Opslaan", type="primary"):
                        target = edit_tk
                        new_tk = e_ticker.strip().upper()
                        ok = True
                        if new_tk and new_tk != edit_tk:
                            if db.rename_ticker(edit_tk, new_tk):
                                target = new_tk
                            else:
                                ok = False
                                st.error(f"Ticker '{new_tk}' bestaat al — kies een andere of voeg ze samen handmatig.")
                        if ok:
                            db.update_asset(target, name=e_name.strip() or target,
                                            asset_type=e_type, etf_subtype=e_sub,
                                            currency=e_cur, exchange=e_exch.strip() or "",
                                            isin=e_isin.strip() or "",
                                            belgian_registered=int(e_breg))
                            if e_snap and e_snap > 0:
                                _fx, snap_eur = compute_eur(e_snap, e_cur, tax_mod.SNAPSHOT_DATE)
                                db.set_asset_snapshot(target, float(e_snap), snap_eur)
                            else:
                                db.set_asset_snapshot(target, None, None)
                            st.session_state.pop(f"esnap_{edit_tk}", None)
                            clear_cache()
                            st.session_state.pop("edit_asset", None)
                            st.success(f"✅ {target} bijgewerkt!")
                            st.rerun()
                    if s2.form_submit_button("✖️ Annuleren"):
                        st.session_state.pop("edit_asset", None)
                        st.rerun()
                st.divider()

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
        rows = []
        for a in assets:
            lp = db.get_latest_price(a["ticker"])
            sub = a.get("etf_subtype") if a["asset_type"] == "etf" else ""
            rows.append({
                "Ticker":   a["ticker"],
                "Naam":     a.get("name") or "—",
                "Type":     {"stock": "Aandeel", "etf": "ETF", "bond": "Obligatie"}.get(a["asset_type"], a["asset_type"]),
                "ETF-type": {"distributing": "uitkerend", "accumulating": "kapitaliserend"}.get(sub, ""),
                "BE":       "✓" if a.get("belgian_registered") else "✗",
                "Munt":     a["currency"],
                "Beurs":    a.get("exchange") or "—",
                "ISIN":     a.get("isin") or "—",
                "Fotomoment": round(a["snapshot_price"], 4) if a.get("snapshot_price") is not None else None,
                "Laatste koers": round(lp["price"], 4) if lp else None,
            })
        a_names = {a["ticker"]: (a.get("name") or a["ticker"]) for a in assets}
        sel_idx = df_row_select(pd.DataFrame(rows), "asset_table")
        if sel_idx is None:
            st.caption("👆 Klik op een rij om dat activum te bewerken of verwijderen.")
        else:
            sel_a = assets[sel_idx]
            sel_tk = sel_a["ticker"]
            st.caption(f"Geselecteerd: **{asset_label(sel_tk, a_names)}**")
            b1, b2 = st.columns(2)
            if b1.button("✏️ Bewerk", key="asset_action_edit", width="stretch"):
                st.session_state["edit_asset"] = sel_tk
                st.rerun()
            delete_with_confirm(
                "🗑️ Wis (incl. transacties)", "confirm_del_asset", sel_tk,
                f"⚠️ **{asset_label(sel_tk, a_names)}** verwijderen wist óók ALLE transacties, "
                "dividenden en splitsingen van dit activum. Dit is onomkeerbaar. Doorgaan?",
                lambda: db.delete_asset(sel_tk), btn_container=b2)

    with tab_splits:
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
                for sp in splits:
                    cc1, cc2, cc3 = st.columns([4, 2, 1])
                    with cc1:
                        st.markdown(f"🔀 **{sp['ticker']}** — {s_names.get(sp['ticker'], sp['ticker'])}")
                        st.caption(f"📅 {sp['split_date']}")
                    with cc2:
                        st.markdown(f"Ratio **{sp['ratio']:g}**")
                    with cc3:
                        if st.button("🗑️", key=f"del_split_{sp['id']}"):
                            db.delete_split(sp["id"])
                            clear_cache()
                            st.rerun()
                    st.divider()
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

    tab_add, tab_view, tab_costs = st.tabs(
        ["📝 Nieuwe transactie", "📋 Overzicht", "🏦 Rekeningkosten"])

    CUR = ["EUR", "USD", "GBP", "CHF"]

    with tab_add:
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
            quantity   = st.number_input("Aantal *", min_value=0.0, step=0.001,
                                         format="%.4f", value=None, key=kk("qty"))
            price_unit = st.number_input("Prijs per stuk *", min_value=0.0,
                                         step=0.01, format="%.4f", value=None,
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
                                           min_value=0.0, step=0.01, format="%.2f",
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
                                    step=0.01, format="%.2f", value=None,
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
                "🎁 Performance shares (toekenning / vesting)", key=kk("perf"),
                help="Aandelen die je kreeg i.p.v. kocht (bv. via je werkgever). Voer het aantal en de "
                     "koers op de toekenningsdatum in — die waarde wordt je kostbasis voor de "
                     "meerwaarde (je betaalde er al personenbelasting op). Geen TOB en geen cash-uitgave.")
            if is_perf:
                _, _vest_eur = compute_eur(total_amount, currency, txn_date)
                pb_pct = st.number_input(
                    "Personenbelasting bij toekenning (%)", min_value=0.0, max_value=100.0,
                    value=53.5, step=0.5, key=kk("perf_pct"),
                    help="Marginaal tarief waartegen de toekenning als beroepsinkomen belast werd "
                         "(vaak ± 53,5%). Dit bedrag wordt apart bijgehouden als personenbelasting.")
                income_tax_eur = round(_vest_eur * pb_pct / 100, 2)
                if st.checkbox("Bedrag personenbelasting manueel ingeven", key=kk("perf_man")):
                    income_tax_eur = st.number_input(
                        "Personenbelasting (€)", min_value=0.0, value=income_tax_eur,
                        step=0.01, format="%.2f", key=kk("perf_taxval"))
                st.caption(f"📌 Kostbasis ≈ **€{_vest_eur:,.2f}** | personenbelasting "
                           f"**€{income_tax_eur:,.2f}** (apart bijgehouden, toggle op dashboard). "
                           "Geen TOB, geen cash-uitgave.")

        asset_info = assets_map.get(ticker, {})
        _fx_prev, _eur_prev = compute_eur(total_amount, currency, txn_date)
        if is_perf:
            tob_amount = 0.0
            st.info(f"**Waarde bij toekenning:** {currency} {total_amount:,.4f}"
                    f"{'' if currency == 'EUR' else f' ≈ €{_eur_prev:,.2f}'} | **TOB:** €0,00 (toekenning)")
        else:
            tob_amount = tax_mod.calculate_tob(asset_info.get("asset_type", "stock"),
                                               asset_info.get("etf_subtype", "distributing"),
                                               _eur_prev,
                                               bool(asset_info.get("belgian_registered", 1)),
                                               txn_date=txn_date)
            eur_hint = "" if currency == "EUR" else f" ≈ **€{_eur_prev:,.2f}** (koers {_fx_prev:.4f})"
            st.info(f"**Totaalwaarde:** {currency} {total_amount:,.4f}{eur_hint} | **TOB:** €{tob_amount:,.2f}")
            if st.checkbox("TOB manueel aanpassen", key=kk("tob_man")):
                tob_amount = st.number_input("TOB (€)", min_value=0.0, value=tob_amount,
                                             step=0.01, format="%.2f", key=kk("tob_val"))
        notes = st.text_area("Notities (optioneel)", height=60, key=kk("notes"))

        if st.button("✅ Transactie toevoegen", type="primary", key=kk("submit")):
            if not quantity or not price_unit or quantity <= 0 or price_unit <= 0:
                st.error("Vul een geldig aantal en prijs in (beide groter dan 0).")
            else:
                fx_rate, tot_eur = compute_eur(total_amount, currency, txn_date)
                _, costs_eur = compute_eur(costs, costs_currency, txn_date)
                proceed = True
                if txn_type == "sell":
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
                                       total_amount_eur=tot_eur, costs_eur=costs_eur,
                                       price_target=(price_target or None),
                                       is_performance_share=int(is_perf),
                                       income_tax_eur=income_tax_eur)
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

    with tab_view:
        # ── Bewerkformulier (verschijnt bij klik op ✏️) ───────────────────────
        edit_id = st.session_state.get("edit_txn")
        if edit_id:
            # Spring naar boven zodat het bewerkformulier meteen zichtbaar is
            components.html(
                """<script>
                const doc = window.parent.document;
                const el = doc.querySelector('section.main')
                        || doc.querySelector('[data-testid="stMain"]')
                        || doc.querySelector('[data-testid="stAppViewContainer"]')
                        || doc.scrollingElement;
                if (el) { el.scrollTo({top: 0, behavior: 'smooth'}); }
                </script>""", height=0)
            et = next((x for x in db.get_transactions(adjusted=False) if x["id"] == edit_id), None)
            if et:
                st.markdown(f"### ✏️ Transactie #{edit_id} bewerken")
                with st.form("edit_txn_form"):
                    e1, e2, e3 = st.columns(3)
                    with e1:
                        e_ticker = st.selectbox("Activum", asset_tickers,
                                                index=asset_tickers.index(et["ticker"]) if et["ticker"] in asset_tickers else 0,
                                                format_func=fmt)
                        e_type = st.selectbox("Type", ["buy", "sell"],
                                              index=0 if et["transaction_type"] == "buy" else 1)
                        e_date = st.date_input("Datum", value=datetime.strptime(et["date"][:10], "%Y-%m-%d").date(), min_value=date(2000,1,1), max_value=date.today())
                        e_acct = st.selectbox("Rekening", db.get_accounts(),
                                              index=db.get_accounts().index(et.get("account")) if et.get("account") in db.get_accounts() else 0)
                    with e2:
                        e_qty   = st.number_input("Aantal", min_value=0.0001, value=float(et["quantity"]), step=0.001, format="%.4f")
                        e_price = st.number_input("Prijs per stuk", min_value=0.0001, value=float(et["price_per_unit"]), step=0.01, format="%.4f")
                        e_cur   = st.selectbox("Munt", CUR, index=CUR.index(et["currency"]) if et["currency"] in CUR else 0)
                        e_tgt   = st.number_input("Koersdoel", min_value=0.0, value=float(et.get("price_target") or 0.0), step=0.01, format="%.2f")
                    with e3:
                        e_tob   = st.number_input("TOB (€)", min_value=0.0, value=float(et.get("tob_tax") or 0.0), step=0.01, format="%.2f")
                        e_costs = st.number_input("Kosten", min_value=0.0, value=float(et.get("costs") or 0.0), step=0.01, format="%.2f")
                        e_costs_cur = st.selectbox("Kostenmunt", CUR, index=CUR.index(et.get("costs_currency") or "EUR") if (et.get("costs_currency") or "EUR") in CUR else 0)
                    e_notes = st.text_area("Notities", value=et.get("notes") or "", height=60)

                    # Performance shares — ook om bestaande transacties om te vormen
                    _cur_inctax = float(et.get("income_tax_eur") or 0.0)
                    _cur_baseeur = float(et.get("total_amount_eur") or 0.0)
                    _def_pct = round(_cur_inctax / _cur_baseeur * 100, 1) if (_cur_inctax and _cur_baseeur) else 53.5
                    st.markdown("**🎁 Performance shares (toekenning / vesting)**")
                    pf1, pf2, pf3 = st.columns(3)
                    e_perf = pf1.checkbox("Is een toekenning", value=bool(et.get("is_performance_share")),
                                          help="Vink aan om deze (reeds ingevoerde) transactie om te vormen tot "
                                               "performance shares. De kostbasis blijft de ingevulde waarde; TOB wordt op €0 gezet.")
                    e_pb_pct = pf2.number_input("Personenbelasting (%)", min_value=0.0, max_value=100.0,
                                                value=_def_pct, step=0.5)
                    e_inctax = pf3.number_input("of exact bedrag (€)", min_value=0.0, value=_cur_inctax,
                                                step=0.01, format="%.2f",
                                                help="Laat op 0 om uit het % te berekenen; vul in voor een exact bedrag.")
                    s1, s2 = st.columns(2)
                    save = s1.form_submit_button("💾 Opslaan", type="primary")
                    cancel = s2.form_submit_button("✖️ Annuleren")
                    if save:
                        e_total = e_qty * e_price
                        fx, tot_eur = compute_eur(e_total, e_cur, e_date)
                        _, ce = compute_eur(e_costs, e_costs_cur, e_date)
                        if e_perf:
                            inc_tax = e_inctax if e_inctax > 0 else round(tot_eur * e_pb_pct / 100, 2)
                            tob_final = 0.0
                        else:
                            inc_tax = 0.0
                            tob_final = e_tob
                        db.update_transaction(edit_id, ticker=e_ticker, transaction_type=e_type,
                                              date=str(e_date), quantity=e_qty, price_per_unit=e_price,
                                              total_amount=e_total, currency=e_cur, tob_tax=tob_final,
                                              notes=e_notes or None, account=e_acct, costs=e_costs,
                                              costs_currency=e_costs_cur, fx_rate=fx,
                                              total_amount_eur=tot_eur, costs_eur=ce,
                                              price_target=(e_tgt or None),
                                              is_performance_share=int(e_perf), income_tax_eur=inc_tax)
                        clear_cache()
                        st.session_state.pop("edit_txn", None)
                        st.success("✅ Transactie bijgewerkt!"
                                   + (" Omgevormd tot performance shares." if e_perf else ""))
                        st.rerun()
                    if cancel:
                        st.session_state.pop("edit_txn", None)
                        st.rerun()
                st.divider()

        c1, c2, c3, c4 = st.columns(4)
        f_asset = c1.selectbox("Activum", ["Alle"] + asset_tickers,
                               format_func=lambda t: "Alle" if t == "Alle" else fmt(t))
        f_type = c2.selectbox("Type", ["Alle", "Aankoop", "Verkoop"])
        f_year = c3.selectbox("Jaar", ["Alle"] + [str(y) for y in range(datetime.now().year, 2019, -1)])
        f_acct = c4.selectbox("Rekening", ["Alle"] + db.get_accounts())

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
        rows = []
        for t in ordered:
            rows.append({
                "Datum":    t["date"][:10],
                "Type":     "🟢 Aankoop" if t["transaction_type"] == "buy" else "🔴 Verkoop",
                "Activum":  asset_label(t["ticker"], names),
                "Aantal":   round(t["quantity"], 4),
                "Prijs":    round(t["price_per_unit"], 4),
                "Munt":     t["currency"],
                "Totaal":   round(t["total_amount"], 2),
                "€ Totaal": round(t.get("total_amount_eur") or t["total_amount"], 2),
                "Rekening": t.get("account") or db.DEFAULT_ACCOUNT,
                "TOB €":    round(t.get("tob_tax") or 0, 2),
                "Kosten €": round(t.get("costs_eur") or 0, 2),
                "Koersdoel": t.get("price_target") or None,
                "Notities": t.get("notes") or "",
            })
        sel_idx = df_row_select(pd.DataFrame(rows), "txn_table")

        # Acties voor de aangeklikte rij
        if sel_idx is None:
            st.caption("👆 Klik op een rij om die te bewerken, verwijderen of naar een andere rekening te verplaatsen.")
        else:
            sel_t = ordered[sel_idx]
            sel_id = sel_t["id"]
            accounts = db.get_accounts()
            cur_acct = sel_t.get("account") or db.DEFAULT_ACCOUNT
            st.caption(f"Geselecteerd: **#{sel_id} · {sel_t['date'][:10]} · "
                       f"{'Aankoop' if sel_t['transaction_type']=='buy' else 'Verkoop'} · "
                       f"{asset_label(sel_t['ticker'], names)}**")
            a1, a2, a3 = st.columns([2, 1, 1])
            new_acct = a1.selectbox("Verplaats naar rekening", accounts,
                                    index=accounts.index(cur_acct) if cur_acct in accounts else 0,
                                    key=f"txn_action_acct_{sel_id}")
            if new_acct != cur_acct:
                db.update_transaction_account(sel_id, new_acct)
                clear_cache()
                st.rerun()
            if a2.button("✏️ Bewerk", key="txn_action_edit", width="stretch"):
                st.session_state["edit_txn"] = sel_id
                st.rerun()
            delete_with_confirm(
                "🗑️ Wis", "confirm_del_txn", sel_id,
                f"Transactie #{sel_id} ({asset_label(sel_t['ticker'], names)}, {sel_t['date'][:10]}) "
                "definitief verwijderen? Dit kan niet ongedaan gemaakt worden.",
                lambda: db.delete_transaction(sel_id), btn_container=a3)

    with tab_costs:
        st.subheader("🏦 Algemene rekeningkosten")
        st.caption("Kosten die niet aan een specifiek aandeel hangen (bv. beheerskosten, bewaarloon). "
                   "Ze drukken het totale rendement van de rekening, maar niet de individuele posities of de meerwaardeberekening.")
        with st.form("acct_cost_form", clear_on_submit=True):
            a1, a2, a3 = st.columns(3)
            with a1:
                ac_acct = st.selectbox("Rekening *", db.get_accounts())
                ac_date = st.date_input("Datum *", value=date.today(), min_value=date(2000,1,1), max_value=date.today())
            with a2:
                ac_amount = st.number_input("Bedrag *", min_value=0.0, step=0.01, format="%.2f")
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
            for c in costs:
                cc1, cc2, cc3 = st.columns([4, 2, 1])
                with cc1:
                    st.markdown(f"🏦 **{c['account']}** — {c.get('description') or 'kost'}")
                    st.caption(f"📅 {c['date']}")
                with cc2:
                    eur_str = f" (€{c['amount_eur']:,.2f})" if c["currency"] != "EUR" else ""
                    st.markdown(f"{c['currency']} {c['amount']:,.2f}{eur_str}")
                with cc3:
                    if st.button("🗑️", key=f"del_ac_{c['id']}"):
                        db.delete_account_cost(c["id"])
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
        div_names = {a["ticker"]: (a.get("name") or a["ticker"]) for a in assets}
        amap = {a["ticker"]: a for a in assets}
        if not tickers:
            st.warning("Voeg eerst activa toe via 🏢 Activa.")
        else:
            if st.session_state.get("div_added_msg"):
                st.success(st.session_state.pop("div_added_msg"))
            dn = st.session_state.get("div_amt_nonce", 0)
            dk = lambda s: f"div_{s}_{dn}"
            CURS = ["EUR", "USD", "GBP", "CHF"]

            cc1, cc2, cc3 = st.columns(3)
            d_ticker  = cc1.selectbox("Activum *", tickers, key=dk("tkr"),
                                      format_func=lambda t: asset_label(t, div_names))
            d_date    = cc2.date_input("Datum *", value=date.today(), min_value=date(2000,1,1), max_value=date.today(), key=dk("date"))
            d_account = cc3.selectbox("Rekening *", db.get_accounts(), key=dk("acct"),
                                      help="De rekening waarop dit dividend is uitgekeerd. "
                                           "Hetzelfde dividend op een andere rekening voer je als een aparte lijn in.")
            asset_cur = amap.get(d_ticker, {}).get("currency", "EUR")
            cur_opts  = CURS if asset_cur in CURS else CURS + [asset_cur]
            def cur_box(col, keyname):
                return col.selectbox("Munt", cur_opts, index=cur_opts.index(asset_cur),
                                     key=dk(keyname), label_visibility="collapsed")

            mode = st.radio("Invoerwijze", ["Eenvoudig", "Gedetailleerd (bronbelasting + RV)"],
                            horizontal=True, key="div_mode")

            if mode == "Eenvoudig":
                sc1, sc2 = st.columns(2)
                with sc1:
                    gross    = st.number_input("Bruto dividend *", min_value=0.0, step=0.01,
                                               format="%.2f", value=None, key=dk("s_gross"))
                    currency = st.selectbox("Munt", cur_opts, index=cur_opts.index(asset_cur), key=dk("s_cur"))
                with sc2:
                    wh_amt = st.number_input("Ingehouden voorheffing (bedrag)", min_value=0.0,
                                             step=0.01, format="%.2f", value=None, key=dk("s_wh"))
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
                                        belgian_rv_withheld=1 if w > 0 else 0, account=d_account)
                        clear_cache()
                        st.session_state["div_amt_nonce"] = dn + 1
                        st.session_state["div_added_msg"] = (
                            f"✅ Dividend {currency} {g - w:.2f} netto voor {d_ticker} op {d_account} toegevoegd!")
                        st.rerun()

            else:  # Gedetailleerd
                st.caption("Vul in wat je weet; lege velden worden waar mogelijk automatisch berekend "
                           "(zelfde munt verondersteld voor de berekening).")
                r1a, r1b = st.columns([3, 1])
                A = r1a.number_input("① Bruto dividend (vóór buitenlandse bronbelasting)",
                                     min_value=0.0, step=0.01, format="%.4f", value=None, key=dk("A"))
                A_cur = cur_box(r1b, "Acur")
                r2a, r2b = st.columns([3, 1])
                B = r2a.number_input("② Buitenlandse bronbelasting",
                                     min_value=0.0, step=0.01, format="%.4f", value=None, key=dk("B"))
                B_cur = cur_box(r2b, "Bcur")
                r3a, r3b = st.columns([3, 1])
                C = r3a.number_input("③ Bruto na bronbelasting / vóór Belgische RV",
                                     min_value=0.0, step=0.01, format="%.4f", value=None, key=dk("C"))
                C_cur = cur_box(r3b, "Ccur")
                r4a, r4b = st.columns([3, 1])
                D = r4a.number_input("④ Netto dividend (na alle voorheffingen)",
                                     min_value=0.0, step=0.01, format="%.4f", value=None, key=dk("D"))
                D_cur = cur_box(r4b, "Dcur")
                notes = st.text_area("Notities (optioneel)", height=60, key=dk("d_notes"))

                res = tax_mod.resolve_dividend_chain(A, B, C, D)
                rA, rB, rC, rD, rRV = res["a"], res["b"], res["c"], res["d"], res["rv"]
                def _f(v, cur): return "—" if v is None else f"{cur} {v:,.2f}"
                st.markdown(
                    f"**Afgeleide keten:** ① {_f(rA, A_cur)}  →  ② bronbelasting {_f(rB, B_cur)}  →  "
                    f"③ {_f(rC, C_cur)}  →  🇧🇪 RV {_f(rRV, C_cur)}  →  ④ netto {_f(rD, D_cur)}")

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
                        }
                        db.add_dividend(d_ticker, str(d_date), prim_v, wh_native, prim_cur, notes or None,
                                        fx_rate=fx_prim, gross_eur=gross_eur, withholding_eur=wh_eur,
                                        foreign_wht_withheld=1 if (rB and rB > 0) else 0,
                                        belgian_rv_withheld=1 if (rRV and rRV > 0) else 0,
                                        account=d_account, details=details)
                        clear_cache()
                        st.session_state["div_amt_nonce"] = dn + 1
                        st.session_state["div_added_msg"] = (
                            f"✅ Dividend voor {d_ticker} op {d_account} toegevoegd (netto ≈ {eur(net_eur)}).")
                        st.rerun()

    with tab_view:
        # ── Bewerkformulier (bij klik op ✏️) ──────────────────────────────────
        edit_did = st.session_state.get("edit_div")
        if edit_did:
            components.html(
                """<script>const d=window.parent.document;const el=d.querySelector('section.main')
                ||d.querySelector('[data-testid="stMain"]')||d.scrollingElement;
                if(el)el.scrollTo({top:0,behavior:'smooth'});</script>""", height=0)
            ed = next((x for x in db.get_dividends() if x["id"] == edit_did), None)
            if ed:
                st.markdown(f"### ✏️ Dividend #{edit_did} ({ed['ticker']}) bewerken")
                ecur = ed.get("currency") or "EUR"
                ECUR = ["EUR", "USD", "GBP", "CHF"]
                eopts = ECUR if ecur in ECUR else ECUR + [ecur]
                # Standaardwaarden: gebruik de keten indien aanwezig, anders de eenvoudige velden
                dA = ed.get("gross_before_wht")
                dB = ed.get("foreign_wht_amt")
                dC = ed.get("gross_after_wht")
                dD = ed.get("net_received")
                if dA is None and dB is None and dC is None and dD is None:
                    dA = ed.get("gross_amount")
                    dD = (ed.get("gross_amount") or 0) - (ed.get("withholding_tax") or 0)
                with st.form("edit_div_form"):
                    g1, g2, g3 = st.columns(3)
                    e_date = g1.date_input("Datum", value=datetime.strptime(ed["date"][:10], "%Y-%m-%d").date(),
                                           min_value=date(2000, 1, 1), max_value=date.today())
                    e_acct = g2.selectbox("Rekening", db.get_accounts(),
                                          index=db.get_accounts().index(ed.get("account") or db.DEFAULT_ACCOUNT)
                                          if (ed.get("account") or db.DEFAULT_ACCOUNT) in db.get_accounts() else 0)
                    def _ecur(col, key, stored):
                        cc = stored or ecur
                        oo = eopts if cc in eopts else eopts + [cc]
                        return col.selectbox("Munt", oo, index=oo.index(cc), key=key, label_visibility="collapsed")
                    e1a, e1b = st.columns([3, 1])
                    eA = e1a.number_input("① Bruto vóór buitenlandse bronbelasting", min_value=0.0,
                                          step=0.01, format="%.4f", value=dA, key="ediv_A")
                    eAc = _ecur(e1b, "ediv_Ac", ed.get("gross_before_wht_cur"))
                    e2a, e2b = st.columns([3, 1])
                    eB = e2a.number_input("② Buitenlandse bronbelasting", min_value=0.0,
                                          step=0.01, format="%.4f", value=dB, key="ediv_B")
                    eBc = _ecur(e2b, "ediv_Bc", ed.get("foreign_wht_cur"))
                    e3a, e3b = st.columns([3, 1])
                    eC = e3a.number_input("③ Bruto na bronbelasting / vóór Belgische RV", min_value=0.0,
                                          step=0.01, format="%.4f", value=dC, key="ediv_C")
                    eCc = _ecur(e3b, "ediv_Cc", ed.get("gross_after_wht_cur"))
                    e4a, e4b = st.columns([3, 1])
                    eD = e4a.number_input("④ Netto na alle voorheffingen", min_value=0.0,
                                          step=0.01, format="%.4f", value=dD, key="ediv_D")
                    eDc = _ecur(e4b, "ediv_Dc", ed.get("net_received_cur"))
                    e_notes = st.text_area("Notities", value=ed.get("notes") or "", height=60)
                    sd1, sd2 = st.columns(2)
                    if sd1.form_submit_button("💾 Opslaan", type="primary"):
                        res = tax_mod.resolve_dividend_chain(eA, eB, eC, eD)
                        rA, rB, rC, rD, rRV = res["a"], res["b"], res["c"], res["d"], res["rv"]
                        def _te(v, cur): return None if v is None else compute_eur(v, cur, e_date)[1]
                        a_eur, c_eur, d_eur = _te(rA, eAc), _te(rC, eCc), _te(rD, eDc)
                        gross_eur = a_eur if a_eur is not None else (c_eur if c_eur is not None else d_eur)
                        net_eur   = d_eur if d_eur is not None else c_eur
                        if gross_eur is None or net_eur is None:
                            st.error("Geef minstens een bruto- en nettowaarde in.")
                        else:
                            wh_eur = max(0.0, gross_eur - net_eur)
                            prim_v, prim_cur = ((rA, eAc) if rA is not None else
                                                (rC, eCc) if rC is not None else (rD, eDc))
                            fx_prim = compute_eur(prim_v, prim_cur, e_date)[0] or 1.0
                            db.update_dividend(
                                edit_did, date=str(e_date), account=e_acct, notes=e_notes or None,
                                currency=prim_cur, gross_amount=prim_v, withholding_tax=round(wh_eur / fx_prim, 2),
                                fx_rate=fx_prim, gross_eur=gross_eur, withholding_eur=wh_eur, net_eur=net_eur,
                                foreign_wht_withheld=1 if (rB and rB > 0) else 0,
                                belgian_rv_withheld=1 if (rRV and rRV > 0) else 0,
                                gross_before_wht=rA, gross_before_wht_cur=eAc if rA is not None else None,
                                foreign_wht_amt=rB, foreign_wht_cur=eBc if rB is not None else None,
                                gross_after_wht=rC, gross_after_wht_cur=eCc if rC is not None else None,
                                belgian_rv_amt=rRV, net_received=rD,
                                net_received_cur=eDc if rD is not None else None)
                            clear_cache()
                            st.session_state.pop("edit_div", None)
                            st.success("✅ Dividend bijgewerkt!")
                            st.rerun()
                    if sd2.form_submit_button("✖️ Annuleren"):
                        st.session_state.pop("edit_div", None)
                        st.rerun()
                st.divider()

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
        rows = []
        for d in divs:
            rows.append({
                "Datum":    d["date"][:10],
                "Activum":  asset_label(d["ticker"], names_map),
                "Rekening": d.get("account") or db.DEFAULT_ACCOUNT,
                "① Bruto":  d.get("gross_before_wht"),
                "② Bronbel.": d.get("foreign_wht_amt"),
                "③ Na bronbel.": d.get("gross_after_wht"),
                "🇧🇪 RV":   d.get("belgian_rv_amt"),
                "④ Netto":  d.get("net_received") if d.get("net_received") is not None
                            else round(d["gross_amount"] - d["withholding_tax"], 2),
                "Munt":     d.get("net_received_cur") or d.get("gross_before_wht_cur") or d["currency"],
                "Netto €":  round(_neur(d), 2),
                "Notities": d.get("notes") or "",
            })
        sel_idx = df_row_select(pd.DataFrame(rows), "div_table")
        if sel_idx is None:
            st.caption("👆 Klik op een rij om dat dividend te bewerken, verwijderen of te verplaatsen.")
        else:
            sel_d = divs[sel_idx]
            sel_did = sel_d["id"]
            div_accts = db.get_accounts()
            cur_acct = sel_d.get("account") or db.DEFAULT_ACCOUNT
            st.caption(f"Geselecteerd: **#{sel_did} · {sel_d['date'][:10]} · "
                       f"{asset_label(sel_d['ticker'], names_map)} · netto {eur(_neur(sel_d))}**")
            da1, da2, da3 = st.columns([2, 1, 1])
            new_acct = da1.selectbox("Verplaats naar rekening", div_accts,
                                     index=div_accts.index(cur_acct) if cur_acct in div_accts else 0,
                                     key=f"div_action_acct_{sel_did}")
            if new_acct != cur_acct:
                db.set_dividend_account(sel_did, new_acct)
                clear_cache()
                st.rerun()
            if da2.button("✏️ Bewerk", key="div_action_edit", width="stretch"):
                st.session_state["edit_div"] = sel_did
                st.rerun()
            delete_with_confirm(
                "🗑️ Wis", "confirm_del_div", sel_did,
                f"Dividend #{sel_did} ({asset_label(sel_d['ticker'], names_map)}, {sel_d['date'][:10]}) "
                "definitief verwijderen? Dit kan niet ongedaan gemaakt worden.",
                lambda: db.delete_dividend(sel_did), btn_container=da3)


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
            "Aantal":      f"{g['quantity']:.4f}",
            "Kostbasis":   eur(g["cost_basis"]),
            "Verkoopwaarde": eur(g["sell_total"]),
            "Winst/Verlies": eur(g["gain_loss"]),
        } for g in sorted(year_gains, key=lambda x: x["date"], reverse=True)]
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
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
                st.dataframe(pd.DataFrame(tob_rows), width='stretch', hide_index=True)


# ── PAGINA: AI Advisor ────────────────────────────────────────────────────────

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
                st.dataframe(pd.DataFrame([{
                    "Model": r["model"],
                    "Oproepen": r["n"],
                    "Input-tokens": f"{r['pt']:,}",
                    "Output-tokens": f"{r['ct']:,}",
                    "Kost (USD)": f"${r['c']:.4f}",
                } for r in usage["by_model"]]), width='stretch', hide_index=True)
            if usage["by_function"]:
                st.caption("Per functie")
                func_labels = {"tax_optimization": "Belastingadvies",
                               "daily_advice": "Dagelijks advies",
                               "market_evaluation": "Marktevaluatie (oud)",
                               "portfolio_ratings": "Portefeuille-ratings (oud)",
                               "price_target": "Koersdoel", "chat": "Overig",
                               "price_refresh": "Prijsverversing"}
                st.dataframe(pd.DataFrame([{
                    "Functie": func_labels.get(r["function"], r["function"]),
                    "Oproepen": r["n"],
                    "Kost (USD)": f"${r['c']:.4f}",
                } for r in usage["by_function"]]), width='stretch', hide_index=True)

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
            st.dataframe(pd.DataFrame([{
                "Model": m, "Input ($/1M)": f"{p[0]:.2f}", "Output ($/1M)": f"{p[1]:.2f}",
            } for m, p in pricing.items()]), width='stretch', hide_index=True)
            st.caption("ℹ️ Richtprijzen medio 2026; werkelijke kosten kunnen afwijken. "
                       "Controleer je OpenAI-dashboard voor de exacte factuur.")
        st.divider()

    # Actieve privacymodus tonen
    _plvl = ai_advisor.privacy_level()
    if _plvl != "off":
        _pl = "bedragen verborgen (percentages)" if _plvl == "amounts" else "volledig anoniem (ook tickers)"
        st.caption(f"🔒 Privacymodus actief: **{_pl}**. Pas aan via ⚙️ Instellingen → AI.")

    tab_tax, tab_daily = st.tabs([
        "💡 Belastingoptimalisatie (maandelijks)",
        "🤖 Dagelijks portefeuilleadvies",
    ])

    with tab_tax:
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

    with tab_daily:
        st.subheader("🤖 Dagelijks portefeuilleadvies")
        st.caption("Eén advies per werkdag (18:00) voor de hele portefeuille. Levert zowel dit "
                   "tekstadvies als de koop/houden/verkoop-ratings die de tabellen op de "
                   "**💼 Portefeuille**-pagina voeden.")
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

    tab_api, tab_acct, tab_tax, tab_tob, tab_data = st.tabs(
        ["🔑 API-sleutel", "🏦 Rekeningen", "🧾 Meerwaardebelasting", "🏛️ TOB-tarieven", "🗃️ Data"])

    with tab_api:
        st.subheader("OpenAI API & AI-instellingen")
        current = db.get_setting("openai_api_key", "")
        new_key = st.text_input("API-sleutel", value=current, type="password",
                                help="Beschikbaar via platform.openai.com/api-keys")

        model_keys = list(ai_advisor.AVAILABLE_MODELS.keys())
        def _model_idx(setting, default):
            cur = db.get_setting(setting, default) or default
            return model_keys.index(cur) if cur in model_keys else 0

        m1, m2 = st.columns(2)
        with m1:
            model = st.selectbox("Model voor regulier advies", model_keys,
                                 index=_model_idx("openai_model", "gpt-4.1-mini"),
                                 format_func=lambda k: ai_advisor.AVAILABLE_MODELS[k])
        with m2:
            pt_model = st.selectbox("Model voor koersdoelbepaling", model_keys,
                                    index=_model_idx("openai_price_target_model", "gpt-4.1"),
                                    format_func=lambda k: ai_advisor.AVAILABLE_MODELS[k],
                                    help="Mag een sterker (duurder) model zijn dan voor het reguliere advies.")

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
        en1, en2 = st.columns(2)
        enable_tax = en1.checkbox("Maandelijks belastingadvies actief",
                                  value=db.get_setting("ai_enable_tax", "1") != "0")
        enable_daily = en2.checkbox("Dagelijks portefeuilleadvies actief",
                                    value=db.get_setting("ai_enable_daily", "1") != "0")

        if st.button("💾 Opslaan", key="save_api"):
            db.set_setting("openai_api_key", new_key.strip())
            db.set_setting("openai_model", model)
            db.set_setting("openai_price_target_model", pt_model)
            db.set_setting("investment_volume_month", str(vol_m))
            db.set_setting("investment_volume_year", str(vol_y))
            db.set_setting("ai_privacy_mode", privacy)
            db.set_setting("ai_enable_tax", "1" if enable_tax else "0")
            db.set_setting("ai_enable_daily", "1" if enable_daily else "0")
            st.success("✅ Instellingen opgeslagen!")
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
            "Kostenbasis":    eur(s["cost_basis"]),
            "Huidige waarde": eur(s["current_value"]),
            "W/V (€)":        eur(s["gain_loss"]),
            "W/V (%)":        pct(s["gain_loss_pct"]),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width='stretch', hide_index=True)
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


# ── Navigatie ─────────────────────────────────────────────────────────────────

# ── PAGINA: Cash-grootboek ────────────────────────────────────────────────────

def page_cash():
    st.title("💶 Cash")
    st.caption("Volwaardig cash-grootboek per rekening. **Beschikbare cash** = stortingen − opnames "
               "+ verkopen − aankopen + dividenden − rekeningkosten. Toekenningen (performance shares) "
               "kosten geen brokergeld en tellen hier voor €0.")

    tab_pos, tab_add, tab_log = st.tabs(["📊 Posities", "➕ Storting / opname", "📜 Bewegingen"])

    with tab_pos:
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
                    "Stortingen":     eur(r["deposits"]),
                    "Opnames":        eur(-r["withdrawals"]),
                    "Aankopen":       eur(-r["buys"]),
                    "Verkopen":       eur(r["sells"]),
                    "Dividenden":     eur(r["dividends"]),
                    "Rekeningkosten": eur(-r["costs"]),
                    "Beschikbaar":    eur(r["available"]),
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            st.caption("Aankopen en rekeningkosten verlagen de cash (−); verkopen en dividenden verhogen ze (+). "
                       "Een negatieve beschikbare cash betekent dat er meer is uitgegeven dan gestort — "
                       "registreer dan je ontbrekende stortingen. Betaalde je de personenbelasting op "
                       "performance shares vanaf je beleggingsrekening, boek die dan als een opname.")

    with tab_add:
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
                cm_amt = cc4.number_input("Bedrag", min_value=0.0, step=0.01, format="%.2f", value=None)
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

    with tab_log:
        laccts = db.get_accounts()
        lsel = st.multiselect("Rekeningen", laccts, default=[], key="cash_log_acct",
                              placeholder="Alle rekeningen")
        ledger = db.cash_ledger(tuple(lsel) if lsel else None)
        if not ledger:
            st.info("Nog geen cashbewegingen. Voeg een storting toe of registreer transacties.")
        else:
            lbl = {"Storting": "🟢 Storting", "Opname": "🔴 Opname", "Aankoop": "🔻 Aankoop",
                   "Verkoop": "🔺 Verkoop", "Dividend": "💰 Dividend",
                   "Rekeningkost": "🧾 Rekeningkost", "Toekenning": "🎁 Toekenning"}
            rows = [{
                "Datum":    it["date"],
                "Rekening": it["account"],
                "Type":     lbl.get(it["label"], it["label"]),
                "Omschrijving": it["desc"],
                "Mutatie":  eur(it["delta"]),
                "Saldo":    eur(it["balance"]),
            } for it in reversed(ledger)]   # nieuwste bovenaan
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
            st.caption("Volledig grootboek: stortingen/opnames samen met de automatisch afgeleide "
                       "bewegingen uit aankopen (−), verkopen (+), dividenden (+) en rekeningkosten (−). "
                       "'Saldo' is het lopende cashsaldo per rekening. Toekenningen (performance shares) "
                       "staan als €0 (geen cash).")

            # Enkel handmatige bewegingen kunnen verwijderd worden
            manual = [it for it in ledger if it["source"] == "manual"]
            if manual:
                st.divider()
                st.caption("Een handmatige storting/opname verwijderen:")
                opts = {it["ref"]: f"{it['date']} · {it['account']} · {it['label']} · {eur(it['delta'])}"
                        for it in reversed(manual)}
                dsel = st.selectbox("Beweging", list(opts.keys()),
                                    format_func=lambda i: opts[i], key="cash_del_sel",
                                    label_visibility="collapsed")
                delete_with_confirm(
                    "🗑️ Wis beweging", "confirm_del_cash", dsel,
                    f"Handmatige cashbeweging #{dsel} definitief verwijderen?",
                    lambda: db.delete_cash_movement(dsel))


PAGES = {
    "📊 Dashboard":            page_dashboard,
    "💼 Portefeuille":         page_portfolio,
    "💶 Cash":                 page_cash,
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
    st.caption("🤖 AI: 3× per dag + 08:00")

PAGES[selected]()