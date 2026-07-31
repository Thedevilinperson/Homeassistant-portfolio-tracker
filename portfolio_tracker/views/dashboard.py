"""
views/dashboard.py — pagina 'Dashboard'.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import ai_advisor
import belgian_tax as tax_mod
import database as db

from views.common import (
    PERF_MODES, PERF_MODE_LABELS, RATING_BADGE, _short_ts,
    account_filter_widget, asset_label, asset_name_map, change_arrow,
    daily_pl, delta_color, dividends_net_eur, eur, get_overview,
    has_income_tax, num, pct, per_asset_result, perf_held_summary,
    perf_mode, perf_net, render_realized_history, show_df, sign_icon,
    sticky, sticky_save
)

logger = logging.getLogger("app.dashboard")


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
    # Blokkering (werkgeversplannen/FCPE): toon het niet-vrij-verhandelbare deel van de
    # portefeuille — enkel als er effectief iets geblokkeerd is, anders geen ruis.
    try:
        # Komt uit het gecachete overzicht — geen tweede FIFO-pass per render.
        _lk_d = (overview.get("locked") or {}).get("by_ticker") or {}
        if _lk_d:
            _lk_val = 0.0
            for _t, _info in _lk_d.items():
                _p = pv.get(_t)
                if _p and (_p.get("quantity") or 0) > 0:
                    _lk_val += (_p.get("current_value") or 0.0) * \
                               min(1.0, _info["locked_qty"] / _p["quantity"])
            if _lk_val > 0:
                st.caption(f"🔒 **Geblokkeerd kapitaal** (deze selectie): **{eur(_lk_val)}** is "
                           "(nog) niet vrij verhandelbaar (bv. werkgeversplannen). Detail per "
                           "positie op de **💼 Portefeuille**-pagina.")
    except Exception:
        pass

    st.divider()

    # ── Dagresultaat per positie ─────────────────────────────────────────────
    st.subheader("📆 Dagresultaat vandaag")
    dpl = daily_pl(pv, accset)
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
        _chg = db.get_last_price_changes(list(dpl))
        drows = []
        for t in sorted(dpl, key=lambda x: dpl[x]["pl_eur"], reverse=True):
            d = dpl[t]
            _mark = ""
            if d["bought_today"] and d["sold_today"]:
                _mark = f"🔁 {num(d['bought_today'], 4)} bij / {num(d['sold_today'], 4)} af"
            elif d["bought_today"]:
                _mark = f"📥 {num(d['bought_today'], 4)}"
            elif d["sold_today"]:
                _mark = f"📤 {num(d['sold_today'], 4)}"
            drows.append({
                "": sign_icon(d["pl_eur"]),
                "Activum":        asset_label(t, names_dp),
                "Aantal":         d["quantity"],
                "Gem. waarde (€)": pv[t]["avg_cost"],
                "Vorige slot":    d["prev"],
                "Referentie":     d["ref"],
                "Koers nu":       d["price"],
                "Δ vandaag (%)":  d["change_pct"],
                "Dag-P/L (€)":    d["pl_eur"],
                "Huidige waarde": pv[t]["current_value"],
                "Vandaag":        _mark,
                "Koers gewijzigd": _short_ts((_chg.get(t.upper()) or {}).get("timestamp")),
            })
        show_df(pd.DataFrame(drows), width="stretch", hide_index=True, column_config={
            "Aantal":         st.column_config.NumberColumn(format="%.10g"),
            "Gem. waarde (€)": st.column_config.NumberColumn(
                format="€ %.10g",
                help="Gemiddelde aankoopwaarde per stuk (kostbasis in euro, FIFO). Dit is "
                     "wat je gemiddeld voor één stuk betaald hebt — koersen en de vorige "
                     "slotkoers hiernaast staan in de NATIVE munt, dit bedrag in euro. "
                     "Vergelijk het met 'Koers nu' om te zien hoe ver de positie in het "
                     "totaal boven of onder water staat, los van de beweging van vandaag."),
            "Vorige slot":    st.column_config.NumberColumn(
                format="%.10g",
                help="Laatste vastgelegde koers van de vorige beursdag (native munt)."),
            "Referentie":     st.column_config.NumberColumn(
                format="%.10g",
                help="De koers waartegen de dagwinst gemeten wordt (native munt). Zonder "
                     "transacties vandaag is dat gewoon de vorige slotkoers. Kocht of "
                     "verkocht je vandaag, dan is dit het GEWOGEN GEMIDDELDE van de vorige "
                     "slotkoers (voor de stukken die je al had) en de effectieve prijs van "
                     "elke transactie van vandaag — zo krijg je geen winst of verlies "
                     "toegerekend van vóór je aankoop."),
            "Koers nu":       st.column_config.NumberColumn(format="%.10g"),
            "Δ vandaag (%)":  st.column_config.NumberColumn(format="%+.10g%%"),
            "Dag-P/L (€)":    st.column_config.NumberColumn(format="€ %+.10g"),
            "Huidige waarde": st.column_config.NumberColumn(format="€ %.10g"),
            "Vandaag":        st.column_config.TextColumn(
                help="Transacties van vandaag op de geselecteerde rekeningen: 📥 bijgekocht, "
                     "📤 verkocht, 🔁 allebei. Die worden in de dag-P/L verrekend tegen hun "
                     "eigen aankoop- of verkoopprijs."),
            "Koers gewijzigd": st.column_config.TextColumn(
                help="Tijdstip (DD/MM UU:MM, Brusselse tijd) waarop de koers voor het LAATST "
                     "VERANDERDE — niet wanneer ze laatst werd opgehaald. De app haalt ook op "
                     "momenten dat de markt dicht is (weekend, feestdagen); die ophalingen "
                     "leveren dezelfde koers op en verschuiven dit tijdstip dus niet. Blijft "
                     "dit ver in het verleden staan terwijl de markt open was, dan is er "
                     "wellicht een echt probleem (bv. een tickerwijziging) — zie de pagina "
                     "Status."),
        })
        _missing = [t for t in pv if t not in dpl]
        _traded = [t for t in dpl if dpl[t]["n_txn"]]
        cap = ("Referentie = de laatste vastgelegde koers van de vorige (beurs)dag, gewogen "
               "met de prijs van je transacties van vandaag. Koersen, vorige slotkoersen en "
               "de referentie staan in de native munt; de gemiddelde waarde en de dag-P/L "
               "staan in euro. 'Koers gewijzigd' = wanneer de koers voor het laatst "
               "effectief veranderde, niet wanneer ze laatst werd opgehaald.")
        if _traded:
            cap += ("  ·  📥/📤 Vandaag verhandeld: "
                    + ", ".join(names_dp.get(t, t) for t in _traded)
                    + ". Voor die posities telt enkel de beweging ná jouw aankoop "
                      "(of vóór je verkoop) mee — niet de volledige dagbeweging.")
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
