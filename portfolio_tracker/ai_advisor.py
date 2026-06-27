"""
ai_advisor.py — OpenAI GPT-integratie: belasting-, markt- en beleggingsadvies.

Functies:
  • generate_tax_optimization   → belastingadvies (Belgische meerwaardebelasting)
  • generate_market_evaluation  → marktevaluatie per beursmoment
  • generate_portfolio_ratings  → gestructureerde ratings per ticker (JSON)
  • suggest_price_target        → AI-koersdoel voor één ticker (apart model)

De adviseur houdt rekening met de actuele portefeuille, macro-economische trends,
technologische ontwikkelingen, de Belgische fiscaliteit en een instelbaar
beleggingsprofiel PER REKENING.
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

MAX_TOKENS = 1800

# Richtprijzen per 1M tokens (USD, input/output) — stand medio 2026.
# Dit zijn schattingen voor kostenraming; de echte factuur staat op je
# OpenAI-dashboard. Pas indien nodig aan bij prijswijzigingen.
MODEL_PRICING = {
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o":       (2.50, 10.00),
    "gpt-4o-mini":  (0.15, 0.60),
}
_DEFAULT_PRICE = (0.40, 1.60)  # fallback ~ gpt-4.1-mini


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = MODEL_PRICING.get(model, _DEFAULT_PRICE)
    return (prompt_tokens / 1_000_000) * pin + (completion_tokens / 1_000_000) * pout

AVAILABLE_MODELS = {
    "gpt-4.1-mini":  "GPT-4.1 Mini — aanbevolen (snel, kostenefficiënt, sterk)",
    "gpt-4.1":       "GPT-4.1 — hoogste kwaliteit, hogere kost",
    "gpt-4.1-nano":  "GPT-4.1 Nano — snelst en goedkoopst, minder diepgang",
    "gpt-4o-mini":   "GPT-4o Mini — alternatief (oudere generatie)",
    "gpt-4o":        "GPT-4o — alternatief flagship (oudere generatie)",
}

# Beleggingsprofielen (per rekening instelbaar)
PROFILE_LABELS = {
    "aggressive":  "Agressief — hoog risico, focus op groei en kapitaalwinst",
    "neutral":     "Neutraal — gebalanceerd tussen risico en rendement",
    "speculative": "Speculatief korte termijn — actief handelen, hoog risico, snelle winst",
    "long_term":   "Lange termijn aanhouden — buy & hold, lage omloopsnelheid",
    "defensive":   "Defensief — kapitaalbehoud, dividend, laag risico",
}

# Ratings (gestructureerd advies)
RATING_ORDER  = ["strong_buy", "buy", "hold", "sell", "strong_sell"]
RATING_LABELS = {
    "strong_buy":  "Sterk kopen",
    "buy":         "Kopen",
    "hold":        "Behouden",
    "sell":        "Verkopen",
    "strong_sell": "Sterk verkopen",
}


# ── Interne hulpfuncties ──────────────────────────────────────────────────────

def _get_client(model_setting: str = "openai_model") -> tuple[OpenAI | None, str]:
    """Geeft (client, model) terug, of (None, '') als API-sleutel ontbreekt."""
    key   = db.get_setting("openai_api_key", "")
    model = db.get_setting(model_setting, "") or db.get_setting("openai_model", "gpt-4.1-mini")
    if not key or not key.strip():
        return None, ""
    return OpenAI(api_key=key.strip()), model


def _investment_volume() -> dict:
    return {
        "per_maand": float(db.get_setting("investment_volume_month", "0") or 0),
        "per_jaar":  float(db.get_setting("investment_volume_year", "0") or 0),
    }


def _build_portfolio_context(year: int | None = None) -> dict:
    """Rijke samenvatting van de portefeuille voor de AI-prompt."""
    if year is None:
        year = datetime.now().year

    assets   = db.get_assets()
    tickers  = [a["ticker"] for a in assets]
    prices   = md.get_prices_for_tickers(tickers)
    overview = tax_mod.calculate_tax_overview(year=year, current_prices=prices)
    asset_map = {a["ticker"]: a for a in assets}

    div_net: dict[str, float] = {}
    for d in db.get_dividends(year=year):
        div_net[d["ticker"]] = div_net.get(d["ticker"], 0) + (
            d["gross_amount"] - d["withholding_tax"])

    posities = []
    for ticker, pv in overview["position_values"].items():
        asset = asset_map.get(ticker, {})
        posities.append({
            "ticker":             ticker,
            "naam":               asset.get("name", ticker),
            "type":               asset.get("asset_type", "stock"),
            "etf_subtype":        asset.get("etf_subtype", ""),
            "munt":               pv["current_price_currency"],
            "aantal":             round(pv["quantity"], 4),
            "gem_kostprijs_eur":  round(pv["avg_cost"], 4),
            "huidige_koers":      round(pv["current_price"], 4) if pv["current_price"] else None,
            "huidige_waarde_eur": round(pv["current_value"], 2) if pv["current_value"] else None,
            "ongerealiseerd_pct": round(pv["unrealized_gain_loss_pct"], 2) if pv["unrealized_gain_loss_pct"] is not None else None,
            "netto_dividend_ytd": round(div_net.get(ticker, 0), 2),
        })

    # Per rekening: profiel + samenvatting
    by_acct = tax_mod.account_summary(db.get_transactions(), prices)
    profiles = db.get_account_profiles()
    per_account = []
    for acct, s in by_acct.items():
        prof = profiles.get(acct, "neutral")
        per_account.append({
            "rekening":         acct,
            "profiel":          prof,
            "profiel_omschrijving": PROFILE_LABELS.get(prof, prof),
            "kostenbasis_eur":  round(s["cost_basis"], 2),
            "huidige_waarde_eur": round(s["current_value"], 2),
            "rendement_pct":    round(s["gain_loss_pct"], 2),
            "aantal_posities":  s["n_positions"],
        })

    belasting = {
        "jaar":                       year,
        "gerealiseerde_winst_verlies": round(overview["total_realized_gl"], 2),
        "jaarlijkse_vrijstelling":    overview["annual_exemption"],
        "resterend_vrijstelling":     round(overview["remaining_exemption"], 2),
        "belastbaar_bedrag":          round(overview["taxable_amount"], 2),
        "tarief":                     f"{overview['tax_rate']*100:.0f}%",
        "geschatte_belasting":        round(overview["tax_due"], 2),
        "ongerealiseerde_wv":         round(overview["unrealized_gl"], 2),
        "totale_portefeuillewaarde":  round(overview["total_portfolio_value"], 2),
        "totale_kostbasis":           round(overview["total_cost_basis"], 2),
        "netto_dividenden_ytd":       round(overview["total_dividends_net"], 2),
        "transactiekosten_eur":       round(overview.get("total_costs", 0), 2),
        "rekeningkosten_eur":         round(overview.get("account_costs_total", 0), 2),
    }

    return {
        "posities":          posities,
        "per_rekening":      per_account,
        "belasting":         belasting,
        "investeringsvolume": _investment_volume(),
    }


# Gedeelde expert-rol voor alle adviezen
ADVISOR_PERSONA = (
    "Je bent een absolute topadviseur in beleggen én Belgische fiscaliteit, met de "
    "expertise van een private banker, een doorgewinterde portefeuillebeheerder en "
    "een fiscalist gespecialiseerd in de Belgische meerwaardebelasting (De Wever-"
    "hervorming, 10%). Je adviseert een PARTICULIERE belegger, geen instelling: "
    "je houdt rekening met realistische, beperkte instapbedragen, spreiding en kosten. "
    "Je weegt steeds drie dimensies af: (1) de actuele portefeuillepositie en het "
    "ingestelde beleggingsprofiel per rekening, (2) macro-economische trends "
    "(rente, inflatie, groei, sectorrotatie, valuta), en (3) technologische en "
    "structurele ontwikkelingen (AI, halfgeleiders, energietransitie, defensie, "
    "demografie) die de bestaande posities én nieuwe koopopportuniteiten beïnvloeden. "
    "Je past je toon en aanbevelingen aan het profiel van elke rekening aan "
    "(agressief, neutraal, speculatief, lange termijn, defensief). "
    "Je schrijft in helder Nederlands en bent concreet met tickers en bedragen. "
    "Belangrijk: je kennis heeft een trainingsgrens en je hebt GEEN live nieuws; "
    "wees transparant over onzekerheid en vermeld een korte disclaimer dat dit geen "
    "gepersonaliseerd financieel advies is."
)


def _chat(client: OpenAI, model: str, system_msg: str, user_msg: str,
          max_tokens: int = MAX_TOKENS, temperature: float = 0.4,
          track_as: str = "chat") -> str:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user",   "content": user_msg},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )
    # Tokengebruik + kost registreren (best effort — nooit de call laten falen)
    try:
        usage = getattr(response, "usage", None)
        pt = getattr(usage, "prompt_tokens", 0) or 0
        ct = getattr(usage, "completion_tokens", 0) or 0
        cost = estimate_cost_usd(model, pt, ct)
        db.record_ai_usage(track_as, model, pt, ct, cost)
    except Exception as exc:
        logger.warning(f"AI-gebruik registreren mislukt: {exc}")
    return response.choices[0].message.content or ""


def _parse_json(text: str):
    """Robuust JSON parsen, ook als het model markdown-fences toevoegt."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t.lower().startswith("json"):
            t = t[4:]
    # Zoek het eerste { ... } of [ ... ] blok
    for open_c, close_c in (("{", "}"), ("[", "]")):
        i, j = t.find(open_c), t.rfind(close_c)
        if i != -1 and j != -1 and j > i:
            try:
                return json.loads(t[i:j+1])
            except Exception:
                continue
    return json.loads(t)  # laatste poging (werpt bij mislukking)


