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
