"""
views/transactions.py — pagina 'Transacties'.
"""
from __future__ import annotations

import logging
from datetime import date
from datetime import datetime

import pandas as pd
import streamlit as st

import ai_advisor
import belgian_tax as tax_mod
import database as db

from views.common import (
    _cell_eq, _date_or_none, _recompute_tob_preview, _section_radio,
    asset_label, clear_cache, compute_eur, eur, fx_lookup,
    multiselect_delete, num, pct, show_df, sticky_select
)

logger = logging.getLogger("app.transactions")


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
                if not ai_advisor.openai_key():
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
                _auto_tob = tob_amount
                tob_amount = st.number_input("TOB (€)", min_value=0.0, value=tob_amount,
                                             step=0.01, format="%.10g", key=kk("tob_val"))
                if abs(tob_amount - _auto_tob) >= 0.01:
                    st.caption(f"ℹ️ Automatisch berekend op de huidige EUR-tegenwaarde: "
                               f"**€{_auto_tob:,.2f}** (verschil {eur(tob_amount - _auto_tob)}). "
                               "Wijzig je hierboven nog de wisselkoers, dan volgt dit veld niet "
                               "mee — het is nu jouw waarde. Klopt je broker's afrekening met "
                               "dit bedrag, dan is dat prima; anders zet je het vinkje even uit "
                               "en weer aan om de berekende waarde over te nemen.")
        # Blokkering (bv. werkgeversplan/FCPE): dit lot is pas vanaf een bepaalde
        # datum vrij verhandelbaar. Enkel bij aankopen/toekenningen relevant.
        lock_until = None
        if txn_type == "buy":
            if st.checkbox("🔒 (Nog) niet vrij verhandelbaar — geblokkeerd tot een datum",
                           key=kk("lock_chk"),
                           help="Voor stukken uit werkgeversplannen (bv. FCPE-fondsen) met een "
                                "resterende blokkeringsperiode. De portefeuille toont ze dan "
                                "apart als geblokkeerd kapitaal, en het verkoopformulier "
                                "waarschuwt als je meer wil verkopen dan er vrij is."):
                lock_until = st.date_input(
                    "🔓 Vrij verhandelbaar vanaf", value=date.today(),
                    min_value=date(2000, 1, 1), max_value=date(2100, 12, 31),
                    key=kk("lock_date"),
                    help="Vanaf deze datum (inbegrepen) telt dit lot als vrij. Tot de dag "
                         "ervoor verschijnt het als geblokkeerd kapitaal.")
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
                    else:
                        # Blokkering: waarschuwen (niet blokkeren) als de verkoop het VRIJE
                        # deel overschrijdt — detectie zonder automatische toepassing. In de
                        # praktijk kan zo'n verkoop niet bij de beheerder, dus dit wijst
                        # meestal op een vergeten of foute 'vrij vanaf'-datum.
                        _lk = tax_mod.locked_summary(upto, on_date=str(txn_date))
                        _lqty = _lk["by_key"].get((ticker, account), {}).get("locked_qty", 0.0)
                        if _lqty and quantity - (available - _lqty) > 1e-6:
                            st.warning(
                                f"⚠️ Op {txn_date} is **{_lqty:.4f}** stuk(s) van deze positie "
                                f"nog geblokkeerd (vrij: {max(0.0, available - _lqty):.4f}). "
                                "Deze verkoop raakt dus (deels) aan geblokkeerde stukken. De "
                                "transactie wordt wél opgeslagen — controleer of de 'vrij "
                                "vanaf'-datum van je aankooploten nog klopt.")
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
                                       tob_manual=int(bool(st.session_state.get(kk("tob_man")))),
                                       lock_until=(str(lock_until) if lock_until else None))
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
                "Vrij vanaf": (t.get("lock_until") or "")[:10],
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
                "Vrij vanaf": cc.TextColumn(
                    help="Blokkering (bv. werkgeversplan/FCPE): dit lot is pas VANAF deze datum "
                         "(JJJJ-MM-DD) vrij verhandelbaar. Leeg = nooit geblokkeerd. De "
                         "portefeuille toont geblokkeerde stukken apart als niet-vrij kapitaal."),
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
                            "FX-koers", "FX eigen", "TOB €", "TOB eigen", "Vrij vanaf")):
                        continue
                    nd = _date_or_none(str(r["Datum"]))
                    if nd is None:
                        problems.append(f"#{t['id']}: datum '{r['Datum']}' ongeldig (JJJJ-MM-DD).")
                        continue
                    _lock_raw = "" if (r["Vrij vanaf"] is None or pd.isna(r["Vrij vanaf"])) \
                                else str(r["Vrij vanaf"]).strip()
                    if _lock_raw:
                        _lock_d = _date_or_none(_lock_raw)
                        if _lock_d is None:
                            problems.append(f"#{t['id']}: 'Vrij vanaf' '{_lock_raw}' ongeldig "
                                            "(JJJJ-MM-DD, of leeg voor niet geblokkeerd).")
                            continue
                        new_lock = str(_lock_d)
                    else:
                        new_lock = None
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
                    if perf or t.get("is_stock_dividend"):
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
                        fx_manual=fx_man, tob_manual=tob_man, lock_until=new_lock)
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
                "De TOB is een Belgische heffing op de **EUR-tegenwaarde**. Verandert die "
                "tegenwaarde, dan verandert de TOB mee — of je nu de marktkoers gebruikt of "
                "je eigen brokerkoers. Deze controle herberekent beide en toont het verschil.\n\n"
                "• Lijnen met een **eigen wisselkoers** behouden **jouw** koers; enkel de "
                "EUR-tegenwaarde en de TOB worden erop hertekend. Zo blijft de koers die je "
                "broker echt gebruikt heeft bewaard, terwijl de beurstaks wél klopt.\n"
                "• Alle andere lijnen krijgen de historische marktkoers van hun "
                "transactiedatum. In oudere versies kon die stilzwijgend op 1,0 blijven "
                "staan wanneer ze niet opgehaald raakte — dan werd het tarief op het bedrag "
                "in **vreemde munt** toegepast, en was de TOB fout.\n"
                "• Lijnen met een **handmatige TOB** en toekenningen blijven ongemoeid.")
            rt_changes, rt_suspect = _recompute_tob_preview(txns, ainfo)
            if not rt_changes:
                st.success("✅ Alle transacties in deze selectie kloppen — niets te herberekenen.")
            else:
                _dtob = sum(c["nieuw_tob"] - c["oud_tob"] for c in rt_changes)
                _neigen = sum(1 for c in rt_changes if c.get("eigen_fx"))
                st.warning(
                    f"**{len(rt_changes)} transactie(s)** zouden wijzigen"
                    + (f", waarvan **{rt_suspect}** met een TOB die duidelijk op de vréémde munt "
                       "berekend lijkt" if rt_suspect else "")
                    + (f" en **{_neigen}** met een eigen wisselkoers (die koers blijft behouden)"
                       if _neigen else "")
                    + f". Verschil in totale TOB: **{eur(_dtob)}**.")
                show_df(pd.DataFrame([{
                    "": "🚩" if c["verdacht"] else ("💱" if c.get("eigen_fx") else ""),
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
                           "bedrag in vréémde munt — dat is precies de oude fout.  "
                           "💱 = eigen wisselkoers; die blijft ongewijzigd, enkel de "
                           "EUR-tegenwaarde en de TOB worden bijgewerkt.")
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
