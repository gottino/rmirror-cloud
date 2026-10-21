#!/usr/bin/env bash
# Package a standalone Next.js build for deployment (runs in GitHub Actions).
#
# Usage: NEXT_OUTPUT=standalone npm run build && deploy/package-standalone.sh out.tgz
#
# The archive holds .next/standalone (server.js + the node_modules it needs)
# plus the static assets and public/ files, which Next leaves out of it.
set -euo pipefail
cd "$(dirname "$0")/.."

out="${1:?usage: package-standalone.sh <output.tgz>}"

if [ ! -f .next/standalone/server.js ]; then
  echo "No standalone build found; run: NEXT_OUTPUT=standalone npm run build" >&2
  exit 1
fi

# Next copies .env files into the standalone folder. Server secrets must come
# from the server's own .env at install time, never ride along in the archive.
if compgen -G ".next/standalone/.env*" > /dev/null; then
  echo "Refusing to package: .env file(s) found in .next/standalone" >&2
  exit 1
fi

cp -r .next/static .next/standalone/.next/static
if [ -d public ]; then
  cp -r public .next/standalone/public
fi

tar czf "$out" -C .next/standalone .
echo "Packaged $(du -h "$out" | cut -f1) dashboard build to $out"
