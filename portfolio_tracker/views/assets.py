"""
views/assets.py — pagina 'Activa'.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

import ai_advisor
import belgian_tax as tax_mod
import database as db
import market_data as md

from views.common import (
    _cell_eq, _section_radio, _short_ts, _ui_save, asset_label, clear_cache,
    compute_eur, multiselect_delete, num, show_df
)

logger = logging.getLogger("app.assets")


# ── PAGINA: Activa ────────────────────────────────────────────────────────────

def page_assets():
    st.title("🏢 Activa beheren")

    CUR = ["EUR", "USD", "GBP", "CHF"]
    _asec = _section_radio("assets_section",
        ["➕ Activum toevoegen", "📋 Overzicht", "🔀 Splitsingen"])

    if _asec == "➕ Activum toevoegen":
        n = st.session_state.get("as_nonce", 0)
        def k(name): return f"as_{name}_{n}"

        st.caption("Tip: vul de ticker in en klik op **🔍 Info ophalen** — naam, munt, type, beurs en ISIN "
                   "worden dan ingevuld in het formulier, zodat je ze kunt nakijken vóór je opslaat.")
        c1, c2 = st.columns(2)
        with c1:
            ticker = st.text_input("Ticker *", placeholder="bv. AAPL, VWCE.AS", key=k("ticker"))
            if st.button("🔍 Info ophalen via Yahoo Finance", key=k("fetch")):
                if not ticker.strip():
                    st.warning("Vul eerst een ticker in.")
                else:
                    with st.spinner("Info ophalen via Yahoo Finance..."):
                        info = md.get_stock_info(ticker.strip().upper())
                    _tk = ticker.strip().upper()
                    if not info.get("found") and md._isin_valid(_tk):
                        # Geen Yahoo-notering, maar het is een geldige ISIN (bv. een warrant).
                        # Vul naam/type/beurs/land in en probeer de munt/koers via externe bronnen.
                        with st.spinner("ISIN testen op externe bronnen..."):
                            _p, _c, _src = md.probe_isin(_tk)
                            _meta = md.probe_isin_meta(_tk)
                        st.session_state[k("isin")] = _tk
                        st.session_state[k("country")] = _tk[:2]
                        st.session_state[k("cur")] = _c or "EUR"
                        st.session_state[k("isin_only_src")] = _src or ""
                        if _meta.get("name"):
                            st.session_state[k("name")] = _meta["name"]
                        if _meta.get("type"):
                            st.session_state[k("type")] = _meta["type"]
                        if _meta.get("exchange"):
                            st.session_state[k("exch")] = _meta["exchange"]
                        _si = md.get_sector_info(_tk, _tk)
                        if _si.get("sector"):
                            _sn = db.normalize_sector(_si["sector"])
                            if _sn:
                                db.add_sector(_sn)
                                st.session_state[k("sector_stage")] = _sn
                                st.session_state[k("sector_src")] = _si.get("bron") or "online"
                        st.session_state[k("fetched")] = True
                        st.rerun()
                    elif not info.get("found"):
                        st.error(
                            f"❌ Yahoo Finance vond geen gegevens voor '{_tk}'. "
                            "Controleer de ticker — Europese beurzen vereisen een suffix "
                            "(bv. .PA Parijs, .AS Amsterdam, .BR Brussel, .DE Xetra, .MI Milaan, .L Londen). "
                            "Heeft dit effect geen ticker maar wél een ISIN (bv. een warrant)? "
                            "Vul dan de ISIN in het Ticker-veld in.")
                    else:
                        st.session_state[k("name")] = info.get("name", "") or ""
                        st.session_state[k("cur")]  = info.get("currency", "EUR") or "EUR"
                        st.session_state[k("type")] = info.get("type", "stock") or "stock"
                        st.session_state[k("exch")] = info.get("exchange", "") or ""
                        st.session_state[k("isin")] = info.get("isin", "") or ""
                        _isin = (info.get("isin") or "").strip().upper()
                        if len(_isin) >= 2 and _isin[:2].isalpha():
                            st.session_state[k("country")] = _isin[:2]
                        # Domein/sector: Yahoo geeft die mee voor aandelen. Fondsen en
                        # trackers hebben er meestal geen — dat is geen fout, een brede
                        # tracker zit nu eenmaal in alle sectoren tegelijk.
                        _sn = db.normalize_sector(info.get("sector"))
                        if _sn:
                            db.add_sector(_sn)
                            st.session_state[k("sector_stage")] = _sn
                            st.session_state[k("sector_src")] = "Yahoo Finance"
                        elif info.get("type") == "etf":
                            st.session_state[k("sector_stage")] = "Gediversifieerd (index/fonds)"
                            st.session_state[k("sector_src")] = "afgeleid (fonds/tracker)"
                        st.session_state[k("fetched")] = True
                        if not (info.get("isin") or "").strip():
                            st.session_state[k("isin_missing")] = True
                        else:
                            st.session_state.pop(k("isin_missing"), None)
                        st.rerun()
            if st.session_state.get(k("isin_missing")):
                st.warning("ℹ️ Yahoo gaf voor deze ticker geen ISIN mee (komt vaak voor bij "
                           ".BR/.DE-listings). Vul de ISIN hieronder handmatig in — je vindt ze op "
                           "de website van de uitgever, op justETF, of op de beurspagina.")
            name = st.text_input("Naam *", key=k("name"),
                                 placeholder="bv. Vanguard FTSE All-World")
            cur_val  = st.session_state.get(k("cur"), "EUR")
            cur_opts = CUR if cur_val in CUR else CUR + [cur_val]
            currency = st.selectbox("Munt", cur_opts, key=k("cur"))
        with c2:
            asset_type = st.radio("Type", ["stock", "etf", "bond"],
                                  format_func=lambda x: {"stock": "📊 Aandeel", "etf": "🧺 ETF/fonds", "bond": "📈 Obligatie"}[x],
                                  key=k("type"))
            etf_subtype = "distributing"
            belg_reg = True
            if asset_type == "etf":
                etf_subtype = st.radio("ETF-type", ["distributing", "accumulating"],
                                       format_func=lambda x: "📤 Uitkerend (distributie)" if x == "distributing" else "📦 Kapitaliserend",
                                       help="Samen met de registratie bepaalt dit de TOB.", key=k("sub"))
                belg_reg = st.checkbox("🇧🇪 In België aangeboden / geregistreerd (FSMA)",
                                       value=st.session_state.get(k("breg"), True), key=k("breg"),
                                       help="Vink AAN voor in België aangeboden fondsen (TOB 0,12% uitkerend / 1,32% kapitaliserend). "
                                            "Vink UIT voor niet in België aangeboden trackers/ETC's (bv. G2XJ.DE): dan geldt 0,35%.")
            exchange = st.text_input("Beurs", key=k("exch"), placeholder="bv. NMS, AMS")
            isin     = st.text_input("ISIN", key=k("isin"), placeholder="bv. IE00BK5BQT80")
            _clist = list(tax_mod.COUNTRY_NAMES.keys())
            # Default via session state (géén index-parameter): de fetch-flows zetten
            # het land ook via st.session_state, en Streamlit staat niet toe dat een
            # widget zowel een default als een session-state-waarde krijgt.
            st.session_state.setdefault(k("country"), "BE")
            if st.session_state[k("country")] not in _clist:
                _clist = _clist + [st.session_state[k("country")]]
            country = st.selectbox("Land van herkomst", _clist, key=k("country"),
                                   format_func=lambda c: f"{c} — {tax_mod.COUNTRY_NAMES.get(c, c)}",
                                   help="Bepaalt het tarief van de buitenlandse bronbelasting bij "
                                        "dividenden (zie ⚙️ Instellingen). Tip: het land van de "
                                        "uitgever, vaak herkenbaar aan de eerste 2 letters van de ISIN.")

        # TOB-indicatie tonen
        _tob_rate = tax_mod.calculate_tob(asset_type, etf_subtype, 10000, belg_reg) / 10000 * 100
        st.caption(f"➡️ TOB-tarief voor dit activum: **{_tob_rate:.2f}%**".replace(".", ","))

        # ── Domein / sector ──────────────────────────────────────────────────
        # Keuzelijst uit de database, met de mogelijkheid om er ter plekke een
        # rubriek aan toe te voegen. Zo hoeft er niets in de code te veranderen als
        # je een eigen indeling wil (bv. 'Defensie' of 'Waterstof').
        #
        # Let op de staging + nonce: Streamlit verbiedt het overschrijven van een
        # widget-key nadat de widget is aangemaakt (StreamlitAPIException). De
        # gewenste waarde gaat daarom naar een GEWONE sessiesleutel (sector_stage),
        # en de selectbox krijgt een nonce in zijn key — bij de volgende run is dat
        # een nieuwe widget, die netjes met de nieuwe waarde start.
        SEC_NONE = "— nog niet toegewezen —"
        SEC_NEW  = "➕ nieuwe sector toevoegen…"
        st.session_state.setdefault(k("sector_stage"), SEC_NONE)
        st.session_state.setdefault("as_sec_nonce", 0)
        secn = st.session_state["as_sec_nonce"]
        _staged = st.session_state[k("sector_stage")]
        _opts = [SEC_NONE] + db.get_sectors() + [SEC_NEW]
        if _staged not in _opts:
            _opts.insert(1, _staged)
        sc1, sc2 = st.columns([2, 3])
        with sc1:
            sector_pick = st.selectbox(
                "🏭 Domein / sector", _opts, index=_opts.index(_staged),
                key=f"as_sector_{n}_{secn}",
                help="Bepaalt in welk taartpunt dit activum belandt op de "
                     "portefeuillepagina. Voor een brede indextracker kies je best "
                     "'Gediversifieerd (index/fonds)': die zit in alle sectoren tegelijk "
                     "en zou de spreiding anders vertekenen.")
        sector = None if sector_pick in (SEC_NONE, SEC_NEW) else sector_pick
        with sc2:
            if sector_pick == SEC_NEW:
                nc1, nc2 = st.columns([3, 1])
                new_sec = nc1.text_input("Naam van de nieuwe sector", key=k("sector_new"),
                                         placeholder="bv. Defensie")
                nc2.write(""); nc2.write("")
                if nc2.button("Toevoegen", key=k("sector_add")):
                    if not new_sec.strip():
                        st.warning("Geef eerst een naam in.")
                    else:
                        db.add_sector(new_sec.strip())
                        st.session_state[k("sector_stage")] = new_sec.strip()
                        st.session_state["as_sec_nonce"] = secn + 1
                        st.rerun()
            elif st.session_state.get(k("sector_src")) and sector:
                st.write(""); st.write("")
                st.caption(f"✨ Automatisch ingevuld via **{st.session_state[k('sector_src')]}** "
                           "— pas gerust aan, jouw keuze heeft altijd voorrang.")

        # Fotomoment (slotkoers 31/12/2025) — voor de meerwaardebelasting op vóór-2026 stukken
        st.session_state.setdefault(k("snap_stage"), None)
        st.session_state.setdefault("as_snap_nonce", 0)
        snn = st.session_state["as_snap_nonce"]
        fm1, fm2 = st.columns([2, 1])
        with fm1:
            snap_val = st.number_input(
                f"📸 Fotomomentwaarde 31/12/2025 ({currency}/stuk) — optioneel",
                min_value=0.0, step=0.01, format="%.10g",
                value=st.session_state[k("snap_stage")], key=f"as_snap_{n}_{snn}",
                help="Slotkoers op 31/12/2025. Voor stukken die je vóór 2026 kocht vertrekt de "
                     "belastbare meerwaarde van de hoogste van (werkelijke aankoopprijs, fotomomentwaarde). "
                     "Laat leeg voor activa die je pas vanaf 2026 koopt.")
        with fm2:
            st.write(""); st.write("")
            if st.button("📸 Ophalen 31/12/2025", key=k("snapfetch")):
                if not ticker.strip():
                    st.warning("Vul eerst een ticker in.")
                else:
                    with st.spinner("Slotkoers 31/12/2025 ophalen..."):
                        p = md.get_close_on_date(ticker.strip().upper(), tax_mod.SNAPSHOT_DATE)
                    if p is None:
                        st.error(
                            "Geen slotkoers gevonden voor 31/12/2025. Kocht je dit activum pas "
                            "**vanaf 2026**? Dan heb je geen fotomomentwaarde nodig — laat het "
                            "veld gewoon leeg (zie tip hierboven). Effecten die pas in 2026 "
                            "uitgegeven of verhandeld werden (zoals sommige warrants/certificaten) "
                            "hadden op 31/12/2025 uiteraard nog geen koers. Bezat je dit al vóór "
                            "2026, vul de koers dan handmatig in.")
                    else:
                        st.session_state[k("snap_stage")] = float(p)
                        st.session_state["as_snap_nonce"] = snn + 1
                        st.rerun()
        if snap_val and snap_val > 0 and currency != "EUR":
            _fxs, _snap_eur_prev = compute_eur(snap_val, currency, tax_mod.SNAPSHOT_DATE)
            st.caption(f"≈ €{num(_snap_eur_prev, 2)}/stuk (koers 31/12/2025: {_fxs:.4f})")

        # Koersdoel meteen bij het toevoegen instellen (i.p.v. pas bij een transactie).
        # Staging analoog aan het koersdoel in het transactieformulier, maar met eigen
        # keys (as_pt_*) zodat beide formulieren elkaars widgetstatus niet delen.
        st.session_state.setdefault(k("pt_stage"), 0.0)
        st.session_state.setdefault("as_pt_nonce", 0)
        ptn = st.session_state["as_pt_nonce"]
        ptc1, ptc2 = st.columns([2, 1])
        with ptc1:
            price_target = st.number_input(
                f"🎯 Koersdoel (optioneel, {currency})", min_value=0.0, step=0.01,
                format="%.10g", value=float(st.session_state[k("pt_stage")]),
                key=f"as_pt_input_{n}_{ptn}",
                help="Je koersdoel voor dit activum — verschijnt op het dashboard en wordt "
                     "gebruikt bij het AI-advies. Kan later nog aangepast worden via een "
                     "transactie of in het overzicht hieronder.")
        with ptc2:
            st.write(""); st.write("")
            if st.button("🤖 Bepaal via AI", key=k("ai_pt")):
                if not ticker.strip():
                    st.warning("Vul eerst een ticker in.")
                elif not ai_advisor.openai_key():
                    st.warning("Geen OpenAI-sleutel — stel die in via ⚙️ Instellingen.")
                else:
                    with st.spinner("AI bepaalt koersdoel..."):
                        res = ai_advisor.suggest_price_target(ticker.strip().upper())
                    if res.get("error"):
                        st.error(res["error"])
                    else:
                        st.session_state[k("pt_stage")] = float(res["price_target"])
                        st.session_state["as_pt_nonce"] = ptn + 1
                        st.session_state[k("pt_info")] = (
                            f"🎯 AI-koersdoel {res['price_target']:.2f} {res['currency']} "
                            f"(model {res.get('model','?')}). {res.get('rationale','')} {res.get('scenario','')}")
                        st.rerun()
        if st.session_state.get(k("pt_info")):
            st.caption(st.session_state.pop(k("pt_info")))

        if st.session_state.get(k("fetched")):
            _src = st.session_state.get(k("isin_only_src"))
            if _src is not None:
                # ISIN-only activum (geen Yahoo-notering, bv. een warrant)
                _name_found = bool(st.session_state.get(k("name")))
                if _src and _name_found:
                    st.success(f"✅ ISIN herkend — naam ingevuld en automatische koers beschikbaar "
                               f"via **{_src}**. Controleer de velden en klik op Toevoegen.")
                elif _src:
                    st.success(f"✅ ISIN herkend — automatische koers beschikbaar via **{_src}**, "
                               "maar geen naam gevonden. Vul zelf een **naam** in en klik op Toevoegen.")
                elif _name_found:
                    st.info("ℹ️ Naam gevonden, maar (nog) geen automatische koers. Controleer de "
                            "velden en klik op Toevoegen — de app blijft koersen proberen via de "
                            "ISIN (onvista, Euronext, Tradegate, Deutsche Börse Live). Lukt dat "
                            "niet, zet dan een **handmatige koers** in het overzicht als laatste redmiddel.")
                else:
                    st.info("ℹ️ Deze ISIN staat niet op Yahoo en er werd (nog) geen naam of externe koers "
                            "gevonden. Vul zelf een **naam** in en klik op Toevoegen — de app blijft koersen "
                            "proberen via de ISIN (onvista, Euronext, Tradegate, Deutsche Börse Live). "
                            "Lukt dat niet, zet dan een **handmatige koers** in het overzicht als laatste "
                            "redmiddel.")
            else:
                st.success("✨ Velden ingevuld via Yahoo Finance — controleer en pas aan waar nodig, en klik daarna op Toevoegen.")

        if st.button("✅ Activum toevoegen", type="primary", key=k("save")):
            if not ticker.strip():
                st.error("Vul een ticker in.")
            elif not name.strip():
                st.error("Vul een naam in (verplicht). Gebruik eventueel '🔍 Info ophalen' om die automatisch in te vullen.")
            else:
                t = ticker.strip().upper()
                db.add_asset(t, name.strip(), asset_type, etf_subtype,
                             currency, exchange.strip() or None, isin.strip() or None,
                             belgian_registered=int(belg_reg), country=country,
                             price_target=(price_target or None),
                             price_target_currency=(currency if price_target else None),
                             sector=sector,
                             sector_source=("auto" if st.session_state.get(k("sector_src"))
                                            else "manual"))
                if snap_val and snap_val > 0:
                    _fx, snap_eur = compute_eur(snap_val, currency, tax_mod.SNAPSHOT_DATE)
                    db.set_asset_snapshot(t, float(snap_val), snap_eur)
                clear_cache()
                st.session_state["as_nonce"] = n + 1   # formulier leegmaken
                st.session_state["as_pt_nonce"] = ptn + 1
                st.success(f"✅ {t} — {name.strip()} toegevoegd!")
                st.rerun()

    if _asec == "📋 Overzicht":
        st.session_state.pop("edit_asset", None)  # inline bewerken vervangt het oude formulier

        assets = db.get_assets()
        if not assets:
            st.info("Nog geen activa geregistreerd.")
            return

        f_asset = st.text_input("🔎 Filter op naam of ticker", key="asset_filter",
                                placeholder="bv. Apple, VWCE, STMPA.PA")
        if f_asset.strip():
            q = f_asset.strip().lower()
            assets = [a for a in assets
                      if q in (a.get("name") or "").lower() or q in a["ticker"].lower()]
        if not assets:
            st.info("Geen activa gevonden voor deze filter.")
            return
        st.caption(f"{len(assets)} activum/activa")
        a_names = {a["ticker"]: (a.get("name") or a["ticker"]) for a in assets}
        TYPE_LBL = {"stock": "Aandeel", "etf": "ETF", "bond": "Obligatie"}
        TYPE_KEY = {v: k for k, v in TYPE_LBL.items()}
        SUB_LBL  = {"distributing": "uitkerend", "accumulating": "kapitaliserend", "": "—"}
        SUB_KEY  = {v: k for k, v in SUB_LBL.items()}
        ACUR = ["EUR", "USD", "GBP", "CHF"]
        clist = list(tax_mod.COUNTRY_NAMES.keys())
        SEC_EMPTY = "—"
        sec_opts = [SEC_EMPTY] + db.get_sectors()
        rows = []
        for a in assets:
            lp = db.get_latest_price(a["ticker"])
            mp = a.get("manual_price")
            sub = a.get("etf_subtype") if a["asset_type"] == "etf" else ""
            cur = a["currency"] if a["currency"] in ACUR else "EUR"
            ctry = (a.get("country") or "BE").upper()
            _sec = (a.get("sector") or "").strip() or SEC_EMPTY
            if _sec not in sec_opts:
                sec_opts.append(_sec)
            rows.append({
                "Ticker":     a["ticker"],
                "Naam":       a.get("name") or "",
                "Sector":     _sec,
                "Type":       TYPE_LBL.get(a["asset_type"], a["asset_type"]),
                "ETF-type":   SUB_LBL.get(sub, "—"),
                "BE":         bool(a.get("belgian_registered")),
                "Munt":       cur,
                "Land":       ctry if ctry in clist else "BE",
                "Beurs":      a.get("exchange") or "",
                "ISIN":       a.get("isin") or "",
                "Gevonden ticker": a.get("resolved_symbol") or "",
                "Koersdoel":  round(a["price_target"], 4) if a.get("price_target") is not None else None,
                "Fotomoment": round(a["snapshot_price"], 4) if a.get("snapshot_price") is not None else None,
                "Handmatige koers": round(mp, 4) if mp is not None else None,
                "Enkel handm.": bool(a.get("manual_only")),
                "Mislukt": int(a.get("price_fail_count") or 0),
                "Laatste koers": round(mp, 4) if mp is not None else (round(lp["price"], 4) if lp else None),
            })
        cc = st.column_config
        edited = st.data_editor(
            pd.DataFrame(rows), width="stretch", hide_index=True, key="asset_editor",
            num_rows="fixed",
            column_config={
                "Ticker":     cc.TextColumn(disabled=True,
                                            help="Ticker corrigeren doe je onderaan (verhuist transacties mee)."),
                "Naam":       cc.TextColumn(),
                "Sector":     cc.SelectboxColumn(
                    options=sec_opts,
                    help="Domein/sector — bepaalt het taartdiagram 'Spreiding per domein' "
                         "op de portefeuillepagina. '—' = nog niet toegewezen. Staat de "
                         "rubriek die je zoekt er niet bij, voeg ze dan toe met "
                         "'Sectoren beheren' onder de tabel; ze verschijnt dan meteen in "
                         "deze keuzelijst. Voor brede indextrackers kies je best "
                         "'Gediversifieerd (index/fonds)'."),
                "Type":       cc.SelectboxColumn(options=list(TYPE_LBL.values())),
                "ETF-type":   cc.SelectboxColumn(options=list(SUB_LBL.values()),
                                                 help="Enkel relevant voor ETF's (bepaalt mee de TOB)."),
                "BE":         cc.CheckboxColumn(
                    help="In België aangeboden/geregistreerd (FSMA). Dit vinkje stuurt de "
                         "TOB (beurstaks) voor FONDSEN en ETF's:\n"
                         "• aangeboden in België + KAPITALISEREND → 1,32% (max €4.000)\n"
                         "• aangeboden in België + UITKEREND → 0,12% (max €1.300)\n"
                         "• NIET in België aangeboden → 0,35% (max €1.600)\n"
                         "Voor gewone aandelen maakt dit vinkje niets uit: die zijn altijd "
                         "0,35%. Het heeft ook GEEN invloed op de roerende voorheffing — "
                         "die 30% hangt af van de aard van de inkomsten en van je "
                         "tussenpersoon, niet van de FSMA-registratie. Onderaan kan je dit "
                         "automatisch laten bevestigen via de Euronext-notering."),
                "Munt":       cc.SelectboxColumn(options=ACUR),
                "Land":       cc.SelectboxColumn(options=clist,
                                                 help="Land van herkomst — bepaalt de buitenlandse bronbelasting."),
                "Beurs":      cc.TextColumn(),
                "ISIN":       cc.TextColumn(help="De ISIN is de bron van waarheid voor koersopzoeking — "
                                                  "uniek per effect, i.t.t. een Yahoo-ticker die door "
                                                  "beurssuffixen ambigu kan zijn. Vul ze in voor de meest "
                                                  "betrouwbare koersen."),
                "Gevonden ticker": cc.TextColumn(disabled=True,
                                                 help="Het Yahoo-symbool dat laatst via de ISIN gevonden werd "
                                                      "(informatief). De ISIN blijft de bron van waarheid; "
                                                      "dit veld is enkel een gemakskolom."),
                "Koersdoel":  cc.NumberColumn(min_value=0.0, format="%.10g",
                                             help="Je koersdoel (native munt) — verschijnt op het dashboard "
                                                  "en bij het AI-advies. Leeg = geen koersdoel op activumniveau "
                                                  "(dan geldt het laatste transactie- of AI-koersdoel)."),
                "Fotomoment": cc.NumberColumn(min_value=0.0, format="%.10g",
                                              help="Slotkoers 31/12/2025 (native). Leeg = geen fotomoment."),
                "Handmatige koers": cc.NumberColumn(min_value=0.0, format="%.10g",
                                              help="Laatste redmiddel: enkel gebruikt als geen enkele onlinebron "
                                                   "(Yahoo, onvista, Euronext, Tradegate, Deutsche Börse Live) een koers "
                                                   "vindt. Zet de ISIN correct in — dan werken de meeste warrants "
                                                   "automatisch. Leeg = volledig automatisch."),
                "Mislukt": cc.NumberColumn(
                    disabled=True, format="%d",
                    help=f"Aantal mislukte koersophalingen op rij. Vanaf "
                         f"{md.MAX_PRICE_FAILURES} stopt de app met proberen voor dit activum "
                         "(geen nutteloze netwerkcalls en logruis meer). Heractiveer hieronder "
                         "of zet een handmatige koers."),
                "Enkel handm.": cc.CheckboxColumn(
                    help="Sla ALLE onlinebronnen over voor dit effect en gebruik enkel de "
                         "handmatige koers. Aanzetten voor effecten die nergens publiek "
                         "genoteerd zijn: dat scheelt vijf mislukte netwerkcalls en evenveel "
                         "foutregels in de log bij elke koersverversing (om de 5 minuten)."),
                "Laatste koers": cc.NumberColumn(disabled=True, format="%.10g"),
            })
        st.caption("✏️ Bewerk rechtstreeks in de tabel en klik op 'Wijzigingen opslaan'. TOB-tarief, "
                   "buitenlandse bronbelasting en de EUR-fotomomentwaarde volgen automatisch. "
                   "Staat een effect niet op Yahoo (bv. een warrant)? Vul de **ISIN** in — koersen "
                   "worden dan via de ISIN opgehaald (Yahoo, onvista, Euronext, Tradegate, L&S, "
                   "Deutsche Börse Live). Vindt geen enkele bron het effect, zet dan een "
                   "**handmatige koers** én vink **Enkel handm.** aan — dat stopt ook de "
                   "foutmeldingen in de log.")

        _open_t, _closed_t = tax_mod.open_position_tickers()
        if _closed_t:
            st.caption(
                f"⏭️ **Geen koersen meer voor {len(_closed_t)} gesloten positie(s):** "
                + ", ".join(asset_label(t, a_names) for t in _closed_t)
                + ".  Dit zijn de activa waarvan de app denkt dat je ze volledig verkocht hebt "
                  "(zelfde FIFO-berekening als het dashboard). Staat hier iets tussen dat je nog "
                  "wél bezit, dan ontbreekt er een transactie — controleer de aankopen/verkopen "
                  "op de 💰 Transacties-pagina.")

        _stuck = [a for a in assets
                  if int(a.get("price_fail_count") or 0) >= md.MAX_PRICE_FAILURES
                  and not a.get("manual_only")]
        if _stuck:
            st.warning(
                f"⏸️ Koersophaling **gestopt** voor {len(_stuck)} activum/activa na "
                f"{md.MAX_PRICE_FAILURES} mislukte pogingen op rij: "
                + ", ".join(asset_label(a["ticker"], a_names) for a in _stuck)
                + ".  Vijf bronnen die tien keer na elkaar niets vinden, wijst op een effect dat "
                  "nergens genoteerd staat — verdere pogingen zijn dan enkel verspilde "
                  "netwerkcalls. Zet een **handmatige koers** (en vink **Enkel handm.** aan), of "
                  "heractiveer hieronder als je denkt dat het een tijdelijke storing was.")
            rc1, rc2 = st.columns([3, 1])
            _rsel = rc1.multiselect("Heractiveren", [a["ticker"] for a in _stuck],
                                    default=[a["ticker"] for a in _stuck],
                                    format_func=lambda t: asset_label(t, a_names),
                                    key="reactivate_sel", label_visibility="collapsed")
            if rc2.button("🔄 Heractiveer", key="reactivate_btn") and _rsel:
                for t in _rsel:
                    db.reset_price_failures(t)
                    md._GIVEN_UP_LOGGED.discard(t)
                clear_cache()
                st.success(f"✅ Koersophaling opnieuw actief voor {len(_rsel)} activum/activa.")
                st.rerun()

        with st.expander("🧮 Afgeleide koers — koppel aan een onderliggende waarde (FCPE / werkgeversfondsen)"):
            st.caption(
                "Voor effecten **zonder eigen publieke notering** waarvan de waarde een formule "
                "op een ander activum is — typisch werkgeversfondsen zoals de Amundi/ENGIE "
                "Link-fondsen (QS-ISIN's, bij geen enkele koersbron te vinden). De koers wordt "
                "dan berekend als:  \n"
                "**koers = basis + multiplicator × (koers onderliggend − referentiekoers)**, "
                "optioneel met een ondergrens op de basis (kapitaalgarantie van "
                "hefboomfondsen).  \n"
                "• **1:1-fonds** (bv. Link Classic/Liberty = 1 aandeel ENGIE): basis 0, "
                "multiplicator 1, referentie 0.  \n"
                "• **Hefboomfonds** (bv. Link Multiple): basis = gegarandeerd bedrag per "
                "deelbewijs, multiplicator en referentiekoers uit je plandocumentatie, en "
                "vink de ondergrens aan.  \n"
                "Koersen, dagresultaat, fotomoment en koershistoriek volgen dan automatisch "
                "de onderliggende waarde — de bronnenketen wordt volledig overgeslagen (geen "
                "nutteloze netwerkcalls of faaltellers voor een ISIN die nergens noteert). "
                "Het onderliggende activum moet in de app bestaan; heb je het zelf niet in "
                "portefeuille (bv. het losse ENGIE-aandeel), voeg het dan gewoon toe zonder "
                "transacties.")
            _all_tk = [a["ticker"] for a in assets]
            dp_sel = st.selectbox("Activum met afgeleide koers", _all_tk,
                                  format_func=lambda t: asset_label(t, a_names),
                                  key="dp_asset")
            _cur_cfg = db.get_derived_pricing(dp_sel) or {}
            if _cur_cfg:
                st.info(f"🔗 **{asset_label(dp_sel, a_names)}** volgt momenteel "
                        f"**{asset_label(_cur_cfg['underlying_ticker'], a_names)}**: "
                        f"koers = {_cur_cfg['base']:g} + {_cur_cfg['multiplier']:g} × "
                        f"(koers − {_cur_cfg['ref_price']:g})"
                        + (" — met ondergrens op de basis." if _cur_cfg.get("floor") else "."))
            _und_opts = [t for t in _all_tk if t != dp_sel]
            if not _und_opts:
                st.warning("Er is geen ander activum om als onderliggende waarde te kiezen.")
            else:
                _und_def = _cur_cfg.get("underlying_ticker")
                dp_und = st.selectbox(
                    "Onderliggende waarde", _und_opts,
                    index=_und_opts.index(_und_def) if _und_def in _und_opts else 0,
                    format_func=lambda t: asset_label(t, a_names), key="dp_underlying")
                if db.get_derived_pricing(dp_und):
                    st.warning("⚠️ De gekozen onderliggende waarde heeft zélf een afgeleide "
                               "koers. Dat mag (de app volgt de keten, met een maximum van "
                               "3 stappen tegen circulaire verwijzingen), maar kies bij "
                               "voorkeur rechtstreeks het genoteerde activum.")
                dc1, dc2, dc3, dc4 = st.columns(4)
                dp_mult = dc1.number_input("Multiplicator", value=float(_cur_cfg.get("multiplier", 1.0)),
                                           step=0.01, format="%.10g", key="dp_mult",
                                           help="1 voor een 1:1-fonds; de hefboomfactor voor een "
                                                "Multiple-achtig fonds.")
                dp_base = dc2.number_input("Basisbedrag", value=float(_cur_cfg.get("base", 0.0)),
                                           step=0.01, format="%.10g", key="dp_base",
                                           help="Vast bedrag per deelbewijs (bv. de kapitaalgarantie "
                                                "van een hefboomfonds). 0 voor een 1:1-fonds.")
                dp_ref = dc3.number_input("Referentiekoers", value=float(_cur_cfg.get("ref_price", 0.0)),
                                          step=0.01, format="%.10g", key="dp_ref",
                                          help="De koers van de onderliggende waarde waartegen de "
                                               "hefboom gemeten wordt (uit je plandocumentatie). "
                                               "0 voor een 1:1-fonds.")
                with dc4:
                    st.write(""); st.write("")
                    dp_floor = st.checkbox("Ondergrens", value=bool(_cur_cfg.get("floor")),
                                           key="dp_floor",
                                           help="Aan = de koers zakt nooit onder het basisbedrag "
                                                "(kapitaalgarantie). Uit = de formule geldt ook "
                                                "onder de referentiekoers.")
                # Voorbeeld op de laatst gekende koers van de onderliggende waarde — geen
                # netwerkcall; de scheduler houdt price_history toch al elke 5 min bij.
                _ulp = db.get_latest_price(dp_und)
                if _ulp:
                    _prev = md.derived_value(_ulp["price"], {
                        "base": dp_base, "multiplier": dp_mult,
                        "ref_price": dp_ref, "floor": dp_floor})
                    st.caption(f"🔎 Voorbeeld met de laatst gekende koers van "
                               f"{asset_label(dp_und, a_names)} ({_ulp['price']:g} "
                               f"{_ulp.get('currency') or 'EUR'}): afgeleide koers = "
                               f"**{_prev:g} {_ulp.get('currency') or 'EUR'}**.")
                else:
                    st.caption("🔎 Nog geen opgeslagen koers voor de onderliggende waarde — het "
                               "voorbeeld verschijnt zodra de achtergrondplanner er een heeft "
                               "vastgelegd (of na '🔄 Ververs prijzen' op de portefeuillepagina).")
                bp1, bp2 = st.columns([1, 1])
                if bp1.button("💾 Koppeling opslaan", type="primary", key="dp_save"):
                    db.set_derived_pricing(dp_sel, dp_und, multiplier=dp_mult,
                                           base=dp_base, ref_price=dp_ref,
                                           floor=int(dp_floor))
                    md._CACHE.pop(dp_sel, None)
                    clear_cache()
                    st.success(f"✅ {asset_label(dp_sel, a_names)} volgt voortaan "
                               f"{asset_label(dp_und, a_names)}.")
                    st.rerun()
                if _cur_cfg and bp2.button("🗑️ Koppeling verwijderen", key="dp_clear"):
                    db.clear_derived_pricing(dp_sel)
                    md._CACHE.pop(dp_sel, None)
                    clear_cache()
                    st.success(f"✅ Koppeling verwijderd — {asset_label(dp_sel, a_names)} volgt "
                               "weer de gewone bronnenketen (of de handmatige koers).")
                    st.rerun()

        with st.expander("🔬 Bronnen diagnose — waarom vindt de app geen koers?"):
            st.caption("Vraagt élke koersbron apart wat ze van deze ISIN weet en toont het "
                       "antwoord. Zo zie je of een effect ergens gekend is, in plaats van enkel "
                       "'alle bronnen faalden'.")
            _isins = [(a["ticker"], a.get("isin") or "") for a in assets if (a.get("isin") or "")]
            if not _isins:
                st.info("Geen enkel activum heeft een ISIN ingevuld.")
            else:
                _dsel = st.selectbox("Activum", _isins,
                                     format_func=lambda p: f"{asset_label(p[0], a_names)} — {p[1]}",
                                     key="diag_sel")
                if st.button("🔬 Diagnose uitvoeren", key="diag_run"):
                    with st.spinner("Alle koersbronnen bevragen..."):
                        res = md.diagnose_isin(_dsel[1])
                    show_df(pd.DataFrame([{
                        "": "✅" if r["ok"] else "❌",
                        "Bron": r["bron"],
                        "Koers": r["koers"],
                        "Munt": r["munt"] or "",
                        "Antwoord": r["detail"],
                    } for r in res]), width="stretch", hide_index=True, column_config={
                        "Koers": st.column_config.NumberColumn(format="%.10g"),
                    })
                    if not any(r["ok"] for r in res):
                        st.warning(
                            "**Geen enkele bron kent dit effect** — ook Euronext niet, en dat is "
                            "de beurs waar Nederlandse en Belgische gestructureerde producten "
                            "noteren. Dat wijst er sterk op dat dit instrument **niet publiek "
                            "beursgenoteerd** is (bv. een warrant uit een werkgeversplan, die wel "
                            "een ISIN heeft maar niet verhandeld wordt op een beurs). Er is dan "
                            "geen koers om op te halen: vul een **handmatige koers** in en vink "
                            "**Enkel handm.** aan.")

        if st.button("💾 Wijzigingen opslaan", type="primary", key="asset_save_inline"):
            n_upd, problems = 0, []
            try:
                for i, a in enumerate(assets):
                    r = edited.iloc[i]
                    orig = rows[i]
                    if all(_cell_eq(r[k], orig[k]) for k in
                           ("Naam", "Type", "ETF-type", "BE", "Munt", "Land", "Beurs", "ISIN",
                            "Koersdoel", "Fotomoment", "Handmatige koers", "Enkel handm.",
                            "Sector")):
                        continue
                    atype = TYPE_KEY.get(str(r["Type"]), a["asset_type"])
                    asub  = SUB_KEY.get(str(r["ETF-type"]), a.get("etf_subtype") or "distributing") or "distributing"
                    ncur  = str(r["Munt"]) if r["Munt"] in ACUR else (a.get("currency") or "EUR")
                    ctry  = str(r["Land"]) if r["Land"] in clist else "BE"
                    tgt = r["Koersdoel"]
                    has_tgt = not (tgt is None or pd.isna(tgt) or float(tgt) <= 0)
                    _newsec = str(r["Sector"]).strip()
                    _has_sec = bool(_newsec) and _newsec != SEC_EMPTY
                    db.update_asset(a["ticker"], name=(str(r["Naam"]).strip() or a["ticker"]),
                                    asset_type=atype, etf_subtype=asub, currency=ncur,
                                    exchange=(str(r["Beurs"]).strip() or ""),
                                    isin=(str(r["ISIN"]).strip() or ""),
                                    belgian_registered=int(bool(r["BE"])), country=ctry,
                                    price_target=(float(tgt) if has_tgt else None),
                                    price_target_currency=(ncur if has_tgt else None),
                                    clear_price_target=(not has_tgt),
                                    sector=(_newsec if _has_sec else None),
                                    sector_source=("manual" if _has_sec else None),
                                    clear_sector=(not _has_sec))
                    snap = r["Fotomoment"]
                    if snap is None or pd.isna(snap) or float(snap) <= 0:
                        db.set_asset_snapshot(a["ticker"], None, None)
                    else:
                        _fx, snap_eur = compute_eur(float(snap), ncur, tax_mod.SNAPSHOT_DATE)
                        db.set_asset_snapshot(a["ticker"], float(snap), snap_eur)
                    mpv = r["Handmatige koers"]
                    if mpv is None or pd.isna(mpv) or float(mpv) <= 0:
                        db.set_manual_price(a["ticker"], None, None)
                    else:
                        db.set_manual_price(a["ticker"], float(mpv), ncur)
                    db.set_manual_only(a["ticker"], bool(r["Enkel handm."]))
                    n_upd += 1
            except Exception as exc:
                problems.append(f"Onverwachte fout: {exc}")
            for p in problems:
                st.warning("⚠️ " + p)
            if n_upd:
                clear_cache()
                st.success(f"✅ {n_upd} activum/activa bijgewerkt.")
                st.rerun()
            elif not problems:
                st.info("Geen wijzigingen gevonden.")

        st.divider()
        sc_a, sc_b = st.columns([3, 1])
        sc_a.caption(
            "🏭 **Domein/sector** — de kolom hierboven bepaalt het taartdiagram *Spreiding "
            "per domein* op de portefeuillepagina. De keuzelijst zelf beheer je op "
            "**⚙️ Instellingen → 🏭 Sectoren**: daar voeg je rubrieken toe, hernoem je ze, "
            "en ken je sectoren in bulk toe aan meerdere activa tegelijk.")
        sc_b.write("")
        if sc_b.button("⚙️ Naar sectoren", key="assets_to_sectors", width="stretch"):
            st.session_state["nav_goto"] = "⚙️ Instellingen"
            # Zowel de sessie als de bewaarde UI-status zetten: sticky() leest de
            # database enkel wanneer de sleutel nog NIET in de sessie zit, dus met
            # alleen _ui_save zou je op de laatst bekeken sectie belanden. Het is
            # veilig om de widget-key hier te zetten — de instellingenpagina (en dus
            # haar radio) wordt in deze run niet gerenderd.
            st.session_state["settings_section"] = "🏭 Sectoren"
            _ui_save("settings_section", "🏭 Sectoren")
            st.rerun()

        st.divider()
        bec1, bec2 = st.columns([3, 1])
        bec1.caption("🇧🇪 **Belgische notering (FSMA) automatisch bepalen** — controleert per ISIN "
                     "bij Euronext of het effect op de Belgische gereglementeerde markt "
                     "(Euronext Brussel, XBRU) noteert. Noteert het daar, dan wordt het BE-vinkje "
                     "aangezet. Een effect dat NIET op XBRU noteert wordt nooit automatisch "
                     "afgezet: veel in België aangeboden ETF's noteren in Amsterdam of Parijs, "
                     "en dat afzetten zou je TOB verkeerd berekenen.")
        if bec2.button("🇧🇪 Bepalen", key="be_detect_all", width="stretch"):
            res_rows, n_set = [], 0
            with st.spinner("Euronext-noteringen controleren..."):
                for a in assets:
                    isin = (a.get("isin") or "").strip()
                    if not isin:
                        res_rows.append({"Activum": asset_label(a["ticker"]), "ISIN": "—",
                                         "Handelsplaats": "—",
                                         "Uitslag": "Geen ISIN — niet te bepalen"})
                        continue
                    pr = md.belgian_listing_probe(isin)
                    if pr.get("xbru"):
                        if not a.get("belgian_registered"):
                            db.update_asset(a["ticker"], belgian_registered=1)
                            n_set += 1
                            uit = "✅ XBRU — BE-vinkje aangezet"
                        else:
                            uit = "✅ XBRU — stond al aan"
                    elif pr.get("ok"):
                        uit = (f"Noteert op {pr['mic']}, niet op XBRU — vinkje ONGEMOEID "
                               "(kan nog steeds in België aangeboden zijn)")
                    else:
                        uit = "Niet gevonden bij Euronext — vinkje ongemoeid"
                    res_rows.append({"Activum": asset_label(a["ticker"]), "ISIN": isin,
                                     "Handelsplaats": pr.get("mic") or "—", "Uitslag": uit})
            st.session_state["be_detect_result"] = res_rows
            if n_set:
                clear_cache()
            st.success(f"Klaar — {n_set} activum/activa op 'in België aangeboden' gezet.")
        if st.session_state.get("be_detect_result"):
            show_df(pd.DataFrame(st.session_state["be_detect_result"]),
                    width="stretch", hide_index=True)
            st.caption("Waarom dit fiscaal telt: het BE-vinkje bepaalt de **TOB** voor fondsen "
                       "en ETF's — 1,32% (kapitaliserend, in België aangeboden), 0,12% "
                       "(uitkerend, in België aangeboden) of 0,35% (niet in België aangeboden). "
                       "Voor gewone aandelen verandert het niets (altijd 0,35%), en op de "
                       "roerende voorheffing heeft het geen invloed. Bevestig bij twijfel in het "
                       "prospectus/KIID van het fonds of via je bank — dit is geen fiscaal advies.")

        with st.expander("📋 Tweede bron: FSMA-lijst van in België aangeboden fondsen"):
            st.caption("De FSMA publiceert de officiële lijsten van openbare ICB's en hun "
                       "compartimenten (Belgisch én buitenlands recht). Dat is DE bron voor "
                       "'wordt dit fonds in België openbaar aangeboden' — en dus voor de TOB. "
                       "Ze vult de XBRU-controle aan: fondsen die in Amsterdam of Parijs "
                       "noteren maar wél in België aangeboden zijn, staan hier wel in.")
            st.warning("Belangrijk: deze lijsten bevatten **geen ISIN's**, enkel namen. Koppelen "
                       "gebeurt dus op naam en is nooit sluitend. Daarom is dit een **advies met "
                       "een score** dat jij bevestigt — de app zet hier niets automatisch om.")
            fi = st.session_state.get("fsma_index")
            fc1, fc2 = st.columns([1, 2])
            if fc1.button("📥 Lijsten ophalen", key="fsma_fetch", width="stretch"):
                with st.spinner("FSMA-lijsten ophalen en verwerken (PDF's, kan even duren)..."):
                    fi = md.fsma_build_index(force=True)
                st.session_state["fsma_index"] = fi
            if fi:
                fc2.caption(f"{len(fi.get('names', []))} namen · bijgewerkt "
                            f"{_short_ts(fi.get('built'))}"
                            + (" · " + ", ".join(f"{k}: {v}" for k, v in
                                                 (fi.get("sources") or {}).items())
                               if fi.get("sources") else ""))
                for err in (fi.get("errors") or []):
                    st.warning("⚠️ " + err)
                if fi.get("diag"):
                    with st.expander("🔧 Diagnose van het inlezen"):
                        st.caption("Per lijst: aantal pagina's, hoeveel tekst eruit kwam, en "
                                   "hoeveel namen daaruit herkend werden. Staan er pagina's en "
                                   "tekens maar 0 namen, dan leest de app de PDF wel maar "
                                   "herkent ze de opmaak niet — stuur me dan het staal "
                                   "hieronder.")
                        show_df(pd.DataFrame([
                            {"Lijst": k, "Pagina's": v.get("paginas"),
                             "Tekens": v.get("tekens"), "Namen": v.get("namen")}
                            for k, v in fi["diag"].items()]),
                            width="stretch", hide_index=True)
                        for k, v in fi["diag"].items():
                            if v.get("staal"):
                                st.caption(f"Staal — {k}:")
                                st.code(v["staal"])
                if not fi.get("names"):
                    st.error("Er werden geen namen herkend. Open 'Diagnose van het inlezen' "
                             "hierboven en bezorg me het staal, dan pas ik het inlezen aan.")
            else:
                fc2.caption("Nog niet opgehaald. De lijsten worden lokaal gecachet en "
                            "wekelijks ververst.")

            if fi and fi.get("names"):
                funds = [a for a in assets if a.get("asset_type") in ("etf", "fund")]
                if not funds:
                    st.info("Je hebt geen fondsen/ETF's — voor gewone aandelen speelt dit niet "
                            "(die zijn altijd 0,35% TOB).")
                else:
                    frows, opts = [], {}
                    for a in funds:
                        hits = md.fsma_lookup(a.get("name") or a["ticker"], index=fi)
                        best = hits[0] if hits else None
                        frows.append({
                            "Activum": asset_label(a["ticker"]),
                            "BE nu": "✅" if a.get("belgian_registered") else "—",
                            "Beste FSMA-match": best["naam"] if best else "geen match",
                            "Score": best["score"] if best else 0,
                            "Alternatieven": ", ".join(h["naam"] for h in hits[1:]) or "—",
                        })
                        if best and not a.get("belgian_registered"):
                            opts[f"{asset_label(a['ticker'])} → {best['naam']} "
                                 f"({best['score']})"] = a["ticker"]
                    show_df(pd.DataFrame(frows), width="stretch", hide_index=True,
                            column_config={"Score": st.column_config.NumberColumn(
                                format="%d", help="Naamgelijkenis 0-100. Alles onder ~85 zelf "
                                                  "nakijken: een hoge score is geen bewijs.")})
                    if opts:
                        chosen = st.multiselect(
                            "Bevestig welke fondsen in België worden aangeboden "
                            "(zet het BE-vinkje aan):", list(opts.keys()), key="fsma_confirm")
                        if st.button("✅ Bevestigde fondsen op 'in België aangeboden' zetten",
                                     key="fsma_apply", type="primary"):
                            for lbl in chosen:
                                db.update_asset(opts[lbl], belgian_registered=1)
                            if chosen:
                                clear_cache()
                                st.success(f"{len(chosen)} fonds(en) bijgewerkt.")
                                st.rerun()
                            else:
                                st.info("Niets geselecteerd.")
                    else:
                        st.caption("Geen openstaande voorstellen: al je fondsen met een match "
                                   "staan al op 'in België aangeboden'.")

        fmc1, fmc2 = st.columns([3, 1])
        fmc1.caption("📸 Fotomoment = slotkoers 31/12/2025 (native munt), gebruikt voor de "
                     "meerwaardebelasting op stukken gekocht vóór 2026. Je kunt de waarde in de "
                     "tabel intypen, of hiernaast automatisch ophalen voor activa zonder waarde.")
        if fmc2.button("📸 Ophalen (ontbrekende)", key="snap_fetch_all", width="stretch"):
            n_ok, n_fail = 0, 0
            with st.spinner("Slotkoersen 31/12/2025 ophalen..."):
                for a in assets:
                    if a.get("snapshot_price") is not None:
                        continue
                    p = md.get_close_on_date(a["ticker"], tax_mod.SNAPSHOT_DATE)
                    if p:
                        _fx, p_eur = compute_eur(p, a["currency"], tax_mod.SNAPSHOT_DATE)
                        db.set_asset_snapshot(a["ticker"], p, p_eur)
                        n_ok += 1
                    else:
                        n_fail += 1
            clear_cache()
            if n_ok:
                st.success(f"✅ {n_ok} fotomoment(en) opgehaald." + (f" {n_fail} niet gevonden." if n_fail else ""))
                st.rerun()
            else:
                st.info("Geen ontbrekende fotomomenten gevonden of geen koersen beschikbaar.")

        # Ticker corrigeren (verhuist transacties, dividenden en koershistoriek mee)
        missing_snap = [a for a in assets if a.get("snapshot_price") is None]
        if missing_snap:
            if st.button(f"📸 Fotomoment ophalen (ontbrekende: {len(missing_snap)})",
                         key="fetch_snaps",
                         help=f"Haalt de slotkoers van {tax_mod.SNAPSHOT_DATE} op voor alle activa "
                              "zonder fotomoment. Handig na het toevoegen van nieuwe activa."):
                got = 0
                for a in missing_snap:
                    px = md.get_close_on_date(a["ticker"], tax_mod.SNAPSHOT_DATE)
                    if px:
                        _fx, px_eur = compute_eur(px, a.get("currency") or "EUR", tax_mod.SNAPSHOT_DATE)
                        db.set_asset_snapshot(a["ticker"], px, px_eur)
                        got += 1
                clear_cache()
                if got:
                    st.success(f"✅ Fotomoment opgehaald voor {got} activum/activa.")
                else:
                    st.warning("Geen koersen gevonden (mogelijk niet op Yahoo genoteerd — vul de "
                               "fotomomentwaarde dan handmatig in de tabel in).")
                st.rerun()

        with st.expander("🔧 Ticker corrigeren"):
            rc1, rc2, rc3 = st.columns([2, 2, 1])
            old_tk = rc1.selectbox("Huidige ticker", [a["ticker"] for a in assets], key="rename_old")
            new_tk = rc2.text_input("Nieuwe ticker", key="rename_new",
                                    placeholder="bv. STMPA → STMPA.PA").strip().upper()
            rc3.write(""); rc3.write("")
            if rc3.button("Hernoem", key="rename_btn", width="stretch"):
                if not new_tk:
                    st.warning("Vul een nieuwe ticker in.")
                elif new_tk == old_tk:
                    st.info("Dezelfde ticker.")
                elif db.rename_ticker(old_tk, new_tk):
                    clear_cache()
                    st.success(f"✅ {old_tk} → {new_tk} (transacties/dividenden/koersen verhuisd). "
                               "Ververs de koersen op de Portefeuille-pagina.")
                    st.rerun()
                else:
                    st.error(f"'{new_tk}' bestaat al — kies een andere ticker.")

        # Verwijderen (meerdere tegelijk, met bevestiging — incl. transacties!)
        st.divider()
        adel_opts = {a["ticker"]: f"{asset_label(a['ticker'], a_names)}" for a in assets}
        multiselect_delete(
            "confirm_del_asset", adel_opts,
            lambda tk: db.delete_asset(tk), noun="activum",
            extra_warning="⚠️ Dit wist óók ALLE transacties, dividenden en splitsingen van de "
                          "geselecteerde activa.")

    if _asec == "🔀 Splitsingen":
        st.subheader("🔀 Aandelensplitsingen")
        st.caption("Registreer een splitsing (bv. NVIDIA 1 → 10) of een omgekeerde splitsing "
                   "(bv. 10 → 1). Transacties van vóór de splitsdatum worden automatisch omgerekend "
                   "(aantal × ratio, prijs ÷ ratio); je kostbasis blijft gelijk. Yahoo-koersen zijn al "
                   "split-gecorrigeerd, zodat je posities en waarde correct blijven.")
        all_assets = db.get_assets()
        if not all_assets:
            st.info("Voeg eerst activa toe.")
        else:
            s_tickers = [a["ticker"] for a in all_assets]
            s_names = {a["ticker"]: (a.get("name") or a["ticker"]) for a in all_assets}
            with st.form("split_form", clear_on_submit=True):
                sc1, sc2, sc3, sc4 = st.columns(4)
                with sc1:
                    s_tk = st.selectbox("Activum", s_tickers,
                                        format_func=lambda t: asset_label(t, s_names))
                with sc2:
                    s_date = st.date_input("Splitsdatum", value=date.today(), min_value=date(2000,1,1), max_value=date.today())
                with sc3:
                    s_from = st.number_input("Van (oude aandelen)", min_value=1, value=1, step=1)
                with sc4:
                    s_to = st.number_input("Naar (nieuwe aandelen)", min_value=1, value=2, step=1)
                ratio = s_to / s_from if s_from else 1
                st.caption(f"Ratio = {s_to}/{s_from} = **{ratio:g}** "
                           f"(1 aandeel wordt {ratio:g} aandelen; prijs gedeeld door {ratio:g})")
                if st.form_submit_button("✅ Splitsing registreren", type="primary"):
                    db.add_split(s_tk, str(s_date), ratio)
                    clear_cache()
                    st.success(f"✅ Splitsing {s_from}→{s_to} voor {s_tk} op {s_date} geregistreerd!")
                    st.rerun()

            splits = db.get_splits()
            if splits:
                st.divider()
                sp_rows = [{
                    "ID":      sp["id"],
                    "Datum":   sp["split_date"][:10],
                    "Activum": f"{sp['ticker']} — {s_names.get(sp['ticker'], sp['ticker'])}",
                    "Ratio":   f"{sp['ratio']:g}",
                } for sp in splits]
                show_df(pd.DataFrame(sp_rows), width="stretch", hide_index=True)
                sp_opts = {sp["id"]: f"#{sp['id']} · {sp['split_date'][:10]} · {sp['ticker']} · ratio {sp['ratio']:g}"
                           for sp in splits}
                multiselect_delete("confirm_del_split", sp_opts,
                                   lambda i: db.delete_split(i), noun="splitsing",
                                   extra_warning="De transacties van vóór de splitsdatum worden weer "
                                                 "zonder deze ratio getoond.")
            else:
                st.info("Nog geen splitsingen geregistreerd.")