def _profiel_blok(ctx: dict) -> str:
    iv = ctx["investeringsvolume"]
    return f"""PROFIEL PARTICULIERE BELEGGER:
• Geschat investeringsvolume: €{iv['per_maand']:,.0f}/maand, €{iv['per_jaar']:,.0f}/jaar
• Beleggingsprofiel per rekening:
{json.dumps(ctx['per_rekening'], indent=2, ensure_ascii=False)}"""


# ── Belastingadvies ────────────────────────────────────────────────────────────

def generate_tax_optimization(year: int | None = None) -> str:
    client, model = _get_client()
    if not client:
        return ("❌ Geen OpenAI API-sleutel geconfigureerd.\n"
                "Ga naar ⚙️ Instellingen → API-sleutel om er één in te voeren.")
    if year is None:
        year = datetime.now().year

    ctx   = _build_portfolio_context(year)
    today = datetime.now().strftime("%d/%m/%Y")

    user = f"""DATUM: {today}  |  BOEKJAAR: {year}  |  MODEL: {model}

PORTEFEUILLE (actuele data):
{json.dumps(ctx["posities"], indent=2, ensure_ascii=False)}

{_profiel_blok(ctx)}

BELGISCHE BELASTINGSTATUS {year}:
{json.dumps(ctx["belasting"], indent=2, ensure_ascii=False)}

BELGISCHE FISCALE REGELS (samenvatting):
• 10% meerwaardebelasting op NETTO gerealiseerde meerwaarden boven €{ctx["belasting"]["jaarlijkse_vrijstelling"]:,.0f}/jaar
• Minwaarden verrekenen met meerwaarden binnen hetzelfde boekjaar (tax-loss harvesting)
• TOB: 0,35% aandelen (max €1.600) | 0,12% distr. ETF (max €1.300) | 1,32% kap. ETF (max €4.000)
• Roerende voorheffing 30% op dividenden — apart stelsel

OPDRACHT:
Geef 4 concrete, actiegerichte aanbevelingen voor belastingoptimalisatie voor de rest van {year}:
1. Tax-loss harvesting (posities met verlies)
2. Timing van geplande verkopen t.o.v. de vrijstellingsdrempel
3. Posities dicht bij fiscaal interessante niveaus
4. Dividend- of herbalanceringstrategie met fiscale impact
Houd rekening met het profiel per rekening. Gebruik vetgedrukte koppen en verwijs naar tickers en bedragen.
"""
    try:
        content = _chat(client, model, ADVISOR_PERSONA, user, track_as="tax_optimization")
        db.save_ai_evaluation("tax_optimization", content, timing="daily",
                              tickers=",".join(p["ticker"] for p in ctx["posities"]))
        return content
    except OpenAIError as exc:
        logger.error(f"generate_tax_optimization: {exc}")
        return f"❌ OpenAI-fout: {exc}"
    except Exception as exc:
        logger.error(f"generate_tax_optimization: {exc}")
        return f"❌ Onverwachte fout: {exc}"


