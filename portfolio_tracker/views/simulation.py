"""
views/simulation.py — pagina 'Simulatie'.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import streamlit as st

import belgian_tax as tax_mod
import database as db
import market_data as md

from views.common import (
    compute_eur, delta_color, eur
)

logger = logging.getLogger("app.simulation")


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
