# DukaanFlow API (FastAPI). Runtime dependencies only; runs as a non-root user.
FROM python:3.13-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

FROM python:3.13-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ENVIRONMENT=production \
    WEB_CONCURRENCY=2
RUN useradd --system --uid 10001 --home-dir /app dukaanflow
WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
# Demo data (only loaded when you run it: python -m seed.run_seed / seed.bulk_demo)
COPY seed ./seed
USER dukaanflow
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"
# On start: check the settings (a bad setting stops the container with the reason), apply the
# database migrations, then serve. WEB_CONCURRENCY = number of worker processes.
CMD ["sh", "-c", "python -c 'import app.core.config' && alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY} --proxy-headers --forwarded-allow-ips='*'"]
