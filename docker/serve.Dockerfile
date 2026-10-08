# The hosted runtime: `thespis serve --server`, projects with their own keys, sessions in Postgres.
#   docker build -f docker/serve.Dockerfile -t thespis-serve .
#   docker run -e DATABASE_URL=postgresql://... -e THESPIS_SECRET_KEY=... -p 8000:8000 thespis-serve
# Without DATABASE_URL it keeps everything in a SQLite file on the /data volume. Projects are made with
#   docker exec <container> thespis projects create <name>
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 DB_PATH=/data/serve.sqlite
WORKDIR /app
RUN useradd --system --uid 10001 --user-group --no-create-home --shell /usr/sbin/nologin thespis
COPY requirements.txt requirements-server.txt ./
RUN pip install --no-cache-dir -r requirements-server.txt
COPY pyproject.toml README.md LICENSE ./
COPY thespis/ thespis/
RUN pip install --no-cache-dir --no-deps .
COPY examples/tavern/ examples/tavern/
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod 755 /usr/local/bin/docker-entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["sh", "-c", "exec thespis serve --server --host 0.0.0.0 --port ${PORT} --db \"${DATABASE_URL:-$DB_PATH}\" --game examples/tavern/game.toml"]
