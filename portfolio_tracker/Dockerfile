# Officieel Python 3.14 slim — ondersteunt ARM64 (Raspberry Pi 4 / aarch64) en amd64.
# Alle pakketten uit requirements.txt bestaan voor 3.14 als kant-en-klaar wiel op
# beide architecturen (gecontroleerd bij 1.8.20), dus er wordt niets gecompileerd.
FROM python:3.14-slim

WORKDIR /app

# Systeemdependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Pip upgraden
RUN pip install --no-cache-dir --upgrade pip

# tzlocal apart installeren — directe dependency van apscheduler
# (apart laag zodat caching dit niet kan overslaan)
# Let op de aanhalingstekens: zonder zou de shell '>=5.0' lezen als een omleiding
# naar een bestand '=5.0' en zomaar eender welke versie installeren.
RUN pip install --no-cache-dir "tzlocal>=5.0"

# Overige pakketten installeren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Alle applicatiebestanden kopiëren
COPY . .

# Streamlit leest zijn configuratie uit .streamlit/config.toml, relatief aan de
# werkmap. Dat bestand staat in deze repo al op de juiste plek
# (portfolio_tracker/.streamlit/config.toml) en komt met de COPY hierboven meteen
# goed terecht op /app/.streamlit/config.toml. Er valt dus niets te verplaatsen.
# Deze regel controleert dat alleen en drukt het resultaat af in het bouwlogboek;
# ze eindigt bewust op 'true', zodat een ontbrekend configuratiebestand nooit de
# hele build kan laten mislukken.
RUN ls -l /app/.streamlit/config.toml \
    && echo "Streamlit-configuratie staat goed." \
    || echo "Let op: geen /app/.streamlit/config.toml - run.sh geeft de essentiele instellingen als vlaggen mee."

# Omgevingsvariabelen
ENV DATA_DIR=/share/portfolio_tracker \
    TZ=Europe/Brussels \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN chmod +x /app/run.sh

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:8501/_stcore/health || exit 1

CMD ["/app/run.sh"]
