FROM python:3.13-slim
WORKDIR /srv
COPY pyproject.toml alembic.ini ./
COPY app ./app
COPY migrations ./migrations
RUN pip install --no-cache-dir .
RUN useradd -r lifey && mkdir -p /data/garmin_tokens && chown -R lifey /srv /data
USER lifey
EXPOSE 8000
# Migrations are idempotent; the API only starts once the schema is current.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