# ── Marktevaluatie ─────────────────────────────────────────────────────────────

def generate_market_evaluation(timing: str, open_exchanges: list[str]) -> str:
    client, model = _get_client()
    if not client:
        return "❌ Geen OpenAI API-sleutel geconfigureerd."

    ctx = _build_portfolio_context()
    if not ctx["posities"]:
        return "ℹ️ Geen open posities in de portefeuille."

    timing_labels = {"open": "OPENING VAN DE BEURS 🔔",
                     "midday": "MIDDEN VAN DE BEURSDAG ☀️",
                     "close": "SLOTRING VAN DE BEURS 🔕"}
    label   = timing_labels.get(timing, timing.upper())
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")

    user = f"""TIJDSTIP: {label} — {now_str} (Brussels Time)
OPEN BEURZEN: {", ".join(open_exchanges) if open_exchanges else "Geen"}
GEBRUIKT MODEL: {model}

HUIDIGE PORTEFEUILLE:
{json.dumps(ctx["posities"], indent=2, ensure_ascii=False)}

{_profiel_blok(ctx)}

FISCALE CONTEXT:
• Gerealiseerde W/V dit jaar: €{ctx["belasting"]["gerealiseerde_winst_verlies"]:,.2f}
• Resterend vrijstelling: €{ctx["belasting"]["resterend_vrijstelling"]:,.2f}

OPDRACHT — Geef een marktevaluatie in dit formaat:

**📊 Marktoverzicht** (2-3 zinnen: macro + relevante tech/sector-context)

**📋 Posities** — per ticker (naam + ticker):
- Situatie en relevante macro-/technologische factor
- Aanbeveling afgestemd op het profiel van de rekening: **📈 BIJKOPEN** / **⏸️ HOUDEN** / **📉 VERKOPEN**
- Reden (max 2 zinnen) + fiscale impact indien relevant

**🎯 Koopopportuniteiten** (1-3 ideeën buiten de huidige portefeuille, passend bij profiel en investeringsvolume)

**📌 Conclusie** (1-2 zinnen)
"""
    try:
        content = _chat(client, model, ADVISOR_PERSONA, user, track_as="market_evaluation")
        db.save_ai_evaluation("market_evaluation", content, timing=timing,
                              tickers=",".join(p["ticker"] for p in ctx["posities"]))
        return content
    except OpenAIError as exc:
        logger.error(f"generate_market_evaluation: {exc}")
        return f"❌ OpenAI-fout: {exc}"
    except Exception as exc:
        logger.error(f"generate_market_evaluation: {exc}")
        return f"❌ Onverwachte fout: {exc}"


