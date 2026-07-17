"""
scheduler.py — APScheduler achtergrondproces
Draait naast de Streamlit-app via run.sh.

Jobs:
  • Elke 5 minuten        → koersen van de portefeuille opslaan in price_history
  • Werkdag 07:45         → LUIK 2: marktopportuniteiten (6 koopideeën wereldwijd)
  • Werkdag 18:00         → LUIK 1: dagelijks portefeuilleadvies (ratings + tekst)
  • Dagelijks 22:30       → koersen van de voorgestelde aandelen opvolgen
  • Dagelijks 22:45       → statuscontrole (verouderde koersen, splits, tickerwijzigingen)
  • 1e van de maand 07:30 → AI-modelprijzen verversen
  • 1e van de maand 08:00 → belastingoptimalisatieadvies
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# ── Zorg dat de map van dit bestand altijd in het Python-pad staat,
#    ongeacht hoe het proces gestart werd (achtergrond via run.sh,
#    direct via CLI, vanuit een andere werkdirectory, enz.)
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

import database as db
import market_data as md
import belgian_tax as tax
import ai_advisor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("scheduler")

BRUSSELS = ZoneInfo("Europe/Brussels")


# ── Jobs ──────────────────────────────────────────────────────────────────────

def job_track_prices():
    """Sla actuele koersen op voor de activa met een OPEN positie.

    Volledig verkochte posities worden overgeslagen: hun historiek blijft bewaard, maar
    er is geen reden om er elke 5 minuten netwerkcalls aan te besteden. Activa waarvoor
    de koersophaling is gestopt (10 mislukte pogingen op rij, zie market_data) worden
    binnenin get_current_price overgeslagen."""
    if not db.get_assets():
        logger.info("Geen activa geregistreerd — koerstracking overgeslagen.")
        return
    # Dezelfde FIFO-logica als het dashboard (zie belgian_tax.open_position_tickers):
    # geen tweede, afwijkende positieberekening.
    tickers, closed = tax.open_position_tickers()
    if not tickers:
        logger.info("Geen open posities — koerstracking overgeslagen.")
        return
    logger.info(f"📈 Koersen ophalen voor {len(tickers)} ticker(s)...")
    if closed:
        # Namen erbij: zonder die lijst kan je niet controleren of de app terecht
        # denkt dat een positie gesloten is.
        logger.info(f"⏭️  {len(closed)} gesloten positie(s) overgeslagen: {', '.join(closed)}")
    prices = md.get_prices_for_tickers(tickers)
    saved, failed = 0, []
    for ticker, info in prices.items():
        if info["price"] is not None:
            db.save_price(ticker, info["price"], info.get("currency", "EUR"))
            saved += 1
        else:
            failed.append(ticker)
    logger.info(f"✅ {saved}/{len(tickers)} koersen opgeslagen")
    if failed:
        logger.warning(f"⚠️ Geen koers gevonden voor: {', '.join(failed)} "
                       "(alle bronnen faalden — zie eventuele voorgaande regels voor detail "
                       "per bron, of zet een handmatige koers in het activaoverzicht).")
    db.cleanup_old_prices(keep_days=90)


def job_daily_advice():
    """LUIK 1 — dagelijks advies over de BESTAANDE portefeuille (ratings + tekst)."""
    logger.info("🤖 Luik 1: dagelijks portefeuilleadvies genereren...")
    res = ai_advisor.generate_daily_portfolio_advice()
    if res.get("error"):
        logger.warning(f"Luik 1 niet gegenereerd: {res['error'][:80]}")
    else:
        logger.info(f"✅ Luik 1 opgeslagen ({res.get('stored', 0)} ratings)")


def job_market_opportunities():
    """LUIK 2 — dagelijkse koopopportuniteiten in de wereldwijde markt: 2 defensieve,
    2 matig speculatieve en 2 sterk speculatieve aandelen, met onderbouwing."""
    logger.info("🌍 Luik 2: marktopportuniteiten zoeken...")
    res = ai_advisor.generate_market_opportunities()
    if res.get("error"):
        logger.warning(f"Luik 2 niet gegenereerd: {res['error'][:80]}")
        return
    pb = res.get("per_bucket", {})
    logger.info(f"✅ Luik 2: {res.get('stored', 0)} koopidee(ën) "
                f"(defensief {pb.get('defensive', 0)}, matig {pb.get('moderate', 0)}, "
                f"speculatief {pb.get('speculative', 0)}) — "
                f"websearch={'ja' if res.get('websearch') else 'nee (trainingskennis)'}")
    # Meteen de koersen van de nieuwe ideeën vastleggen, zodat het rendement sinds
    # advies vanaf dag één opvolgbaar is.
    job_track_idea_prices()


def job_track_idea_prices():
    """Volg de koers op van elk aandeel dat de AI de afgelopen ~100 dagen als
    koopopportuniteit voorstelde. Zo toont de app het rendement sinds advies
    (7 dagen / 1 maand / 3 maanden) rechtstreeks uit de database, zonder netwerkcalls
    tijdens het renderen. Draait één keer per dag (na de Amerikaanse slotbel), niet om
    de 5 minuten: deze aandelen zitten niet in de portefeuille, dus intraday-precisie
    is overbodig en zou nodeloos veel calls kosten."""
    from datetime import timedelta
    since = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    tickers = db.get_idea_tickers_since(since, limit=200)
    if not tickers:
        logger.info("Geen AI-koopideeën om op te volgen — overgeslagen.")
        return
    logger.info(f"🔎 Koersen van {len(tickers)} voorgesteld(e) aande(e)l(en) opvolgen...")
    prices = md.get_prices_for_tickers(tickers)
    saved, failed = 0, []
    for ticker, info in prices.items():
        if info["price"] is not None:
            db.save_price(ticker, info["price"], info.get("currency", "EUR"))
            saved += 1
        else:
            failed.append(ticker)
    logger.info(f"✅ {saved}/{len(tickers)} koersen van koopideeën opgeslagen")
    if failed:
        logger.warning(f"⚠️ Geen koers voor voorgestelde aandelen: {', '.join(failed)} "
                       "(ticker mogelijk verkeerd opgegeven door de AI — het rendement sinds "
                       "advies blijft dan leeg voor deze namen).")
    db.cleanup_old_market_ideas(keep_days=400)


def job_tax_optimization():
    """Genereer en sla het belastingadvies op (maandelijks)."""
    logger.info("💡 Maandelijks belastingadvies genereren...")
    result = ai_advisor.generate_tax_optimization()
    if result.startswith("❌"):
        logger.warning(f"Belastingadvies niet gegenereerd: {result[:80]}")
    else:
        logger.info("✅ Belastingadvies opgeslagen")


def job_refresh_ai_prices():
    """Zoek maandelijks de actuele AI-modelprijzen op en pas ze indien nodig aan."""
    logger.info("💲 AI-modelprijzen verversen...")
    res = ai_advisor.refresh_model_prices()
    if res.get("error"):
        logger.warning(f"Prijsverversing niet gelukt: {res['error']}")
    else:
        logger.info(f"✅ Prijsverversing: {len(res['updated'])} bijgewerkt "
                    f"({', '.join(res['updated']) or 'geen'}), "
                    f"{len(res['unchanged'])} ongewijzigd")


def job_status_checks():
    """Dagelijkse statuscontrole van de portefeuille (punt 2/3): verouderde koersen,
    dagen zonder koersbeweging, tickerwijzigingen / meerdere producten onder één ISIN
    (met bijwerken van de resolved_symbol), niet-geregistreerde aandelensplits en
    naamsafwijkingen. Resultaten komen op de statuspagina in de app."""
    logger.info("🩺 Statuscontrole van de portefeuille...")
    try:
        s = db.run_status_checks(online=True)
    except Exception as exc:
        logger.warning(f"Statuscontrole mislukt (niet kritiek): {exc}")
        return
    logger.info(f"✅ Statuscontrole: {s.get('checked', 0)} activa gecontroleerd — "
                f"{s.get('new', 0)} nieuw(e), {s.get('resolved', 0)} opgelost, "
                f"{s.get('open', 0)} open waarschuwing(en)"
                + (f", {s['errors']} netwerkfout(en)" if s.get('errors') else ""))


def on_job_error(event):
    logger.error(f"❌ Job '{event.job_id}' mislukt: {event.exception}")


def on_job_executed(event):
    logger.debug(f"Job '{event.job_id}' klaar")


# ── Main ──────────────────────────────────────────────────────────────────────

def _next_run(job):
    """Volgende runtijd van een job, ook als die nog 'pending' is.

    Nieuwere APScheduler-versies zetten 'next_run_time' pas na scheduler.start().
    Omdat de jobs hier (BlockingScheduler) vóór start() worden gelogd, valt dat
    attribuut soms weg -> we berekenen de volgende runtijd dan uit de trigger.
    """
    nrt = getattr(job, "next_run_time", None)
    if nrt is not None:
        return nrt
    try:
        return job.trigger.get_next_fire_time(None, datetime.now(BRUSSELS))
    except Exception:
        return "n.t.b."


def main():
    db.init_db()

    scheduler = BlockingScheduler(timezone=BRUSSELS)
    scheduler.add_listener(on_job_error,    EVENT_JOB_ERROR)
    scheduler.add_listener(on_job_executed, EVENT_JOB_EXECUTED)

    # Koerstracking elke 5 minuten (altijd actief)
    scheduler.add_job(
        job_track_prices,
        trigger="interval",
        minutes=5,
        id="price_tracking",
        replace_existing=True,
        misfire_grace_time=60,
    )

    # ── Eén dagelijks portefeuilleadvies: elke werkdag om 18:00 (na EU-slot) ──
    scheduler.add_job(
        job_daily_advice,
        trigger=CronTrigger(day_of_week="mon-fri", hour=18, minute=0, timezone=BRUSSELS),
        id="daily_advice",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── LUIK 2: marktopportuniteiten, elke werkdag om 07:45 (vóór de opening) ──
    scheduler.add_job(
        job_market_opportunities,
        trigger=CronTrigger(day_of_week="mon-fri", hour=7, minute=45, timezone=BRUSSELS),
        id="market_ideas",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Koersopvolging van de voorgestelde aandelen: dagelijks 22:30 (na de VS) ──
    scheduler.add_job(
        job_track_idea_prices,
        trigger=CronTrigger(hour=22, minute=30, timezone=BRUSSELS),
        id="idea_prices",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Maandelijks belastingadvies: 1e van de maand om 08:00 ──
    scheduler.add_job(
        job_tax_optimization,
        trigger=CronTrigger(day=1, hour=8, minute=0, timezone=BRUSSELS),
        id="monthly_tax",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Maandelijkse AI-prijsverversing: 1e van de maand om 07:30 ──
    scheduler.add_job(
        job_refresh_ai_prices,
        trigger=CronTrigger(day=1, hour=7, minute=30, timezone=BRUSSELS),
        id="monthly_ai_prices",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # ── Dagelijkse statuscontrole: 22:45 (na de VS-slotbel + koersopvolging) ──
    scheduler.add_job(
        job_status_checks,
        trigger=CronTrigger(hour=22, minute=45, timezone=BRUSSELS),
        id="status_checks",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    logger.info("🚀 Scheduler gestart. Geplande jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"   • {job.id:<15s} → volgende run: {_next_run(job)}")

    # Initiële koerstracking bij opstart
    try:
        job_track_prices()
    except Exception as exc:
        logger.warning(f"Initiële koerstracking mislukt (niet kritiek): {exc}")

    scheduler.start()


if __name__ == "__main__":
    main()