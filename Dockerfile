# Officieel Python 3.11 slim — ondersteunt ARM64 (Raspberry Pi 4 / aarch64)
FROM python:3.11-slim

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
RUN pip install --no-cache-dir tzlocal>=4.0

# Overige pakketten installeren
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Alle applicatiebestanden kopiëren
COPY . .

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
