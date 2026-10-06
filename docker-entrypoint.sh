#!/bin/sh
# Start as root only long enough to give the app user its data directory, then drop root for good.
# Railway mounts volumes owned by root, so the app user couldn't otherwise write the database.
set -e
if [ "$(id -u)" = "0" ]; then
  data="$(dirname "${DB_PATH:-/data/thespis.sqlite}")"
  mkdir -p "$data"
  chown -R thespis:thespis "$data"
  exec setpriv --reuid=thespis --regid=thespis --init-groups "$@"
fi
exec "$@"
