"""
views/status.py — pagina 'Status'.
"""
from __future__ import annotations

import logging

import streamlit as st

import database as db
import market_data as md

from views.common import (
    _short_ts, asset_name_map, clear_cache
)

logger = logging.getLogger("app.status")


def page_status():
    st.title("🩺 Status & waarschuwingen")
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
