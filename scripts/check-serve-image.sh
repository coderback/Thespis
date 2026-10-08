#!/bin/sh
# Run the server image beside Postgres, as a host would, and check what it promises: it answers only with a
# project's key, keeps sessions in Postgres across a restart, and doesn't run as root.
#   docker build -f docker/serve.Dockerfile -t thespis-serve:dev . && sh scripts/check-serve-image.sh thespis-serve:dev
set -eu
export MSYS_NO_PATHCONV=1  # Git Bash on Windows would otherwise rewrite the container paths below
image="${1:-thespis-serve:dev}"
name="thespis-serve-check-$$"
net="$name-net"
port=18001
secret=$(head -c 32 /dev/urandom | base64)

cleanup() {
  docker rm -f "$name" "$name-db" >/dev/null 2>&1 || true
  docker network rm "$net" >/dev/null 2>&1 || true
}
trap cleanup EXIT

healthy() {
  for _ in $(seq 60); do
    curl -fsS "http://127.0.0.1:$port/v1/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  docker logs "$name"
  echo "the server never answered /v1/health"
  return 1
}

docker network create "$net" >/dev/null
docker run -d --name "$name-db" --network "$net" -e POSTGRES_PASSWORD=check -e POSTGRES_DB=thespis postgres:17-alpine >/dev/null
for _ in $(seq 60); do
  docker exec "$name-db" pg_isready -U postgres -d thespis >/dev/null 2>&1 && break
  sleep 1
done
docker run -d --name "$name" --network "$net" -p "127.0.0.1:$port:8000" \
  -e DATABASE_URL="postgresql://postgres:check@$name-db:5432/thespis" -e THESPIS_SECRET_KEY="$secret" "$image" >/dev/null
healthy
uid=$(docker exec "$name" cat /proc/1/status | awk '/^Uid:/ {print $2}')
[ "$uid" = 10001 ] || { echo "the server runs as uid $uid, not 10001"; exit 1; }

key=$(docker exec "$name" thespis projects create check | tail -n 1)
url="http://127.0.0.1:$port/v1"
code=$(curl -s -o /dev/null -w '%{http_code}' "$url/games")
[ "$code" = 401 ] || { echo "without a key it answered $code, not 401"; exit 1; }
sid=$(curl -fsS -H "Authorization: Bearer $key" -H 'Content-Type: application/json' -d '{"game": "tavern"}' \
  "$url/sessions" | sed -n 's/.*"session":"\([^"]*\)".*/\1/p')
[ -n "$sid" ] || { echo "no session opened"; exit 1; }
curl -fsS -H "Authorization: Bearer $key" -H 'Content-Type: application/json' -d '{"verb": "insult", "actor": "player",
  "target": "garrick", "witnesses": ["wren"], "claim": {"pred": "insulted", "a": "player", "b": "garrick"}}' \
  "$url/sessions/$sid/observe" >/dev/null
docker restart "$name" >/dev/null
healthy
curl -fsS -H "Authorization: Bearer $key" "$url/sessions/$sid/snapshot" | grep -q '"e0001"' \
  || { docker logs "$name"; echo "the session didn't survive a restart"; exit 1; }
echo "server image ok: it runs as uid 10001, wants a project's key, and its sessions outlive it in Postgres"
