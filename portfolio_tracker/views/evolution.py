"""
views/evolution.py — pagina 'Evolutie'.
"""
from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import belgian_tax as tax_mod
import database as db
import market_data as md

from views.common import (
    _short_ts, asset_name_map, clear_cache, num, pct, show_df
)

logger = logging.getLogger("app.evolution")


@st.cache_data(ttl=1800, show_spinner=False)
def _evolution_df(sig: str):
    """Reconstrueer de historische waarde/kostenbasis per rekening (1800s cache)."""
    txns = db.get_transactions()
    assets = db.get_assets()
    if not txns:
        return None
    ticker_currency = {a["ticker"]: a.get("currency", "EUR") for a in assets}
    start = min(t["date"] for t in txns)[:10]
    price_map, fx_map, currencies = {}, {}, set()
    for a in assets:
        s = md.get_price_series(a["ticker"], start)
        if s is not None:
            price_map[a["ticker"]] = s
        currencies.add(a.get("currency", "EUR"))
    for cur in currencies:
        if cur != "EUR":
            fx_map[cur] = md.get_fx_series(cur, start)
    return tax_mod.reconstruct_portfolio_evolution(txns, price_map, fx_map, ticker_currency)


def _ma200_section():
    """Punt 5: het 200-daags voortschrijdend gemiddelde van de posities in
    portefeuille, en hoe ver de koers erboven of eronder staat.

    Bewust enkel voor de OPEN POSITIES: voor een verkochte positie is de trend geen
    beslissingsinformatie meer, en elke extra ticker kost een koersreeks van
    anderhalf jaar. Dezelfde cijfers gaan als 'ma200' en 'koers_vs_ma200_pct' mee
    naar de AI-adviseur, zodat wat je hier ziet en wat de AI weegt niet uit elkaar
    kunnen lopen.
    """
    st.divider()
    st.subheader("📉 200-daags voortschrijdend gemiddelde")
    st.caption(
        "Het gemiddelde van de laatste 200 slotkoersen, de meest gebruikte "
        "trendmaatstaf op de beurs. Noteert een aandeel **boven** zijn 200-daags "
        "gemiddelde, dan is de langetermijntrend opwaarts; **eronder** neerwaarts. "
        "Het is een trendmaatstaf, geen koop- of verkoopsignaal: ver boven het "
        "gemiddelde betekent ook een minder gunstig instapmoment, en ver eronder "
        "maakt een aandeel niet vanzelf koopwaardig. Deze cijfers gaan ook mee naar "
        "de AI-adviseur bij het dagelijkse portefeuilleadvies.")

    tickers, _closed = tax_mod.open_position_tickers()
    if not tickers:
        st.info("Geen open posities. Het gemiddelde wordt enkel berekend voor de "
                "aandelen die je nu aanhoudt.")
        return

    names = asset_name_map()
    sig = ":".join(sorted(tickers))
    with st.spinner(f"Koershistoriek ophalen voor {len(tickers)} positie(s)..."):
        ma = _ma200_map(sig)

    if not ma:
        st.warning("Geen bruikbare koershistoriek gevonden voor je posities — zonder "
                   "historiek valt er geen gemiddelde te berekenen.")
        return

    rows = []
    for tk in sorted(ma, key=lambda t: ma[t]["ratio_pct"], reverse=True):
        m = ma[tk]
        rows.append({
            "":          "🟢" if m["ratio_pct"] >= 0 else "🔴",
            "Activum":   f"{names.get(tk, tk)} ({tk})",
            "Koers":     m["price"],
            "MA200":     m["ma"],
            "Verhouding": m["ratio"],
            "Δ t.o.v. MA200": m["ratio_pct"],
            "Trend":     "Boven het gemiddelde" if m["ratio_pct"] >= 0 else "Onder het gemiddelde",
            "Slotkoersen": m["n"],
            "Laatste koers op": m.get("laatste_datum") or "",
        })
    show_df(pd.DataFrame(rows), width="stretch", hide_index=True, column_config={
        "Koers":      st.column_config.NumberColumn(
            format="%.10g", help="Laatste slotkoers uit de historiek (native munt)."),
        "MA200":      st.column_config.NumberColumn(
            format="%.10g",
            help="Gemiddelde van de laatste 200 slotkoersen, zonder dividendcorrectie: "
                 "een gecorrigeerde reeks ligt in het verleden lager en zou het "
                 "gemiddelde te laag zetten."),
        "Verhouding": st.column_config.NumberColumn(
            format="%.4f",
            help="Koers gedeeld door het gemiddelde. 1,00 = precies op het gemiddelde."),
        "Δ t.o.v. MA200": st.column_config.NumberColumn(format="%+.10g%%"),
        "Slotkoersen": st.column_config.NumberColumn(
            format="%d",
            help="Op hoeveel slotkoersen het gemiddelde berust. Minder dan 200 betekent "
                 "dat er niet genoeg historiek is (bv. een recente notering); het "
                 "signaal is dan zwakker."),
    })
    _kort = [t for t, m in ma.items() if not m["volledig"]]
    _mist = [t for t in tickers if t.upper() not in ma]
    _boven = sum(1 for m in ma.values() if m["ratio_pct"] >= 0)
    st.caption(f"**{_boven}** van de **{len(ma)}** posities noteert boven haar 200-daags "
               "gemiddelde."
               + ("  ·  ⚠️ Minder dan 200 slotkoersen voor: "
                  + ", ".join(names.get(t, t) for t in _kort) + "." if _kort else "")
               + ("  ·  Geen historiek voor: "
                  + ", ".join(names.get(t, t) for t in _mist)
                  + " (bv. een gekoppeld fonds zonder notering)." if _mist else ""))

    # ── Grafiek per positie: koers tegenover het gemiddelde ─────────────────
    _sel = st.selectbox("Grafiek voor", sorted(ma),
                        format_func=lambda t: f"{names.get(t, t)} ({t})",
                        key="ma200_ticker")
    _start = (datetime.now() - pd.Timedelta(days=520)).strftime("%Y-%m-%d")
    try:
        series = md.get_price_series(_sel, _start, auto_adjust=False)
    except Exception as exc:
        logger.warning(f"_ma200_section({_sel}): reeks niet opgehaald ({exc})")
        series = None
    if series is None or not len(series):
        st.caption("Geen koersreeks beschikbaar voor dit activum.")
        return
    _s = pd.Series(list(series.values), index=list(series.index)).astype(float)
    _ma_line = _s.rolling(window=200, min_periods=20).mean()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=list(_s.index), y=list(_s.values), mode="lines",
                             name="Koers", line=dict(color="#74b9ff", width=1.8)))
    fig.add_trace(go.Scatter(x=list(_ma_line.index), y=list(_ma_line.values),
                             mode="lines", name="200-daags gemiddelde",
                             line=dict(color="#fdcb6e", width=2)))
    fig.update_layout(height=340, margin=dict(t=40, b=30, l=20, r=20),
                      plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                      legend=dict(orientation="h", yanchor="bottom", y=1.0,
                                  xanchor="right", x=1.0),
                      hovermode="x unified",
                      title=f"{names.get(_sel, _sel)} — koers en 200-daags gemiddelde")
    st.plotly_chart(fig, width="stretch")
    st.caption("De eerste maanden van de lijn steunen op minder dan 200 slotkoersen "
               "(vanaf 20) — daar is het gemiddelde nog nerveus. Koersen staan in de "
               "native munt van het aandeel.")


