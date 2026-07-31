"""
views/cash.py — pagina 'Cash'.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import streamlit as st

import database as db

from views.common import (
    _section_radio, clear_cache, compute_eur, eur, multiselect_delete,
    show_df
)

logger = logging.getLogger("app.cash")


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
