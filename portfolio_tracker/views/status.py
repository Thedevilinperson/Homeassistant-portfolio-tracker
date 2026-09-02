"""
views/status.py — pagina 'Status'.
"""
from __future__ import annotations

import logging

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import belgian_tax as tax_mod
import database as db
import market_data as md

import views.common as common
from views.common import (
    _section_radio, _short_ts, asset_label, asset_name_map, clear_cache, show_df
)

logger = logging.getLogger("app.status")


def _overdue_dividends_section():
    """Uitkeringen waarvan de datum voorbij is terwijl er nog geen dividend geboekt is.

    Dit is bewust een WERKLIJST en geen opsomming van alles wat ooit uitgekeerd werd:
    wat al geboekt staat, hoort hier niet meer thuis. Er wordt ook niets automatisch
    ingeboekt — een kalenderbron die een dag naast de betaaldatum zit, mag nooit
    zelfstandig in je fiscale keten schrijven.
    """
    st.caption(
        "Uitkeringen waarvan de **betaaldatum** voorbij is terwijl er in de app nog "
        "geen dividend voor geboekt staat. Enkel activa waarvoor je op de ex-datum "
        "effectief stukken aanhield: voor de rest viel er ook niets te ontvangen. "
        "Is de betaaldatum niet gekend, dan geldt de ex-datum als benadering.")

    rows = common.overdue_dividend_rows()
    _last = db.get_setting("divcal_last_refresh", "")
    st.caption((f"Kalender laatst opgehaald: {_short_ts(_last)}."
                if _last else
                "⚠️ De dividendkalender is nog nooit opgehaald — deze lijst blijft leeg "
                "tot dat gebeurd is.")
               + " Ophalen doe je op 💰 Dividenden → 📅 Kalender; de planner doet het "
                 "ook dagelijks om 23:40.")

    if not rows:
        st.success("✅ Geen openstaande dividenddatums: elke voorbije uitkering waarvoor "
                   "je stukken had, is geboekt.")
        return

    names = asset_name_map()
    _tot = {}
    for r in rows:
        _cur = r.get("currency") or ""
        if r.get("bruto_geschat"):
            _tot[_cur] = _tot.get(_cur, 0.0) + r["bruto_geschat"]
    st.warning(f"**{len(rows)}** voorbije uitkering(en) zonder boeking"
               + ("  ·  samen ruwweg " +
                  ", ".join(f"{v:,.2f} {c}" for c, v in sorted(_tot.items()))
                  + " bruto." if _tot else "."))

    show_df(pd.DataFrame([{
        "Activum":     asset_label(r["ticker"], names),
        "Datum":       r["datum"] + (" (ex)" if r["datum_is_ex"] else ""),
        "Ex-datum":    r["ex_date"],
        "Per aandeel": r.get("amount"),
        "Munt":        r.get("currency") or "",
        "Aantal":      r["aantal"] or None,
        "Bruto (geschat)": r["bruto_geschat"],
        "Rekening(en)": ", ".join(sorted(r["per_rekening"])) or "—",
    } for r in rows]), width="stretch", hide_index=True, column_config={
        "Datum":       st.column_config.TextColumn(
            help="De betaaldatum. '(ex)' = de betaaldatum is niet gekend en dit is de "
                 "ex-datum bij benadering."),
        "Per aandeel": st.column_config.NumberColumn(format="%.10g"),
        "Aantal":      st.column_config.NumberColumn(format="%.10g"),
        "Bruto (geschat)": st.column_config.NumberColumn(format="%.10g"),
    })
    st.caption(
        "Een lijn kan hier ook staan omdat je het dividend op een **andere datum** "
        "geboekt hebt dan de kalender vermeldt: er wordt gezocht binnen drie weken "
        "rond de datum. Klopt de kalenderlijn niet, corrigeer of verwijder ze dan op "
        "💰 Dividenden → 📅 Kalender. Boeken doe je in diezelfde kalender met "
        "'📥 Boek dit dividend'.")
    if st.button("➡️ Naar de dividendkalender", key="status_to_divcal"):
        st.session_state["nav_goto"] = "💰 Dividenden"
        st.session_state["div_goto_section"] = "📅 Kalender"
        st.rerun()


