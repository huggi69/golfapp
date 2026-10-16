FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/golf.sqlite

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY golfapp ./golfapp
COPY wsgi.py .

RUN useradd --system --uid 1000 golf && mkdir -p /data && chown golf /data
USER golf
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')" || exit 1

# Ein Worker reicht für zwei Spieler und vermeidet konkurrierende SQLite-Schreibzugriffe.
# --timeout 120: das Auslesen eines Scorekarten-Fotos kann 30–60 s dauern
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "4", "--timeout", "120", "wsgi:app"]
