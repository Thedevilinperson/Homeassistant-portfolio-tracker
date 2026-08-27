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
import fcpe_pricing as fcpe
import market_data as md

from views.common import (
    _cell_eq, _section_radio, _short_ts, _ui_save, asset_label, clear_cache,
    compute_eur, multiselect_delete, num, show_df
)

logger = logging.getLogger("app.assets")


# ── PAGINA: Activa ────────────────────────────────────────────────────────────


def _d_or(value, fallback):
    """Datum uit de bewaarde parameters, of een verstandige beginwaarde."""
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return fallback


def _import_official_nav(ticker: str, upload) -> int:
    """Lees de NAV-export van de beheerder in.

    De export van Amundi heeft een kop van enkele regels boven de eigenlijke tabel,
    dus we zoeken zelf de kolom met datums en die met bedragen in plaats van een vaste
    positie aan te nemen — dan blijft het werken als de export er volgend jaar anders
    uitziet.
    """
    if str(getattr(upload, "name", "")).lower().endswith(".csv"):
        raw = pd.read_csv(upload, header=None)
    else:
        raw = pd.read_excel(upload, header=None)
    n = 0
    for _, row in raw.iterrows():
        d = v = None
        for cell in row:
            if d is None:
                try:
                    ts = pd.to_datetime(cell, errors="raise")
                    if 1990 < ts.year < 2100:
                        d = ts.date().isoformat()
                        continue
                except Exception:
                    pass
            if d is not None and v is None and isinstance(cell, (int, float)) and cell == cell:
                v = float(cell)
        if d and v and v > 0:
            db.save_official_nav(ticker, d, v, source="import")
            n += 1
    return n


