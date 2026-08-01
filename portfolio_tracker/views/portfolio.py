"""
views/portfolio.py — pagina 'Portefeuille'.
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
import market_data as md

from views.common import (
    RATING_BADGE, account_filter_widget, ai_badge, asset_label,
    asset_name_map, clear_cache, delta_color, dividend_net_eur,
    dividends_net_eur, eur, get_overview, num, pct, per_asset_result,
    perf_mode, perf_net, render_realized_history, show_df, sign_icon,
    sticky, sticky_save
)

logger = logging.getLogger("app.portfolio")


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
    accset = set(acct) if acct else None

    # Dividenden per activum, MET de rekeningfilter. Zonder die filter zou een
    # dividend blijven meetellen van een rekening waarop de positie intussen
    # gesloten is (bv. hetzelfde aandeel op twee rekeningen, waarvan er één
    # verkocht is) — dan toont de tabel met open posities dividenden die niets met
    # de getoonde positie te maken hebben.
    divs_net = {}
    for d in db.get_dividends():
        if accset is not None and (d.get("account") or db.DEFAULT_ACCOUNT) not in accset:
            continue
        divs_net[d["ticker"]] = divs_net.get(d["ticker"], 0) + dividend_net_eur(d)

    # Koersdoelen (punt 1): een HANDMATIG koersdoel heeft altijd voorrang — op het
    # activum, anders het laatste transactie-koersdoel. Is er geen handmatig doel, dan
    # tonen we het GEMIDDELDE van de laatste 9 AI-bepalingen (of minder als er minder
    # zijn). Nulwaarden ('niet bepaald') tellen nooit mee (punt 2).
    manual_asset, manual_txn = {}, {}
    for a in db.get_assets():
        if a.get("price_target"):
            manual_asset[a["ticker"]] = a["price_target"]
    for t in db.get_transactions():           # ASC op datum -> laatste wint
        if t.get("price_target"):
            manual_txn[t["ticker"]] = t["price_target"]
    price_targets, target_meta = {}, {}
    for tk in pv:
        eff = db.get_effective_price_target(
            tk, 9, manual_asset=manual_asset.get(tk), manual_txn=manual_txn.get(tk))
        if eff.get("value") is not None:
            price_targets[tk] = eff["value"]
        target_meta[tk] = eff

    nmap = asset_name_map()
    sec_map = db.get_asset_sectors()

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
        if acct:
            st.caption(f"📂 Gefilterd op **{', '.join(acct)}** — ook de kolom *Dividend* volgt "
                       "die filter. Heb je hetzelfde aandeel op meerdere rekeningen gehad, dan "
                       "tellen enkel de dividenden van de geselecteerde rekening(en) mee.")
        # Blokkering (werkgeversplannen/FCPE): vrij vs. geblokkeerd deel per positie.
        # Komt uit het gecachete overzicht, dat dezelfde rekeningfilter toepast als
        # de rest van de tabel — geen tweede FIFO-pass per render.
        _lk_by = (overview.get("locked") or {}).get("by_ticker") or {}
        any_locked = bool(_lk_by)
        locked_val_total = 0.0
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
            _qty = pos["quantity"] or 0.0
            _lqty = min(_lk_by.get(ticker, {}).get("locked_qty", 0.0), _qty)
            if _lqty and _qty:
                locked_val_total += (pos["current_value"] or 0.0) * (_lqty / _qty)
            row = {
                "":             sign_icon(pos["unrealized_gain_loss"]),
                "Ticker":       ticker,
                "Naam":         (asset.get("name") or ticker)[:20],
                "Sector":       sec_map.get(ticker) or "—",
                "Munt":         pos["current_price_currency"] or "EUR",
                "Aantal":       pos["quantity"],
            }
            if any_locked:
                row["Vrij"] = round(_qty - _lqty, 6)
                row["🔒 Geblokkeerd"] = round(_lqty, 6) if _lqty else None
                row["🔓 Vrij vanaf"] = _lk_by.get(ticker, {}).get("next_unlock") if _lqty else None
            row.update({
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
            rows.append(row)
        _pos_cfg = {
            "Sector":           st.column_config.TextColumn(
                help="Domein/sector van dit activum. Toewijzen doe je op de pagina "
                     "🏢 Activa (kolom Sector); '—' betekent nog niet toegewezen."),
            "Aantal":           st.column_config.NumberColumn(format="%.10g"),
            "Gem.kostpr.(€)":   st.column_config.NumberColumn(format="%.10g"),
            "Koers (native)":   st.column_config.NumberColumn(format="%.10g"),
            "Koersdoel":        st.column_config.NumberColumn(
                format="%.10g",
                help="Een HANDMATIG koersdoel (op het activum, anders van de laatste "
                     "transactie) heeft altijd voorrang. Is er geen handmatig doel, dan is dit "
                     "het GEMIDDELDE van de laatste 9 AI-bepalingen (of minder als er minder "
                     "zijn). Koersdoelen van 0 tellen als 'niet bepaald' en worden niet "
                     "meegerekend. De volledige tijdlijn staat op de pagina Evolutie."),
            "Potentieel":       st.column_config.NumberColumn(format="%+.10g%%"),
            "Huidige waarde":   st.column_config.NumberColumn(format="€ %.10g"),
            "W/V (%)":          st.column_config.NumberColumn(format="%+.10g%%"),
            "Dividend":         st.column_config.NumberColumn(format="€ %.10g"),
            "Tot. rendement":   st.column_config.NumberColumn(format="€ %.10g"),
        }
        if any_locked:
            _pos_cfg["Vrij"] = st.column_config.NumberColumn(
                format="%.10g",
                help="Aantal stukken dat vandaag vrij verhandelbaar is (aantal − geblokkeerd).")
            _pos_cfg["🔒 Geblokkeerd"] = st.column_config.NumberColumn(
                format="%.10g",
                help="Aantal stukken dat nog geblokkeerd is (bv. werkgeversplan/FCPE). "
                     "Volgt de 'vrij vanaf'-datum van de aankooploten (in te stellen bij het "
                     "toevoegen van een transactie of in de transactietabel, kolom "
                     "'Vrij vanaf').")
            _pos_cfg["🔓 Vrij vanaf"] = st.column_config.TextColumn(
                help="Eerstvolgende datum waarop (een deel van) de geblokkeerde stukken "
                     "vrijkomt.")
        show_df(pd.DataFrame(rows), width="stretch", hide_index=True, height=420,
                column_config=_pos_cfg)

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
        if any_locked:
            st.caption(f"🔒 **Geblokkeerd kapitaal** (deze selectie): **{eur(locked_val_total)}** "
                       f"van de totale waarde is (nog) niet vrij verhandelbaar — vrij "
                       f"beschikbaar: **{eur(max(0.0, total_val - locked_val_total))}**. "
                       "Zie de kolommen 'Vrij' / '🔒 Geblokkeerd' hierboven; de 'vrij "
                       "vanaf'-datum stel je in per aankooplot op de transactiepagina.")
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
                if not ai_advisor.openai_key():
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

    def render_sectors():
        st.subheader("🥧 Spreiding per domein / sector")
        rows, unknown = {}, []
        for ticker, pos in pv.items():
            val = pos.get("current_value") or 0.0
            if val <= 0:
                continue
            s = sec_map.get(ticker)
            if not s:
                unknown.append(ticker)
                s = db.SECTOR_UNKNOWN
            rows[s] = rows.get(s, 0.0) + val
        if not rows:
            st.info("Geen posities met een waarde om te verdelen.")
            return

        SEC_VALUE, SEC_COST = "💰 Huidige waarde", "📥 Geïnvesteerd kapitaal"
        sticky("port_sec_basis", SEC_VALUE, [SEC_VALUE, SEC_COST])
        basis = st.radio("Verdeling volgens", [SEC_VALUE, SEC_COST], horizontal=True,
                         key="port_sec_basis", label_visibility="collapsed",
                         help="Huidige waarde toont het gewicht van elke sector vandaag. "
                              "Geïnvesteerd kapitaal toont hoe je je geld oorspronkelijk "
                              "verdeeld hebt — het verschil tussen beide laat zien welke "
                              "sectoren zwaarder of lichter zijn gaan wegen.")
        sticky_save("port_sec_basis")
        if basis == SEC_COST:
            rows = {}
            for ticker, pos in pv.items():
                val = pos.get("total_cost") or 0.0
                if val <= 0:
                    continue
                rows[sec_map.get(ticker) or db.SECTOR_UNKNOWN] = \
                    rows.get(sec_map.get(ticker) or db.SECTOR_UNKNOWN, 0.0) + val

        labels = sorted(rows, key=lambda s: -rows[s])
        values = [rows[s] for s in labels]
        total = sum(values) or 1.0
        fig = go.Figure(go.Pie(
            labels=labels, values=values, hole=0.45,
            textinfo="label+percent", sort=False,
            hovertemplate="<b>%{label}</b><br>€%{value:,.2f} (%{percent})<extra></extra>",
        ))
        fig.update_layout(
            title=("Spreiding per sector — " + ("huidige waarde" if basis == SEC_VALUE
                                                else "geïnvesteerd kapitaal")),
            height=380, margin=dict(t=45, b=0, l=0, r=0),
            paper_bgcolor="rgba(0,0,0,0)", showlegend=True,
        )
        pc1, pc2 = st.columns([3, 2])
        with pc1:
            st.plotly_chart(fig, width="stretch")
        with pc2:
            st.markdown("**Gewicht per sector**")
            show_df(pd.DataFrame([{
                "Sector": s,
                "Bedrag": rows[s],
                "Aandeel": rows[s] / total * 100,
            } for s in labels]), width="stretch", hide_index=True, column_config={
                "Bedrag":  st.column_config.NumberColumn(format="€ %.10g"),
                "Aandeel": st.column_config.NumberColumn(format="%.10g%%"),
            })
            _top = labels[0]
            _share = rows[_top] / total * 100
            if _share >= 40:
                st.warning(f"⚠️ **{_share:.0f}%** van deze selectie zit in één sector "
                           f"(*{_top}*). Dat is een concentratierisico: gaat die sector "
                           "onderuit, dan volgt je hele portefeuille mee. Geen advies — "
                           "wel iets om bewust te kiezen.")

        if unknown:
            st.caption(f"ℹ️ **{len(unknown)} activum/activa zonder sector** — "
                       + ", ".join(asset_label(t, nmap) for t in unknown[:12])
                       + ("…" if len(unknown) > 12 else "")
                       + ".  Ze staan samen onder *Niet toegewezen*. Ken ze een domein toe "
                         "via **🏢 Activa → 📋 Overzicht** (kolom *Sector*), of laat ze daar "
                         "in één keer online ophalen met de knop *Sectoren ophalen*.")
        st.caption("De sectorindeling volgt de gangbare GICS-hoofdsectoren. Een brede "
                   "indextracker hoort per definitie in geen enkele sector thuis — die zet "
                   "je best op *Gediversifieerd (index/fonds)*, anders lijkt je portefeuille "
                   "geconcentreerder dan ze is.")

    def render_unlock_calendar():
        """Deblokkeringskalender: wanneer komt hoeveel geblokkeerd kapitaal vrij?

        Voor werkgeversplannen (FCPE en dergelijke) met meerdere jaargangen is dat de
        vraag die er echt toe doet — niet 'hoeveel zit vast', maar 'wanneer kan ik erbij
        en wat is het dan waard'. De waarde is de HUIDIGE waarde van die stukken, geen
        voorspelling: wat ze op de dag van deblokkering waard zijn, weet niemand.
        """
        _txns = [t for t in db.get_transactions()
                 if accset is None or (t.get("account") or db.DEFAULT_ACCOUNT) in accset]
        sch = tax_mod.unlock_schedule(_txns, prices)
        rows = sch["by_date"]
        st.subheader("🔓 Deblokkeringskalender")
        if not rows:
            st.caption(
                "Geen geblokkeerde stukken in deze selectie. Heb je effecten uit een "
                "werkgeversplan met een resterende blokkeringsperiode, geef het aankooplot "
                "dan een *vrij vanaf*-datum mee (➕ Transacties, of de kolom **Vrij vanaf** "
                "in de transactietabel). Ze verschijnen dan hier op een tijdlijn.")
            return

        t = sch["totals"]
        u1, u2, u3 = st.columns(3)
        u1.metric("🔒 Geblokkeerd", eur(t["locked_value"]),
                  help=f"{num(t['locked_qty'], 4)} stuk(s), tegen de huidige koers.")
        u2.metric("🔓 Vrij beschikbaar", eur(t["free_value"]))
        u3.metric("Eerstvolgende deblokkering",
                  f"{rows[0]['date'][8:10]}/{rows[0]['date'][5:7]}/{rows[0]['date'][:4]}",
                  delta=f"over {rows[0]['days_until']} dagen", delta_color="off")
        if not t["priced_ok"]:
            st.caption("⚠️ Voor een deel van deze stukken is er geen actuele koers; "
                       "daar toont de kalender de **kostbasis** in plaats van de "
                       "marktwaarde.")

        _cum, chart_rows = 0.0, []
        for b in rows:
            _cum += b["value_eur"]
            chart_rows.append({"Datum": b["date"], "Komt vrij €": round(b["value_eur"], 2),
                               "Cumulatief vrij €": round(_cum, 2)})
        cdf = pd.DataFrame(chart_rows)
        fig = go.Figure()
        fig.add_bar(x=cdf["Datum"], y=cdf["Komt vrij €"], name="Komt vrij",
                    marker_color="#4c9be8")
        fig.add_scatter(x=cdf["Datum"], y=cdf["Cumulatief vrij €"], name="Cumulatief",
                        mode="lines+markers", line=dict(color="#f0a202"))
        fig.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=0),
                          yaxis_title="EUR", xaxis_title=None,
                          legend=dict(orientation="h", y=1.1))
        st.plotly_chart(fig, width="stretch")

        show_df(pd.DataFrame([{
            "Vrij vanaf":   b["date"],
            "Over (dagen)": b["days_until"],
            "Activa":       ", ".join(asset_label(x, nmap) for x in b["tickers"]),
            "Aantal":       b["quantity"],
            "Kostbasis €":  round(b["cost_eur"], 2),
            "Waarde nu €":  round(b["value_eur"], 2),
            "Cumulatief €": round(c["Cumulatief vrij €"], 2),
        } for b, c in zip(rows, chart_rows)]), width="stretch", hide_index=True,
            column_config={
                "Aantal":       st.column_config.NumberColumn(format="%.10g"),
                "Kostbasis €":  st.column_config.NumberColumn(format="€ %.10g"),
                "Waarde nu €":  st.column_config.NumberColumn(format="€ %.10g"),
                "Cumulatief €": st.column_config.NumberColumn(
                    format="€ %.10g",
                    help="Totaal dat vanaf die datum vrij verhandelbaar is."),
            })

        with st.expander(f"📄 Detail per lot ({len(sch['events'])})"):
            show_df(pd.DataFrame([{
                "Vrij vanaf": e["date"],
                "Activum":    asset_label(e["ticker"], nmap),
                "Rekening":   e["account"],
                "Aantal":     e["quantity"],
                "Kostbasis €": round(e["cost_eur"], 2),
                "Waarde nu €": round(e["value_eur"], 2),
            } for e in sch["events"]]), width="stretch", hide_index=True)
        st.caption("De waarde is de huidige marktwaarde van die stukken, geen prognose. "
                   "Verkopen vóór de datum kan de app niet tegenhouden — ze waarschuwt "
                   "wel in het verkoopformulier.")

    # Volgorde: open posities → deblokkeringskalender → sectorspreiding →
    # totaal per activum → gerealiseerde historiek → AI-synthese → prijsgeschiedenis
    render_positions()
    st.divider()
    render_unlock_calendar()
    st.divider()
    render_sectors()
    st.divider()
    render_per_asset()
    st.divider()
    render_realized()
    st.divider()
    render_ai_synth()
    st.divider()
    render_price_history()