def _ma_cross_section():
    """Golden cross / death cross: het punt waar het 50-daags gemiddelde (MA50) het
    200-daags gemiddelde (MA200) van onder naar boven kruist (golden, doorgaans als
    bullish gelezen) of van boven naar onder (death, doorgaans als bearish gelezen).

    Bewust een apart logboek los van 'status_events' hierboven: een kruising is een
    vaststaand feit op een vaste datum, geen toestand die later weer kan verdwijnen
    zoals een verouderde koers. Detectie draait automatisch mee met de dagelijkse
    statuscontrole (22:45) en kan hier ook manueel opnieuw."""
    st.caption(
        "Een **golden cross** is het moment waarop het 50-daags gemiddelde (MA50) van "
        "onder naar boven door het 200-daags gemiddelde (MA200) breekt — algemeen "
        "gelezen als een bullish signaal. Het omgekeerde heet een **death cross** en "
        "wordt als bearish gelezen. Beide zijn **achterlopende** indicatoren: ze "
        "bevestigen een trendwissel pas nadat die al bezig is, geven in een zijwaartse "
        "markt makkelijk valse signalen, en werken historisch iets betrouwbaarder op "
        "brede indices dan op individuele aandelen. Geen koop- of verkoopadvies — enkel "
        "een trendmaatstaf, net als het 200-daags gemiddelde op 📈 Evolutie.")

    last = db.get_setting("ma_cross_last_run", "")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🔄 Nu controleren op kruisingen", type="primary",
                     width="stretch", key="ma_cross_run"):
            with st.spinner("Koershistoriek ophalen en MA50/MA200 berekenen..."):
                ma_summary = db.detect_ma_crosses()
            st.session_state["ma_cross_last_summary"] = ma_summary
            common.clear_cache()
            st.rerun()
    with c2:
        if last:
            st.caption(f"Laatste controle: {_short_ts(last)} · draait ook automatisch "
                       "mee met de dagelijkse statuscontrole (22:45).")
        else:
            st.caption("Nog geen controle uitgevoerd — klik op 'Nu controleren op "
                       "kruisingen' of wacht op de dagelijkse run (22:45).")

    ma_summ = st.session_state.get("ma_cross_last_summary")
    if ma_summ:
        st.info(f"Laatste run: {ma_summ.get('checked', 0)} positie(s) met voldoende "
                f"historiek (≥200 slotkoersen) gecontroleerd · "
                f"{ma_summ.get('new', 0)} nieuwe kruising(en)"
                + (f" · {ma_summ['errors']} netwerkfout(en)" if ma_summ.get('errors') else ""))

    try:
        tickers, _closed = tax_mod.open_position_tickers()
    except Exception:
        tickers = [a["ticker"] for a in db.get_assets()]
    names = asset_name_map()

    st.divider()
    st.markdown("**Actuele stand per open positie**")
    if not tickers:
        st.caption("Geen open posities.")
    else:
        with st.spinner(f"MA50/MA200 ophalen voor {len(tickers)} positie(s)..."):
            ma50_map = md.moving_average_map(tickers, 50)
            ma200_map = md.moving_average_map(tickers, 200)

        rows = []
        for t in sorted(tickers):
            m50, m200 = ma50_map.get(t), ma200_map.get(t)
            if not m50 or not m200:
                continue
            golden = m50["ma"] > m200["ma"]
            last_ev = db.get_ma_cross_events(t, limit=1)
            laatste = (("🟡 Golden" if last_ev[0]["event_type"] == "golden_cross"
                       else "⚫ Death") + f" op {last_ev[0]['cross_date']}") \
                      if last_ev else "— (nog geen kruising gedetecteerd)"
            rows.append({
                "Activum":  asset_label(t, names),
                "Koers":    m50["price"],
                "MA50":     m50["ma"],
                "MA200":    m200["ma"],
                "Status":   "🟢 Golden (MA50 > MA200)" if golden else "🔴 Death (MA50 < MA200)",
                "Laatste kruising": laatste,
            })
        if rows:
            show_df(pd.DataFrame(rows), width="stretch", hide_index=True, column_config={
                "Koers": st.column_config.NumberColumn(format="%.10g"),
                "MA50":  st.column_config.NumberColumn(
                    format="%.10g", help="Gemiddelde van de laatste 50 slotkoersen, "
                                        "zonder dividendcorrectie."),
                "MA200": st.column_config.NumberColumn(
                    format="%.10g", help="Gemiddelde van de laatste 200 slotkoersen, "
                                        "zonder dividendcorrectie."),
            })
            _g = sum(1 for r in rows if r["Status"].startswith("🟢"))
            st.caption(f"**{_g}** van de **{len(rows)}** posities staat momenteel in "
                       "'golden'-stand (MA50 boven MA200).")

            _sel = st.selectbox("Grafiek voor", sorted(r["Activum"] for r in rows),
                                key="ma_cross_chart_ticker")
            _sel_ticker = next((t for t in sorted(tickers)
                               if asset_label(t, names) == _sel), None)
            if _sel_ticker:
                _render_ma_cross_chart(_sel_ticker, names)
        else:
            st.caption("Nog geen enkele open positie heeft voldoende koershistoriek "
                       "(200 slotkoersen) voor dit overzicht.")

    st.divider()
    st.markdown("**Logboek gedetecteerde kruisingen**")
    all_events = db.get_ma_cross_events(limit=200)
    if not all_events:
        st.info("Nog geen golden of death cross gedetecteerd. Het logboek vult zich "
                "bij de eerstvolgende controle met kruisingen binnen de laatste "
                "ongeveer 2,5 jaar, en daarna met elke nieuwe kruising die zich voordoet.")
        return

    ev_rows = [{
        "": "🟡" if e["event_type"] == "golden_cross" else "⚫",
        "Activum": asset_label(e["ticker"], names),
        "Type": "Golden cross" if e["event_type"] == "golden_cross" else "Death cross",
        "Datum": e["cross_date"],
        "MA50 toen": e.get("ma50"),
        "MA200 toen": e.get("ma200"),
        "Koers toen": e.get("price"),
        "Gedetecteerd op": _short_ts(e["detected_at"]),
    } for e in all_events]
    show_df(pd.DataFrame(ev_rows), width="stretch", hide_index=True, column_config={
        "MA50 toen":  st.column_config.NumberColumn(format="%.10g"),
        "MA200 toen": st.column_config.NumberColumn(format="%.10g"),
        "Koers toen": st.column_config.NumberColumn(format="%.10g"),
    })