@st.cache_data(ttl=1800, show_spinner=False)
def _ma200_map(sig: str):
    """Het 200-daags gemiddelde per open positie (cache 30 min).

    'sig' is de gesorteerde tickerlijst: verandert je portefeuille, dan vervalt de
    cache vanzelf. Zonder deze cache zou elke rerun van de pagina opnieuw een
    koersreeks van anderhalf jaar per positie ophalen.
    """
    return md.moving_average_map([t for t in sig.split(":") if t], 200)


def _koersdoel_historiek_section():
    """Punt 8: evolutie van de koersdoelen per activum (handmatig én AI), met de
    mogelijkheid om het koersdoel opnieuw te bepalen. Toont per activum een tijdlijn
    van wanneer welk koersdoel is vastgelegd of gewijzigd."""
    st.divider()
    st.subheader("🎯 Koersdoel-historiek")

    hist_tickers = db.get_tickers_with_target_history()
    names = asset_name_map()

    if not hist_tickers:
        st.caption("Nog geen koersdoelen vastgelegd. Zodra je een koersdoel instelt "
                   "(handmatig bij een activum/transactie of via een AI-advies), verschijnt "
                   "de evolutie hier per activum.")
        return

    sel = st.selectbox("Activum", hist_tickers,
                       format_func=lambda t: f"{names.get(t, t)} ({t})",
                       key="pt_hist_ticker")
    hist = db.get_price_target_history(sel)   # chronologisch (oudste eerst)
    if not hist:
        st.caption("Geen koersdoelen voor dit activum.")
        return

    SRC_LBL = {"manual": "✍️ Handmatig", "ai": "🤖 AI"}

    # ── Tabel: nieuwste eerst, met wijziging t.o.v. het vorige koersdoel ──────
    rows = []
    for i, h in enumerate(hist):
        prev = hist[i - 1]["target"] if i > 0 else None
        delta = (h["target"] - prev) if prev is not None else None
        note = h.get("note")
        label = SRC_LBL.get(h["source"], h["source"])
        if h["source"] == "ai" and note:
            label += f" ({note})"
        elif note and note != "huidig koersdoel (migratie)":
            label += f" · {note}"
        rows.append({
            "Vastgelegd op": _short_ts(h["set_at"]),
            "Koersdoel":     h["target"],
            "Munt":          h["currency"],
            "Δ t.o.v. vorige": delta,
            "Bron":          label,
        })
    rows.reverse()   # nieuwste bovenaan
    show_df(pd.DataFrame(rows), width="stretch", hide_index=True, column_config={
        "Koersdoel":       st.column_config.NumberColumn(format="%.10g"),
        "Δ t.o.v. vorige": st.column_config.NumberColumn(format="%+.10g"),
    })

    # ── Grafiek: koersdoel-evolutie (trapjeslijn) + werkelijke koers ─────────
    try:
        xs = [datetime.strptime(str(h["set_at"])[:19], "%Y-%m-%d %H:%M:%S") for h in hist]
    except (ValueError, TypeError):
        xs = None
    if xs and len(xs) >= 1:
        fig = go.Figure()
        # Werkelijke koers als achtergrond (native munt), indien beschikbaar.
        try:
            start = min(xs).strftime("%Y-%m-%d")
            series = md.get_price_series(sel, start)
            if series is not None and len(series):
                fig.add_trace(go.Scatter(
                    x=list(series.index), y=list(series.values), mode="lines",
                    name="Koers", line=dict(color="rgba(160,160,160,0.55)", width=1.5)))
        except Exception:
            pass
        # Koersdoel als trapjeslijn tot vandaag doorgetrokken.
        tx = xs + [datetime.now()]
        ty = [h["target"] for h in hist] + [hist[-1]["target"]]
        fig.add_trace(go.Scatter(
            x=tx, y=ty, mode="lines", name="Koersdoel",
            line=dict(color="#fdcb6e", width=2, shape="hv")))
        # Markers per bron (kleur = handmatig vs AI).
        for src, col, nm in (("manual", "#0984e3", "Handmatig"), ("ai", "#00b894", "AI")):
            pts = [(x, h["target"]) for x, h in zip(xs, hist) if h["source"] == src]
            if pts:
                fig.add_trace(go.Scatter(
                    x=[p[0] for p in pts], y=[p[1] for p in pts], mode="markers",
                    name=nm, marker=dict(color=col, size=9,
                                         line=dict(color="white", width=1))))
        fig.update_layout(height=320, margin=dict(t=30, b=30, l=20, r=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", yanchor="bottom", y=1.0,
                                      xanchor="right", x=1.0),
                          title=f"Koersdoel-evolutie — {names.get(sel, sel)} ({hist[-1]['currency']})")
        st.plotly_chart(fig, width="stretch")

    st.caption("De trapjeslijn toont het geldende koersdoel over de tijd; elk bolletje is een "
               "moment waarop een koersdoel werd vastgelegd of gewijzigd (blauw = handmatig, "
               "groen = AI). De grijze lijn is de werkelijke koers, indien beschikbaar.")

    # ── Koersdoel opnieuw bepalen (handmatig) ────────────────────────────────
    with st.expander("🎯 Koersdoel opnieuw bepalen"):
        _cur_default = hist[-1]["currency"] or "EUR"
        hc1, hc2, hc3 = st.columns([2, 1, 1])
        new_tgt = hc1.number_input(f"Nieuw koersdoel ({_cur_default})", min_value=0.0,
                                   step=0.01, value=float(hist[-1]["target"]),
                                   key=f"pt_new_{sel}")
        new_cur = hc2.text_input("Munt", value=_cur_default, key=f"pt_cur_{sel}").strip().upper()
        hc3.markdown("&nbsp;")
        if hc3.button("Vastleggen", key=f"pt_set_{sel}", type="primary"):
            if new_tgt and new_tgt > 0:
                db.update_asset(sel, price_target=float(new_tgt),
                                price_target_currency=(new_cur or _cur_default))
                clear_cache()
                st.success(f"🎯 Nieuw koersdoel {num(new_tgt, 2)} {new_cur or _cur_default} "
                           f"vastgelegd voor {names.get(sel, sel)}.")
                st.rerun()
            else:
                st.warning("Geef een koersdoel groter dan 0 in.")
        st.caption("Het nieuwe koersdoel wordt het actieve doel op het activum én komt als "
                   "handmatige wijziging in de historiek hierboven.")


