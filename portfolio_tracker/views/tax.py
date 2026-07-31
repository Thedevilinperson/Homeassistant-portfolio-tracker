"""
views/tax.py — pagina 'Belgische belasting'.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import streamlit as st

import belgian_tax as tax_mod
import database as db

from views.common import (
    delta_color, eur, get_overview, pct, show_df, sign_icon
)

logger = logging.getLogger("app.tax")


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