# ── Gestructureerde ratings (synthese-pagina) ─────────────────────────────────

def generate_portfolio_ratings() -> dict:
    """
    Genereer per ticker een rating (strong_buy..strong_sell) + koersdoel,
    rekening houdend met profiel per rekening en investeringsvolume.
    Slaat elke rating op in ai_ratings onder één batch-id. Returnt een dict.
    """
    client, model = _get_client()
    if not client:
        return {"error": "Geen OpenAI API-sleutel geconfigureerd."}

    ctx = _build_portfolio_context()
    if not ctx["posities"]:
        return {"error": "Geen open posities om te beoordelen."}

    today = datetime.now().strftime("%d/%m/%Y")
    valid = ", ".join(RATING_ORDER)
    user = f"""DATUM: {today}  |  MODEL: {model}

PORTEFEUILLE:
{json.dumps(ctx["posities"], indent=2, ensure_ascii=False)}

{_profiel_blok(ctx)}

OPDRACHT:
Geef voor ELKE ticker in de portefeuille een rating, rekening houdend met:
de huidige positie en het profiel van de rekening(en), macro-economische trends,
en technologische/sectorale ontwikkelingen. Bepaal ook een koersdoel op 12 maanden
in de native munt van het aandeel.

Antwoord UITSLUITEND met geldige JSON in exact dit formaat (geen markdown):
{{
  "samenvatting": "max 2 zinnen over de hele portefeuille",
  "ratings": [
    {{"ticker": "AAPL", "rating": "<één van: {valid}>", "price_target": 250.0,
      "currency": "USD", "rationale": "max 1-2 zinnen, profiel-bewust"}}
  ]
}}
"""
    try:
        raw = _chat(client, model, ADVISOR_PERSONA, user, temperature=0.3, track_as="portfolio_ratings")
        data = _parse_json(raw)
        ratings = data.get("ratings", []) if isinstance(data, dict) else data
        batch_id = datetime.now().strftime("%Y%m%d%H%M%S")
        valid_tickers = {p["ticker"] for p in ctx["posities"]}
        stored = 0
        for r in ratings:
            tk = str(r.get("ticker", "")).upper()
            rating = str(r.get("rating", "")).lower().replace(" ", "_")
            if tk not in valid_tickers or rating not in RATING_LABELS:
                continue
            db.save_ai_rating(
                batch_id, tk, rating,
                price_target=r.get("price_target"),
                currency=r.get("currency", "EUR"),
                rationale=r.get("rationale", ""),
                model=model,
            )
            stored += 1
        db.save_ai_evaluation("portfolio_ratings",
                              data.get("samenvatting", "") if isinstance(data, dict) else "",
                              timing="ratings",
                              tickers=",".join(valid_tickers))
        return {"batch_id": batch_id, "stored": stored,
                "samenvatting": data.get("samenvatting", "") if isinstance(data, dict) else ""}
    except OpenAIError as exc:
        logger.error(f"generate_portfolio_ratings: {exc}")
        return {"error": f"OpenAI-fout: {exc}"}
    except Exception as exc:
        logger.error(f"generate_portfolio_ratings: {exc}")
        return {"error": f"Kon AI-antwoord niet verwerken: {exc}"}


