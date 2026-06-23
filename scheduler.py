"""
scheduler.py — APScheduler achtergrondproces
Draait naast de Streamlit-app via run.sh.

Jobs:
  • Elke 5 minuten   → actuele koersen opslaan in price_history
  • Euronext 09:05   → marktevaluatie opening
  • Euronext 13:15   → marktevaluatie middag
  • Euronext 17:35   → marktevaluatie sluiting
  • NYSE/NASDAQ 15:35→ marktevaluatie opening
  • NYSE/NASDAQ 18:45→ marktevaluatie middag
  • NYSE/NASDAQ 22:05→ marktevaluatie sluiting
  • Werkdag 08:00    → dagelijks belastingoptimalisatieadvies
"""
from __future__ import annotations

import logging
import os
import sys
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
    """Sla actuele koersen op voor alle gekende activa."""
    assets = db.get_assets()
    if not assets:
        logger.info("Geen activa geregistreerd — koerstracking overgeslagen.")
        return
    tickers = [a["ticker"] for a in assets]
    logger.info(f"📈 Koersen ophalen voor {len(tickers)} ticker(s)...")
    prices = md.get_prices_for_tickers(tickers)
    saved = 0
    for ticker, info in prices.items():
        if info["price"] is not None:
            db.save_price(ticker, info["price"], info.get("currency", "EUR"))
            saved += 1
    logger.info(f"✅ {saved}/{len(tickers)} koersen opgeslagen")
    db.cleanup_old_prices(keep_days=90)


def job_market_eval(timing: str, exchanges: list[str]):
    """Genereer en sla een marktevaluatie op."""
    logger.info(f"🤖 Marktevaluatie ({timing}) voor {exchanges}...")
    result = ai_advisor.generate_market_evaluation(timing, exchanges)
    if result.startswith("❌"):
        logger.warning(f"Marktevaluatie ({timing}) niet gegenereerd: {result[:80]}")
    else:
        logger.info(f"✅ Marktevaluatie ({timing}) opgeslagen")


def job_tax_optimization():
    """Genereer en sla het dagelijkse belastingadvies op."""
    logger.info("💡 Dagelijks belastingadvies genereren...")
    result = ai_advisor.generate_tax_optimization()
    if result.startswith("❌"):
        logger.warning(f"Belastingadvies niet gegenereerd: {result[:80]}")
    else:
        logger.info("✅ Belastingadvies opgeslagen")


def on_job_error(event):
    logger.error(f"❌ Job '{event.job_id}' mislukt: {event.exception}")


def on_job_executed(event):
    logger.debug(f"Job '{event.job_id}' klaar")


# ── Main ──────────────────────────────────────────────────────────────────────

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

    # ── Euronext Brussels/Amsterdam/Paris: 09:00–17:30 CET ──
    for job_id, hour, minute, timing, exchanges in [
        ("eu_open",   9,  5,  "open",   ["Euronext"]),
        ("eu_midday", 13, 15, "midday", ["Euronext"]),
        ("eu_close",  17, 35, "close",  ["Euronext"]),
    ]:
        scheduler.add_job(
            job_market_eval,
            trigger=CronTrigger(day_of_week="mon-fri", hour=hour,
                                minute=minute, timezone=BRUSSELS),
            id=job_id, args=[timing, exchanges],
            replace_existing=True, misfire_grace_time=300,
        )

    # ── NYSE / NASDAQ: 09:30–16:00 ET = 15:30–22:00 CET ──
    for job_id, hour, minute, timing, exchanges in [
        ("us_open",   15, 35, "open",   ["NYSE", "NASDAQ"]),
        ("us_midday", 18, 45, "midday", ["NYSE", "NASDAQ"]),
        ("us_close",  22,  5, "close",  ["NYSE", "NASDAQ"]),
    ]:
        scheduler.add_job(
            job_market_eval,
            trigger=CronTrigger(day_of_week="mon-fri", hour=hour,
                                minute=minute, timezone=BRUSSELS),
            id=job_id, args=[timing, exchanges],
            replace_existing=True, misfire_grace_time=300,
        )

    # ── Dagelijks belastingadvies: 08:00 op werkdagen ──
    scheduler.add_job(
        job_tax_optimization,
        trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=0, timezone=BRUSSELS),
        id="daily_tax",
        replace_existing=True,
        misfire_grace_time=600,
    )

    logger.info("🚀 Scheduler gestart. Geplande jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"   • {job.id:<15s} → volgende run: {job.next_run_time}")

    # Initiële koerstracking bij opstart
    try:
        job_track_prices()
    except Exception as exc:
        logger.warning(f"Initiële koerstracking mislukt (niet kritiek): {exc}")

    scheduler.start()


if __name__ == "__main__":
    main()
