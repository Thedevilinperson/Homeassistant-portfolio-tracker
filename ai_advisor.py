"""
ai_advisor.py — OpenAI GPT-integratie voor belasting- en marktadvies.

Standaard model : gpt-4.1-mini  (instelbaar via ⚙️ Instellingen)
Alternatieven   : gpt-4.1 (hogere kwaliteit), gpt-4.1-nano (snelst/goedkoopst)

Twee hoofdfuncties:
  • generate_tax_optimization  → dagelijks belastingadvies (werkdagen 08:00)
  • generate_market_evaluation → 3× per dag marktevaluatie per beurs
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from openai import OpenAI, OpenAIError

import database as db
import belgian_tax as tax_mod
import market_data as md

logger = logging.getLogger(__name__)

MAX_TOKENS = 1500

AVAILABLE_MODELS = {
    "gpt-4.1-mini":  "GPT-4.1 Mini — aanbevolen (snel, kostenefficiënt, sterk)",
    "gpt-4.1":       "GPT-4.1 — hoogste kwaliteit, hogere kost",
    "gpt-4.1-nano":  "GPT-4.1 Nano — snelst en goedkoopst, minder diepgang",
    "gpt-4o-mini":   "GPT-4o Mini — alternatief (oudere generatie)",
    "gpt-4o":        "GPT-4o — alternatief flagship (oudere generatie)",
}


# ── Interne hulpfuncties ──────────────────────────────────────────────────────

def _get_client() -> tuple[OpenAI | None, str]:
    """Geeft (client, model) terug, of (None, '') als API-sleutel ontbreekt."""
    key   = db.get_setting("openai_api_key", "")
    model = db.get_setting("openai_model", "gpt-4.1-mini")
    if not key or not key.strip():
        return None, ""
    return OpenAI(api_key=key.strip()), model


def _build_portfolio_context(year: int | None = None) -> dict:
    """Samenvatting van de portefeuille voor de AI-prompt."""
    if year is None:
        year = datetime.now().year

    assets   = db.get_assets()
    tickers  = [a["ticker"] for a in assets]
    prices   = md.get_prices_for_tickers(tickers)
    overview = tax_mod.calculate_tax_overview(year=year, current_prices=prices)

    # Dividenden netto YTD per ticker
    div_net: dict[str, float] = {}
    for d in db.get_dividends(year=year):
        div_net[d["ticker"]] = div_net.get(d["ticker"], 0) + (
            d["gross_amount"] - d["withholding_tax"])

    posities = []
    for ticker, pv in overview["position_values"].items():
        asset = next((a for a in assets if a["ticker"] == ticker), {})
        posities.append({
            "ticker":             ticker,
            "naam":               asset.get("name", ticker),
            "type":               asset.get("asset_type", "stock"),
            "etf_subtype":        asset.get("etf_subtype", ""),
            "aantal":             round(pv["quantity"], 4),
            "gem_kostprijs":      round(pv["avg_cost"], 4),
            "huidig_prijs":       round(pv["current_price"], 4) if pv["current_price"] else None,
            "munt":               pv["current_price_currency"],
            "totaal_kost":        round(pv["total_cost"], 2),
            "huidig_waarde":      round(pv["current_value"], 2) if pv["current_value"] else None,
            "ongerealiseerd_wv":  round(pv["unrealized_gain_loss"], 2) if pv["unrealized_gain_loss"] else None,
            "ongerealiseerd_pct": round(pv["unrealized_gain_loss_pct"], 2) if pv["unrealized_gain_loss_pct"] else None,
            "netto_dividend_ytd": round(div_net.get(ticker, 0), 2),
        })

    belasting = {
        "jaar":                      year,
        "gerealiseerde_winst_verlies": round(overview["total_realized_gl"], 2),
        "jaarlijkse_vrijstelling":   overview["annual_exemption"],
        "resterend_vrijstelling":    round(overview["remaining_exemption"], 2),
        "belastbaar_bedrag":         round(overview["taxable_amount"], 2),
        "tarief":                    f"{overview['tax_rate']*100:.0f}%",
        "geschatte_belasting":       round(overview["tax_due"], 2),
        "ongerealiseerde_wv":        round(overview["unrealized_gl"], 2),
        "totale_portefeuillewaarde": round(overview["total_portfolio_value"], 2),
        "totale_kostbasis":          round(overview["total_cost_basis"], 2),
        "netto_dividenden_ytd":      round(overview["total_dividends_net"], 2),
    }

    return {"posities": posities, "belasting": belasting}


def _chat(client: OpenAI, model: str, system_msg: str, user_msg: str) -> str:
    """Wrapper rond de OpenAI Chat Completions API."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=MAX_TOKENS,
        temperature=0.4,   # licht creatief maar consistent
    )
    return response.choices[0].message.content or ""


# ── Publieke functies ──────────────────────────────────────────────────────────

