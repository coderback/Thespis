# One image serves the engine API and the built client from the same URL.

# 1. Build the client, if it exists yet. Without client/package.json this stage yields an empty dist/.
FROM node:22-slim AS client
WORKDIR /client
COPY client/ ./
RUN if [ -f package.json ]; then \
      if [ -f package-lock.json ]; then npm ci; else npm install; fi && npm run build; \
    fi && mkdir -p dist

# 2. Before the Ice Goes Out for the browser: Godot exports the game (games/before-the-ice/export_presets.cfg, "Web"),
# and games/ice/api.py serves it at /ice/. Godot and its export templates come from Godot's own releases, checked
# against the SHA-512 sums published with them; of the templates (1.3 GB, every platform) only the web one is kept.
FROM debian:bookworm-slim AS ice
ARG GODOT=4.7.2
ARG GODOT_SHA512=9aa00f7a605200940bce3027a567b782f49bd8e940dd06ae9e987bd65aee1b1467edd56ed84fcdcbdd44354bf613bdbb4e5d2913e925850368e150c59ed54c65
ARG TEMPLATES_SHA512=ca4d71c4d7b81dfc15d1a98baa07534aa95b03fdda78a0075b06672e1648d2e5f40980c9adc28d23e1b92e732ee7bf3461997aa804af74ec2fcd7a93ccb84079
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip     && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL -o /tmp/godot.zip       "https://github.com/godotengine/godot/releases/download/${GODOT}-stable/Godot_v${GODOT}-stable_linux.x86_64.zip"     && echo "${GODOT_SHA512}  /tmp/godot.zip" | sha512sum -c -     && unzip -q /tmp/godot.zip -d /tmp && mv "/tmp/Godot_v${GODOT}-stable_linux.x86_64" /usr/local/bin/godot     && rm /tmp/godot.zip
RUN curl -fsSL -o /tmp/templates.tpz       "https://github.com/godotengine/godot/releases/download/${GODOT}-stable/Godot_v${GODOT}-stable_export_templates.tpz"     && echo "${TEMPLATES_SHA512}  /tmp/templates.tpz" | sha512sum -c -     && mkdir -p "/root/.local/share/godot/export_templates/${GODOT}.stable"     && unzip -q -j /tmp/templates.tpz templates/version.txt templates/web_nothreads_release.zip       -d "/root/.local/share/godot/export_templates/${GODOT}.stable"     && rm /tmp/templates.tpz
COPY games/before-the-ice/ /game/
WORKDIR /game
RUN godot --headless --import >/dev/null 2>&1; mkdir -p build/web     && godot --headless --export-release "Web" build/web/index.html     && test -s build/web/index.wasm && test -s build/web/index.pck

# 3. The engine.
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
COPY --from=ice /game/build/web games/ice/web
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
# The host sets PORT (Railway does); the volume is mounted at /data.
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn games.crypt_road.app:app --host 0.0.0.0 --port ${PORT} --no-access-log"]