def _render_ma_cross_chart(ticker: str, names: dict):
    """Koerslijn met MA50/MA200, plus markers op elk gedetecteerd kruispunt."""
    start = (pd.Timestamp.now() - pd.Timedelta(days=900)).strftime("%Y-%m-%d")
    try:
        series = md.get_price_series(ticker, start, auto_adjust=False)
    except Exception as exc:
        logger.warning(f"_render_ma_cross_chart({ticker}): reeks niet opgehaald ({exc})")
        series = None
    if series is None or not len(series):
        st.caption("Geen koersreeks beschikbaar voor dit activum.")
        return

    s = pd.Series(list(series.values), index=list(series.index)).astype(float)
    ma50 = s.rolling(window=50, min_periods=50).mean()
    ma200 = s.rolling(window=200, min_periods=200).mean()

    events = db.get_ma_cross_events(ticker, limit=50)
    golden_pts = [(e["cross_date"], e["price"]) for e in events
                  if e["event_type"] == "golden_cross" and e.get("price") is not None]
    death_pts = [(e["cross_date"], e["price"]) for e in events
                 if e["event_type"] == "death_cross" and e.get("price") is not None]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(s.index), y=list(s.values), mode="lines",
                             name="Koers", line=dict(color="#74b9ff", width=1.4)))
    fig.add_trace(go.Scatter(x=list(ma50.index), y=list(ma50.values), mode="lines",
                             name="MA50", line=dict(color="#00cec9", width=1.8)))
    fig.add_trace(go.Scatter(x=list(ma200.index), y=list(ma200.values), mode="lines",
                             name="MA200", line=dict(color="#fdcb6e", width=2)))
    if golden_pts:
        fig.add_trace(go.Scatter(x=[p[0] for p in golden_pts], y=[p[1] for p in golden_pts],
                                 mode="markers", name="Golden cross",
                                 marker=dict(symbol="triangle-up", size=13, color="#f1c40f",
                                            line=dict(width=1, color="#7f6a00"))))
    if death_pts:
        fig.add_trace(go.Scatter(x=[p[0] for p in death_pts], y=[p[1] for p in death_pts],
                                 mode="markers", name="Death cross",
                                 marker=dict(symbol="triangle-down", size=13, color="#2d3436",
                                            line=dict(width=1, color="#000000"))))
    fig.update_layout(height=360, margin=dict(t=40, b=30, l=20, r=20),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", yanchor="bottom", y=1.0,
                                  xanchor="right", x=1.0),
                      hovermode="x unified",
                      title=f"{names.get(ticker, ticker)} — koers, MA50 en MA200")
    st.plotly_chart(fig, width="stretch")
    st.caption("Koersen in de native munt van het activum. Het venster toont ongeveer "
               "2,5 jaar; markers verschijnen enkel voor kruisingen binnen dat venster "
               "die ook effectief in het logboek staan.")


