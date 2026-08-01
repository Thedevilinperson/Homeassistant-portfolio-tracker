"""
views/dividends.py — pagina 'Dividenden'.
"""
from __future__ import annotations

import logging
from datetime import date
from datetime import datetime

import pandas as pd
import streamlit as st

import belgian_tax as tax_mod
import database as db

from views.common import (
    _cell_eq, _date_or_none, _div_fx_widget, _recompute_dividend_chain,
    asset_label, asset_name_map, clear_cache, compute_eur,
    dividend_gross_eur, dividend_net_eur, eur, multiselect_delete, show_df
)

logger = logging.getLogger("app.dividends")


# ── PAGINA: Dividenden ────────────────────────────────────────────────────────

def page_dividends():
    st.title("💰 Dividenden")

    assets = db.get_assets()

    _div_section = st.radio(
        "Weergave", ["📝 Dividend toevoegen", "📋 Overzicht"],
        key="div_section", horizontal=True, label_visibility="collapsed")

    if _div_section == "📝 Dividend toevoegen":
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
            # Stabiele keys (géén nonce): activum/datum/rekening/soort/munt/cash-keuze
            # mogen NIET resetten wanneer 'Vul lege velden in' de bedragvelden ververst
            # — enkel de bedragvelden zelf (A/B/C/D, RV%, eenvoudige bruto/ingehouden)
            # gebruiken de nonce-key, zodat ze via 'pre' opnieuw ingevuld kunnen worden.
            sk = lambda s: f"div_stable_{s}"
            CURS = ["EUR", "USD", "GBP", "CHF"]

            _KIND_LBL = {"dividend": "💰 Dividend", "interest": "🏦 Interest",
                         "securities_lending": "🔁 Securities lending"}
            _kinds = list(_KIND_LBL.keys())
            d_kind = st.radio("Soort inkomst", _kinds, horizontal=True, key=sk("kind"),
                              format_func=lambda k: _KIND_LBL[k],
                              help="Dividend telt mee voor de vrijstelling van €833 p.p.; interest en "
                                   "securities lending niet (die hebben hun eigen fiscale regels).")

            # Interest is meestal cash-rekeninginterest (niet aan één specifiek
            # activum gekoppeld); securities lending is dat niet noodzakelijk
            # (kan een vergoeding voor de hele portefeuille zijn). Dividend blijft
            # altijd aan een activum gekoppeld — dat IS letterlijk waarvoor het
            # uitgekeerd wordt.
            if d_kind != "dividend":
                _no_asset = st.checkbox(
                    "Niet gekoppeld aan een specifiek activum (bv. algemene "
                    "cash-rekeninginterest)", value=True, key=sk("no_asset"),
                    help="Standaard aan voor interest/securities lending, aangezien dit meestal "
                         "een algemene rekeningvergoeding is. Vink uit als dit bedrag wél bij één "
                         "specifiek activum hoort (bv. securities-lendingvergoeding voor een "
                         "uitgeleende positie).")
            else:
                _no_asset = False

            cc1, cc2, cc3 = st.columns(3)
            if _no_asset:
                cc1.text_input("Activum", value="— Algemeen (niet gekoppeld) —", disabled=True,
                               key=sk("tkr_disabled"))
                d_ticker = None
            else:
                d_ticker = cc1.selectbox("Activum *", tickers, key=sk("tkr"),
                                         format_func=lambda t: asset_label(t, div_names))
            d_date    = cc2.date_input("Datum *", value=date.today(), min_value=date(2000,1,1), max_value=date.today(), key=sk("date"))
            d_account = cc3.selectbox("Rekening *", db.get_accounts(), key=sk("acct"),
                                      help="De rekening waarop dit bedrag is uitgekeerd. "
                                           "Hetzelfde bedrag op een andere rekening voer je als een aparte lijn in.")
            asset_cur = amap.get(d_ticker, {}).get("currency", "EUR") if d_ticker else "EUR"
            cur_opts  = CURS if asset_cur in CURS else CURS + [asset_cur]

            # ── Uitkering in aandelen (stockdividend / kapitalisatie) ─────────
            # Bv. FCPE-werkgeversfondsen: het dividend van de onderliggende aandelen
            # wordt niet uitbetaald maar als extra deelbewijzen toegekend. Fiscaal is
            # en blijft dit een dividend (RV, €833-vrijstelling), maar er beweegt
            # GEEN cash — de tegenwaarde is een aanwas van stukken, die als een
            # gekoppelde transactie zonder cash-effect wordt geboekt.
            d_stock, d_shares, d_shareval, d_stock_lock = False, None, None, None
            if d_kind == "dividend" and d_ticker:
                d_stock = st.checkbox(
                    "📦 Uitgekeerd in aandelen (aanwas — geen cash)", key=sk("stockdiv"),
                    help="Voor kapitalisaties/stockdividenden (bv. FCPE-fondsen): het bruto "
                         "dividend = aantal toegekende stukken × waarde per stuk. De fiscale "
                         "keten (bronbelasting, RV, €833-vrijstelling) geldt zoals bij elk "
                         "dividend, maar er wordt niets in het cash-grootboek geboekt. "
                         "Tegelijk wordt automatisch een gekoppelde AANKOOP zonder "
                         "cash-effect en zonder TOB aangemaakt, zodat de nieuwe stukken "
                         "met hun brutowaarde als kostbasis in je positie zitten.")
                if d_stock:
                    _lastp = db.get_latest_price(d_ticker)
                    sdc1, sdc2, sdc3 = st.columns(3)
                    d_shares = sdc1.number_input(
                        "Aantal toegekende stukken *", min_value=0.0, step=0.0001,
                        format="%.10g", value=None, key=dk("stk_qty"))
                    d_shareval = sdc2.number_input(
                        f"Waarde per stuk * ({asset_cur})", min_value=0.0, step=0.0001,
                        format="%.10g", value=None, key=dk("stk_val"),
                        help=("De waarde waartegen de stukken zijn toegekend (uit je "
                              "afrekening). Ter info, de laatst gekende koers: "
                              f"{_lastp['price']:g} {_lastp.get('currency') or 'EUR'}."
                              if _lastp else
                              "De waarde waartegen de stukken zijn toegekend (uit je afrekening)."))
                    with sdc3:
                        if st.checkbox("🔒 Nieuwe stukken geblokkeerd", key=sk("stk_lock_chk"),
                                       help="Bij werkgeversplannen zijn ook de aangegroeide "
                                            "stukken vaak nog een tijd geblokkeerd."):
                            d_stock_lock = st.date_input(
                                "🔓 Vrij vanaf", value=date.today(),
                                min_value=date(2000, 1, 1), max_value=date(2100, 12, 31),
                                key=sk("stk_lock_date"))
                    if d_shares and d_shareval:
                        st.caption(f"➡️ Bruto dividend = {d_shares:g} × {d_shareval:g} = "
                                   f"**{asset_cur} {d_shares * d_shareval:,.2f}** — "
                                   "cash-boeking: geen (aanwas van stukken).")

            def _stock_txn_kwargs(fx_override):
                """Bouw de argumenten voor de gekoppelde aanwastransactie (aankoop
                zonder cash, zonder TOB) van een stockdividend. Kostbasis = brutowaarde
                van de toegekende stukken. Geeft None terug (en toont een fout) als er
                geen wisselkoers is — NOOIT stilzwijgend naar koers 1,0 terugvallen."""
                _tot = float(d_shares) * float(d_shareval)
                _fx, _tot_eur = compute_eur(_tot, asset_cur, d_date, fx_override)
                if _fx is None or _tot_eur is None:
                    st.error(f"Geen wisselkoers beschikbaar voor {asset_cur} op {d_date}. "
                             "Vink '💱 Eigen wisselkoers gebruiken' aan en vul de koers in — "
                             "zonder koers zou de kostbasis van de nieuwe stukken fout zijn.")
                    return None
                return {
                    "ticker": d_ticker, "transaction_type": "buy", "date": str(d_date),
                    "quantity": float(d_shares), "price_per_unit": float(d_shareval),
                    "total_amount": _tot, "currency": asset_cur, "tob_tax": 0.0,
                    "notes": "Stockdividend / kapitalisatie in aandelen (automatisch gekoppeld)",
                    "account": d_account, "costs": 0.0, "costs_currency": "EUR",
                    "fx_rate": _fx, "total_amount_eur": _tot_eur, "costs_eur": 0.0,
                    "is_stock_dividend": 1, "fx_manual": int(bool(fx_override)),
                    "lock_until": (str(d_stock_lock) if d_stock_lock else None),
                }

            mode = st.radio("Invoerwijze", ["Eenvoudig", "Gedetailleerd (bronbelasting + RV)"],
                            horizontal=True, key="div_mode")

            if mode == "Eenvoudig":
                sc1, sc2 = st.columns(2)
                with sc1:
                    if d_stock:
                        gross = ((d_shares or 0.0) * (d_shareval or 0.0)) or None
                        st.number_input("Bruto dividend (= stukken × waarde)",
                                        value=float(gross) if gross else 0.0,
                                        disabled=True, format="%.10g", key=dk("s_gross_ro"))
                        currency = asset_cur
                        st.caption(f"Munt: **{asset_cur}** (volgt het activum bij een "
                                   "uitkering in aandelen).")
                    else:
                        gross = st.number_input("Bruto dividend *", min_value=0.0, step=0.01,
                                                format="%.10g", value=None, key=dk("s_gross"))
                        currency = st.selectbox("Munt", cur_opts, index=cur_opts.index(asset_cur),
                                                key=sk(f"s_cur_{d_ticker}"))
                with sc2:
                    wh_amt = st.number_input("Ingehouden voorheffing (bedrag)", min_value=0.0,
                                             step=0.01, format="%.10g", value=None, key=dk("s_wh"))
                notes = st.text_area("Notities (optioneel)", height=60, key=dk("s_notes"))
                g = gross or 0.0
                w = wh_amt or 0.0
                s_fx_manual, s_fx_override = _div_fx_widget(
                    currency, d_date, key_prefix=dk("s"), context="het dividend")
                _fxs, _g_eur = compute_eur(g, currency, d_date, s_fx_override)
                st.info(f"**Netto:** {currency} {g - w:,.2f}"
                        + ("" if currency == "EUR" or _fxs is None else
                           f"  ≈  €{(g - w) * _fxs:,.2f}  (koers {_fxs:.6g})"))
                if st.button("✅ Dividend toevoegen", type="primary", key=dk("s_submit")):
                    if d_stock and (not d_shares or not d_shareval):
                        st.error("Vul het aantal toegekende stukken én de waarde per stuk in.")
                    elif not gross or gross <= 0:
                        st.error("Vul een bruto dividend in.")
                    else:
                        fx_rate, gross_eur = compute_eur(g, currency, d_date, s_fx_override)
                        _, wh_eur = compute_eur(w, currency, d_date, s_fx_override)
                        if fx_rate is None:
                            st.error("Geen wisselkoers beschikbaar voor "
                                     f"{currency} op {d_date}. Vink '💱 Eigen wisselkoers "
                                     "gebruiken' aan en vul de koers van je broker in — "
                                     "zonder koers zou het EUR-bedrag fout zijn.")
                        else:
                            _details = {"kind": d_kind, "net_eur": gross_eur - wh_eur}
                            _div_kwargs = dict(
                                ticker=d_ticker, date=str(d_date), gross_amount=g,
                                withholding_tax=w, currency=currency, notes=notes or None,
                                fx_rate=fx_rate, gross_eur=gross_eur, withholding_eur=wh_eur,
                                belgian_rv_withheld=1 if w > 0 else 0, account=d_account,
                                fx_manual=s_fx_manual, details=_details)
                            if d_stock:
                                _details.update({"cash_basis": "none", "cash_eur": 0.0,
                                                 "paid_in_shares": 1,
                                                 "shares_received": float(d_shares)})
                                _txn_kwargs = _stock_txn_kwargs(s_fx_override)
                                if _txn_kwargs is None:
                                    st.stop()
                                db.add_stock_dividend(_txn_kwargs, _div_kwargs)
                            else:
                                db.add_dividend(**_div_kwargs)
                            clear_cache()
                            st.session_state["div_amt_nonce"] = dn + 1
                            _lbl = d_ticker or "algemeen (niet gekoppeld)"
                            if d_stock:
                                st.session_state["div_added_msg"] = (
                                    f"✅ Stockdividend voor {_lbl} op {d_account} toegevoegd: "
                                    f"{d_shares:g} stuk(s) à {currency} {d_shareval:g} "
                                    f"(bruto {currency} {g:,.2f}) — geen cash-boeking, wel een "
                                    "gekoppelde aanwastransactie (zonder cash en zonder TOB).")
                            else:
                                st.session_state["div_added_msg"] = (
                                    f"✅ Dividend {currency} {g - w:.2f} netto voor {_lbl} op {d_account} toegevoegd!")
                            st.rerun()

            else:  # Gedetailleerd
                a_country = (amap.get(d_ticker, {}).get("country") or "BE").upper()
                wht_pct_default = tax_mod.get_wht_rates(tax_mod.year_of(str(d_date))).get(a_country, 0.0)
                is_foreign = a_country != "BE"
                cname = tax_mod.COUNTRY_NAMES.get(a_country, a_country)
                st.caption(f"Vul in wat je weet — lege velden worden automatisch berekend en ingevuld. "
                           f"Land van dit activum: **{cname}**"
                           + (f" (bronbelasting {wht_pct_default:g}%)." if is_foreign else " (geen buitenlandse bronbelasting)."))

                # Prefill (gezet door de aanvul-knop) — nonce zorgt voor verse widgets
                pre = st.session_state.pop("div_prefill", {})
                rv_pct = st.number_input(
                    "🇧🇪 Roerende voorheffing (%)", min_value=0.0, max_value=100.0,
                    value=float(pre.get("rv_pct", 30.0)), step=0.5, key=dk("rvpct"),
                    help="Belgische roerende voorheffing op dividenden — standaard 30%. Pas aan bij "
                         "een afwijkend tarief (bv. VVPR-bis 15%). Gebruikt om ④ uit ③ te berekenen "
                         "(of omgekeerd) wanneer een van beide leeg is.")

                # Munt-widgets keyen op het activum: bij een ander activum verschijnen
                # verse muntvelden met de juiste standaardmunt.
                def cur_box_t(col, keyname):
                    return col.selectbox("Munt", cur_opts, index=cur_opts.index(asset_cur),
                                         key=sk(f"{keyname}_{d_ticker}"), label_visibility="collapsed")

                r1a, r1b = st.columns([3, 1])
                A = r1a.number_input("① Bruto dividend (vóór buitenlandse bronbelasting)",
                                     min_value=0.0, step=0.01, format="%.10g",
                                     value=pre.get("A"), key=dk("A"),
                                     help="Het brutobedrag vóór eender welke inhouding. Enkel invullen "
                                          "bij een BUITENLANDS activum (bv. VS, Nederland, Frankrijk); "
                                          "voor Belgische aandelen laat je dit leeg en start je bij ③.")
                A_cur = cur_box_t(r1b, "Acur")
                r2a, r2b = st.columns([3, 1])
                B = r2a.number_input("② Buitenlandse bronbelasting",
                                     min_value=0.0, step=0.01, format="%.10g",
                                     value=pre.get("B"), key=dk("B"),
                                     help="Wordt automatisch berekend uit ① × het heffingstarief van het "
                                          f"land van het activum ({cname}: {wht_pct_default:g}% — zie ⚙️ "
                                          "Instellingen). Klopt het ingehouden bedrag niet (bv. ander "
                                          "verdragstarief), pas het hier aan.")
                B_cur = cur_box_t(r2b, "Bcur")
                r3a, r3b = st.columns([3, 1])
                C = r3a.number_input("③ Bruto na bronbelasting / vóór Belgische RV",
                                     min_value=0.0, step=0.01, format="%.10g",
                                     value=pre.get("C"), key=dk("C"),
                                     help="Het bedrag waarop de Belgische roerende voorheffing wordt "
                                          "berekend. Voor BELGISCHE aandelen is dit het brutodividend: "
                                          "vul het hier in en laat ① en ② leeg.")
                C_cur = cur_box_t(r3b, "Ccur")
                r4a, r4b = st.columns([3, 1])
                D = r4a.number_input("④ Netto dividend (na alle voorheffingen)",
                                     min_value=0.0, step=0.01, format="%.10g",
                                     value=pre.get("D"), key=dk("D"),
                                     help="Wat er uiteindelijk overblijft na ALLE belastingen: eventuele "
                                          "buitenlandse bronbelasting én de Belgische roerende voorheffing. "
                                          "Dit is doorgaans wat je broker daadwerkelijk uitkeert.")
                D_cur = cur_box_t(r4b, "Dcur")
                notes = st.text_area("Notities (optioneel)", height=60, key=dk("d_notes"))

                # Eén eigen koers voor de hele lijn. De velden ①-④ kunnen elk een eigen
                # munt hebben, maar in de praktijk gaat het om één vreemde munt die je
                # broker tegen één koers omrekent; die koers geldt dan voor elk veld dat
                # niet al in euro staat.
                _fx_curs = sorted({c for c, v in ((A_cur, A), (B_cur, B), (C_cur, C), (D_cur, D))
                                   if v is not None and c != "EUR"})
                d_fx_manual, d_fx_override = 0, None
                if _fx_curs:
                    if len(_fx_curs) > 1:
                        st.warning("⚠️ Je gebruikt meer dan één vreemde munt in deze keten "
                                   f"({', '.join(_fx_curs)}). Eén eigen koers kan er maar voor "
                                   "één gelden — voer zulke gevallen beter als aparte lijnen in, "
                                   "of laat de marktkoersen hun werk doen.")
                    else:
                        d_fx_manual, d_fx_override = _div_fx_widget(
                            _fx_curs[0], d_date, key_prefix=dk("d"), context="deze keten")

                # Keten aanvullen met de tarieven (land + RV%)
                # Stockdividend: is de keten leeg, veranker ze dan op stukken × waarde
                # (bij een buitenlands activum als ① bruto, anders als ③).
                if d_stock and d_shares and d_shareval and all(v is None for v in (A, B, C, D)):
                    _anchor = round(float(d_shares) * float(d_shareval), 2)
                    if is_foreign:
                        A = _anchor
                    else:
                        C = _anchor
                    st.caption(f"📦 Keten verankerd op de aandelenuitkering: "
                               f"{'①' if is_foreign else '③'} = {d_shares:g} × {d_shareval:g} "
                               f"= {asset_cur} {_anchor:,.2f}.")
                res = tax_mod.resolve_dividend_chain(
                    A, B, C, D,
                    rv_rate=(rv_pct / 100.0),
                    wht_rate=(wht_pct_default / 100.0) if (is_foreign and d_kind == "dividend") else 0.0)
                rA, rB, rC, rD, rRV = res["a"], res["b"], res["c"], res["d"], res["rv"]
                def _f(v, cur): return "—" if v is None else f"{cur} {v:,.2f}"
                st.markdown(
                    f"**Afgeleide keten:** ① {_f(rA, A_cur)}  →  ② bronbelasting {_f(rB, B_cur)}  →  "
                    f"③ {_f(rC, C_cur)}  →  🇧🇪 RV {_f(rRV, C_cur)}  →  ④ netto {_f(rD, D_cur)}")

                # Omgekeerde controle (④ → ③ → ② → ①) met tolerantie voor afronding
                filled = [v for v in (A, B, C, D) if v is not None]
                if len(filled) >= 2:
                    issues = tax_mod.verify_dividend_chain(rA, rB, rC, rD, tol=0.02)
                    if issues:
                        for i in issues:
                            st.warning("⚠️ Controle (④→③→②→①): " + i)
                    else:
                        st.caption("✅ Omgekeerde controle (④→③→②→①) klopt binnen de afrondingstolerantie (± €0,02).")

                bc1, bc2 = st.columns([1, 2])
                if bc1.button("🪄 Vul lege velden in", key=dk("fill"),
                              help="Zet de automatisch berekende bedragen in de lege invoervelden, "
                                   "zodat je ze kunt nakijken en zo nodig aanpassen vóór het opslaan."):
                    st.session_state["div_prefill"] = {
                        "A": rA, "B": rB, "C": rC, "D": rD, "rv_pct": rv_pct,
                        "cash_basis": st.session_state.get(sk("cashbasis"), "④ Netto"),
                    }
                    st.session_state["div_amt_nonce"] = dn + 1
                    st.rerun()

                if d_stock:
                    cash_choice = "📦 Geen (uitkering in aandelen)"
                    bc2.caption("💶 **Cash-boeking: geen** — dit dividend wordt in aandelen "
                                "uitgekeerd; er beweegt niets in het cash-grootboek. De "
                                "tegenwaarde wordt als aanwastransactie geboekt.")
                else:
                    cash_choice = bc2.radio(
                        "Cash-boeking op basis van", ["④ Netto", "③ Bruto na bronbelasting", "① Bruto vóór bronbelasting"],
                        horizontal=True, key=sk("cashbasis"),
                        index=["④ Netto", "③ Bruto na bronbelasting", "① Bruto vóór bronbelasting"].index(pre["cash_basis"]) if pre.get("cash_basis") in ("④ Netto", "③ Bruto na bronbelasting", "① Bruto vóór bronbelasting") else 0,
                        help="Welk bedrag als dividend in het cash-grootboek (💶 Cash) geboekt wordt. "
                             "Standaard het netto (④) — wat je broker effectief stort. Kies ③ of ① als je "
                             "broker bruto uitkeert en de belasting later apart afhoudt. Er kan er maar één "
                             "gekozen worden.")

                if st.button("✅ Dividend toevoegen", type="primary", key=dk("d_submit")):
                    # EUR per veld (elk in zijn eigen munt op de dividenddatum). Een eigen
                    # brokerkoers geldt enkel voor de munt waarvoor je ze ingaf.
                    def to_eur(v, cur):
                        if v is None: return None
                        _ov = d_fx_override if (d_fx_manual and cur in _fx_curs) else None
                        return compute_eur(v, cur, d_date, _ov)[1]
                    a_eur = to_eur(rA, A_cur); b_eur = to_eur(rB, B_cur)
                    c_eur = to_eur(rC, C_cur); d_eur = to_eur(rD, D_cur)
                    gross_eur = a_eur if a_eur is not None else (c_eur if c_eur is not None else d_eur)
                    net_eur   = d_eur if d_eur is not None else (c_eur if c_eur is not None else
                                (a_eur - b_eur if (a_eur is not None and b_eur is not None) else None))
                    if d_stock and (not d_shares or not d_shareval):
                        st.error("Vul het aantal toegekende stukken én de waarde per stuk in.")
                    elif gross_eur is None or net_eur is None:
                        st.error("Geef minstens een bruto- én een nettowaarde in (of voldoende velden om ze te berekenen).")
                    else:
                        wh_eur = max(0.0, gross_eur - net_eur)
                        # Cash-boeking op basis van het gekozen veld
                        if d_stock:
                            cash_basis, cash_eur_v = "none", 0.0
                        elif cash_choice.startswith("①"):
                            cash_basis, cash_eur_v = "gross_before", (a_eur if a_eur is not None else net_eur)
                        elif cash_choice.startswith("③"):
                            cash_basis, cash_eur_v = "gross_after", (c_eur if c_eur is not None else net_eur)
                        else:
                            cash_basis, cash_eur_v = "net", net_eur
                        # Native rollup (voor weergave/compat): primair veld = ① of ③ of ④
                        prim_v, prim_cur = ((rA, A_cur) if rA is not None else
                                            (rC, C_cur) if rC is not None else (rD, D_cur))
                        _ov = d_fx_override if (d_fx_manual and prim_cur in _fx_curs) else None
                        fx_prim = compute_eur(prim_v, prim_cur, d_date, _ov)[0] or 1.0
                        wh_native = round(wh_eur / fx_prim, 2)
                        details = {
                            "gross_before_wht": rA, "gross_before_wht_cur": A_cur if rA is not None else None,
                            "foreign_wht_amt":  rB, "foreign_wht_cur":      B_cur if rB is not None else None,
                            "gross_after_wht":  rC, "gross_after_wht_cur":  C_cur if rC is not None else None,
                            "belgian_rv_amt":   rRV,
                            "net_received":     rD, "net_received_cur":     D_cur if rD is not None else None,
                            "net_eur":          net_eur,
                            "cash_basis":       cash_basis,
                            "cash_eur":         cash_eur_v,
                            "kind":             d_kind,
                        }
                        _div_kwargs = dict(
                            ticker=d_ticker, date=str(d_date), gross_amount=prim_v,
                            withholding_tax=wh_native, currency=prim_cur, notes=notes or None,
                            fx_rate=fx_prim, gross_eur=gross_eur, withholding_eur=wh_eur,
                            foreign_wht_withheld=1 if (rB and rB > 0) else 0,
                            belgian_rv_withheld=1 if (rRV and rRV > 0) else 0,
                            account=d_account, details=details,
                            fx_manual=int(bool(_ov)))
                        if d_stock:
                            details["paid_in_shares"] = 1
                            details["shares_received"] = float(d_shares)
                            _stk_fx_ov = d_fx_override if (d_fx_manual and asset_cur in _fx_curs) else None
                            _txn_kwargs = _stock_txn_kwargs(_stk_fx_ov)
                            if _txn_kwargs is None:
                                st.stop()
                            db.add_stock_dividend(_txn_kwargs, _div_kwargs)
                        else:
                            db.add_dividend(**_div_kwargs)
                        clear_cache()
                        st.session_state["div_amt_nonce"] = dn + 1
                        _lbl = d_ticker or "algemeen (niet gekoppeld)"
                        if d_stock:
                            st.session_state["div_added_msg"] = (
                                f"✅ Stockdividend voor {_lbl} op {d_account} toegevoegd: "
                                f"{d_shares:g} stuk(s) à {asset_cur} {d_shareval:g} "
                                f"(netto ≈ {eur(net_eur)}) — geen cash-boeking, wel een gekoppelde "
                                "aanwastransactie (zonder cash en zonder TOB).")
                        else:
                            st.session_state["div_added_msg"] = (
                                f"✅ Dividend voor {_lbl} op {d_account} toegevoegd (netto ≈ {eur(net_eur)}; "
                                f"cash-boeking: {cash_choice}).")
                        st.rerun()

    else:  # 📋 Overzicht
        st.session_state.pop("edit_div", None)  # oude bewerkstaat opruimen
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

        # Geen eigen berekening: dit zijn dezelfde functies als overal elders.
        _geur, _neur = dividend_gross_eur, dividend_net_eur
        total_gross = sum(_geur(d) for d in divs)
        total_net   = sum(_neur(d) for d in divs)
        total_wh    = total_gross - total_net

        c1, c2, c3 = st.columns(3)
        c1.metric("Bruto (EUR)", eur(total_gross))
        c2.metric("Ingehouden voorheffingen", eur(total_wh))
        c3.metric("Netto ontvangen", eur(total_net))

        # Fiscaal recupereerbaar (833-vrijstelling + FBB) voor de huidige selectie
        _acc = (f_acct if f_acct != "Alle rekeningen" else None)
        _ben = tax_mod.dividend_tax_benefit(int(f_year) if f_year != "Alle" else None, _acc)
        if _ben["total_benefit"] > 0:
            st.success(f"💡 Fiscaal recupereerbaar via de aangifte: **{eur(_ben['total_benefit'])}** "
                       f"(RV-vrijstelling {eur(_ben['total_reclaimable_rv'])}"
                       + (f" + FBB {eur(_ben['total_fbb'])}" if _ben["total_fbb"] else "")
                       + "). Volledige uitwerking op de **🧾 Belgische Belasting**-pagina.")

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
        a_by_tk   = {a["ticker"]: a for a in db.get_assets()}
        CASH_LBL  = {"net": "④ Netto", "gross_after": "③ Bruto na", "gross_before": "① Bruto vóór",
                     "none": "📦 In aandelen (geen cash)"}
        CASH_KEY  = {v: k for k, v in CASH_LBL.items()}
        KIND_LBL  = {"dividend": "Dividend", "interest": "Interest", "securities_lending": "Securities lending"}
        KIND_KEY  = {v: k for k, v in KIND_LBL.items()}
        accounts_all = db.get_accounts()
        rows = []
        for d in divs:
            rows.append({
                "ID":       d["id"],
                "Datum":    d["date"][:10],
                "Activum":  asset_label(d["ticker"], names_map),
                "Soort":    KIND_LBL.get(d.get("kind") or "dividend", "Dividend"),
                "Rekening": d.get("account") or db.DEFAULT_ACCOUNT,
                "① Bruto":  d.get("gross_before_wht"),
                "② Bronbel.": d.get("foreign_wht_amt"),
                "③ Na bronbel.": d.get("gross_after_wht"),
                "🇧🇪 RV":   d.get("belgian_rv_amt"),
                "④ Netto":  d.get("net_received") if d.get("net_received") is not None
                            else round(d["gross_amount"] - d["withholding_tax"], 2),
                "Munt":     d.get("net_received_cur") or d.get("gross_before_wht_cur") or d["currency"],
                "FX-koers": round(float(d.get("fx_rate") or 1.0), 6),
                "FX eigen": bool(d.get("fx_manual")),
                "Cash":     CASH_LBL.get(d.get("cash_basis") or "net", "④ Netto"),
                "Netto €":  round(_neur(d), 2),
                "🔒 Handmatig": bool(d.get("manual_override")),
                "Notities": d.get("notes") or "",
            })
        cc = st.column_config
        CUR_OPTS = ["EUR", "USD", "GBP", "CHF"]
        edited = st.data_editor(
            pd.DataFrame(rows), width="stretch", hide_index=True, key="div_editor",
            num_rows="fixed",
            column_config={
                "ID":            cc.NumberColumn(disabled=True, format="%d", width="small",
                                                 help="Uniek dividend-ID — handig om een lijn te selecteren voor verwijdering."),
                "Datum":         cc.TextColumn(help="JJJJ-MM-DD"),
                "Activum":       cc.TextColumn(disabled=True),
                "Soort":         cc.SelectboxColumn(options=list(KIND_LBL.values()),
                                                    help="Dividend telt mee voor de 833-vrijstelling; "
                                                         "interest en securities lending niet."),
                "Rekening":      cc.SelectboxColumn(options=accounts_all),
                "① Bruto":       cc.NumberColumn(min_value=0.0, format="%.10g",
                                                 help="Bruto vóór buitenlandse bronbelasting (enkel buitenlandse aandelen)."),
                "② Bronbel.":    cc.NumberColumn(min_value=0.0, format="%.10g",
                                                 help="Laat leeg om automatisch te berekenen uit het land."),
                "③ Na bronbel.": cc.NumberColumn(min_value=0.0, format="%.10g",
                                                 help="Grondslag Belgische RV. Voor Belgische aandelen begin je hier."),
                "🇧🇪 RV":        cc.NumberColumn(disabled=True, format="%.10g",
                                                 help="Belgische roerende voorheffing (berekend)."),
                "④ Netto":       cc.NumberColumn(min_value=0.0, format="%.10g",
                                                 help="Laat leeg om automatisch te berekenen (③ × (1 − RV%))."),
                "Munt":          cc.SelectboxColumn(options=CUR_OPTS),
                "FX-koers":      cc.NumberColumn(
                    format="%.10g",
                    help="1 eenheid van de munt in EUR. Vink 'FX eigen' aan om je EIGEN "
                         "koers (die van je broker) te bewaren; ze wordt dan nooit "
                         "overschreven door een herberekening met de marktkoers."),
                "FX eigen":      cc.CheckboxColumn(
                    help="Aan = de koers hiernaast is JOUW koers en blijft voorgoed bij deze "
                         "lijn. Pas je de koers aan, dan wordt dit vinkje automatisch gezet. "
                         "Vink af om weer met de historische marktkoers te rekenen."),
                "Cash":          cc.SelectboxColumn(options=list(CASH_LBL.values()),
                                                    help="Welk veld naar het cash-grootboek gaat."),
                "Netto €":       cc.NumberColumn(disabled=True, format="%.10g"),
                "🔒 Handmatig":  cc.CheckboxColumn(
                    help="Deze lijn is door jou handmatig gecorrigeerd. De knop 'keten "
                         "herberekenen' laat ze dan met rust. Wordt automatisch aangevinkt zodra "
                         "je een bedrag (①-④) aanpast; vink af om de lijn weer automatisch te "
                         "laten herberekenen."),
                "Notities":      cc.TextColumn(),
            })
        st.caption("✏️ Bewerk rechtstreeks in de tabel. Laat ② en ④ leeg om ze automatisch te laten "
                   "berekenen (bronbelasting uit het land van het activum, RV uit de instellingen). "
                   "De keten, RV, EUR-bedragen en cash-boeking worden bij het opslaan herberekend en gecontroleerd.")

        _rvrate = float(db.get_setting("withholding_tax_rate", "0.30"))
        if st.button("💾 Wijzigingen opslaan", type="primary", key="div_save_inline"):
            n_upd, problems = 0, []
            try:
                for i, d in enumerate(divs):
                    r = edited.iloc[i]
                    orig = rows[i]
                    if all(r[k] == orig[k] or (pd.isna(r[k]) and orig[k] is None)
                           for k in ("Datum", "Soort", "Rekening", "① Bruto", "② Bronbel.", "③ Na bronbel.",
                                     "④ Netto", "Munt", "Cash", "Notities", "🔒 Handmatig",
                                     "FX-koers", "FX eigen")):
                        continue
                    nd = _date_or_none(str(r["Datum"]))
                    if nd is None:
                        problems.append(f"#{d['id']}: datum '{r['Datum']}' ongeldig (JJJJ-MM-DD).")
                        continue
                    def _num(v):
                        try:
                            return None if v is None or pd.isna(v) else float(v)
                        except (TypeError, ValueError):
                            return None
                    nA, nB = _num(r["① Bruto"]), _num(r["② Bronbel."])
                    nC, nD = _num(r["③ Na bronbel."]), _num(r["④ Netto"])
                    ncur   = str(r["Munt"]) if r["Munt"] in CUR_OPTS else (d.get("currency") or "EUR")
                    kind   = KIND_KEY.get(str(r["Soort"]), "dividend")
                    # Tarieven toepassen: bronbelasting uit het land, RV uit de instellingen
                    ctry = (a_by_tk.get(d["ticker"], {}).get("country") or "BE").upper()
                    _wht = (tax_mod.get_wht_rate(ctry, tax_mod.year_of(d["date"]))
                            if (kind == "dividend" and ctry != "BE") else 0.0)
                    res = tax_mod.resolve_dividend_chain(nA, nB, nC, nD, rv_rate=_rvrate, wht_rate=_wht)
                    rA, rB, rC, rD, rRV = res["a"], res["b"], res["c"], res["d"], res["rv"]

                    # ── Wisselkoers ──────────────────────────────────────────
                    # Zelf ingevulde koers (of 'FX eigen' aangevinkt) = die van je broker:
                    # die blijft bij de lijn en wordt nooit door de marktkoers vervangen.
                    fx_edited = not _cell_eq(r["FX-koers"], orig["FX-koers"])
                    fx_man = int(bool(r["FX eigen"]) or fx_edited)
                    fx_ov = None
                    if fx_man and ncur != "EUR":
                        try:
                            fx_ov = float(r["FX-koers"])
                        except (TypeError, ValueError):
                            fx_ov = None
                        if not fx_ov or fx_ov <= 0:
                            problems.append(f"#{d['id']}: 'FX eigen' staat aan maar de FX-koers "
                                            "is leeg of 0.")
                            continue
                    if ncur == "EUR":
                        fx_man, fx_ov = 0, None

                    def _te(v):
                        return None if v is None else compute_eur(v, ncur, nd, fx_ov)[1]
                    a_eur, c_eur, d_eur = _te(rA), _te(rC), _te(rD)
                    gross_eur = a_eur if a_eur is not None else (c_eur if c_eur is not None else d_eur)
                    net_eur   = d_eur if d_eur is not None else c_eur
                    if gross_eur is None or net_eur is None:
                        problems.append(f"#{d['id']}: minstens een bruto- en nettowaarde nodig.")
                        continue
                    issues = tax_mod.verify_dividend_chain(rA, rB, rC, rD, tol=0.02)
                    if issues:
                        problems.append(f"#{d['id']}: " + "; ".join(issues) + " — niet opgeslagen.")
                        continue
                    cbk = CASH_KEY.get(str(r["Cash"]), "net")
                    if cbk == "none":
                        # Uitkering in aandelen: nooit cash boeken (0.0 is falsy, dus geen
                        # 'or'-terugval gebruiken — die zou het netto stilzwijgend invullen).
                        cash_eur_v = 0.0
                    else:
                        cash_eur_v = {"gross_before": a_eur, "gross_after": c_eur, "net": net_eur}.get(cbk)
                        if cash_eur_v is None:
                            cash_eur_v = net_eur
                    wh_eur = max(0.0, gross_eur - net_eur)
                    prim_v = rA if rA is not None else (rC if rC is not None else rD)
                    fx_prim = fx_ov or (compute_eur(prim_v, ncur, nd)[0] or 1.0)
                    db.update_dividend(
                        d["id"], date=str(nd), account=str(r["Rekening"]),
                        notes=(str(r["Notities"]) or None) if not pd.isna(r["Notities"]) else None,
                        currency=ncur, gross_amount=prim_v,
                        withholding_tax=round(wh_eur / fx_prim, 2), fx_rate=fx_prim,
                        fx_manual=fx_man,
                        gross_eur=gross_eur, withholding_eur=wh_eur, net_eur=net_eur,
                        foreign_wht_withheld=1 if (rB and rB > 0) else 0,
                        belgian_rv_withheld=1 if (rRV and rRV > 0) else 0,
                        gross_before_wht=rA, gross_before_wht_cur=ncur if rA is not None else None,
                        foreign_wht_amt=rB, foreign_wht_cur=ncur if rB is not None else None,
                        gross_after_wht=rC, gross_after_wht_cur=ncur if rC is not None else None,
                        belgian_rv_amt=rRV, net_received=rD,
                        net_received_cur=ncur if rD is not None else None,
                        cash_basis=cbk, cash_eur=cash_eur_v, kind=kind,
                        # Bedragen zelf aangepast? Dan is dit een HANDMATIGE CORRECTIE en
                        # laat de knop 'keten herberekenen' deze lijn voortaan met rust.
                        # (Enkel de datum/rekening/notities wijzigen telt niet als correctie.)
                        manual_override=1 if any(
                            not _cell_eq(r[k], orig[k])
                            for k in ("① Bruto", "② Bronbel.", "③ Na bronbel.", "④ Netto")
                        ) else (1 if bool(r["🔒 Handmatig"]) else 0))
                    n_upd += 1
            except Exception as exc:
                problems.append(f"Onverwachte fout: {exc}")
            for p in problems:
                st.warning("⚠️ " + p)
            if n_upd:
                clear_cache()
                st.success(f"✅ {n_upd} lijn(en) bijgewerkt.")
                st.rerun()
            elif not problems:
                st.info("Geen wijzigingen gevonden.")

        # ── Keten herberekenen: eerst tonen wát er zou wijzigen, dan pas uitvoeren ──
        st.divider()
        st.markdown("#### 🔄 Keten herberekenen")
        st.caption("Herbouwt de keten vanaf ① bruto met de bronbelasting van het **land** van het "
                   "activum **en van het jaar van het dividend**, plus de RV uit de instellingen "
                   "(inclusief EUR-bedragen en cash-boeking). Lijnen die al kloppen blijven "
                   "ongemoeid. **Handmatig gecorrigeerde lijnen (🔒) worden standaard niet "
                   "aangeraakt** — je ziet hieronder eerst wat er precies zou wijzigen.  \n"
                   "💱 **Lijnen met een eigen wisselkoers behouden jouw koers**: enkel de "
                   "bedragen en hun EUR-tegenwaarde worden herrekend, de koers zelf blijft "
                   "staan zoals je broker ze afrekende.")

        _n_manual = sum(1 for d in divs
                        if d.get("manual_override") and (d.get("kind") or "dividend") == "dividend")
        RC_SAFE = "🔒 Handmatig gecorrigeerde lijnen overslaan (aanbevolen)"
        RC_ALL  = "⚠️ Ook handmatig gecorrigeerde lijnen overschrijven"
        rc_scope = st.radio("Bereik", [RC_SAFE, RC_ALL], key="div_rc_scope",
                            index=0, label_visibility="collapsed",
                            help="Bij 'overschrijven' worden ook je eigen correcties vervangen door "
                                 "de theoretisch berekende waarden. Dat kan zinvol zijn na een "
                                 "tariefcorrectie, maar je verliest dan de handmatige waarden.")
        _incl = rc_scope == RC_ALL
        if _n_manual:
            st.caption(f"🔒 **{_n_manual}** lijn(en) staan als handmatig gecorrigeerd gemarkeerd."
                       + ("  Die worden nu **wél** overschreven." if _incl
                          else "  Die blijven ongemoeid."))

        _preview = _recompute_dividend_chain(divs, _rvrate, include_manual=_incl, dry_run=True)
        if not _preview:
            st.success("✅ Alle lijnen kloppen al met de tarieven — er valt niets te herberekenen.")
        else:
            _dnet = sum((c["nieuw_netto_eur"] or 0) - (c["oud_netto_eur"] or 0) for c in _preview)
            _nman = sum(1 for c in _preview if c["handmatig"])
            st.warning(f"**{len(_preview)} lijn(en)** zouden wijzigen"
                       + (f", waarvan **{_nman} handmatig gecorrigeerd**" if _nman else "")
                       + f". Impact op het totale netto: **{eur(_dnet)}**.")
            show_df(pd.DataFrame([{
                "": ("🔒" if c["handmatig"] else "") + ("💱" if c.get("eigen_fx") else ""),
                "ID":        c["id"],
                "Datum":     c["datum"],
                "Activum":   asset_label(c["ticker"], names_map),
                "Land/jaar": f"{c['land']} {c['jaar']} ({c['wht_pct']:g}%)",
                "② Bronbel. nu":  c["oud_wht"],
                "② wordt":        c["nieuw_wht"],
                "④ Netto nu":     c["oud_netto"],
                "④ wordt":        c["nieuw_netto"],
                "Δ netto €":      (c["nieuw_netto_eur"] or 0) - (c["oud_netto_eur"] or 0),
            } for c in _preview]), width="stretch", hide_index=True, column_config={
                "ID":            st.column_config.NumberColumn(format="%d", width="small"),
                "② Bronbel. nu": st.column_config.NumberColumn(format="%.10g"),
                "② wordt":       st.column_config.NumberColumn(format="%.10g"),
                "④ Netto nu":    st.column_config.NumberColumn(format="%.10g"),
                "④ wordt":       st.column_config.NumberColumn(format="%.10g"),
                "Δ netto €":     st.column_config.NumberColumn(format="€ %+.10g"),
            })
            _neigen = sum(1 for c in _preview if c.get("eigen_fx"))
            if _neigen:
                st.caption(f"💱 **{_neigen}** lijn(en) hebben een eigen wisselkoers. Die koers "
                           "blijft behouden; enkel de bedragen en hun EUR-tegenwaarde worden "
                           "herrekend.")
            _conf_lbl = ("Ja, overschrijf ook mijn handmatige correcties" if (_incl and _nman)
                         else "Ja, voer deze herberekening uit")
            # Zelfde valkuil als bij de TOB: een widget-key mag niet overschreven worden
            # nadat de widget is aangemaakt. Nonce in de key i.p.v. de waarde resetten.
            _divn = st.session_state.get("div_rc_nonce", 0)
            if st.checkbox(_conf_lbl, key=f"div_rc_confirm_{_divn}"):
                if st.button("🔄 Herberekening uitvoeren", type="primary", key="div_recompute"):
                    done = _recompute_dividend_chain(divs, _rvrate, include_manual=_incl)
                    clear_cache()
                    st.session_state["div_rc_nonce"] = _divn + 1   # geen widget-key
                    st.success(f"✅ {len(done)} lijn(en) herberekend.")
                    st.rerun()

        # Verwijderen (meerdere tegelijk, met bevestiging)
        st.divider()
        del_opts = {d["id"]: f"#{d['id']} · {d['date'][:10]} · {asset_label(d['ticker'], names_map)} "
                             f"· netto {eur(_neur(d))}"
                             + (" · 📦 met gekoppelde aanwastransactie" if d.get("linked_txn_id") else "")
                    for d in divs}
        if any(d.get("linked_txn_id") for d in divs):
            st.caption("📦 Bij een stockdividend verdwijnt de automatisch aangemaakte "
                       "aanwastransactie mee — anders blijven er stukken in je positie "
                       "staan waarvan de aanleiding weg is.")
        multiselect_delete("confirm_del_div", del_opts,
                           lambda i, group=None: db.delete_dividend(i, group=group),
                           noun="dividend")
