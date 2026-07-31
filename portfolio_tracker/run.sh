#!/bin/bash
# run.sh — Startscript voor Portfolio Tracker (Home Assistant add-on)
set -e

echo "============================================"
echo " Portfolio Tracker 📈 — Opstarten"
echo " $(date '+%d/%m/%Y %H:%M:%S') | TZ=${TZ:-Europe/Brussels}"
echo "============================================"

# Werken vanuit /app zodat Python-modules vindbaar zijn
cd /app
export PYTHONPATH=/app

# Data-map aanmaken in /share (persistent HA-opslag)
DATA_DIR="${DATA_DIR:-/share/portfolio_tracker}"
mkdir -p "$DATA_DIR"
echo "📁 Data-map: $DATA_DIR"

# OpenAI-sleutel uit de add-on-configuratie halen (indien ingevuld).
# Home Assistant schrijft de opties naar /data/options.json — dat bestand zit in de
# privéopslag van deze add-on, niet in /share. Zo hoeft de sleutel niet in
# portfolio.db te staan, waar andere add-ons bij kunnen. Een sleutel die al in de
# omgeving staat, laten we ongemoeid.
if [ -z "${OPENAI_API_KEY:-}" ] && [ -f /data/options.json ]; then
    _key="$(python -c "
import json
try:
    print((json.load(open('/data/options.json')).get('openai_api_key') or '').strip())
except Exception:
    print('')
" 2>/dev/null)"
    if [ -n "$_key" ]; then
        export OPENAI_API_KEY="$_key"
        echo "🔐 OpenAI-sleutel uit de add-on-configuratie geladen (niet in de database)."
    fi
    unset _key
fi

# Veiligheidskopie VÓÓR de database geopend en gemigreerd wordt.
# Dit is het risicomoment: een nieuwe versie voegt kolommen toe, en gaat er iets mis,
# dan wil je de toestand van vlak daarvoor terug. De kopie gebeurt met VACUUM INTO
# (consistent bij een draaiende WAL-database) en enkel als er al een database is —
# bij een verse installatie valt er niets te bewaren.
echo "💾 Veiligheidskopie maken (vóór eventuele migraties)..."
python - <<'PY' || echo "   ⚠️  Back-up niet gelukt — de app start gewoon door."
import os
import database as db
if os.path.exists(db.DB_PATH):
    b = db.create_backup("voor-start")
    n = db.prune_backups(int(db.get_setting("backup_keep", "14") or 14))
    print(f"   ✅ {b['name']} ({b['size'] / 1_000_000:.1f} MB)"
          + (f" — {n} oude opgeruimd" if n else ""))
else:
    print("   (nog geen database — overgeslagen)")
PY

# Database initialiseren
echo "🗄️  Database initialiseren..."
python -c "import database; database.init_db(); print('   ✅ Database klaar')"

# Scheduler starten als achtergrondproces
echo "⏱️  Scheduler starten..."
python /app/scheduler.py &
SCHEDULER_PID=$!
echo "   Scheduler PID: ${SCHEDULER_PID}"

sleep 3

# Streamlit starten
# --------------------------------------------------------------------------
# XSRF-bescherming staat AAN. Ze was uitgezet om het achter de reverse proxy van
# Home Assistant zeker werkend te krijgen, maar dat verzwakt de app: zonder deze
# bescherming kan een kwaadaardige pagina in je browser meeliften op je geopende
# sessie. Via ingress werkt ze gewoon (de cookies lopen mee).
# Streamlit dwingt bij XSRF=true zelf CORS terug aan; die vlag geven we dus niet
# meer mee, anders logt het bij elke start een override-waarschuwing.
# Loopt de bulk-import (bestandsupload) bij jou vast op een 403, zet dan tijdelijk
# XSRF_PROTECTION=false in de add-on-omgeving — maar liefst niet permanent.
XSRF_PROTECTION="${XSRF_PROTECTION:-true}"
echo "🌐 Streamlit starten op poort 8501 (XSRF-bescherming: ${XSRF_PROTECTION})..."
exec streamlit run /app/app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableXsrfProtection="${XSRF_PROTECTION}" \
    --server.fileWatcherType=none \
    --browser.gatherUsageStats=false
