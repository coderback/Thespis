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
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DB_PATH=/data/thespis.sqlite PORT=8000
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY thespis/ thespis/
COPY games/ games/
COPY tools/ tools/
COPY --from=client /client/dist client/dist
EXPOSE 8000
# The host sets PORT (Railway does); the volume is mounted at /data.
CMD ["sh", "-c", "uvicorn games.crypt_road.app:app --host 0.0.0.0 --port ${PORT}"]
