#!/bin/bash
#
# Smoke-test a built rmirror-core the way rMirror.app runs it (docs/local-api.md, "Process contract").
#
# Usage:
#   scripts/smoke_core.sh <path/to/rmirror-core>
#   scripts/smoke_core.sh build/app/rMirror.app/Contents/Resources/core/rmirror-core
#
# Runs `rmirror-core --headless` in isolation: throwaway HOME, its own config (port 5599 unless
# SMOKE_PORT is set, unreachable cloud URL, empty reMarkable folder), the null keyring backend
# (the login keychain is never touched) and a random app token. Checks, in order:
#   1. the ready line `RMIRROR_CORE_READY port=<port> api=2` within 60 s
#   2. GET /health -> 200
#   3. GET /api/v2/state without the token -> 401, with the token -> 200
#   4. closing stdin makes the core exit 0 within 10 s
# Exits 0 when all pass. On failure prints the core's stdout/stderr tail and exits 1.
# Never touches ~/.config/rmirror.

set -euo pipefail

if [ $# -ne 1 ]; then
    sed -n '3,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
    exit 2
fi

CORE="$1"
PORT="${SMOKE_PORT:-5599}"

if [ ! -x "$CORE" ]; then
    echo "smoke_core: not an executable: $CORE" >&2
    exit 2
fi
if ! command -v curl >/dev/null 2>&1; then
    echo "smoke_core: curl is required" >&2
    exit 2
fi
if curl -s -o /dev/null --max-time 2 "http://127.0.0.1:$PORT/health"; then
    echo "smoke_core: something already answers on 127.0.0.1:$PORT; set SMOKE_PORT to a free port" >&2
    exit 2
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/rmirror-core-smoke.XXXXXX")"
CORE_PID=""

cleanup() {
    exec 3>&- 2>/dev/null || true
    if [ -n "$CORE_PID" ] && kill -0 "$CORE_PID" 2>/dev/null; then
        kill -TERM "$CORE_PID" 2>/dev/null || true
        sleep 2
        kill -KILL "$CORE_PID" 2>/dev/null || true
    fi
    # $WORK comes from mktemp above; never empty or /
    case "$WORK" in
        */rmirror-core-smoke.*) rm -rf "$WORK" ;;
    esac
}
trap cleanup EXIT

fail() {
    echo "smoke_core: FAIL: $*" >&2
    echo "--- core stdout (tail) ---" >&2
    tail -n 30 "$WORK/stdout" >&2 2>/dev/null || true
    echo "--- core stderr (tail) ---" >&2
    tail -n 30 "$WORK/stderr" >&2 2>/dev/null || true
    echo "--- agent.log (tail) ---" >&2
    tail -n 30 "$WORK/home/.config/rmirror/agent.log" >&2 2>/dev/null || true
    exit 1
}

mkdir -p "$WORK/home" "$WORK/remarkable"
cat > "$WORK/config.yaml" <<EOF
api:
  url: http://127.0.0.1:9/api/v1
web:
  port: $PORT
  auto_launch_browser: false
remarkable:
  source_directory: $WORK/remarkable
EOF

TOKEN="$(openssl rand -hex 32)"
mkfifo "$WORK/stdin"

# The core blocks opening the FIFO until the write end below is opened.
env -i \
    HOME="$WORK/home" \
    PATH="/usr/bin:/bin:/usr/sbin:/sbin" \
    TMPDIR="$WORK" \
    LANG="en_US.UTF-8" \
    RMIRROR_CONFIG_PATH="$WORK/config.yaml" \
    PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring" \
    RMIRROR_APP_TOKEN="$TOKEN" \
    "$CORE" --headless < "$WORK/stdin" > "$WORK/stdout" 2> "$WORK/stderr" &
CORE_PID=$!
exec 3> "$WORK/stdin"

# 1. Ready line
READY_LINE="RMIRROR_CORE_READY port=$PORT api=2"
for _ in $(seq 1 120); do
    if grep -qx "$READY_LINE" "$WORK/stdout" 2>/dev/null; then
        break
    fi
    if ! kill -0 "$CORE_PID" 2>/dev/null; then
        wait "$CORE_PID" && code=0 || code=$?
        fail "core exited with code $code before the ready line"
    fi
    sleep 0.5
done
grep -qx "$READY_LINE" "$WORK/stdout" || fail "no ready line within 60 s"
echo "smoke_core: ready line: $READY_LINE"

# 2. /health
code="$(curl -s -o "$WORK/health.json" -w '%{http_code}' --max-time 10 "http://127.0.0.1:$PORT/health")" || true
[ "$code" = "200" ] || fail "/health returned $code"
echo "smoke_core: /health -> $code"

# 3. /api/v2/state without and with the app token
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://127.0.0.1:$PORT/api/v2/state")" || true
[ "$code" = "401" ] || fail "/api/v2/state without token returned $code (expected 401)"
echo "smoke_core: /api/v2/state without token -> $code"
code="$(curl -s -o "$WORK/state.json" -w '%{http_code}' --max-time 20 \
    -H "X-RMirror-App-Token: $TOKEN" "http://127.0.0.1:$PORT/api/v2/state")" || true
[ "$code" = "200" ] || fail "/api/v2/state with token returned $code (expected 200)"
CORE_VERSION="$(plutil -extract core_version raw -o - "$WORK/state.json" 2>/dev/null || echo '?')"
echo "smoke_core: /api/v2/state with token -> $code (core_version $CORE_VERSION)"

# 4. stdin EOF -> clean exit 0
exec 3>&-
for _ in $(seq 1 20); do
    kill -0 "$CORE_PID" 2>/dev/null || break
    sleep 0.5
done
if kill -0 "$CORE_PID" 2>/dev/null; then
    fail "core still running 10 s after stdin EOF"
fi
wait "$CORE_PID" && code=0 || code=$?
CORE_PID=""
[ "$code" = "0" ] || fail "core exited with $code after stdin EOF (expected 0)"
echo "smoke_core: exit after stdin EOF -> $code"
echo "smoke_core: PASS"