def page_assets():
    st.title("🏢 Activa beheren")

    CUR = ["EUR", "USD", "GBP", "CHF"]
    _asec = _section_radio("assets_section",
        ["➕ Activum toevoegen", "📋 Overzicht", "🔗 Koppelingen", "🔀 Splitsingen"])

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
                "Div=aandeel": bool(a.get("dividend_as_stock")),
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
                "Div=aandeel": cc.CheckboxColumn(
                    help="Dividenden van dit activum tellen mee voor de 833-vrijstelling "
                         "roerende voorheffing en de FBB (🧾 Aangifte), ook al staat 'Type' "
                         "hierboven op ETF/fonds. Bedoeld voor fondsen die fiscaal gewoon "
                         "als aandeel behandeld worden — bv. bepaalde FCPE-werkgeversfondsen "
                         "die een echt, aan Belgische roerende voorheffing onderworpen "
                         "dividend uitkeren. Standaard UIT voor alles behalve 'Aandeel' "
                         "(dat telt sowieso altijd mee, dit vinkje is dan overbodig). Twijfel "
                         "je? Laat uit en vraag het na bij je boekhouder of de FOD Financiën — "
                         "onterecht aanvinken levert een te hoge (foutieve) teruggave op."),
                "Laatste koers": cc.NumberColumn(disabled=True, format="%.10g"),
            })
        st.caption("✏️ Bewerk rechtstreeks in de tabel en klik op 'Wijzigingen opslaan'. TOB-tarief, "
                   "buitenlandse bronbelasting en de EUR-fotomomentwaarde volgen automatisch. "
                   "Staat een effect niet op Yahoo (bv. een warrant)? Vul de **ISIN** in — koersen "
                   "worden dan via de ISIN opgehaald (Yahoo, onvista, Euronext, Tradegate, L&S, "
                   "Deutsche Börse Live). Vindt geen enkele bron het effect, zet dan een "
                   "**handmatige koers** én vink **Enkel handm.** aan — dat stopt ook de "
                   "foutmeldingen in de log. Keert een fonds (Type ETF) in de praktijk gewone, "
                   "aan Belgische roerende voorheffing onderworpen dividenden uit — bv. sommige "
                   "FCPE-werkgeversfondsen — vink dan **Div=aandeel** aan zodat die dividenden "
                   "meetellen voor de 833-vrijstelling en de FBB op de 🧾 Aangiftepagina.")

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
                            "Div=aandeel", "Sector")):
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
                    db.set_dividend_as_stock(a["ticker"], bool(r["Div=aandeel"]))
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

    if _asec == "🔗 Koppelingen":
        st.subheader("🔗 Gekoppelde fondsen — overzicht")
        st.caption(
            "Alle activa met een **afgeleide koers** (🧮, lineair op een onderliggende "
            "waarde) of een **fondsformule** (📐, FCPE Multiple) op één plaats, zodat je "
            "ze niet meer per stuk in het activum-formulier hoeft op te zoeken.")

        assets = db.get_assets()
        a_names = {a["ticker"]: (a.get("name") or a["ticker"]) for a in assets}

        _rows = []
        for a in assets:
            _tk = a["ticker"]
            _mode = a.get("pricing_mode") or "auto"
            if _mode == "derived":
                _cfg = db.get_derived_pricing(_tk) or {}
                if not _cfg:
                    continue
                _rows.append({
                    "Fonds": asset_label(_tk, a_names),
                    "Methode": "🧮 Afgeleide koers",
                    "Onderliggende waarde": asset_label(_cfg["underlying_ticker"], a_names),
                    "Parameters": (f"basis {_cfg['base']:g} · multiplicator "
                                  f"{_cfg['multiplier']:g} · referentie {_cfg['ref_price']:g}"
                                  + (" · ondergrens" if _cfg.get("floor") else "")),
                    "Waarnemingen": "—",
                    "Majoraties": "—",
                })
            elif _mode == "fcpe":
                _fp = db.get_fcpe_params(_tk) or {}
                if not _fp:
                    continue
                _und = _fp.get("underlying_ticker")
                _n = int(_fp.get("n_readings", 60) or 60)
                _known = len(db.get_fcpe_readings(_tk))
                _md = _fp.get("md_entries") or []
                _rows.append({
                    "Fonds": asset_label(_tk, a_names),
                    "Methode": "📐 Fondsformule",
                    "Onderliggende waarde": asset_label(_und, a_names) if _und else "—",
                    "Parameters": (f"α {float(_fp.get('alpha', 0) or 0):g} · referentie "
                                  f"{float(_fp.get('reference_price', 0) or 0):g} · inschrijving "
                                  f"{float(_fp.get('subscription_price', 0) or 0):g} · rendement "
                                  f"{float(_fp.get('annual_rate', 0) or 0)*100:g}%/"
                                  f"{float(_fp.get('maturity_return', 0) or 0)*100:g}%"),
                    "Waarnemingen": f"{_known} / {_n}",
                    "Majoraties": (", ".join(f"{e.get('date')}={e.get('amount')}" for e in _md)
                                  if _md else "geen"),
                })

        if not _rows:
            st.info("Nog geen enkel activum gekoppeld. Stel hieronder een afgeleide koers of "
                    "een fondsformule in.")
        else:
            show_df(pd.DataFrame(_rows), width="stretch", hide_index=True)
            st.caption(f"{len(_rows)} gekoppeld fonds/fondsen. Klik hieronder open om de "
                       "instellingen te wijzigen — de panelen openen meteen op je gekoppelde "
                       "fonds, niet op een willekeurig activum.")

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
            # Standaard tonen we enkel de activa die al een afgeleide koers hebben, en
            # landen we meteen op de eerste daarvan. Anders opent dit paneel op het
            # alfabetisch eerste activum uit de hele portefeuille (een willekeurig
            # aandeel), moet je het juiste fonds elke keer opnieuw opzoeken, en lijken
            # alle parameters leeg te staan terwijl er niets mis is.
            _dp_linked = [a["ticker"] for a in assets
                          if (a.get("pricing_mode") or "auto") == "derived"
                          and (a.get("underlying_ticker") or "").strip()]
            _all_tk = [a["ticker"] for a in assets]
            if _dp_linked:
                _dp_only = st.checkbox(
                    ("Toon enkel het gekoppelde activum" if len(_dp_linked) == 1
                     else f"Toon enkel de {len(_dp_linked)} gekoppelde activa"),
                    value=True, key="dp_only_linked",
                    help="Vink uit om een nieuw activum aan een onderliggende waarde te "
                         "koppelen — dan verschijnt de volledige lijst.")
            else:
                _dp_only = False
                st.caption("Nog geen enkel activum met een afgeleide koers. Kies er hieronder "
                           "één om te beginnen.")
            _dp_opts = (_dp_linked if (_dp_only and _dp_linked)
                        else _dp_linked + [t for t in _all_tk if t not in _dp_linked])
            if not _dp_opts:
                st.warning("Er zijn nog geen activa geregistreerd.")
                _dp_opts = []
            # Een eerder gekozen ticker kan buiten de (nu gefilterde) lijst vallen —
            # bv. na het aanvinken van de filter. Streamlit struikelt over een bewaarde
            # waarde die niet in de opties zit, dus ruimen we ze op vóór het renderen.
            if _dp_opts and st.session_state.get("dp_asset") not in _dp_opts:
                st.session_state.pop("dp_asset", None)
            dp_sel = st.selectbox("Activum met afgeleide koers", _dp_opts,
                                  format_func=lambda t: ("🔗 " if t in _dp_linked else "")
                                                        + asset_label(t, a_names),
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

        with st.expander("📐 Fondsformule (FCPE Multiple) — waarde uit het maandgemiddelde"):
            st.caption(
                "De tweede waarderingsmethode, voor hefboomfondsen zoals **Link Multiple**. "
                "Die hangen niet aan de koers van vandaag maar aan het **gemiddelde van "
                "zestig maandelijkse waarnemingen**, elk afzonderlijk afgetopt op de "
                "referentieprijs:  \n"
                "**waarde = inschrijvingsprijs + max(rendement, α × (gemiddelde van de "
                "waarnemingen − referentieprijs)) + majoraties**  \n"
                "Het rendement is een **bodem**, geen opslag: het reglement neemt de "
                "hoogste van rendement en participatie, dus zodra de koers boven de "
                "referentieprijs noteert telt alleen de participatie.  \n"
                "Twee gevolgen die de lineaire methode hierboven niet kan nabootsen: de "
                "gevoeligheid **daalt** naarmate er waarnemingen vastliggen (elke weegt "
                "1/60), en een eenmaal vastgelegde stijging kan **niet meer verdwijnen**, "
                "omdat een koersval onder de referentieprijs het gemiddelde niet omlaag "
                "haalt. De app haalt de waarnemingen zelf op vanaf de start van het fonds; "
                "je hoeft niets in te typen.")

            # Zelfde principe als hierboven: open op een fonds dat écht met de
            # fondsformule gewaardeerd wordt, niet op het alfabetisch eerste aandeel.
            # Fondsen met bewaarde parameters tellen ook mee, ook als de methode nog
            # niet geactiveerd is — anders raak je een half ingevulde configuratie kwijt.
            _f_linked = [a["ticker"] for a in assets
                         if (a.get("pricing_mode") or "auto") == "fcpe"
                         or (a.get("fcpe_params") or "").strip()]
            if _f_linked:
                _f_only = st.checkbox(
                    ("Toon enkel het fonds met een fondsformule" if len(_f_linked) == 1
                     else f"Toon enkel de {len(_f_linked)} fondsen met een fondsformule"),
                    value=True, key="fcpe_only_linked",
                    help="Vink uit om een nieuw fonds in te stellen — dan verschijnt de "
                         "volledige lijst.")
            else:
                _f_only = False
                st.caption("Nog geen enkel fonds met een fondsformule. Kies er hieronder één "
                           "om te beginnen.")
            _f_opts = (_f_linked if (_f_only and _f_linked)
                       else _f_linked + [t for t in _all_tk if t not in _f_linked])
            if not _f_opts:
                st.warning("Er zijn nog geen activa geregistreerd.")
                _f_opts = []
            if _f_opts and st.session_state.get("fcpe_asset") not in _f_opts:
                st.session_state.pop("fcpe_asset", None)
            f_sel = st.selectbox("Fonds", _f_opts,
                                 format_func=lambda t: ("📐 " if t in _f_linked else "")
                                                       + asset_label(t, a_names),
                                 key="fcpe_asset")
            _fp = db.get_fcpe_params(f_sel) or {}
            _row = db.get_asset(f_sel) or {}
            _active = (_row.get("pricing_mode") or "auto") == "fcpe"
            if _active:
                st.success(f"📐 **{asset_label(f_sel, a_names)}** wordt met de fondsformule "
                           f"gewaardeerd (α={_fp.get('alpha')}, referentie "
                           f"{_fp.get('reference_price')}, {_fp.get('n_readings', 60)} "
                           "waarnemingen).")

            _uo = [t for t in _all_tk if t != f_sel]
            if not _uo:
                st.warning("Er is geen ander activum om als onderliggende waarde te kiezen.")
            else:
                _ud = _fp.get("underlying_ticker")
                f_und = st.selectbox("Onderliggende waarde (het aandeel)", _uo,
                                     index=_uo.index(_ud) if _ud in _uo else 0,
                                     format_func=lambda t: asset_label(t, a_names),
                                     key="fcpe_und")
                st.markdown("**Parameters uit het fondsreglement**")
                g1, g2, g3 = st.columns(3)
                f_alpha = g1.number_input("α (multiplicator)", value=float(_fp.get("alpha", 16.0)),
                                          step=0.5, format="%.10g", key="fcpe_alpha",
                                          help="Staat letterlijk in het reglement. Voor Link "
                                               "Multiple BEL 2022 is dat 16; voor de jaargang "
                                               "2018 was het 19.")
                f_ref = g2.number_input("Referentieprijs (Prix de Référence)",
                                        value=float(_fp.get("reference_price", 0.0)),
                                        step=0.01, format="%.10g", key="fcpe_ref",
                                        help="De prijs waarop elke waarneming wordt afgetopt "
                                             "én waarvan de stijging gemeten wordt. Ken je ze "
                                             "niet, gebruik dan de kalibratie onderaan.")
                f_sub = g3.number_input("Inschrijvingsprijs (Prix de Souscription)",
                                        value=float(_fp.get("subscription_price", 0.0)),
                                        step=0.01, format="%.10g", key="fcpe_sub",
                                        help="Bepaalt het gegarandeerde deel en het rendement.")
                h1, h2, h3 = st.columns(3)
                f_n = h1.number_input("Aantal waarnemingen", min_value=1, max_value=240,
                                      value=int(_fp.get("n_readings", 60)), step=1,
                                      key="fcpe_n")
                f_day = h2.number_input("Waarnemingsdag van de maand", min_value=1, max_value=31,
                                        value=int(_fp.get("reading_day", 15)), step=1,
                                        key="fcpe_day",
                                        help="Valt die dag niet op een beursdag, dan neemt de "
                                             "app de beursdag ervóór — zoals het reglement "
                                             "voorschrijft.")
                f_first = h3.date_input("Eerste waarnemingsmaand",
                                        value=_d_or(_fp.get("first_reading_month"), date(2023, 1, 15)),
                                        min_value=date(2000, 1, 1), max_value=date(2100, 12, 31),
                                        key="fcpe_first",
                                        help="Alleen de maand telt; de dag wordt door de regel "
                                             "hierboven bepaald.")
                i1, i2, i3, i4 = st.columns(4)
                f_start = i1.date_input("Datum van aanvang", 
                                        value=_d_or(_fp.get("start_date"), date(2022, 12, 22)),
                                        min_value=date(2000, 1, 1), max_value=date(2100, 12, 31),
                                        key="fcpe_start",
                                        help="Date de Commencement — vanaf hier loopt het rendement.")
                f_mat = i2.date_input("Eindvervaldag",
                                      value=_d_or(_fp.get("maturity_date"), date(2027, 12, 15)),
                                      min_value=date(2000, 1, 1), max_value=date(2100, 12, 31),
                                      key="fcpe_mat")
                f_rate = i3.number_input("Rendement per jaar", value=float(_fp.get("annual_rate", 0.015)),
                                         step=0.001, format="%.10g", key="fcpe_rate",
                                         help="1,5% bij vervroegde uitstap.")
                f_mret = i4.number_input("Rendement op vervaldag",
                                         value=float(_fp.get("maturity_return", 0.0773)),
                                         step=0.001, format="%.10g", key="fcpe_mret",
                                         help="7,73% op de eindvervaldag.")

                st.caption("**Majorations de Dividende**: keert ENGIE een dividend met "
                           "majoration uit (+10% voor aandelen die twee volle kalenderjaren "
                           "op naam staan — voor de jaargang 2022 dus vanaf het dividend van "
                           "2025), dan verhoogt dat de prestatie. Eén regel per majoration, "
                           "als `JJJJ-MM-DD = bedrag per deelbewijs`. Het bedrag per "
                           "deelbewijs = 10 aandelen × 10% × dividend per aandeel; zonder "
                           "deze regels loopt de berekende waarde vanaf de eerste majoration "
                           "blijvend achter op de officiële NAV.")
                f_md_txt = st.text_area(
                    "Majoraties", value="\n".join(
                        f"{e.get('date')} = {e.get('amount')}" for e in (_fp.get("md_entries") or [])),
                    height=68, key="fcpe_md",
                    placeholder="2025-04-30 = 1.48\n2026-05-05 = 1.35")

                _dates = fcpe.reading_dates(int(f_n), day_of_month=int(f_day),
                                            first_month=str(f_first))
                _done = [d for d in _dates if d <= date.today().isoformat()]
                st.caption(f"➡️ Waarnemingen: **{_dates[0]}** t/m **{_dates[-1]}**, "
                           f"waarvan **{len(_done)}** in het verleden. "
                           f"Bewaard: **{len(db.get_fcpe_readings(f_sel))}**.")

                b1, b2, b3 = st.columns(3)
                if b1.button("💾 Opslaan en activeren", type="primary", key="fcpe_save"):
                    _md = []
                    for line in (f_md_txt or "").splitlines():
                        if "=" in line:
                            dd, _, aa = line.partition("=")
                            try:
                                _md.append({"date": dd.strip()[:10], "amount": float(aa.strip().replace(",", "."))})
                            except ValueError:
                                st.warning(f"Majoration overgeslagen (onleesbaar): {line}")
                    db.set_fcpe_params(f_sel, {
                        "underlying_ticker": f_und, "alpha": f_alpha,
                        "reference_price": f_ref, "subscription_price": f_sub,
                        "n_readings": int(f_n), "reading_day": int(f_day),
                        "first_reading_month": str(f_first), "start_date": str(f_start),
                        "maturity_date": str(f_mat), "annual_rate": f_rate,
                        "maturity_return": f_mret, "md_entries": _md})
                    db.set_pricing_mode(f_sel, "fcpe")
                    md._CACHE.pop(f_sel, None)
                    clear_cache()
                    st.success("✅ Opgeslagen. Haal nu de waarnemingen op.")
                    st.rerun()
                if b2.button("🔄 Waarnemingen ophalen", key="fcpe_sync",
                             help="Haalt de slotkoers van de onderliggende waarde op voor elke "
                                  "voorbije waarnemingsdatum, vanaf de start van het fonds, en "
                                  "controleert meteen de eerder automatisch opgehaalde "
                                  "waarnemingen tegen de definitieve slotkoers. Handmatig "
                                  "ingevoerde waarnemingen blijven ongemoeid."):
                    with st.spinner("Slotkoersen ophalen en controleren…"):
                        r = md.fcpe_sync_readings(f_sel, verify=True)
                    if r["added"]:
                        st.success(f"✅ {r['added']} waarneming(en) opgehaald "
                                   f"({r['skipped']} stonden er al).")
                    elif r["skipped"]:
                        st.info(f"Alle {r['skipped']} voorbije waarnemingen stonden er al.")
                    elif not r.get("corrected"):
                        st.warning("Niets opgehaald — controleer de parameters en de "
                                   "onderliggende waarde.")
                    if r.get("corrected"):
                        st.warning(f"🩺 {r['corrected']} eerder opgehaalde waarneming(en) week(en) "
                                   "af van de definitieve slotkoers en zijn bijgewerkt. Kalibreer "
                                   "je parameters opnieuw als je dat eerder op deze cijfers deed.")
                    if r.get("pending"):
                        if r["pending"] == date.today().isoformat():
                            st.caption("De waarneming van vandaag wordt pas vastgelegd na "
                                       "sluiting van de beurs (18u Parijse tijd) — een Relevé is "
                                       "de slotkoers van die dag, niet de koers van dit moment. "
                                       "Tot dan telt de actuele koers gewoon mee als invulling "
                                       "van de openstaande waarnemingen.")
                        else:
                            st.caption(f"Volgende waarneming: **{r['pending']}**.")
                    if r["missing"]:
                        st.warning(f"Geen slotkoers gevonden voor {len(r['missing'])} datum(s): "
                                   + ", ".join(r["missing"][:5])
                                   + ("…" if len(r["missing"]) > 5 else "")
                                   + ". Vul die desnoods handmatig aan in de tabel hieronder.")
                    md._CACHE.pop(f_sel, None)
                    # Bewust GEEN st.rerun(): die gooit het net getekende scherm weg,
                    # inclusief de meldingen hierboven — je klikte dan op de knop en
                    # zag niets gebeuren. Alles wat hieronder staat (de tabel met
                    # waarnemingen, de waarde, de metrieken) wordt in deze zelfde run
                    # opnieuw uit de database gelezen en is dus al bijgewerkt.
                if _active and b3.button("🗑️ Formule uitschakelen", key="fcpe_off"):
                    db.set_pricing_mode(f_sel, "auto")
                    md._CACHE.pop(f_sel, None)
                    clear_cache()
                    st.success("✅ Uitgeschakeld — het fonds volgt weer de gewone bronnenketen.")
                    st.rerun()

                _rd = db.get_fcpe_readings(f_sel)
                if _rd:
                    _res, _cur = md.fcpe_value(f_sel, auto_sync=False)
                    if _res:
                        v1, v2, v3, v4 = st.columns(4)
                        v1.metric("Waarde per deelbewijs", f"{_res['value']:,.2f} {_cur}")
                        v2.metric("Participatie", f"{_res['participation']:,.2f}")
                        v3.metric("Vastgelegd", f"{_res['n_known']} / {_res['n_readings']}")
                        v4.metric("Gevoeligheid", f"{_res['sensitivity']:,.2f}",
                                  help="Hoeveel de waarde verschuift bij €1 koersbeweging van "
                                       "de onderliggende waarde. Dit daalt naarmate er meer "
                                       "waarnemingen vastliggen; op het einde is ze nul.")
                        st.caption(
                            f"Gemiddelde van de waarnemingen: **{_res['average']:,.4f}** · "
                            f"prestatie **{_res.get('performance', 0):,.2f}** = hoogste van "
                            f"participatie ({_res['participation']:,.2f}) en rendement "
                            f"({_res['rendement']:,.2f}) — nu wint de "
                            f"**{_res.get('performance_source', '?')}** · majoraties "
                            f"**{_res['md']:,.2f}** · nog **{_res['n_open']}** waarnemingen open"
                            + (f", ingevuld met **{_res['fill_value']:,.4f}**"
                               if _res["fill_value"] is not None else ""))
                    with st.expander(f"📅 Waarnemingen ({len(_rd)})"):
                        show_df(pd.DataFrame([{
                            "Datum": r["date"], "Slotkoers": r["close"],
                            "Afgetopt op referentie": max(r["close"], f_ref),
                            "Bron": r["source"] or "",
                        } for r in _rd]), width="stretch", hide_index=True, height=280)
                        st.caption("De slotkoersen worden RUW bewaard, zodat je ze regel per "
                                   "regel tegen een beursoverzicht kunt houden. Het aftoppen "
                                   "op de referentieprijs gebeurt pas bij het rekenen.")

                with st.expander("🎯 Parameters kalibreren tegen de officiële NAV"):
                    st.caption(
                        "Ken je de referentieprijs of de inschrijvingsprijs niet, dan kan de "
                        "app ze afleiden uit de gepubliceerde NAV van de beheerder. Laad "
                        "daarvoor de NAV-export van Amundi op (kolommen datum en NAV). Dit is "
                        "een SCHATTING: lees de gevonden afwijking mee, en gebruik de cijfers "
                        "uit je fondsreglement zodra je die hebt. **Vul éérst de majoraties "
                        "hierboven in en bewaar ze** — kalibreren zonder schuift de "
                        "referentieprijs scheef, omdat de sprongen in de officiële NAV dan "
                        "ergens anders in geperst worden. Neem in de NAV-export bij voorkeur "
                        "de **oprichtingsdag** mee: die NAV is per reglement exact de "
                        "inschrijvingsprijs en pint die vast.")
                    st.caption(
                        f"**α blijft vast op {f_alpha:g}.** Die staat in het reglement en is "
                        "geen onbekende. Hem toch laten meebewegen geeft altijd een iets "
                        "kleinere afwijking — een extra vrijheidsgraad past nu eenmaal beter — "
                        "maar het resultaat is dan geen schatting van de werkelijkheid meer, "
                        "alleen nog een kromme die door de punten loopt.")
                    _c1, _c2 = st.columns(2)
                    _fit_sub = _c1.checkbox(
                        "Ook de inschrijvingsprijs afleiden", value=False, key="fcpe_fit_sub",
                        help="Aan als je ook die niet zeker weet. Ze bepaalt het gegarandeerde "
                             "deel en het rendement.")
                    _fit_alpha = _c2.checkbox(
                        "α toch meekalibreren", value=False, key="fcpe_fit_alpha",
                        help="Alleen als je het reglement van jouw jaargang echt niet hebt. "
                             "Wijkt de gevonden α ver af van een rond getal, dan klopt er "
                             "elders iets niet.")
                    _up = st.file_uploader("NAV-export (.xlsx)", type=["xlsx", "xls", "csv"],
                                           key="fcpe_nav_up")
                    if _up is not None and st.button("📥 Inlezen en kalibreren", key="fcpe_cal"):
                        try:
                            _n = _import_official_nav(f_sel, _up)
                            st.success(f"✅ {_n} NAV-regel(s) ingelezen.")
                            _off = {r["date"]: r["nav"] for r in db.get_official_nav(f_sel)}
                            _rdd = db.get_fcpe_readings(f_sel)
                            _spots = {r["date"]: r["close"] for r in _rdd}
                            _md_now = (db.get_fcpe_params(f_sel) or {}).get("md_entries")
                            fit = fcpe.fit_parameters(
                                _rdd, _off, n_readings=int(f_n), subscription_price=f_sub,
                                spots=_spots, alpha=f_alpha, fit_alpha=_fit_alpha,
                                fit_subscription=_fit_sub, start_date=str(f_start),
                                annual_rate=f_rate, maturity_date=str(f_mat),
                                maturity_return=f_mret, md_entries=_md_now)
                            if fit:
                                _parts = [f"**referentieprijs = {fit['reference_price']}**"]
                                if _fit_alpha:
                                    _parts.insert(0, f"**α = {fit['alpha']}**")
                                if fit.get("anchored_subscription"):
                                    _parts.append("**inschrijvingsprijs = "
                                                  f"{fit['subscription_price']}** (vastgepind "
                                                  "op de NAV van de oprichtingsdag)")
                                elif _fit_sub:
                                    _parts.append("**inschrijvingsprijs = "
                                                  f"{fit['subscription_price']}**")
                                st.info("🎯 Best passend: " + ", ".join(_parts)
                                        + f" (afwijking {fit['rmse']} EUR over "
                                        f"{fit['n_points']} punten). Vast gehouden: "
                                        + (", ".join(fit["fixed"]) or "niets")
                                        + ". Vul deze hierboven in als ze aannemelijk zijn.")
                                for _w in fit.get("warnings") or []:
                                    st.warning("⚠️ " + _w)
                                if fit["rmse"] > 1.0:
                                    st.warning(
                                        "⚠️ De afwijking is groot. Controleer eerst of de "
                                        "waarnemingen volledig zijn en of de aanvangsdatum en "
                                        "de waarnemingsregel kloppen — een verkeerde "
                                        "referentieprijs is zelden de enige oorzaak.")
                            else:
                                st.warning("Kalibratie niet mogelijk — haal eerst de "
                                           "waarnemingen op.")
                        except Exception as exc:
                            st.error(f"Inlezen mislukt: {exc}")
                    _offr = db.get_official_nav(f_sel)
                    if _offr:
                        _cmp_rows = []
                        for r in _offr:
                            _rv, _ = md.fcpe_value(f_sel, on_date=r["date"], auto_sync=False)
                            if _rv:
                                _cmp_rows.append({"Datum": r["date"],
                                                  "Berekend": round(_rv["value"], 2),
                                                  "Officieel": round(r["nav"], 2),
                                                  "Verschil": round(_rv["value"] - r["nav"], 2)})
                        if _cmp_rows:
                            _cd = pd.DataFrame(_cmp_rows)
                            _mad = _cd["Verschil"].abs().mean()
                            st.metric("Gemiddelde afwijking", f"{_mad:,.2f} EUR")
                            st.caption("Ligt dit dicht bij nul, dan kloppen je parameters. "
                                       "Wijkt het stelselmatig af, dan is de officiële NAV de "
                                       "waarheid en niet de berekening.")
                            show_df(_cd, width="stretch", hide_index=True, height=240)


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