def generate_tax_optimization(year: int | None = None) -> str:
    """
    Dagelijks belastingoptimalisatieadvies (Belgische meerwaardebelasting).
    Opgeslagen in de database na generatie.
    """
    client, model = _get_client()
    if not client:
        return (
            "❌ Geen OpenAI API-sleutel geconfigureerd.\n"
            "Ga naar ⚙️ Instellingen → API-sleutel om er één in te voeren."
        )

    if year is None:
        year = datetime.now().year

    ctx   = _build_portfolio_context(year)
    today = datetime.now().strftime("%d/%m/%Y")

    system = (
        "Je bent een erkend Belgisch belasting- en beleggingsadviseur, gespecialiseerd in "
        "de meerwaardebelasting voor particuliere beleggers (De Wever-hervorming). "
        "Je schrijft altijd in het Nederlands, bent concreet en verwijst naar specifieke posities. "
        "Je voegt altijd een korte wettelijke disclaimer toe."
    )

    user = f"""DATUM: {today}  |  BOEKJAAR: {year}  |  MODEL: {model}

PORTEFEUILLE (actuele data):
{json.dumps(ctx["posities"], indent=2, ensure_ascii=False)}

BELGISCHE BELASTINGSTATUS {year}:
{json.dumps(ctx["belasting"], indent=2, ensure_ascii=False)}

BELGISCHE FISCALE REGELS (samenvatting):
• 10% meerwaardebelasting op NETTO gerealiseerde meerwaarden boven €{ctx["belasting"]["jaarlijkse_vrijstelling"]:,.0f}/jaar
• Minwaarden verrekenen met meerwaarden binnen hetzelfde boekjaar (tax-loss harvesting)
• TOB: 0,35% aandelen (max €1.600) | 0,12% distr. ETF (max €1.300) | 1,32% kap. ETF (max €4.000)
• Roerende voorheffing 30% op dividenden — apart stelsel, reeds ingehouden

OPDRACHT:
Geef 4 concrete, actiegerichte aanbevelingen voor belastingoptimalisatie voor de rest van {year}:
1. Mogelijkheden voor tax-loss harvesting (posities met verlies)
2. Timing van geplande verkopen t.o.v. de vrijstellingsdrempel
3. Posities die dicht bij fiscaal interessante niveaus liggen
4. Dividend- of herbalanceringstrategie met fiscale impact

Gebruik vetgedrukte koppen per aanbeveling. Verwijs naar specifieke tickers en bedragen.
"""

    try:
        content = _chat(client, model, system, user)
        db.save_ai_evaluation(
            evaluation_type="tax_optimization",
            content=content,
            timing="daily",
            tickers=",".join(p["ticker"] for p in ctx["posities"]),
        )
        logger.info(f"Belastingadvies opgeslagen (model: {model})")
        return content
    except OpenAIError as exc:
        logger.error(f"generate_tax_optimization OpenAI-fout: {exc}")
        return f"❌ OpenAI-fout: {exc}"
    except Exception as exc:
        logger.error(f"generate_tax_optimization onverwachte fout: {exc}")
        return f"❌ Onverwachte fout: {exc}"


def generate_market_evaluation(timing: str, open_exchanges: list[str]) -> str:
    """
    Marktevaluatie op opening / midden / sluiting van de beursdag.
    Bevat BIJKOPEN / HOUDEN / VERKOPEN per positie.
    Opgeslagen in de database na generatie.

    timing         : 'open' | 'midday' | 'close'
    open_exchanges : bv. ['Euronext'] of ['NYSE', 'NASDAQ']
    """
    client, model = _get_client()
    if not client:
        return "❌ Geen OpenAI API-sleutel geconfigureerd."

    ctx = _build_portfolio_context()
    if not ctx["posities"]:
        return "ℹ️ Geen open posities in de portefeuille."

    timing_labels = {
        "open":   "OPENING VAN DE BEURS 🔔",
        "midday": "MIDDEN VAN DE BEURSDAG ☀️",
        "close":  "SLOTRING VAN DE BEURS 🔕",
    }
    label   = timing_labels.get(timing, timing.upper())
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    system = (
        "Je bent een professionele beursanalist die een Belgische particuliere belegger begeleidt. "
        "Je schrijft altijd in het Nederlands, bent bondig maar concreet, en gebruikt de werkelijke "
        "cijfers uit de portefeuilledata. Je geeft per positie een duidelijke aanbeveling."
    )

    user = f"""TIJDSTIP: {label} — {now_str} (Brussels Time)
OPEN BEURZEN: {", ".join(open_exchanges) if open_exchanges else "Geen"}
GEBRUIKT MODEL: {model}

HUIDIGE PORTEFEUILLE:
{json.dumps(ctx["posities"], indent=2, ensure_ascii=False)}

FISCALE CONTEXT (ter info):
• Gerealiseerde W/V dit jaar: €{ctx["belasting"]["gerealiseerde_winst_verlies"]:,.2f}
• Resterend vrijstelling: €{ctx["belasting"]["resterend_vrijstelling"]:,.2f}
• Geschatte belasting: €{ctx["belasting"]["geschatte_belasting"]:,.2f}

OPDRACHT — Geef een marktevaluatie in dit formaat:

**📊 Marktoverzicht**
(2-3 zinnen over de huidige marktcontext)

**📋 Posities**
Geef per ticker (naam + ticker):
- Situatie vandaag (koersbeweging, context)
- Aanbeveling: **📈 BIJKOPEN** / **⏸️ HOUDEN** / **📉 VERKOPEN**
- Reden (max 2 zinnen)
- Fiscale impact indien relevant (bijv. tax-loss harvesting mogelijk)

**🎯 Conclusie**
(1-2 zinnen over de totale portefeuille op dit moment)
"""

    try:
        content = _chat(client, model, system, user)
        db.save_ai_evaluation(
            evaluation_type="market_evaluation",
            content=content,
            timing=timing,
            tickers=",".join(p["ticker"] for p in ctx["posities"]),
        )
        logger.info(f"Marktevaluatie ({timing}) opgeslagen (model: {model})")
        return content
    except OpenAIError as exc:
        logger.error(f"generate_market_evaluation OpenAI-fout: {exc}")
        return f"❌ OpenAI-fout: {exc}"
    except Exception as exc:
        logger.error(f"generate_market_evaluation onverwachte fout: {exc}")
        return f"❌ Onverwachte fout: {exc}"
