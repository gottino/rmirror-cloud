#!/usr/bin/env bash
# Install a prebuilt dashboard (from package-standalone.sh) on the server and
# (re)start it under pm2. Runs as the deploy user; needs node and pm2 on PATH.
#
# Usage: install-release.sh <tarball> <release_dir> <env_file> <pm2_name> <port> [legacy_dir]
#
# The previous release is kept at <release_dir>.prev. If the new one doesn't
# answer on <port> within 30s, the previous one is restored and the script fails.
# legacy_dir is the old `npm start` checkout, restarted instead when there is
# no previous release yet (the first standalone deploy).
set -euo pipefail

tarball="$1" release="$2" env_file="$3" name="$4" port="$5" legacy_dir="${6:-}"

start() {
  pm2 delete "$name" > /dev/null 2>&1 || true
  # HOSTNAME is set explicitly: standalone server.js binds to $HOSTNAME, which
  # can otherwise be the machine name instead of all interfaces.
  PORT="$port" HOSTNAME=0.0.0.0 pm2 start "$1/server.js" --name "$name" --cwd "$1"
}

healthy() {
  for _ in $(seq 1 15); do
    sleep 2
    code=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:$port" || true)
    if [ "$code" = "200" ] || [ "$code" = "307" ]; then
      return 0
    fi
  done
  return 1
}

mkdir -p "$(dirname "$release")"
rm -rf "$release.new"
mkdir -p "$release.new"
tar xzf "$tarball" -C "$release.new"
install -m 600 "$env_file" "$release.new/.env"

rm -rf "$release.prev"
if [ -d "$release" ]; then
  mv "$release" "$release.prev"
fi
mv "$release.new" "$release"

start "$release"
if healthy; then
  pm2 save
  rm -f "$tarball"
  echo "Dashboard $name is up on port $port"
  exit 0
fi

echo "Dashboard $name did not come up on port $port" >&2
pm2 logs "$name" --lines 30 --nostream >&2 || true
if [ -d "$release.prev" ]; then
  echo "Rolling back to the previous release" >&2
  rm -rf "$release.failed"
  mv "$release" "$release.failed"
  mv "$release.prev" "$release"
  start "$release"
  pm2 save
elif [ -n "$legacy_dir" ]; then
  echo "Restarting the previous npm start dashboard from $legacy_dir" >&2
  pm2 delete "$name" > /dev/null 2>&1 || true
  (cd "$legacy_dir" && PORT="$port" pm2 start npm --name "$name" -- start)
  pm2 save
fi
exit 1
