# ─── Étape 1 : builder — installe les dépendances dans un virtualenv ───
FROM python:3.12-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
# Versions figées (générées depuis uv.lock par `make requirements`) : builds reproductibles,
# et couche de dépendances mise en cache tant que requirements.txt ne change pas.
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-deps .


# ─── Étape 2 : runtime — image minimale, utilisateur non root ───
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --uid 1000 app
COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app src ./src

USER app
EXPOSE 8000

# Santé de l'API (sans curl : absent de l'image slim).
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)"

# Applique les migrations puis démarre l'API. --proxy-headers : derrière nginx, l'API voit
# le vrai schéma (https) et la vraie IP du client. UVICORN_WORKERS : 2 par défaut.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --workers ${UVICORN_WORKERS:-2}"]