def page_status():
    st.title("🩺 Status & waarschuwingen")

    _sec = _section_radio("status_section",
                          ["🩺 Meldingen", "📈 Golden/Death Cross",
                           "💰 Voorbije dividenddatums"])
    if _sec == "💰 Voorbije dividenddatums":
        _overdue_dividends_section()
        return
    if _sec == "📈 Golden/Death Cross":
        _ma_cross_section()
        return

    st.caption("De gezondheid van je koersdata op één plek: verouderde koersen, dagen zonder "
               "koersbeweging, tickerwijzigingen of meerdere producten onder één ISIN, "
               "niet-geregistreerde aandelensplits en naamsafwijkingen (mogelijke fusie of "
               "rebranding).")

    last = db.get_setting("status_last_run")
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("🔄 Nu controleren", type="primary", width="stretch"):
            with st.spinner("Statuscontrole uitvoeren (koersdata + online bronnen)..."):
                summary = db.run_status_checks(online=True)
            st.session_state["status_last_summary"] = summary
            clear_cache()
            st.rerun()
    with c2:
        if last:
            st.caption(f"Laatste controle: {_short_ts(last)} · draait ook automatisch elke dag "
                       "om 22:45.")
        else:
            st.caption("Nog geen automatische controle uitgevoerd — klik op 'Nu controleren' of "
                       "wacht op de dagelijkse run (22:45).")

    summ = st.session_state.get("status_last_summary")
    if summ:
        st.info(f"Laatste run: {summ.get('checked', 0)} activa gecontroleerd · "
                f"{summ.get('new', 0)} nieuw · {summ.get('resolved', 0)} opgelost · "
                f"{summ.get('open', 0)} open"
                + (f" · {summ['errors']} netwerkfout(en)" if summ.get('errors') else "")
                + (f" · {summ['ma_cross_new']} nieuwe MA-kruising(en) (zie tab "
                   "'📈 Golden/Death Cross')" if summ.get('ma_cross_new') else "")
                + ("" if summ.get("online") else " · (offline: enkel koersdata-checks)"))

    with st.expander("🔑 Euronext-wachtwoord (ontsleuteling)"):
        ks = md.euronext_key_status()
        if ks.get("has_key"):
            st.success(f"Wachtwoord ingesteld · afdruk `{ks.get('fingerprint') or '—'}`"
                       + (f" · laatst gecontroleerd {_short_ts(ks['checked'])}"
                          if ks.get("checked") else ""))
        else:
            st.info("Nog geen wachtwoord opgeslagen — de app gebruikt voorlopig het "
                    "ingebouwde terugval-wachtwoord uit de Euronext-JS. Klik hieronder op "
                    "'Wachtwoord opnieuw bepalen' om het te bevestigen en vast te leggen.")
        st.caption("Euronext versleutelt zijn antwoorden met de Drupal-module 'ajax_secure' "
                   "(CryptoJS-AES): per antwoord een eigen salt + IV, afgeleid uit één vast "
                   "WACHTWOORD (drupalSettings.ajax_secure.kye). 'Opnieuw bepalen' leest dat "
                   "wachtwoord uit de live pagina en valideert het tegen een echt versleuteld "
                   "staal. De dagelijkse statuscontrole (22:45) doet dit ook automatisch en "
                   "herstelt een wijziging zelf.")
        if st.button("🔁 Wachtwoord opnieuw bepalen", key="eur_key_rebuild", type="primary"):
            with st.spinner("Euronext-wachtwoord ophalen en valideren..."):
                rep = md.euronext_rebuild_key()
            if rep.get("ok"):
                st.success(rep.get("message") or "Wachtwoord in orde.")
            else:
                st.error(rep.get("message") or "Geen werkend wachtwoord gevonden.")
            st.caption(f"Kandidaten geprobeerd: {rep.get('candidates', 0)}")

        st.markdown("**Handmatig instellen** (als het automatisch bepalen niet lukt)")
        st.caption("Zo vind je het zelf: open op live.euronext.com F12 → tabblad **Sources** en "
                   "zoek (Ctrl+Shift+F) naar `ajax_secure`. In de code staat "
                   "`drupalSettings.ajax_secure.kye`; die waarde is het wachtwoord. Staat ze er "
                   "niet, dan geldt de terugval die in dezelfde functie staat.")
        cur_pw = db.get_setting("euronext_aes_key", "") or ""
        man_pw = st.text_input("Wachtwoord (ajax_secure kye)", value=cur_pw, key="eur_man_key")
        if st.button("Handmatig opslaan & testen", key="eur_man_save"):
            db.set_setting("euronext_aes_key", man_pw.strip())
            with st.spinner("Testen tegen een vers Euronext-staal..."):
                rep = md.euronext_rebuild_key()
            if rep.get("ok"):
                st.success("Wachtwoord werkt: " + (rep.get("message") or ""))
            else:
                st.error("Dit wachtwoord ontsleutelt het staal niet: " + (rep.get("message") or ""))

    with st.expander("🔧 Euronext-respons inspecteren (diagnose)"):
        st.caption("Haalt de RUWE Euronext-respons op zoals de add-on ze ziet — handig om te "
                   "achterhalen waarom Euronext geen koers teruggeeft. Puur diagnostisch, "
                   "verandert niets. Kopieer de uitvoer hieronder en bezorg ze me, dan pas ik "
                   "de parser gericht aan.")
        dc1, dc2 = st.columns([2, 1])
        diag_isin = dc1.text_input("ISIN", key="eur_diag_isin",
                                   placeholder="bv. BE0003739530").strip().upper()
        diag_mic = dc2.text_input("MIC (optioneel)", key="eur_diag_mic",
                                  placeholder="XBRU").strip().upper() or None
        if st.button("Euronext bevragen", key="eur_diag_run"):
            if not diag_isin:
                st.warning("Geef een ISIN in.")
            else:
                with st.spinner("Ruwe Euronext-respons ophalen..."):
                    res = md.euronext_raw_probe(diag_isin, diag_mic)
                st.session_state["eur_diag_result"] = res
        res = st.session_state.get("eur_diag_result")
        if res:
            st.write(f"**ISIN {res.get('isin')} · handelsplaats {res.get('mic')}**")
            if res.get("error"):
                st.error(res["error"])
            for ep in res.get("endpoints", []):
                st.markdown(f"**{ep['name']}** — HTTP {ep.get('status', ep.get('error', '?'))} · "
                            f"{ep.get('content_type', '')} · {ep.get('length', 0)} tekens"
                            + (f" · geparste tabelrijen: {ep['parsed_rows']}"
                               if "parsed_rows" in ep else ""))
                if ep.get("parsed_labels"):
                    st.caption("Labels: " + ", ".join(ep["parsed_labels"]))
                if ep.get("envelope_fields"):
                    st.caption("Envelope-velden: " + ", ".join(ep["envelope_fields"])
                               + " · ontsleuteling: " + str(ep.get("decrypt_status", "—")))
                if ep.get("decrypted_head"):
                    st.caption("Ontsleutelde inhoud (begin):")
                    st.code(ep["decrypted_head"], language="html")
                if ep.get("body_head"):
                    st.code(ep["body_head"], language="html")
                if ep.get("body_tail"):
                    st.caption("Staart van de ruwe respons (hier staan iv en s):")
                    st.code(ep["body_tail"], language="json")
                st.caption(ep["url"])

    events = db.get_status_events()
    if not events:
        st.success("✅ Geen openstaande waarschuwingen. Je koersdata ziet er gezond uit.")
        st.caption("Tip: staat een US-aandeel op 0% dagwinst, kijk dan op het Dashboard naar de "
                   "kolom 'Koers gewijzigd'. Is die recent, dan is 0% normaal (markt gesloten); "
                   "staat ze dagen terug, dan verschijnt hier een waarschuwing 'Verouderde koers'.")
        return

    names = asset_name_map()
    SEV = {"error": "🔴", "warning": "🟠", "info": "🔵"}
    KIND = {"stale_price": "Verouderde koers", "flat_price": "Geen koersbeweging",
            "ticker_change": "Tickerwijziging", "split": "Aandelensplit",
            "name_change": "Naamsafwijking"}

    # Afgevinkte meldingen ('✓ Gezien') verhuizen naar een archief dat standaard
    # dichtgeklapt staat. Ze blijven bestaan — je hebt ze immers niet opgelost maar
    # enkel gezien — maar ze mogen de openstaande punten niet meer verdringen. Een
    # geregistreerde split die je bewust laat staan, hoort niet elke dag opnieuw
    # bovenaan je statuspagina.
    live = [e for e in events if not e.get("acknowledged")]
    archived = [e for e in events if e.get("acknowledged")]

    n_warn = sum(1 for e in live if e["severity"] in ("warning", "error"))
    n_info = sum(1 for e in live if e["severity"] == "info")
    if live:
        st.markdown(f"**{len(live)} openstaande waarschuwing(en)** — {n_warn} ter opvolging, "
                    f"{n_info} informatief."
                    + (f"  ·  {len(archived)} gearchiveerd (onderaan)." if archived else ""))
    else:
        st.success("✅ Geen openstaande waarschuwingen — alles staat op 'gezien'. "
                   "Het archief onderaan bewaart ze.")
    st.divider()

    def _render_event(e, prefix=""):
        icon = SEV.get(e["severity"], "⚪")
        nm = names.get(e["ticker"], e["ticker"])
        d = e.get("detail") or {}
        with st.container(border=True):
            left, right = st.columns([5, 1])
            with left:
                ack = " · ✓ gezien" if e.get("acknowledged") else ""
                st.markdown(f"{icon} **{nm}** ({e['ticker']}) · *{KIND.get(e['kind'], e['kind'])}*{ack}")
                st.write(e["message"])
                meta = f"Sinds {_short_ts(e['detected_at'])}"
                if e.get("isin"):
                    meta += f" · ISIN {e['isin']}"
                if e["kind"] == "ticker_change" and d.get("candidates"):
                    meta += f" · kandidaten: {', '.join(d['candidates'])}"
                if e["kind"] == "name_change" and d.get("yahoo"):
                    meta += f" · bron: '{d['yahoo']}'"
                if e["kind"] == "ticker_change" and d.get("new"):
                    meta += " · 'Gevonden ticker' is automatisch bijgewerkt"
                if e["kind"] == "flat_price" and d.get("market"):
                    meta += f" · beurskalender: {d['market']}"
                st.caption(meta)
            with right:
                if e["kind"] == "split" and d.get("splits"):
                    if st.button("Split registreren", key=f"{prefix}sp_{e['id']}", width="stretch"):
                        for d_, r_ in d["splits"]:
                            db.add_split(e["ticker"], d_, float(r_))
                        db.resolve_status_event_by_id(e["id"])
                        clear_cache()
                        st.rerun()
                if not e.get("acknowledged"):
                    if st.button("✓ Gezien", key=f"{prefix}ack_{e['id']}", width="stretch"):
                        db.acknowledge_status_event(e["id"])
                        st.rerun()
                if st.button("Sluiten", key=f"{prefix}cl_{e['id']}", width="stretch"):
                    db.resolve_status_event_by_id(e["id"])
                    st.rerun()

    for e in live:
        _render_event(e)

    if archived:
        _n_split = sum(1 for e in archived if e["kind"] == "split")
        with st.expander(f"🗄️ Archief — {len(archived)} melding(en) op 'gezien'"
                         + (f", waarvan {_n_split} split(s)" if _n_split else ""),
                         expanded=False):
            st.caption(
                "Meldingen die je met '✓ Gezien' hebt afgevinkt. Ze zijn niet opgelost — "
                "de toestand bestaat nog — maar je hebt ze beoordeeld, en dan hoeven ze niet "
                "meer bij de openstaande punten te staan. Een aandelensplit die je bewust "
                "níét registreert (bv. omdat je broker de stukken al aangepast heeft) blijft "
                "hier gewoon staan. Met 'Sluiten' verdwijnt een melding helemaal; blijft de "
                "toestand bestaan, dan komt ze bij de volgende controle terug.")
            for e in archived:
                _render_event(e, prefix="arch_")

    st.caption("'Sluiten' verbergt een waarschuwing; blijft de toestand bestaan, dan verschijnt "
               "ze bij de volgende controle opnieuw. '✓ Gezien' verplaatst ze naar het archief "
               "hierboven. Een aandelensplit wordt NIET automatisch toegepast — pas na 'Split "
               "registreren' worden je transacties en kostbasis aangepast (FIFO). Een "
               "gedetecteerde tickerwijziging werkt de kolom 'Gevonden ticker' meteen bij en "
               "selecteert voortaan het actieve symbool.  \n"
               "🗓️ **Sluitingsdagen tellen niet mee:** weekends en beursfeestdagen (Nieuwjaar, "
               "Goede Vrijdag, Paasmaandag, 1 mei, Kerstmis en tweede kerstdag voor Euronext; "
               "de NYSE-kalender voor Amerikaanse noteringen) worden overgeslagen bij de "
               "controle op 'geen koersbeweging', en de leeftijd van een koers wordt in "
               "béúrsdagen geteld. Staat een hele markt op dezelfde dag stil, dan wordt dat "
               "ook als sluitingsdag herkend — zo geeft bijvoorbeeld 21 juli geen valse "
               "waarschuwingen.")
