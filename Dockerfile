# One image serves the engine API and the built client from the same URL.

# 1. Build the client, if it exists yet. Without client/package.json this stage yields an empty dist/.
FROM node:22-slim AS client
WORKDIR /client
COPY client/ ./
RUN if [ -f package.json ]; then \
      if [ -f package-lock.json ]; then npm ci; else npm install; fi && npm run build; \
    fi && mkdir -p dist

# 2. The engine.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/data/thespis.sqlite PORT=8000 LOG_FORMAT=json
WORKDIR /app
# The app runs as this user, never as root (docker-entrypoint.sh drops root once /data is its own).
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin thespis
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY thespis/ thespis/
COPY games/ games/
COPY tools/ tools/
COPY --from=client /client/dist client/dist
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
# The host sets PORT (Railway does); the volume is mounted at /data.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn games.crypt_road.app:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