def page_evolution():
    st.title("📈 Waarde-evolutie & vergelijking per rekening")

    txns = db.get_transactions()
    if not txns:
        st.info("Nog geen transacties. Voeg ze toe via ➕ Transacties.")
        return

    sig = f"{len(txns)}:{max(t['id'] for t in txns)}:{min(t['date'] for t in txns)[:10]}"
    with st.spinner("Historische koersen ophalen en portefeuille reconstrueren..."):
        df = _evolution_df(sig)

    if df is None or df.empty:
        st.warning("Kon geen historische reeks opbouwen — koersdata (yfinance) niet beschikbaar voor deze tickers.")
        _ma200_section()
        _koersdoel_historiek_section()
        return

    acct_cols = sorted(c[len("value::"):] for c in df.columns
                       if c.startswith("value::") and c != "value::TOTAL")

    cfg1, cfg2 = st.columns([3, 2])
    with cfg1:
        sel = st.multiselect("Rekeningen", acct_cols, default=acct_cols)
    with cfg2:
        months = st.select_slider("Periode", options=[1, 3, 6, 12, 24, 60], value=12,
                                  format_func=lambda m: f"{m} mnd" if m < 24 else f"{m//12} jaar")
    if not sel:
        st.info("Selecteer minstens één rekening.")
        return

    cutoff = df.index.max() - pd.Timedelta(days=30 * months)
    d = df[df.index >= cutoff]

    # ── Grafiek 1: absolute waarde-evolutie (EUR) ─────────────────────────────
    st.subheader("💼 Waarde-evolutie (EUR)")
    fig_val = go.Figure()
    palette = ["#74b9ff", "#00b894", "#fdcb6e", "#e17055", "#a29bfe", "#fd79a8"]
    for i, acct in enumerate(sel):
        col = f"value::{acct}"
        if col in d:
            fig_val.add_trace(go.Scatter(
                x=d.index, y=d[col], mode="lines", name=acct,
                line=dict(width=2, color=palette[i % len(palette)]),
            ))
    if len(sel) > 1:
        cols = [f"value::{a}" for a in sel if f"value::{a}" in d]
        tot = d[cols].sum(axis=1)
        fig_val.add_trace(go.Scatter(x=d.index, y=tot, mode="lines", name="Totaal (selectie)",
                                     line=dict(width=3, color="#ffffff", dash="dot")))
    fig_val.update_layout(height=360, margin=dict(t=20, b=30, l=20, r=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", y=-0.15), hovermode="x unified")
    fig_val.update_yaxes(tickprefix="€")
    st.plotly_chart(fig_val, width='stretch')

    # ── Grafiek 2: procentuele meer-/minwaarde t.o.v. aankoopprijs ────────────
    st.subheader("📊 Procentuele meer-/minwaarde t.o.v. aankoopprijs")
    st.caption("Per rekening: (huidige waarde − kostenbasis) / kostenbasis. Toont het rendement op het belegde geld, niet het absolute bedrag.")
    fig_pct = go.Figure()
    for i, acct in enumerate(sel):
        vcol, ccol = f"value::{acct}", f"cost::{acct}"
        if vcol in d and ccol in d:
            pct_series = (d[vcol] - d[ccol]) / d[ccol].replace(0, float("nan")) * 100
            fig_pct.add_trace(go.Scatter(
                x=d.index, y=pct_series, mode="lines", name=acct,
                line=dict(width=2, color=palette[i % len(palette)]),
            ))
    fig_pct.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.4)")
    fig_pct.update_layout(height=360, margin=dict(t=20, b=30, l=20, r=20),
                          plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                          legend=dict(orientation="h", y=-0.15), hovermode="x unified")
    fig_pct.update_yaxes(ticksuffix="%")
    st.plotly_chart(fig_pct, width='stretch')

    # ── Huidige momentopname per rekening ─────────────────────────────────────
    st.divider()
    st.subheader("📌 Huidige stand per rekening")
    assets = db.get_assets()
    prices = md.get_prices_for_tickers([a["ticker"] for a in assets])
    summ = tax_mod.account_summary(db.get_transactions(), prices)
    rows = []
    for acct in sorted(summ):
        s = summ[acct]
        rows.append({
            "Rekening":       acct,
            "Posities":       s["n_positions"],
            "Kostenbasis":    s["cost_basis"],
            "Huidige waarde": s["current_value"],
            "W/V (€)":        s["gain_loss"],
            "W/V (%)":        s["gain_loss_pct"],
        })
    if rows:
        show_df(pd.DataFrame(rows), width='stretch', hide_index=True, column_config={
            "Kostenbasis":    st.column_config.NumberColumn(format="€ %.10g"),
            "Huidige waarde": st.column_config.NumberColumn(format="€ %.10g"),
            "W/V (€)":        st.column_config.NumberColumn(format="€ %.10g"),
            "W/V (%)":        st.column_config.NumberColumn(format="%+.10g%%"),
        })
        fig_cmp = go.Figure(go.Bar(
            x=[r["Rekening"] for r in rows],
            y=[summ[r["Rekening"]]["gain_loss_pct"] for r in rows],
            marker_color=["#00b894" if summ[r["Rekening"]]["gain_loss_pct"] >= 0 else "#d63031" for r in rows],
            text=[pct(summ[r["Rekening"]]["gain_loss_pct"]) for r in rows],
            textposition="outside",
        ))
        fig_cmp.add_hline(y=0, line_dash="dot", line_color="rgba(200,200,200,0.3)")
        fig_cmp.update_layout(title="Rendement per rekening (%)", height=300,
                              margin=dict(t=40, b=30, l=20, r=20), showlegend=False,
                              plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)")
        fig_cmp.update_yaxes(ticksuffix="%")
        st.plotly_chart(fig_cmp, width='stretch')

    _ma200_section()
    _koersdoel_historiek_section()
