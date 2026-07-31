"""
views/ai.py — pagina 'AI Advisor en marktopportuniteiten'.
"""
from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

import ai_advisor
import database as db
import market_data as md

from views.common import (
    _section_radio, ai_badge, clear_cache, delta_color, eur, pct, show_df,
    sign_icon
)

logger = logging.getLogger("app.ai")


# ── PAGINA: AI Advisor ────────────────────────────────────────────────────────

def render_market_opportunities():
    """Luik 2: koopopportuniteiten uit de wereldwijde markt + de opvolging ervan
    over 7 dagen, 1 maand en 3 maanden (met het gemiddelde advies per periode)."""
    st.subheader("② 🌍 Marktopportuniteiten — buiten je portefeuille")
    st.caption("Elke werkdag (07:45, vóór de opening) speurt de AI de wereldwijde markt af naar "
               "**nieuwe** koopideeën op basis van bedrijfsprestaties, vooruitzichten, "
               "macro-economie, geopolitiek en financiële berichtgeving: **2 defensieve** "
               "(groei + eventueel dividend), **2 matig speculatieve** en **2 sterk speculatieve** "
               "aandelen — elk met onderbouwing, katalysatoren en risico's. Per categorie zit er "
               "altijd minstens één **niet-Amerikaanse** naam bij, en aandelen die je al in "
               "portefeuille hebt vallen automatisch weg uit de lijst.")

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
            if res.get("skipped_held"):
                st.info("ℹ️ Weggelaten omdat je ze al bezit: "
                        + ", ".join(sorted(set(res["skipped_held"]))))
            if res.get("us_only"):
                st.warning("⚠️ Enkel Amerikaanse namen in: " + ", ".join(res["us_only"])
                           + ". Er werd wél om minstens één niet-Amerikaans aandeel per "
                             "categorie gevraagd — genereer eventueel opnieuw.")
        st.rerun()

    # ── De ideeën van de laatste ronde ───────────────────────────────────────
    batch = db.get_latest_idea_batch()
    if not batch:
        st.info("Nog geen marktopportuniteiten. Klik hierboven of wacht op de dagelijkse run.")
        return

    all_ideas = db.get_market_ideas(batch_id=batch)
    _held = ai_advisor.held_keys()
    ideas, _now_held = [], []
    for i in all_ideas:
        if ai_advisor.is_held(i["ticker"], i.get("isin") or "", _held):
            _now_held.append(i["ticker"])
        else:
            ideas.append(i)
    if not ideas:
        st.info("Alle ideeën van deze ronde zitten intussen als open positie in je "
                "portefeuille — er blijft dus niets over om nog voor te stellen.")
        return
    note = db.get_ai_evaluations("market_ideas", limit=1)
    st.markdown(f"#### 📅 Ideeën van {ideas[0]['idea_date']}")
    if _now_held:
        st.caption("✅ Intussen gekocht (en dus uit de lijst gehaald): "
                   + ", ".join(sorted(set(_now_held))))
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
        if not any(not ai_advisor.is_us_listing(r["ticker"], r.get("exchange") or "",
                                                r.get("currency") or "", r.get("isin") or "")
                   for r in rows):
            st.caption("⚠️ Enkel Amerikaanse noteringen in deze categorie — er is nochtans "
                       "om minstens één niet-Amerikaanse naam gevraagd.")
        cols = st.columns(len(rows))
        for col, it in zip(cols, rows):
            with col:
                with st.container(border=True):
                    _us = ai_advisor.is_us_listing(it["ticker"], it.get("exchange") or "",
                                                   it.get("currency") or "", it.get("isin") or "")
                    st.markdown(f"**{it.get('name') or it['ticker']}** · `{it['ticker']}`"
                                + ("" if _us else " 🌍"))
                    meta = [it.get("exchange") or "", it.get("currency") or ""]
                    st.caption(" · ".join(m for m in meta if m)
                               + ("" if _us else "  ·  niet-Amerikaanse notering"))
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

    api_key = ai_advisor.openai_key()
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
                if not ai_advisor.openai_key():
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
