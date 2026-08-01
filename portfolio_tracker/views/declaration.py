"""
views/declaration.py — pagina 'Aangifte'.

Brengt samen wat tot nu toe over vier schermen verspreid stond: welk bedrag hoort in
welk vak van de personenbelasting, en waar komt dat bedrag vandaan. De app rekent en
verwijst; ze vult niets in en beslist niets.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import streamlit as st

import belgian_tax as tax_mod
import database as db

from views.common import account_filter_widget, eur, show_df

logger = logging.getLogger("app.declaration")


def _rows_df(rows: list[dict]) -> pd.DataFrame:
    """Brondetails van een aangifteregel als tabel."""
    return pd.DataFrame([{
        "Datum":            r["date"],
        "Activum":          r["ticker"],
        "Rekening":         r["account"],
        "Land":             r["country"],
        "Bruto €":          round(r["gross_eur"], 2),
        "Buitenl. bronb. €": round(r["foreign_wht_eur"], 2),
        "Na bronbel. €":    round(r["after_foreign_eur"], 2),
        "Belg. RV €":       round(r["be_rv_eur"], 2),
    } for r in rows])


def page_declaration():
    st.header("🧾 Aangiftehulp")

    years = sorted({int(str(d["date"])[:4]) for d in db.get_dividends()}
                   | {int(str(t["date"])[:4]) for t in db.get_transactions()}
                   | {date.today().year - 1, date.today().year}, reverse=True)
    c1, c2 = st.columns([1, 3])
    with c1:
        # Standaard het vorige jaar: de aangifte die je nu invult, gaat over het
        # inkomstenjaar dat achter je ligt.
        _def = date.today().year - 1
        year = st.selectbox("Inkomstenjaar", years,
                            index=years.index(_def) if _def in years else 0,
                            key="decl_year",
                            help="Het jaar waarin je de inkomsten ontving. De aangifte "
                                 "die je in het voorjaar invult, gaat over het jaar "
                                 "daarvoor.")
    with c2:
        acct = account_filter_widget("decl_accounts")
    accset = set(acct) if acct else None

    st.info(
        f"**Aangifte over inkomstenjaar {year}**, in te dienen in {year + 1}. "
        "Hieronder staat per vak wat je moet invullen en waarom. Klap een regel open "
        "om te zien uit welke dividenden of verkopen het bedrag is opgebouwd.")
    st.warning(
        "⚠️ **Leg dit naast je echte aangifteformulier.** De vakcodes wijzigen van jaar "
        "tot jaar en de app kent het formulier van dit jaar niet — de bedragen zijn "
        "berekend uit jouw gegevens, de codes zijn een geheugensteun. Deze app is geen "
        "aangiftesoftware en geen fiscaal advies; twijfel je, vraag het aan je "
        "boekhouder of aan de FOD Financiën.")

    res = tax_mod.declaration_lines(year, accounts=accset)
    lines = res["lines"]

    # ── Samenvatting: wat levert het op, wat kost het ────────────────────────
    to_declare = sum(l["amount"] for l in lines if l["kind"] == "aangeven")
    to_reclaim = sum(l["amount"] for l in lines if l["kind"] == "terugvorderen")
    m1, m2, m3 = st.columns(3)
    m1.metric("Aan te geven inkomsten", eur(to_declare),
              help="Bedragen die je zelf moet aangeven en waarop nog belasting "
                   "verschuldigd is.")
    m2.metric("Terug te vorderen", eur(to_reclaim),
              help="Voorheffing die je via de aangifte terugkrijgt. Dit is geld dat je "
                   "laat liggen als je het niet invult.")
    m3.metric("Verschuldigde meerwaardebelasting",
              eur(res["overview"].get("tax_due", 0.0)))

    st.divider()

    # ── De regels zelf ───────────────────────────────────────────────────────
    ICON = {"aangeven": "📝", "terugvorderen": "💰"}
    for l in lines:
        if abs(l["amount"]) < 0.005 and not l["rows"] and not l.get("extra"):
            # Niets in te vullen: wel tonen (zodat je weet dat het bekeken is),
            # maar ingeklapt en zonder nadruk.
            with st.expander(f"⚪ Vak {l['vak']} · {l['label']} — niets in te vullen"):
                st.caption(l["explanation"])
            continue

        head = f"{ICON.get(l['kind'], '•')} **{l['label']}**"
        st.markdown(head)
        cc1, cc2, cc3 = st.columns([1, 1, 2])
        cc1.metric("Bedrag", eur(l["amount"]))
        cc2.metric("Vak / code", f"{l['vak']} · {l['code'] or '?'}")
        with cc3:
            st.caption(l["explanation"])
            if l.get("verify"):
                st.caption("🔎 **Code nakijken** op het formulier — deze is niet zeker.")

        with st.expander(f"Waar komt {eur(l['amount'])} vandaan?"):
            if l.get("extra"):
                st.markdown("**Opbouw**")
                show_df(pd.DataFrame([{"Onderdeel": k, "Bedrag €": round(v, 2)}
                                      for k, v in l["extra"].items()]),
                        width="stretch", hide_index=True)
            if l["rows"]:
                st.markdown(f"**Onderliggende lijnen ({len(l['rows'])})**")
                show_df(_rows_df(l["rows"]), width="stretch", hide_index=True)
            elif not l.get("extra"):
                st.caption("Geen onderliggende lijnen.")
        st.divider()

    for n in res["notes"]:
        st.caption(f"ℹ️ {n}")

    # ── Zaken die de app NIET kan weten ──────────────────────────────────────
    with st.expander("❗ Wat de app niet voor je kan invullen"):
        st.markdown(
            "- **Buitenlandse rekeningen (vak XIII)** en de aanmelding bij het "
            "Centraal Aanpuntpunt van de Nationale Bank. De app weet niet in welk land "
            "je broker gevestigd is; heb je een rekening bij een buitenlandse "
            "instelling, dan hoort dat aangegeven te worden.\n"
            "- **De taks op effectenrekeningen** boven de drempel per rekening. Je "
            "broker houdt die meestal zelf in, maar niet altijd.\n"
            "- **Andere inkomsten**: loon, huur, andere beleggingen buiten deze app.\n"
            "- **Je gezinssituatie.** De app rekent met "
            f"**{res['benefit']['persons']}** belastingplichtige(n); staat dat verkeerd, "
            "pas het aan bij ⚙️ Instellingen → fiscale parameters. Het verandert de "
            "vrijstellingen en dus de bedragen hierboven.")

    # ── Codes aanpassen ──────────────────────────────────────────────────────
    with st.expander("⚙️ Vakcodes aanpassen"):
        st.caption(
            "De codes staan als instelling in de database, niet vast in de code — net "
            "als de tarieven. Verschilt een code op jouw formulier, pas ze hier aan; "
            "de app onthoudt het voor volgende jaren.")
        labels = {
            "decl_code_div_no_rv": "Dividenden zonder Belgische voorheffing",
            "decl_code_rv_refund": "Terug te vorderen voorheffing (vrijstelling)",
            "decl_code_fbb":       "FBB (Franse dividenden)",
            "decl_code_cgt":       "Meerwaarde op financiële activa",
        }
        newv = {}
        for k, lab in labels.items():
            newv[k] = st.text_input(lab, value=res["codes"].get(k, ""), key=f"dc_{k}")
        if st.button("💾 Codes opslaan", key="decl_save_codes"):
            for k, v in newv.items():
                db.set_setting(k, v.strip())
            st.success("✅ Opgeslagen.")
            st.rerun()

    st.caption("💡 Tip: neem een schermafdruk of noteer de bedragen vóór je aan de "
               "aangifte begint. Wijzig je nadien nog transacties van dit jaar, dan "
               "veranderen deze cijfers mee.")
