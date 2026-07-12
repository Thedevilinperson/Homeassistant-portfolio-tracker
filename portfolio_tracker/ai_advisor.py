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
DEFAULT_MODEL_PRICING = {
    "gpt-4.1":      (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o":       (2.50, 10.00),
    "gpt-4o-mini":  (0.15, 0.60),
}
_DEFAULT_PRICE = (0.40, 1.60)  # fallback ~ gpt-4.1-mini


def get_model_pricing() -> dict:
    """Actuele modelprijzen (USD per 1M tokens) = standaard, overschreven door wat
    in de instellingen ('ai_model_pricing', JSON) staat — bv. door de maandelijkse
    prijsverversing of handmatig."""
    pricing = {k: tuple(v) for k, v in DEFAULT_MODEL_PRICING.items()}
    try:
        raw = db.get_setting("ai_model_pricing", "")
        if raw:
            for model, pair in json.loads(raw).items():
                if isinstance(pair, (list, tuple)) and len(pair) == 2:
                    pin, pout = float(pair[0]), float(pair[1])
                    if 0 < pin < 1000 and 0 < pout < 1000:
                        pricing[model] = (pin, pout)
    except Exception as e:
        logger.warning(f"get_model_pricing: kon overrides niet lezen ({e})")
    return pricing


# Backwards-compat: sommige modules importeren MODEL_PRICING rechtstreeks.
MODEL_PRICING = DEFAULT_MODEL_PRICING


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    pin, pout = get_model_pricing().get(model, _DEFAULT_PRICE)
    return (prompt_tokens / 1_000_000) * pin + (completion_tokens / 1_000_000) * pout


def refresh_model_prices() -> dict:
    """Vraag de AI naar de actuele prijzen (USD/1M tokens) van de gekende modellen
    en bewaar geldige waarden in de instellingen. Conservatief: enkel gekende
    modellen, plausibele bedragen (0–1000), ongeldige antwoorden worden genegeerd.

    Retourneert {updated: [...], unchanged: [...], error: str|None}.
    """
    client, model = _get_client()
    if not client:
        return {"error": "Geen OpenAI-sleutel ingesteld.", "updated": [], "unchanged": []}
    models = list(DEFAULT_MODEL_PRICING.keys())
    system = ("Je bent een nauwkeurige assistent. Antwoord UITSLUITEND met geldige JSON, "
              "zonder uitleg of opmaak.")
    user = ("Geef de actuele officiële OpenAI API-prijzen in USD per 1 miljoen tokens voor "
            "elk van deze modellen. Formaat: een JSON-object {model: {\"input\": getal, "
            "\"output\": getal}}. Enkel deze modellen: " + ", ".join(models) + ". "
            "Als je een prijs niet zeker weet, laat dat model dan weg.")
    try:
        raw = _chat(client, model, system, user, max_tokens=400, temperature=0.0,
                    track_as="price_refresh")
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
    except Exception as e:
        logger.warning(f"refresh_model_prices: AI-antwoord onbruikbaar ({e})")
        return {"error": f"AI-antwoord onbruikbaar: {e}", "updated": [], "unchanged": []}

    current = get_model_pricing()
    new_pricing = {k: list(v) for k, v in current.items()}
    updated, unchanged = [], []
    for m in models:
        entry = data.get(m) if isinstance(data, dict) else None
        if not isinstance(entry, dict):
            unchanged.append(m); continue
        try:
            pin = float(entry.get("input")); pout = float(entry.get("output"))
        except (TypeError, ValueError):
            unchanged.append(m); continue
        if not (0 < pin < 1000 and 0 < pout < 1000):
            unchanged.append(m); continue
        old = current.get(m)
        if old and abs(old[0] - pin) < 1e-9 and abs(old[1] - pout) < 1e-9:
            unchanged.append(m)
        else:
            new_pricing[m] = [pin, pout]; updated.append(m)

    db.set_setting("ai_model_pricing", json.dumps(new_pricing))
    db.set_setting("ai_pricing_last_refresh", datetime.now().strftime("%Y-%m-%d %H:%M"))
    logger.info(f"AI-prijsverversing: {len(updated)} bijgewerkt, {len(unchanged)} ongewijzigd")
    return {"error": None, "updated": updated, "unchanged": unchanged}

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

# Numerieke schaal om ADVIEZEN TE MIDDELEN over een periode (7 d / 1 m / 3 m).
# Een gemiddelde van bv. 'sterk kopen' + 'kopen' + 'behouden' = 1.0 -> 'Kopen'.
RATING_SCORE = {"strong_buy": 2.0, "buy": 1.0, "hold": 0.0, "sell": -1.0, "strong_sell": -2.0}


def score_to_rating(score: float) -> str:
    """Gemiddelde score terug naar het dichtstbijzijnde ratinglabel."""
    if score >= 1.5:
        return "strong_buy"
    if score >= 0.5:
        return "buy"
    if score >= -0.5:
        return "hold"
    if score >= -1.5:
        return "sell"
    return "strong_sell"


# ── Luik 2: marktopportuniteiten (buiten de eigen portefeuille) ───────────────
# Drie risicoklassen, elk 2 ideeën per dag.
MARKET_BUCKETS = ["defensive", "moderate", "speculative"]
BUCKET_LABELS = {
    "defensive":   "🛡️ Defensief — groei + eventueel dividendrendement",
    "moderate":    "⚖️ Matig speculatief",
    "speculative": "🚀 Sterk speculatief",
}
BUCKET_SHORT = {"defensive": "Defensief", "moderate": "Matig spec.",
                "speculative": "Sterk spec."}
# Aliassen: het model mag Nederlandse of Engelse labels teruggeven.
_BUCKET_ALIASES = {
    "defensive": "defensive", "defensief": "defensive", "defensive_growth": "defensive",
    "moderate": "moderate", "matig": "moderate", "matig_speculatief": "moderate",
    "moderately_speculative": "moderate", "gematigd": "moderate",
    "speculative": "speculative", "speculatief": "speculative",
    "sterk_speculatief": "speculative", "highly_speculative": "speculative",
    "high_risk": "speculative",
}
IDEAS_PER_BUCKET = 2


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


def market_websearch_enabled() -> bool:
    """Mag het marktadvies live het web doorzoeken? Standaard AAN: zonder live
    zoekopdracht kan de AI enkel uit haar trainingskennis putten en is 'recente
    financiële berichtgeving' per definitie verouderd."""
    return db.get_setting("ai_market_websearch", "1") != "0"


def _chat_websearch(client: OpenAI, model: str, system_msg: str, user_msg: str,
                    max_tokens: int = MAX_TOKENS, track_as: str = "market_ideas") -> tuple[str, bool]:
    """Zoals _chat, maar via de Responses-API MET de ingebouwde websearch-tool van
    OpenAI: het model haalt zelf actuele koersen, resultaten en berichtgeving op.
    Geeft (tekst, websearch_gebruikt) terug.

    Valt stil terug op het gewone chat-endpoint als websearch uitstaat, als het
    gekozen model de tool niet ondersteunt of als de call om welke reden ook faalt —
    het advies komt er dan nog steeds, enkel op basis van trainingskennis. Dat wordt
    gelogd én in de app getoond, zodat je nooit denkt dat iets 'live' is terwijl het
    dat niet is."""
    if market_websearch_enabled():
        try:
            resp = client.responses.create(
                model=model,
                tools=[{"type": "web_search_preview"}],
                instructions=system_msg,
                input=user_msg,
                max_output_tokens=max_tokens,
            )
            text = getattr(resp, "output_text", "") or ""
            try:
                usage = getattr(resp, "usage", None)
                pt = getattr(usage, "input_tokens", 0) or 0
                ct = getattr(usage, "output_tokens", 0) or 0
                db.record_ai_usage(track_as, model, pt, ct, estimate_cost_usd(model, pt, ct))
            except Exception as exc:
                logger.warning(f"AI-gebruik registreren mislukt: {exc}")
            if text.strip():
                return text, True
            logger.warning("_chat_websearch: leeg antwoord met websearch — terugval op gewone chat")
        except Exception as exc:
            logger.warning(f"_chat_websearch: websearch niet beschikbaar ({exc}) — "
                           "terugval op gewone chat (enkel trainingskennis)")
    return _chat(client, model, system_msg, user_msg, max_tokens=max_tokens,
                 temperature=0.5, track_as=track_as), False


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
    iv = ctx.get("investeringsvolume")
    vol = (f"• Geschat investeringsvolume: €{iv['per_maand']:,.0f}/maand, €{iv['per_jaar']:,.0f}/jaar\n"
           if iv else "")
    return ("PROFIEL PARTICULIERE BELEGGER:\n" + vol +
            "• Beleggingsprofiel per rekening:\n" +
            json.dumps(ctx.get("per_rekening", []), indent=2, ensure_ascii=False))


# ── Privacy ────────────────────────────────────────────────────────────────────

def privacy_level() -> str:
    """'off' (alles), 'amounts' (bedragen verbergen, tickers blijven) of
    'full' (ook tickers/namen anonimiseren)."""
    lvl = db.get_setting("ai_privacy_mode", "off")
    return lvl if lvl in ("off", "amounts", "full") else "off"


def ai_function_enabled(fn: str) -> bool:
    """Is een AI-functie ingeschakeld? fn in {'tax','daily','market'}."""
    return db.get_setting(f"ai_enable_{fn}", "1") != "0"


def _anonymize_context(ctx: dict, level: str):
    """Pas privacy toe op de context. Retourneert (nieuwe_ctx, alias_map).
    'amounts': eurobedragen -> gewichten in %, tickers blijven.
    'full': bovendien tickers/namen vervangen door POS1, POS2, ... (alias_map mapt terug)."""
    if level == "off":
        return ctx, {}
    ctx = json.loads(json.dumps(ctx))  # diepe kopie
    posities = ctx.get("posities", [])
    total = sum((p.get("huidige_waarde_eur") or 0) for p in posities) or 1.0
    alias_map = {}
    for i, p in enumerate(posities, 1):
        p["gewicht_pct"] = round((p.get("huidige_waarde_eur") or 0) / total * 100, 1)
        for k in ("gem_kostprijs_eur", "huidige_waarde_eur", "netto_dividend_ytd"):
            p.pop(k, None)
        if level == "full":
            alias = f"POS{i}"
            alias_map[alias] = p["ticker"]
            p["ticker"] = alias
            p["naam"] = f"Positie {i}"
            p.pop("huidige_koers", None)
    for a in ctx.get("per_rekening", []):
        for k in ("kostenbasis_eur", "huidige_waarde_eur"):
            a.pop(k, None)
    bel = ctx.get("belasting", {})
    for k in ("totale_portefeuillewaarde", "totale_kostbasis", "netto_dividenden_ytd",
              "transactiekosten_eur", "rekeningkosten_eur", "ongerealiseerde_wv"):
        bel.pop(k, None)
    ctx.pop("investeringsvolume", None)
    return ctx, alias_map


def _privacy_note(level: str) -> str:
    if level == "amounts":
        return ("\nPRIVACY: eurobedragen zijn weggelaten; posities zijn aangeduid met een gewicht in % "
                "van de portefeuille. Redeneer op basis van gewichten en percentages.")
    if level == "full":
        return ("\nPRIVACY: eurobedragen zijn weggelaten en posities zijn geanonimiseerd "
                "(POS1, POS2, ...). Gebruik in je antwoord EXACT diezelfde labels (POS1, ...), "
                "niet de echte namen, en redeneer op basis van type/profiel/gewicht.")
    return ""


# ── Belastingadvies ────────────────────────────────────────────────────────────

def generate_tax_optimization(year: int | None = None) -> str:
    if not ai_function_enabled("tax"):
        return "ℹ️ Het maandelijkse belastingadvies staat uit. Schakel het in via ⚙️ Instellingen → AI."
    client, model = _get_client()
    if not client:
        return ("❌ Geen OpenAI API-sleutel geconfigureerd.\n"
                "Ga naar ⚙️ Instellingen → API-sleutel om er één in te voeren.")
    if year is None:
        year = datetime.now().year

    ctx   = _build_portfolio_context(year)
    level = privacy_level()
    actx, _ = _anonymize_context(ctx, level)
    today = datetime.now().strftime("%d/%m/%Y")

    user = f"""DATUM: {today}  |  BOEKJAAR: {year}  |  MODEL: {model}{_privacy_note(level)}

PORTEFEUILLE (actuele data):
{json.dumps(actx["posities"], indent=2, ensure_ascii=False)}

{_profiel_blok(actx)}

BELGISCHE BELASTINGSTATUS {year}:
{json.dumps(actx["belasting"], indent=2, ensure_ascii=False)}

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
        db.save_ai_evaluation("tax_optimization", content, timing="monthly",
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
        base_map = {}  # basis-symbool (vóór de punt) -> volledige ticker
        for vt in valid_tickers:
            base_map.setdefault(vt.split(".")[0], vt)

        def _match(returned: str):
            r = (returned or "").upper()
            if r in valid_tickers:
                return r
            cand = base_map.get(r.split(".")[0])   # bv. AI gaf 'VWCE' i.p.v. 'VWCE.DE'
            return cand

        stored = 0
        for r in ratings:
            tk = _match(str(r.get("ticker", "")))
            rating = str(r.get("rating", "")).lower().replace(" ", "_")
            if not tk or rating not in RATING_LABELS:
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


# ── Dagelijks portefeuilleadvies (ratings + tekst in één) ─────────────────────

def generate_daily_portfolio_advice() -> dict:
    """LUIK 1 van het dagelijkse advies: uitsluitend de BESTAANDE portefeuille.
    Produceert zowel een tekstadvies als per-ticker ratings
    ((sterk) kopen / behouden / (sterk) verkopen). De ratings voeden de
    synthese-tabellen op de portefeuille- en dashboardpagina; de tekst vult het
    tekstgedeelte daar. Privacy-bewust.

    Nieuwe koopopportuniteiten BUITEN de portefeuille horen hier bewust NIET thuis:
    die zitten in luik 2 (generate_market_opportunities), zodat beide luiken los van
    elkaar leesbaar en opvolgbaar zijn."""
    if not ai_function_enabled("daily"):
        return {"error": "Het dagelijkse portefeuilleadvies staat uit. Schakel het in via ⚙️ Instellingen → AI."}
    client, model = _get_client()
    if not client:
        return {"error": "Geen OpenAI API-sleutel geconfigureerd."}

    ctx = _build_portfolio_context()
    if not ctx["posities"]:
        return {"error": "Geen open posities om te beoordelen."}

    level = privacy_level()
    actx, alias_map = _anonymize_context(ctx, level)
    today = datetime.now().strftime("%d/%m/%Y")
    valid = ", ".join(RATING_ORDER)

    user = f"""DATUM: {today}  |  MODEL: {model}{_privacy_note(level)}

PORTEFEUILLE:
{json.dumps(actx["posities"], indent=2, ensure_ascii=False)}

{_profiel_blok(actx)}

OPDRACHT (LUIK 1 — UITSLUITEND DE BESTAANDE PORTEFEUILLE):
Geef één dagelijks advies over de posities die de belegger NU aanhoudt: (sterk) kopen /
behouden / (sterk) verkopen. Stel hier GEEN nieuwe aandelen voor die niet in de
portefeuille zitten — die koopopportuniteiten komen in een apart luik (luik 2) aan bod.
Focus dus volledig op bijkopen, behouden, afbouwen of verkopen van wat er al is.

Antwoord UITSLUITEND met geldige JSON (geen markdown errond), in exact dit formaat:
{{
  "advies_tekst": "Markdown met de koppen: **📊 Marktoverzicht** (2-3 zinnen macro + tech/sector, voor zover relevant voor DEZE posities), **📋 Posities** (per positie: korte situatie + duidelijke aanbeveling BIJKOPEN/HOUDEN/AFBOUWEN/VERKOPEN + reden), **📌 Conclusie** (1-2 zinnen: waar zit het grootste risico en de grootste kans binnen de huidige portefeuille). Sluit af met een korte disclaimer dat dit geen gepersonaliseerd financieel advies is.",
  "ratings": [
    {{"ticker": "<exact het label uit de portefeuille hierboven>", "rating": "<één van: {valid}>", "price_target": 0.0, "currency": "EUR", "rationale": "max 1-2 zinnen, profiel-bewust"}}
  ]
}}
Geef voor ELKE positie een rating.
"""
    try:
        raw = _chat(client, model, ADVISOR_PERSONA, user, max_tokens=2200,
                    temperature=0.3, track_as="daily_advice")
        data = _parse_json(raw)
        if not isinstance(data, dict):
            return {"error": "AI-antwoord niet bruikbaar."}
        text    = data.get("advies_tekst", "") or ""
        ratings = data.get("ratings", []) or []

        # De-anonimiseren bij volledige privacy: aliassen -> echte tickers (in ratings én tekst)
        if level == "full" and alias_map:
            for r in ratings:
                a = str(r.get("ticker", "")).upper()
                if a in alias_map:
                    r["ticker"] = alias_map[a]
            for alias, real in alias_map.items():
                text = text.replace(alias, real)

        batch_id = datetime.now().strftime("%Y%m%d%H%M%S")
        valid_tickers = {p["ticker"] for p in ctx["posities"]}
        base_map = {}
        for vt in valid_tickers:
            base_map.setdefault(vt.split(".")[0], vt)

        def _match(returned: str):
            r = (returned or "").upper()
            if r in valid_tickers:
                return r
            return base_map.get(r.split(".")[0])

        stored = 0
        for r in ratings:
            tk = _match(str(r.get("ticker", "")))
            rating = str(r.get("rating", "")).lower().replace(" ", "_")
            if not tk or rating not in RATING_LABELS:
                continue
            db.save_ai_rating(batch_id, tk, rating, price_target=r.get("price_target"),
                              currency=r.get("currency", "EUR"),
                              rationale=r.get("rationale", ""), model=model)
            stored += 1
        db.save_ai_evaluation("daily_advice", text, timing="daily",
                              tickers=",".join(valid_tickers))
        return {"batch_id": batch_id, "stored": stored, "advies_tekst": text}
    except OpenAIError as exc:
        logger.error(f"generate_daily_portfolio_advice: {exc}")
        return {"error": f"OpenAI-fout: {exc}"}
    except Exception as exc:
        logger.error(f"generate_daily_portfolio_advice: {exc}")
        return {"error": f"Kon AI-antwoord niet verwerken: {exc}"}


# ── LUIK 2: marktopportuniteiten buiten de portefeuille ───────────────────────

MARKET_PERSONA = (
    "Je bent een topanalist bij een beursresearch-desk die dagelijks de WERELDWIJDE "
    "markt afspeurt naar concrete koopopportuniteiten voor een particuliere Belgische "
    "belegger. Je kijkt uitdrukkelijk BUITEN de bestaande portefeuille: je zoekt nieuwe "
    "namen. Je weegt af: bedrijfsprestaties (omzet- en margegroei, vrije kasstroom, "
    "balans, waardering), vooruitzichten en guidance, macro-economie (rente, inflatie, "
    "groei, sectorrotatie, valuta), geopolitiek (handelsconflicten, defensie, energie, "
    "grondstoffen, regelgeving) en recente financiële berichtgeving. "
    "Je bent kritisch en concreet, geen hype: elk idee krijgt een onderbouwing, "
    "katalysatoren én de belangrijkste risico's. Je noemt altijd het exacte "
    "Yahoo-Finance-ticker MET beurssuffix (bv. ASML.AS, AIR.PA, MC.PA, NVDA, SHELL.AS), "
    "want dat wordt gebruikt om de koers automatisch op te volgen. "
    "Je schrijft in helder Nederlands en vermeldt dat dit geen gepersonaliseerd "
    "financieel advies is."
)


def generate_market_opportunities() -> dict:
    """LUIK 2 van het dagelijkse advies: zoekt koopopportuniteiten in de WERELDWIJDE
    markt, los van de bestaande portefeuille. Levert per dag 6 ideeën:
    2 defensief (groei + eventueel dividend), 2 matig speculatief en 2 sterk
    speculatief — elk met onderbouwing, katalysatoren en risico's.

    Elk idee krijgt ook een rating op dezelfde schaal als luik 1, zodat de adviezen
    over 7 dagen / 1 maand / 3 maanden gemiddeld kunnen worden (zie
    market_idea_synthesis). De koers op het moment van het advies wordt mee
    opgeslagen, zodat het rendement sinds advies opvolgbaar is.

    Gebruikt indien mogelijk de websearch-tool van OpenAI (actuele berichtgeving);
    valt anders terug op trainingskennis (wordt gemeld in het resultaat)."""
    if not ai_function_enabled("market"):
        return {"error": "Het dagelijkse marktadvies (luik 2) staat uit. "
                         "Schakel het in via ⚙️ Instellingen → AI."}
    client, model = _get_client()
    if not client:
        return {"error": "Geen OpenAI API-sleutel geconfigureerd."}

    level = privacy_level()
    ctx = _build_portfolio_context()

    # Wat de belegger al heeft (om dubbels te vermijden). Bij volledige anonimisering
    # geven we geen namen mee; het model krijgt dan enkel types/sectorgewichten.
    if level == "full":
        held_txt = ("(niet meegedeeld wegens privacymodus — vermijd dubbels kan niet "
                    "gecontroleerd worden)")
    else:
        held_txt = ", ".join(f"{p['ticker']} ({p['naam']})" for p in ctx["posities"]) or "geen"

    cash = 0.0
    try:
        cash = db.compute_cash_positions()["totals"]["available"]
    except Exception as exc:
        logger.warning(f"generate_market_opportunities: cash niet bepaald ({exc})")
    iv = _investment_volume()
    budget_txt = (f"Beschikbare cash: €{cash:,.0f}. "
                  f"Geschat investeringsvolume: €{iv['per_maand']:,.0f}/maand, "
                  f"€{iv['per_jaar']:,.0f}/jaar.") if level == "off" else \
                 "Particuliere belegger met beperkte instapbedragen."

    profielen = ", ".join(f"{a['rekening']}: {a['profiel']}" for a in ctx.get("per_rekening", [])) or "neutraal"
    today = datetime.now().strftime("%d/%m/%Y")
    valid = ", ".join(RATING_ORDER)

    user = f"""DATUM: {today}  |  MODEL: {model}

REEDS IN PORTEFEUILLE (niet opnieuw voorstellen): {held_txt}
BELEGGINGSPROFIEL PER REKENING: {profielen}
BUDGET: {budget_txt}

OPDRACHT (LUIK 2 — KOOPOPPORTUNITEITEN IN DE WERELDWIJDE MARKT):
Zoek vandaag exact 6 NIEUWE koopideeën buiten de bestaande portefeuille, verdeeld over
drie risicoklassen:
  • 2x bucket "defensive"   — defensieve aandelen met focus op GROEI en eventueel
    DIVIDENDRENDEMENT: robuuste balans, voorspelbare kasstromen, prijszettingsmacht.
  • 2x bucket "moderate"    — matig speculatief: groeiverhaal met bewezen omzet, maar
    duidelijke uitvoerings- of waarderingsrisico's.
  • 2x bucket "speculative" — sterk speculatief: hoog risico/hoge potentiële opbrengst
    (turnaround, small cap, doorbraaktechnologie, cyclisch dieptepunt, ...).

Onderbouw elk idee op basis van: bedrijfsprestaties en cijfers, vooruitzichten,
macro-economische inzichten, geopolitiek en recente financiële berichtgeving.
Geef bij elk idee ook een rating op deze schaal: {valid}.
Kies liquide, voor een Belgische particulier vlot verhandelbare effecten (Euronext, Xetra,
LSE, US-beurzen). Geef het EXACTE Yahoo-Finance-ticker met beurssuffix.

Antwoord UITSLUITEND met geldige JSON (geen markdown errond), in exact dit formaat:
{{
  "marktbeeld": "3-5 zinnen: het macro-, geopolitieke en nieuwskader van vandaag waarbinnen deze ideeën passen",
  "ideeen": [
    {{"bucket": "defensive|moderate|speculative",
      "ticker": "ASML.AS",
      "naam": "ASML Holding",
      "beurs": "Euronext Amsterdam",
      "isin": "NL0010273215",
      "munt": "EUR",
      "advies": "<één van: {valid}>",
      "koersdoel_12m": 0.0,
      "dividendrendement_pct": 0.0,
      "horizon": "bv. 12-18 maanden",
      "onderbouwing": "3-5 zinnen: bedrijfsprestaties, vooruitzichten, waardering, macro/geopolitiek",
      "katalysatoren": "concrete triggers op korte termijn (resultaten, orders, regelgeving, ...)",
      "risicos": "de 2-3 belangrijkste risico's"
    }}
  ]
}}
Exact 6 ideeën, exact 2 per bucket.
"""
    try:
        raw, used_web = _chat_websearch(client, model, MARKET_PERSONA, user,
                                        max_tokens=3500, track_as="market_ideas")
        data = _parse_json(raw)
        if not isinstance(data, dict):
            return {"error": "AI-antwoord niet bruikbaar."}
        ideas = data.get("ideeen") or data.get("ideas") or []
        if not ideas:
            return {"error": "AI gaf geen koopideeën terug."}

        batch_id = datetime.now().strftime("%Y%m%d%H%M%S")
        idea_date = datetime.now().strftime("%Y-%m-%d")
        stored, per_bucket = 0, {b: 0 for b in MARKET_BUCKETS}

        for it in ideas:
            if not isinstance(it, dict):
                continue
            ticker = str(it.get("ticker") or "").strip().upper()
            if not ticker:
                continue
            bucket = _BUCKET_ALIASES.get(
                str(it.get("bucket") or "").strip().lower().replace(" ", "_"))
            if bucket not in MARKET_BUCKETS:
                continue
            rating = str(it.get("advies") or it.get("rating") or "").lower().replace(" ", "_")
            if rating not in RATING_LABELS:
                rating = "buy"   # luik 2 stelt koopideeën voor; val terug op 'kopen'

            # Koers op het moment van het advies vastleggen -> rendement opvolgbaar.
            price, currency = None, None
            try:
                price, currency = md.get_current_price(ticker)
            except Exception as exc:
                logger.warning(f"generate_market_opportunities: koers {ticker} faalde ({exc})")
            if price is None:
                logger.info(f"generate_market_opportunities: geen koers gevonden voor {ticker} "
                            "— idee wordt opgeslagen zonder startkoers (rendement niet meetbaar)")

            db.save_market_idea(
                batch_id, idea_date, bucket, ticker,
                name=it.get("naam") or it.get("name"),
                exchange=it.get("beurs") or it.get("exchange"),
                isin=(it.get("isin") or "").upper() or None,
                currency=currency or it.get("munt") or it.get("currency") or "EUR",
                rating=rating,
                price_at_advice=price,
                price_target=_num(it.get("koersdoel_12m") or it.get("price_target")),
                dividend_yield=_num(it.get("dividendrendement_pct") or it.get("dividend_yield")),
                horizon=it.get("horizon"),
                rationale=it.get("onderbouwing") or it.get("rationale"),
                catalysts=it.get("katalysatoren") or it.get("catalysts"),
                risks=it.get("risicos") or it.get("risks"),
                model=model,
            )
            stored += 1
            per_bucket[bucket] += 1

        # Het marktbeeld bewaren we als tekstevaluatie (aparte soort dan luik 1).
        marktbeeld = data.get("marktbeeld", "") or ""
        if not used_web:
            marktbeeld += ("\n\n_⚠️ Zonder live websearch gegenereerd — gebaseerd op de "
                           "trainingskennis van het model, niet op de berichtgeving van vandaag._")
        db.save_ai_evaluation("market_ideas", marktbeeld, timing=batch_id,
                              tickers=",".join(sorted({i["ticker"] for i in
                                                       db.get_market_ideas(batch_id=batch_id)})))

        logger.info(f"Marktopportuniteiten: {stored} idee(ën) opgeslagen "
                    f"(defensief {per_bucket['defensive']}, matig {per_bucket['moderate']}, "
                    f"speculatief {per_bucket['speculative']}), websearch={used_web}")
        return {"batch_id": batch_id, "stored": stored, "per_bucket": per_bucket,
                "marktbeeld": marktbeeld, "websearch": used_web}
    except OpenAIError as exc:
        logger.error(f"generate_market_opportunities: {exc}")
        return {"error": f"OpenAI-fout: {exc}"}
    except Exception as exc:
        logger.error(f"generate_market_opportunities: {exc}")
        return {"error": f"Kon AI-antwoord niet verwerken: {exc}"}


def _num(v):
    """Tolerant getal uit het AI-antwoord. Het model schrijft koersdoelen soms als
    'CHF 95,5', '€ 250', '3,1%' of 'ca. 42' — we halen er het eerste getal uit
    (komma of punt als decimaalteken). Geen getal -> None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    import re
    m = re.search(r"-?\d+(?:[.,]\d+)?", str(v))
    if not m:
        return None
    try:
        return float(m.group(0).replace(",", "."))
    except ValueError:
        return None


MARKET_PERIODS = [("7d", "7 dagen", 7), ("1m", "1 maand", 30), ("3m", "3 maanden", 90)]


def market_idea_synthesis(days: int) -> list[dict]:
    """Vat de koopideeën van de afgelopen 'days' dagen samen PER TICKER, met het
    GEMIDDELDE advies over die periode.

    Per ticker: hoe vaak voorgesteld, in welke bucket(s), het gemiddelde advies
    (gemiddelde ratingscore -> label), het laatste advies, en het rendement sinds het
    eerste advies (koers nu t.o.v. de koers op het moment van dat eerste advies).
    De koers 'nu' komt uit price_history (de scheduler volgt de idee-tickers dagelijks
    op) — geen netwerkcalls tijdens het renderen. Geen koersdata -> rendement None.
    """
    from datetime import timedelta
    since = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    ideas = db.get_market_ideas(since_date=since)
    if not ideas:
        return []

    by_ticker: dict[str, list[dict]] = {}
    for it in ideas:
        by_ticker.setdefault(it["ticker"], []).append(it)

    latest = db.get_latest_prices(list(by_ticker.keys()))

    out = []
    for tk, rows in by_ticker.items():
        rows_sorted = sorted(rows, key=lambda r: (r["idea_date"], r["id"]))
        first, last = rows_sorted[0], rows_sorted[-1]
        scores = [RATING_SCORE[r["rating"]] for r in rows_sorted if r.get("rating") in RATING_SCORE]
        avg = sum(scores) / len(scores) if scores else 0.0
        buckets = sorted({r["bucket"] for r in rows_sorted})

        start = first.get("price_at_advice")
        now_row = latest.get(tk)
        now_price = now_row["price"] if now_row else None
        ret_pct = None
        if start and now_price:
            ret_pct = (now_price - start) / start * 100

        out.append({
            "ticker":        tk,
            "naam":          last.get("name") or tk,
            "buckets":       buckets,
            "n":             len(rows_sorted),
            "avg_score":     round(avg, 2),
            "avg_rating":    score_to_rating(avg),
            "latest_rating": last.get("rating"),
            "eerste_advies": first["idea_date"],
            "laatste_advies": last["idea_date"],
            "startkoers":    start,
            "huidige_koers": now_price,
            "rendement_pct": ret_pct,
            "munt":          last.get("currency") or "EUR",
            "koersdoel":     last.get("price_target"),
        })
    # Sterkste gemiddelde advies eerst, daarna het vaakst herhaald
    out.sort(key=lambda r: (-r["avg_score"], -r["n"], r["ticker"]))
    return out


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

def rating_changes(tickers: list[str]) -> dict:
    """Vergelijk de laatste twee adviesrondes per ticker. Returnt {ticker: {from, to, up}}
    voor enkel de tickers waarvan de rating wijzigde. up=True = bullisher geworden."""
    batches = db.get_recent_rating_batches(2)
    if len(batches) < 2:
        return {}
    new_b, old_b = batches[0], batches[1]
    new_r = {r["ticker"]: r["rating"] for r in db.get_ai_ratings(batch_ids=[new_b])}
    old_r = {r["ticker"]: r["rating"] for r in db.get_ai_ratings(batch_ids=[old_b])}
    out: dict[str, dict] = {}
    for tk in tickers:
        a, b = old_r.get(tk), new_r.get(tk)
        if a and b and a != b and a in RATING_ORDER and b in RATING_ORDER:
            out[tk] = {"from": a, "to": b, "up": RATING_ORDER.index(b) < RATING_ORDER.index(a)}
    return out


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