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
echo "🌐 Streamlit starten op poort 8501..."
exec streamlit run /app/app.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.fileWatcherType=none \
    --browser.gatherUsageStats=false
