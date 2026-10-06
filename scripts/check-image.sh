#!/bin/sh
# Run the built image as Railway does, with a volume at /data, and check what it promises: it answers /health, the
# app doesn't run as root, it logs JSON, and the database on the volume survives a restart.
#   docker build -t thespis:dev . && sh scripts/check-image.sh thespis:dev
set -eu
export MSYS_NO_PATHCONV=1  # Git Bash on Windows would otherwise rewrite the container paths below
image="${1:-thespis:dev}"
name="thespis-check-$$"
volume="$name-data"
port=18000

cleanup() {
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker volume rm "$volume" >/dev/null 2>&1 || true
}
trap cleanup EXIT

healthy() {
  for _ in $(seq 60); do
    curl -fsS "http://127.0.0.1:$port/health" >/dev/null 2>&1 && return 0
    sleep 1
  done
  docker logs "$name"
  echo "the image never answered /health"
  return 1
}

docker run -d --name "$name" -p "127.0.0.1:$port:8000" -v "$volume:/data" "$image" >/dev/null
healthy
uid=$(docker exec "$name" cat /proc/1/status | awk '/^Uid:/ {print $2}')
[ "$uid" = 10001 ] || { echo "the app runs as uid $uid, not 10001"; exit 1; }
docker logs "$name" 2>&1 | grep -q '"message": "boot #1' || { docker logs "$name"; echo "no JSON boot line"; exit 1; }
docker restart "$name" >/dev/null
healthy
docker logs "$name" 2>&1 | grep -q 'boot #2' || { docker logs "$name"; echo "the database didn't survive a restart"; exit 1; }
echo "image ok: the app runs as uid 10001, logs JSON, and its volume persists"