# ── AI-koersdoel voor één ticker (apart model) ────────────────────────────────

def suggest_price_target(ticker: str, account: str | None = None) -> dict:
    """
    Bepaal een koersdoel op 12 maanden voor één ticker.
    Gebruikt het apart instelbare model 'openai_price_target_model'
    (valt terug op het reguliere model).
    """
    client, model = _get_client("openai_price_target_model")
    if not client:
        return {"error": "Geen OpenAI API-sleutel geconfigureerd."}

    asset = db.get_asset(ticker) or {}
    price, currency = md.get_current_price(ticker)
    profile = db.get_account_profile(account) if account else "neutral"

    user = f"""TICKER: {ticker} ({asset.get('name', ticker)})
TYPE: {asset.get('asset_type', 'stock')} | MUNT: {currency or asset.get('currency', 'EUR')}
HUIDIGE KOERS: {price if price else 'onbekend'} {currency or ''}
BELEGGINGSPROFIEL REKENING: {PROFILE_LABELS.get(profile, profile)}

OPDRACHT:
Bepaal een realistisch koersdoel op 12 maanden voor dit aandeel/ETF, rekening
houdend met macro-economische trends, sector- en technologische ontwikkelingen,
en het beleggingsprofiel. Antwoord UITSLUITEND met geldige JSON (geen markdown):
{{"price_target": <getal in native munt>, "currency": "{currency or 'EUR'}",
  "rationale": "max 2 zinnen onderbouwing", "scenario": "korte bull/bear-nuance"}}
"""
    system = ADVISOR_PERSONA + (
        " Voor koersdoelen ben je nuchter en onderbouwd; je geeft een puntschatting "
        "maar erkent de onzekerheid.")
    try:
        raw = _chat(client, model, system, user, max_tokens=600, temperature=0.3, track_as="price_target")
        data = _parse_json(raw)
        target = data.get("price_target")
        if target is None:
            return {"error": "Geen koersdoel ontvangen."}
        return {
            "price_target": float(target),
            "currency":     data.get("currency", currency or "EUR"),
            "rationale":    data.get("rationale", ""),
            "scenario":     data.get("scenario", ""),
            "model":        model,
            "current_price": price,
        }
    except OpenAIError as exc:
        logger.error(f"suggest_price_target: {exc}")
        return {"error": f"OpenAI-fout: {exc}"}
    except Exception as exc:
        logger.error(f"suggest_price_target: {exc}")
        return {"error": f"Kon koersdoel niet bepalen: {exc}"}


# ── Synthese-helper voor de portefeuillepagina ────────────────────────────────

def rating_synthesis(tickers: list[str], n_batches: int = 9) -> dict:
    """
    Vat de laatste n AI-advies-rondes samen per ticker.
    Returnt {ticker: {counts:{rating:n}, consensus:rating, latest:rating,
                      latest_target:float, currency:str, n:int}}.
    """
    batches = db.get_recent_rating_batches(n_batches)
    out: dict[str, dict] = {}
    if not batches:
        return out
    ratings = db.get_ai_ratings(batch_ids=batches)
    for tk in tickers:
        rows = [r for r in ratings if r["ticker"] == tk]
        if not rows:
            continue
        counts = {k: 0 for k in RATING_ORDER}
        for r in rows:
            if r["rating"] in counts:
                counts[r["rating"]] += 1
        # consensus = meest voorkomende; bij gelijkspel de "sterkste" richting
        consensus = max(RATING_ORDER, key=lambda k: (counts[k], -RATING_ORDER.index(k)))
        latest = rows[0]  # gesorteerd op created_at DESC
        out[tk] = {
            "counts":        counts,
            "consensus":     consensus,
            "latest":        latest["rating"],
            "latest_target": latest.get("price_target"),
            "currency":      latest.get("currency", "EUR"),
            "n":             len(rows),
        }
    return out