"""
views/settings.py — pagina 'Instellingen'.
"""
from __future__ import annotations

import logging
import os
from datetime import date
from datetime import datetime

import pandas as pd
import streamlit as st

import ai_advisor
import belgian_tax as tax_mod
import bulk_import as bulk
import database as db
import market_data as md

from views.common import (
    _section_radio, _short_ts, asset_label, backfill_eur, clear_cache,
    show_df
)

logger = logging.getLogger("app.settings")


# ── PAGINA: Instellingen ──────────────────────────────────────────────────────

def page_settings():
    st.title("⚙️ Instellingen")

    _ssec = _section_radio("settings_section",
        ["🔑 API-sleutel", "🏦 Rekeningen", "🏭 Sectoren", "🧾 Meerwaardebelasting",
         "🏛️ TOB & bronbelasting", "🗃️ Data"])

    if _ssec == "🔑 API-sleutel":
        st.subheader("OpenAI API & AI-instellingen")
        current = db.get_setting("openai_api_key", "")
        _env_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if _env_key:
            st.info("🔐 Er staat een sleutel in de omgevingsvariabele **OPENAI_API_KEY**. "
                    "Die heeft voorrang op wat hier is opgeslagen — en is veiliger, want ze "
                    "belandt niet in `portfolio.db` (dat bestand staat in `/share` en is "
                    "voor andere add-ons leesbaar).")
        # De opgeslagen sleutel wordt NOOIT als waarde in het invoerveld gezet.
        # 'type=password' maskeert enkel visueel: de echte waarde reist mee naar de
        # browser en staat daar gewoon in de paginastatus. Wie het scherm kan openen,
        # kan de sleutel dan kopiëren. We tonen daarom alleen een herkenningsvorm
        # (eerste en laatste tekens) en laten het veld leeg; leeg laten = ongewijzigd.
        def _mask(k: str) -> str:
            k = (k or "").strip()
            if len(k) <= 12:
                return "•" * len(k)
            return f"{k[:6]}{'•' * 12}{k[-4:]}"

        if current:
            kc1, kc2 = st.columns([3, 1])
            kc1.success(f"✅ API-sleutel geconfigureerd: `{_mask(current)}`")
            with kc2:
                st.write("")
                if st.button("🗑️ Verwijderen", key="api_key_clear",
                             help="Wist de sleutel uit de database. De AI-functies vallen "
                                  "dan stil tot je een nieuwe invult."):
                    db.set_setting("openai_api_key", "")
                    st.success("✅ API-sleutel verwijderd.")
                    st.rerun()
        else:
            st.warning("⚠️ Geen API-sleutel — AI-functies niet beschikbaar.")

        new_key = st.text_input(
            "Nieuwe API-sleutel" if current else "API-sleutel", value="", type="password",
            key="api_key_input",
            help="Beschikbaar via platform.openai.com/api-keys. "
                 + ("Laat leeg om de bestaande sleutel te behouden — ze wordt om "
                    "veiligheidsredenen niet in dit veld getoond."
                    if current else "Wordt opgeslagen in je eigen database."))

        model_keys = list(ai_advisor.AVAILABLE_MODELS.keys())
        def _model_idx(setting, default):
            cur = db.get_setting(setting, default) or default
            return model_keys.index(cur) if cur in model_keys else 0

        m1, m2, m3 = st.columns(3)
        with m1:
            model = st.selectbox("① Model voor portefeuilleadvies", model_keys,
                                 index=_model_idx("openai_model", "gpt-5.6-terra"),
                                 format_func=lambda k: ai_advisor.AVAILABLE_MODELS[k],
                                 help="Gebruikt voor luik 1 (dagelijks portefeuilleadvies) en het "
                                      "maandelijkse belastingadvies.")
        with m2:
            mk_model = st.selectbox("② Model voor marktopportuniteiten", model_keys,
                                    index=_model_idx("openai_market_model", "gpt-5.6-terra"),
                                    format_func=lambda k: ai_advisor.AVAILABLE_MODELS[k],
                                    help="Apart model voor luik 2. Marktonderzoek met live "
                                         "websearch vraagt vaak meer redeneervermogen dan het "
                                         "beoordelen van je eigen posities — hier kan je dus een "
                                         "sterker (of net goedkoper) model kiezen dan voor luik 1.")
        with m3:
            pt_model = st.selectbox("Model voor koersdoelbepaling", model_keys,
                                    index=_model_idx("openai_price_target_model", "gpt-5.6-sol"),
                                    format_func=lambda k: ai_advisor.AVAILABLE_MODELS[k],
                                    help="Mag een sterker (duurder) model zijn dan voor het reguliere advies.")

        # ── Geraamde kost per oproep, per model ──────────────────────────────
        with st.expander("💵 Wat kost één oproep? — raming per model"):
            _ws = db.get_setting("ai_market_websearch", "1") != "0"
            st.caption("Geraamde kost van ÉÉN oproep, per model en per functie. Zodra een functie "
                       "een keer gedraaid heeft, wordt het **gemeten** gemiddelde tokengebruik "
                       "gebruikt (anders een richtwaarde). Voor luik ② is de kost van de "
                       "websearch-oproep en de opgehaalde zoekinhoud meegerekend"
                       + (" (websearch staat AAN)." if _ws else " — maar websearch staat nu UIT.")
                       + " Het blijft een raming: de echte factuur staat op je OpenAI-dashboard.")
            _cost_rows, _measured = [], set()
            for _mk in model_keys:
                _d1 = ai_advisor.estimate_call_cost("daily_advice", _mk)
                _d2 = ai_advisor.estimate_call_cost("market_ideas", _mk, websearch=_ws)
                _dt = ai_advisor.estimate_call_cost("tax_optimization", _mk)
                if _d1["measured"]: _measured.add("① portefeuilleadvies")
                if _d2["measured"]: _measured.add("② marktopportuniteiten")
                if _dt["measured"]: _measured.add("belastingadvies")
                _cost_rows.append({
                    "Model":                     ai_advisor.AVAILABLE_MODELS[_mk],
                    "in $/1M":                   ai_advisor.get_model_pricing().get(_mk, (0, 0))[0],
                    "uit $/1M":                  ai_advisor.get_model_pricing().get(_mk, (0, 0))[1],
                    "① Portefeuilleadvies ($)":  _d1["total"],
                    "② Marktopportuniteiten ($)": _d2["total"],
                    "Belastingadvies ($)":       _dt["total"],
                    "Per maand ($)":             _d1["total"] * 21 + _d2["total"] * 21 + _dt["total"],
                })
            show_df(pd.DataFrame(_cost_rows), column_config={
                "in $/1M":                    st.column_config.NumberColumn(format="$ %.10g"),
                "uit $/1M":                   st.column_config.NumberColumn(format="$ %.10g"),
                "① Portefeuilleadvies ($)":   st.column_config.NumberColumn(format="$ %.4f"),
                "② Marktopportuniteiten ($)": st.column_config.NumberColumn(format="$ %.4f"),
                "Belastingadvies ($)":        st.column_config.NumberColumn(format="$ %.4f"),
                "Per maand ($)":              st.column_config.NumberColumn(
                    format="$ %.2f",
                    help="Ruwe maandraming: 21 werkdagen x (luik ① + luik ②) + 1 belastingadvies."),
            }, dec=4)
            st.caption(("Gemeten tokengebruik gebruikt voor: " + ", ".join(sorted(_measured))
                        + ". De rest is een richtwaarde.") if _measured
                       else "Nog geen historiek: alle bedragen zijn richtwaarden. Na de eerste "
                            "oproepen wordt dit vanzelf accurater.")

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
        en1, en2, en3 = st.columns(3)
        enable_tax = en1.checkbox("Maandelijks belastingadvies actief",
                                  value=db.get_setting("ai_enable_tax", "1") != "0")
        enable_daily = en2.checkbox("① Dagelijks portefeuilleadvies actief",
                                    value=db.get_setting("ai_enable_daily", "1") != "0")
        enable_market = en3.checkbox("② Dagelijkse marktopportuniteiten actief",
                                     value=db.get_setting("ai_enable_market", "1") != "0",
                                     help="Luik 2: elke werkdag 6 koopideeën uit de wereldwijde "
                                          "markt (2 defensief, 2 matig speculatief, 2 sterk "
                                          "speculatief).")
        enable_ws = st.checkbox("🌐 Live websearch voor de marktopportuniteiten",
                                value=db.get_setting("ai_market_websearch", "1") != "0",
                                help="Laat de AI zelf actuele koersen, resultaten en "
                                     "berichtgeving opzoeken via de websearch-tool van OpenAI. "
                                     "Zonder dit put ze enkel uit haar trainingskennis en kent ze "
                                     "het nieuws van vandaag niet. Kost iets meer per oproep; valt "
                                     "automatisch terug op gewoon advies als je model de tool niet "
                                     "ondersteunt.")

        if st.button("💾 Opslaan", key="save_api"):
            # Leeg veld = sleutel ongewijzigd laten. Zou hier onvoorwaardelijk
            # weggeschreven worden, dan wiste elke wijziging aan een modelkeuze
            # stilzwijgend je sleutel.
            _k = (new_key or "").strip()
            if _k:
                db.set_setting("openai_api_key", _k)
            db.set_setting("openai_model", model)
            db.set_setting("openai_market_model", mk_model)
            db.set_setting("openai_price_target_model", pt_model)
            db.set_setting("investment_volume_month", str(vol_m))
            db.set_setting("investment_volume_year", str(vol_y))
            db.set_setting("ai_privacy_mode", privacy)
            db.set_setting("ai_enable_tax", "1" if enable_tax else "0")
            db.set_setting("ai_enable_daily", "1" if enable_daily else "0")
            db.set_setting("ai_enable_market", "1" if enable_market else "0")
            db.set_setting("ai_market_websearch", "1" if enable_ws else "0")
            st.success("✅ Instellingen opgeslagen!"
                       + (" Nieuwe API-sleutel bewaard." if _k else ""))
            if _k:
                st.rerun()

    if _ssec == "🏦 Rekeningen":
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

    if _ssec == "🏭 Sectoren":
        st.subheader("🏭 Domeinen / sectoren")
        st.caption(
            "De sector van een activum bepaalt het taartdiagram **Spreiding per domein** op "
            "de portefeuillepagina. De app levert de elf GICS-hoofdsectoren mee, aangevuld "
            "met *Gediversifieerd (index/fonds)* voor brede trackers en *Overige*. Die lijst "
            "is volledig van jou: voeg toe, hernoem of gooi weg wat je niet gebruikt.")

        assets_all = db.get_assets()
        cur_secs = db.get_sectors()
        in_use = {}
        for a in assets_all:
            s = (a.get("sector") or "").strip()
            if s:
                in_use[s] = in_use.get(s, 0) + 1
        n_unassigned = sum(1 for a in assets_all if not (a.get("sector") or "").strip())

        m1, m2, m3 = st.columns(3)
        m1.metric("Rubrieken in de lijst", str(len(cur_secs)))
        m2.metric("Activa met een sector", str(len(assets_all) - n_unassigned))
        m3.metric("Nog niet toegewezen", str(n_unassigned),
                  delta_color="off",
                  help="Deze activa belanden samen onder 'Niet toegewezen' in het "
                       "taartdiagram. Ken ze hieronder toe of haal ze online op.")

        st.divider()
        st.markdown("**➕ Rubriek toevoegen**")
        ac1, ac2 = st.columns([3, 1])
        new_sec = ac1.text_input("Naam", key="set_sec_new", label_visibility="collapsed",
                                 placeholder="bv. Defensie, Waterstof, Infrastructuur")
        if ac2.button("Toevoegen", key="set_sec_add", width="stretch"):
            if not new_sec.strip():
                st.warning("Geef eerst een naam in.")
            elif db.add_sector(new_sec.strip()):
                st.success(f"✅ '{new_sec.strip()}' toegevoegd.")
                st.rerun()
            else:
                st.info("Die rubriek staat al in de lijst.")

        st.markdown("**✏️ Rubriek hernoemen**")
        st.caption("Hernoemt de rubriek overal in één keer: in de lijst én op elk activum "
                   "dat ze gebruikt. Zo blijft er niets achter onder de oude naam.")
        rc1, rc2, rc3 = st.columns([2, 2, 1])
        _ren_from = rc1.selectbox("Van", cur_secs, key="set_sec_ren_from",
                                  format_func=lambda s: f"{s}  ({in_use.get(s, 0)} activa)")
        _ren_to = rc2.text_input("Naar", key="set_sec_ren_to", placeholder="nieuwe naam")
        rc3.write("")
        if rc3.button("Hernoemen", key="set_sec_ren_btn", width="stretch"):
            if not _ren_to.strip():
                st.warning("Geef een nieuwe naam in.")
            elif _ren_to.strip() == _ren_from:
                st.info("Oude en nieuwe naam zijn gelijk.")
            else:
                n_moved = db.rename_sector(_ren_from, _ren_to.strip())
                clear_cache()
                st.success(f"✅ '{_ren_from}' → '{_ren_to.strip()}' "
                           f"({n_moved} activum/activa mee omgezet).")
                st.rerun()

        st.markdown("**📋 De volledige lijst**")
        show_df(pd.DataFrame([{
            "Sector": s,
            "Activa": in_use.get(s, 0),
            "Herkomst": "standaard" if s in db.DEFAULT_SECTORS else "eigen",
        } for s in cur_secs]), width="stretch", hide_index=True, column_config={
            "Activa": st.column_config.NumberColumn(
                format="%d", help="Hoeveel activa deze rubriek nu gebruiken."),
            "Herkomst": st.column_config.TextColumn(
                help="'standaard' = een van de rubrieken die de app meelevert, "
                     "'eigen' = door jou toegevoegd."),
        })

        _unused = [s for s in cur_secs if not in_use.get(s)]
        if _unused:
            dc1, dc2 = st.columns([3, 1])
            _del = dc1.multiselect("Verwijderen (enkel ongebruikte rubrieken)", _unused,
                                   key="set_sec_del")
            dc2.write("")
            if dc2.button("🗑️ Verwijderen", key="set_sec_del_btn", width="stretch") and _del:
                for s in _del:
                    db.remove_sector(s)
                st.success(f"✅ {len(_del)} rubriek(en) verwijderd.")
                st.rerun()
            st.caption("Enkel rubrieken die aan géén enkel activum hangen kunnen weg. Wil je "
                       "een rubriek in gebruik toch kwijt, hernoem ze dan eerst of wijs de "
                       "activa hieronder aan een andere rubriek toe.")
        else:
            st.caption("Alle rubrieken zijn in gebruik — er valt niets te verwijderen.")

        st.divider()
        st.markdown("**🗂️ Sectoren toewijzen aan je activa**")
        st.caption("Wijzig de kolom *Sector* en klik op opslaan. Sneller dan activum per "
                   "activum via de Activa-pagina, en je ziet in één oogopslag welke nog "
                   "leeg staan.")
        SEC_EMPTY = "—"
        _sopts = [SEC_EMPTY] + cur_secs
        only_empty = st.checkbox("Toon enkel activa zonder sector", key="set_sec_only_empty",
                                 value=bool(n_unassigned))
        _rows_a = [a for a in assets_all
                   if not only_empty or not (a.get("sector") or "").strip()]
        if not _rows_a:
            st.success("✅ Elk activum heeft een sector.")
        else:
            _srows = []
            for a in _rows_a:
                _s = (a.get("sector") or "").strip() or SEC_EMPTY
                if _s not in _sopts:
                    _sopts.append(_s)
                _srows.append({
                    "Ticker": a["ticker"],
                    "Naam":   (a.get("name") or a["ticker"])[:32],
                    "Type":   {"stock": "Aandeel", "etf": "ETF",
                               "bond": "Obligatie"}.get(a["asset_type"], a["asset_type"]),
                    "Sector": _s,
                    "Bron":   {"auto": "automatisch", "manual": "door jou"}.get(
                        a.get("sector_source") or "", ""),
                })
            _sed = st.data_editor(
                pd.DataFrame(_srows), width="stretch", hide_index=True,
                key="set_sec_editor", num_rows="fixed", column_config={
                    "Ticker": st.column_config.TextColumn(disabled=True),
                    "Naam":   st.column_config.TextColumn(disabled=True),
                    "Type":   st.column_config.TextColumn(disabled=True),
                    "Sector": st.column_config.SelectboxColumn(
                        options=_sopts,
                        help="'—' = nog niet toegewezen. Voor brede indextrackers kies je "
                             "best 'Gediversifieerd (index/fonds)': die zitten in alle "
                             "sectoren tegelijk en zouden je spreiding anders vertekenen."),
                    "Bron":   st.column_config.TextColumn(
                        disabled=True,
                        help="'automatisch' = online opgehaald, 'door jou' = handmatig "
                             "gezet. Een online ophaalronde raakt jouw toewijzingen nooit aan."),
                })
            if st.button("💾 Toewijzingen opslaan", type="primary", key="set_sec_save"):
                n_upd = 0
                for i, a in enumerate(_rows_a):
                    new_val = str(_sed.iloc[i]["Sector"]).strip()
                    old_val = (a.get("sector") or "").strip() or SEC_EMPTY
                    if new_val == old_val:
                        continue
                    db.set_asset_sector(a["ticker"],
                                        None if new_val == SEC_EMPTY else new_val,
                                        source="manual")
                    n_upd += 1
                if n_upd:
                    clear_cache()
                    st.success(f"✅ {n_upd} activum/activa bijgewerkt.")
                    st.rerun()
                else:
                    st.info("Geen wijzigingen gevonden.")

        st.divider()
        st.markdown("**🔎 Sectoren online ophalen**")
        st.caption(
            "Vraagt per activum de sector op bij Yahoo Finance — eerst via het ticker, en "
            "anders via de ISIN, wat vaak wél lukt bij .BR-noteringen. De Engelse "
            "sectornamen worden vertaald naar de rubrieken hierboven. Standaard worden "
            "enkel activa **zonder** sector ingevuld; sectoren die jíj gezet hebt blijven "
            "hoe dan ook ongemoeid. Fondsen en trackers krijgen bij de bron meestal geen "
            "sector — dat is geen fout, die ken je zelf toe.")
        oc1, oc2 = st.columns([3, 1])
        _overwrite = oc1.checkbox("Ook eerder automatisch toegekende sectoren vernieuwen",
                                  key="set_sec_over")
        oc2.write("")
        if oc2.button("🔎 Ophalen", key="set_sec_fetch", width="stretch"):
            res_rows, n_set = [], 0
            _targets = [a for a in assets_all
                        if not (a.get("sector") or "").strip()
                        or (_overwrite and (a.get("sector_source") or "") == "auto")]
            with st.spinner(f"Sector opzoeken voor {len(_targets)} activum/activa..."):
                for a in _targets:
                    try:
                        si = md.get_sector_info(a["ticker"], a.get("isin"))
                    except Exception as exc:
                        res_rows.append({"Activum": asset_label(a["ticker"]),
                                         "Gevonden": "—", "Uitslag": f"Fout: {exc}"})
                        continue
                    sn = db.normalize_sector(si.get("sector"))
                    if sn:
                        db.set_asset_sector(a["ticker"], sn, source="auto")
                        n_set += 1
                        uit = f"✅ Toegekend via {si.get('bron') or 'online'}"
                    elif a["asset_type"] == "etf":
                        uit = ("Geen sector bij de bron — normaal voor een tracker. "
                               "Zet ze zelf op 'Gediversifieerd (index/fonds)'.")
                    else:
                        uit = "Geen sector gevonden — zelf toe te kennen hierboven."
                    res_rows.append({"Activum": asset_label(a["ticker"]),
                                     "Gevonden": si.get("sector") or "—", "Uitslag": uit})
            st.session_state["sec_fetch_result"] = res_rows
            st.session_state["sec_fetch_msg"] = (
                f"Klaar — {n_set} activum/activa kregen een sector."
                + ("" if n_set else "  Niets gevonden: fondsen en trackers hebben bij de "
                                    "bron meestal geen sector, die ken je zelf toe."))
            if n_set:
                clear_cache()
            st.rerun()
        if st.session_state.get("sec_fetch_msg"):
            st.success(st.session_state.pop("sec_fetch_msg"))
        if st.session_state.get("sec_fetch_result"):
            show_df(pd.DataFrame(st.session_state["sec_fetch_result"]),
                    width="stretch", hide_index=True)

    if _ssec == "🧾 Meerwaardebelasting":
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

        st.divider()
        st.subheader("💰 Dividendvrijstelling (personenbelasting)")
        st.caption("De eerste schijf 'gewone' aandelendividenden per belastingplichtige is vrijgesteld "
                   "van roerende voorheffing; je recupereert die RV via de aangifte (codes 1437/2437). "
                   "Geldt niet voor dividenden van fondsen/ETF's. Het bedrag is sinds 2025 niet "
                   "geïndexeerd (t/m aanslagjaar 2030).")
        div_exemp = st.number_input("Vrijgestelde dividenden per persoon (€)",
                                    min_value=0.0, value=float(db.get_setting("dividend_exemption_per_person", "833")),
                                    step=1.0,
                                    help="Inkomstenjaar 2025/2026: €833 p.p. (max €249,90 recupereerbare RV p.p.). "
                                         "Het aantal personen volgt uit het huwelijksstelsel hierboven.")
        fbb_on = st.checkbox("FBB voor Franse aandelen toepassen",
                             value=db.get_setting("fbb_enabled", "0") == "1",
                             help="Forfaitair gedeelte buitenlandse belasting (verdrag BE-FR): 15% van het "
                                  "nettobedrag na Franse bronheffing. De fiscus aanvaardt dit na rechtspraak "
                                  "(Hof van Cassatie), maar het blijft betwist — raadpleeg een fiscalist.")
        fbb_r = st.number_input("FBB-tarief (%)", min_value=0.0, max_value=100.0,
                                value=float(db.get_setting("fbb_rate", "0.15")) * 100, step=0.5,
                                disabled=not fbb_on)
        if st.button("💾 Dividendvrijstelling opslaan", key="save_div_tax"):
            db.set_setting("dividend_exemption_per_person", str(div_exemp))
            db.set_setting("fbb_enabled", "1" if fbb_on else "0")
            db.set_setting("fbb_rate", str(fbb_r / 100))
            clear_cache()
            st.success("✅ Dividendvrijstelling opgeslagen!")

    if _ssec == "🏛️ TOB & bronbelasting":
        st.subheader("Taks op Beursverrichtingen (TOB)")
        c1, c2 = st.columns(2)
        with c1:
            r_s  = st.number_input("Aandelen tarief (%)", value=float(db.get_setting("tob_rate_stocks", "0.0035"))*100, step=0.001, format="%.10g")
            r_ed = st.number_input("ETF distribuerend (%)", value=float(db.get_setting("tob_rate_etf_distributing", "0.0012"))*100, step=0.001, format="%.10g")
            r_ea = st.number_input("ETF kapitaliseerend (%)", value=float(db.get_setting("tob_rate_etf_accumulating", "0.0132"))*100, step=0.001, format="%.10g")
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

        st.divider()
        st.subheader("🌍 Buitenlandse bronbelasting op dividenden — per jaar")
        st.caption("Tarief per land van herkomst (het land stel je in per activum op de 🏢 Activa-pagina), "
                   "**per jaar**. Bronbelastingen wijzigen over de jaren, en een dividend hoort belast te "
                   "worden tegen het tarief dat gold **op dat moment** — niet tegen het tarief van vandaag. "
                   "Tarieven **schuiven door**: stel je 2024 in, dan geldt dat ook voor 2025, 2026, ... tot "
                   "je voor een van die jaren iets anders instelt. Je registreert dus enkel de "
                   "**wijzigingen**. Standaardtarieven zijn indicatief — verdragstarieven kunnen afwijken.")

        # Dekking: voor elk jaar met dividenden moet er een tarief gekend zijn
        _dyears = sorted({tax_mod.year_of(d["date"]) for d in db.get_dividends()
                          if (d.get("kind") or "dividend") == "dividend"
                          and tax_mod.year_of(d["date"])})
        _tyears = sorted({tax_mod.year_of(t["date"]) for t in db.get_transactions()
                          if tax_mod.year_of(t["date"])})
        _years_needed = sorted(set(_dyears) | set(_tyears) | {datetime.now().year})
        _cfg = tax_mod.configured_years()
        if _cfg:
            _uncovered = [y for y in _years_needed if y < min(_cfg)]
            if _uncovered:
                st.warning(f"⚠️ Voor {', '.join(map(str, _uncovered))} is er geen jaartabel: die "
                           f"jaren vallen terug op de standaardtarieven. Het vroegst ingestelde jaar "
                           f"is {min(_cfg)}. Stel het oudste jaar in dat je nodig hebt — alle latere "
                           "jaren erven dat automatisch.")
            else:
                st.success(f"✅ Alle jaren met transacties of dividenden ({_years_needed[0]}–"
                           f"{_years_needed[-1]}) zijn gedekt. Ingestelde jaren: "
                           f"{', '.join(map(str, _cfg))}.")
        else:
            st.info("Nog geen jaartabel ingesteld — alles gebruikt voorlopig de standaardtarieven. "
                    "Sla hieronder een jaar op om de historiek vast te leggen.")

        _yopts = sorted(set(_years_needed) | set(_cfg) | {datetime.now().year + 1})
        wy = st.selectbox("Jaar", _yopts, index=_yopts.index(datetime.now().year),
                          key="wht_year",
                          format_func=lambda y: (f"{y} · eigen tarieven ingesteld" if y in _cfg
                                                 else f"{y} · erft van "
                                                      f"{max([c for c in _cfg if c <= y], default='de standaard')}"))
        rates_now = tax_mod.get_wht_rates(wy)
        wrows = [{"Land": c, "Naam": tax_mod.COUNTRY_NAMES.get(c, c), "Tarief (%)": rates_now[c]}
                 for c in sorted(rates_now.keys())]
        wcg = st.column_config
        wedit = st.data_editor(
            pd.DataFrame(wrows), width="stretch", hide_index=True, key=f"wht_editor_{wy}",
            num_rows="dynamic",
            column_config={
                "Land":       wcg.TextColumn(help="Landcode (2 letters, bv. US)", max_chars=2),
                "Naam":       wcg.TextColumn(disabled=True),
                "Tarief (%)": wcg.NumberColumn(min_value=0.0, max_value=100.0, format="%.10g"),
            })
        wb1, wb2, _ = st.columns([2, 2, 3])
        if wb1.button(f"💾 Tarieven {wy} opslaan", key="save_wht", type="primary"):
            try:
                new_rates = {}
                for _, r in wedit.iterrows():
                    code = str(r["Land"] or "").strip().upper()
                    if len(code) == 2 and code.isalpha() and not pd.isna(r["Tarief (%)"]):
                        new_rates[code] = float(r["Tarief (%)"])
                tax_mod.save_year_rates(wy, new_rates)
                clear_cache()
                st.success(f"✅ {len(new_rates)} tarieven opgeslagen voor **{wy}** (en voor alle "
                           "latere jaren zonder eigen tabel). Bestaande dividenden worden hierdoor "
                           "niet herberekend — gebruik daarvoor de knop op de 💰 Dividenden-pagina.")
            except Exception as exc:
                st.error(f"Kon de tarieven niet opslaan: {exc}")
        if wy in _cfg and wb2.button(f"🗑️ Jaartabel {wy} wissen", key="del_wht_year"):
            tax_mod.delete_year_rates(wy)
            clear_cache()
            st.success(f"Jaartabel {wy} gewist — dat jaar erft nu weer van het vorige jaar.")
            st.rerun()
        with st.expander("📅 Overzicht van de ingestelde jaren"):
            if not _cfg:
                st.caption("Nog geen enkel jaar ingesteld.")
            else:
                _codes = sorted({c for y in _cfg for c in tax_mod._year_rate_table()[y]})
                _ov = [{"Land": c, "Naam": tax_mod.COUNTRY_NAMES.get(c, c),
                        **{str(y): tax_mod.get_wht_rates(y).get(c) for y in _cfg}}
                       for c in _codes]
                show_df(pd.DataFrame(_ov), width="stretch", hide_index=True)
                st.caption("Elk jaar toont het tarief dat er effectief geldt (dus inclusief wat het "
                           "van een vorig jaar erft).")

    if _ssec == "🗃️ Data":
        st.subheader("Databeheer")
        assets = db.get_assets()
        txns   = db.get_transactions()
        divs   = db.get_dividends()
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Activa", len(assets))
        c2.metric("Transacties", len(txns))
        c3.metric("Dividenden", len(divs))
        c4.metric("Database", f"{db.database_size() / 1_000_000:.1f} MB")
        st.divider()

        # ── Back-up ──────────────────────────────────────────────────────────
        st.subheader("💾 Back-up en herstel")
        _backups = db.list_backups()
        _last_auto = db.get_setting("backup_last_run")
        st.caption(
            "Je volledige administratie zit in één databasebestand. Een back-up is een "
            "consistente kopie daarvan, gemaakt terwijl de app doordraait (`VACUUM INTO`) "
            "— dus niet zomaar een bestandskopie, die bij een draaiende database "
            f"onbetrouwbaar is. De kopieën staan in `{db.backup_dir()}`. "
            "Er wordt automatisch een kopie gemaakt telkens de app start, dus vlak vóór "
            "een nieuwe versie de database bijwerkt: precies het moment waarop je terug "
            "wil kunnen.")

        if not _backups:
            st.warning("⚠️ Er is nog **geen enkele back-up**. Maak er nu één — het duurt "
                       "een seconde en het scheelt je een reconstructie van jaren "
                       "invoerwerk als er iets misgaat.")
        else:
            _newest = _backups[0]
            _age_h = (datetime.now() - _newest["created"]).total_seconds() / 3600
            _msg = (f"Nieuwste back-up: **{_newest['name']}** "
                    f"({_newest['created'].strftime('%d/%m/%Y %H:%M')}, "
                    f"{_newest['size'] / 1_000_000:.1f} MB) · {len(_backups)} bewaard")
            if _age_h > 48:
                st.warning("⚠️ " + _msg + f" — dat is {_age_h / 24:.0f} dagen geleden.")
            else:
                st.success("✅ " + _msg)

        bc1, bc2, bc3 = st.columns([1, 1, 2])
        if bc1.button("💾 Nu back-uppen", type="primary", key="bk_now"):
            try:
                b = db.create_backup("handmatig")
                db.prune_backups(int(db.get_setting("backup_keep", "14") or 14))
                st.success(f"✅ Back-up gemaakt: **{b['name']}** "
                           f"({b['size'] / 1_000_000:.1f} MB)")
                st.rerun()
            except Exception as exc:
                st.error(f"❌ Back-up mislukt: {exc}")
        with bc2:
            if _backups:
                try:
                    with open(_backups[0]["path"], "rb") as _fh:
                        st.download_button("⬇️ Nieuwste ophalen", data=_fh.read(),
                                           file_name=_backups[0]["name"],
                                           mime="application/vnd.sqlite3",
                                           key="bk_dl_latest",
                                           help="Bewaar deze kopie ergens ANDERS dan op dit "
                                                "toestel — een back-up naast het origineel "
                                                "helpt niet bij een defecte schijf.")
                except OSError as exc:
                    st.error(f"Kon de back-up niet lezen: {exc}")
        with bc3:
            _auto_on = db.get_setting("backup_auto", "1") != "0"
            _keep_cur = int(db.get_setting("backup_keep", "14") or 14)
            ac1, ac2 = st.columns([2, 1])
            _auto_new = ac1.checkbox("Automatische back-up (dagelijks 02:30 + bij elke start)",
                                     value=_auto_on, key="bk_auto")
            _keep_new = ac2.number_input("Bewaren", min_value=1, max_value=200,
                                         value=_keep_cur, step=1, key="bk_keep",
                                         help="Aantal back-ups dat bewaard blijft; de oudste "
                                              "worden opgeruimd.")
            if _auto_new != _auto_on or int(_keep_new) != _keep_cur:
                db.set_setting("backup_auto", "1" if _auto_new else "0")
                db.set_setting("backup_keep", str(int(_keep_new)))
                st.caption("✅ Opgeslagen.")
        if _last_auto:
            st.caption(f"Laatste automatische back-up: {_short_ts(_last_auto)}.")

        with st.expander(f"📂 Alle back-ups ({len(_backups)})"):
            if not _backups:
                st.info("Nog geen back-ups.")
            else:
                for b in _backups:
                    r1, r2, r3 = st.columns([3, 1, 1])
                    r1.write(f"**{b['name']}**  \n"
                             f"{b['created'].strftime('%d/%m/%Y %H:%M')} · "
                             f"{b['size'] / 1_000_000:.1f} MB")
                    with r2:
                        try:
                            with open(b["path"], "rb") as _fh:
                                st.download_button("⬇️", data=_fh.read(), file_name=b["name"],
                                                   mime="application/vnd.sqlite3",
                                                   key=f"bk_dl_{b['name']}")
                        except OSError:
                            st.caption("onleesbaar")
                    if r3.button("🗑️", key=f"bk_del_{b['name']}",
                                 help="Deze back-up verwijderen"):
                        if db.delete_backup(b["name"]):
                            st.success(f"✅ {b['name']} verwijderd.")
                            st.rerun()
                        else:
                            st.error("Verwijderen mislukt.")

        with st.expander("♻️ Herstellen vanaf een back-up"):
            st.warning(
                "Een herstel **overschrijft je huidige database volledig**. Alles wat je "
                "sinds die back-up hebt ingevoerd, is dan weg. Er wordt automatisch eerst "
                "een veiligheidskopie van de huidige toestand gemaakt (`voor-herstel`), "
                "zodat ook een verkeerd herstel nog terug te draaien is.")
            st.caption("Na het herstel moet de add-on **herstart** worden: de draaiende "
                       "app en de achtergrondplanner hebben de oude database nog open.")

            _rsrc = st.radio("Herstellen vanaf", ["Een bewaarde back-up", "Een geüpload bestand"],
                             horizontal=True, key="bk_restore_src")
            _path, _label = None, ""
            if _rsrc == "Een bewaarde back-up":
                if not _backups:
                    st.info("Er zijn geen bewaarde back-ups.")
                else:
                    _pick = st.selectbox(
                        "Back-up", _backups,
                        format_func=lambda b: (f"{b['name']} · "
                                               f"{b['created'].strftime('%d/%m/%Y %H:%M')} · "
                                               f"{b['size'] / 1_000_000:.1f} MB"),
                        key="bk_restore_pick")
                    _path, _label = _pick["path"], _pick["name"]
            else:
                _up = st.file_uploader("Databasebestand (.db)", type=["db", "sqlite", "sqlite3"],
                                       key="bk_restore_upload")
                if _up is not None:
                    import tempfile
                    _tmp = os.path.join(tempfile.gettempdir(), "restore_upload.db")
                    with open(_tmp, "wb") as _fh:
                        _fh.write(_up.getbuffer())
                    _path, _label = _tmp, _up.name

            if _path:
                _chk = db.validate_database_file(_path)
                if not _chk["ok"]:
                    st.error(f"❌ {_chk['reason']}")
                else:
                    _c = _chk["counts"]
                    st.info(f"📋 **{_label}** bevat: {_c.get('assets', 0)} activa · "
                            f"{_c.get('transactions', 0)} transacties · "
                            f"{_c.get('dividends', 0)} dividenden.  \n"
                            f"Je huidige database: {len(assets)} activa · {len(txns)} "
                            f"transacties · {len(divs)} dividenden.")
                    _rn = st.session_state.get("bk_restore_nonce", 0)
                    if st.checkbox("Ja, ik begrijp dat mijn huidige gegevens overschreven worden",
                                   key=f"bk_restore_confirm_{_rn}"):
                        if st.button("♻️ Herstel nu uitvoeren", type="primary",
                                     key="bk_restore_go"):
                            try:
                                res = db.restore_backup(_path)
                                clear_cache()
                                st.session_state["bk_restore_nonce"] = _rn + 1
                                st.success(
                                    f"✅ Hersteld vanaf **{_label}**. Veiligheidskopie van je "
                                    f"vorige toestand: **{res['safety_backup']['name']}**.  \n"
                                    "**Herstart nu de add-on** (Home Assistant → add-on → "
                                    "Herstarten) zodat alle processen de herstelde database "
                                    "gebruiken.")
                            except Exception as exc:
                                st.error(f"❌ Herstel mislukt: {exc}")

        st.divider()

        st.subheader("📥 Bulk-import via Excel")
        st.caption("Laad transacties, dividenden en rekeningkosten in bulk op. Download eerst de "
                   "template, vul ze in en upload ze. Onbekende activa worden automatisch aangemaakt "
                   "(vul naam/type/munt in voor een correcte TOB).")
        try:
            st.download_button("⬇️ Download Excel-template", data=bulk.build_template(),
                               file_name="portfolio_import_template.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                               key="dl_template")
        except Exception as exc:
            st.error(f"Kon de template niet genereren: {exc}")

        up = st.file_uploader("Upload ingevulde Excel", type=["xlsx"], key="bulk_upload")
        if up is not None:
            try:
                parsed = bulk.parse_workbook(up)
            except Exception as exc:
                parsed = None
                st.error(f"Kon het bestand niet verwerken: {exc}")
            if parsed is not None:
                n_t = len(parsed["transacties"]); n_d = len(parsed["dividenden"])
                n_k = len(parsed["kosten"]);      n_a = len(parsed["new_assets"])
                pc1, pc2, pc3, pc4 = st.columns(4)
                pc1.metric("Transacties", n_t)
                pc2.metric("Dividenden", n_d)
                pc3.metric("Kosten", n_k)
                pc4.metric("Nieuwe activa", n_a)
                if parsed["errors"]:
                    with st.expander(f"⚠️ {len(parsed['errors'])} rij(en) overgeslagen — bekijk de fouten",
                                     expanded=True):
                        for e in parsed["errors"]:
                            st.write("• " + e)
                if n_a:
                    st.caption("Nieuw aan te maken activa: "
                               + ", ".join(f"{tk} ({i['asset_type']})" for tk, i in parsed["new_assets"].items())
                               + ". Controleer nadien het type/ETF-subtype op de Activa-pagina.")
                total = n_t + n_d + n_k
                if total == 0:
                    st.warning("Geen geldige rijen gevonden om te importeren.")
                elif st.button(f"✅ Importeer {total} rij(en)", type="primary", key="do_bulk_import"):
                    with st.spinner("Importeren..."):
                        summ = bulk.apply_import(parsed)
                        clear_cache()
                    st.success(f"✅ Geïmporteerd: {summ['transacties']} transacties, "
                               f"{summ['dividenden']} dividenden, {summ['kosten']} kosten, "
                               f"{summ['assets']} nieuwe activa aangemaakt.")
                    st.caption("Tip: draai eventueel '💱 Herbereken EUR-bedragen' hieronder als je "
                               "vreemde munten zonder fx_koers importeerde.")
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
