#!/usr/bin/env bash
# Start a local Redis WITHOUT Docker — for native Windows dev where Docker
# isn't available. No-op on macOS/Linux/Docker setups (use the compose file
# there: `docker compose -f docker-compose.infra.yml up -d redis`).
#
# Why a standalone Windows Redis 8 build:
#   * redis-py 8 (the backend's client) performs a RESP3 `HELLO` handshake on
#     connect, which requires Redis >= 6.0 — the old tporadowski Windows port
#     (Redis 5.0.x) rejects `HELLO` and the backend logs "redis unavailable".
#   * We bind BOTH 127.0.0.1 and ::1 because on Windows `localhost` often
#     resolves to IPv6 ::1 first; binding only IPv4 makes localhost flaky.
#
# The backend only probes Redis once (get_redis caches availability), so after
# starting Redis you MUST restart the backend for the scan worker to pick it up.
set -euo pipefail

REDIS_HOME="${REDIS_HOME:-C:/Users/Admin/dev/tools/redis8/Redis-8.8.0-Windows-x64-msys2}"
PORT="${REDIS_PORT:-6379}"

if command -v redis-cli >/dev/null 2>&1 && redis-cli -p "$PORT" ping >/dev/null 2>&1; then
  echo "[start-redis] Redis already responding on :$PORT — nothing to do."
  exit 0
fi
if [ -x "$REDIS_HOME/redis-cli.exe" ] && "$REDIS_HOME/redis-cli.exe" -p "$PORT" ping >/dev/null 2>&1; then
  echo "[start-redis] Redis already responding on :$PORT — nothing to do."
  exit 0
fi

if [ ! -x "$REDIS_HOME/redis-server.exe" ]; then
  echo "[start-redis] redis-server.exe not found under $REDIS_HOME" >&2
  echo "  Download Redis 8 for Windows (redis-windows/redis-windows releases)" >&2
  echo "  or set REDIS_HOME to your install." >&2
  exit 1
fi

echo "[start-redis] Launching Redis 8 on 127.0.0.1:$PORT and [::1]:$PORT ..."
cd "$REDIS_HOME"
# --save ""/--appendonly no: ephemeral cache+queue store, no disk persistence.
nohup ./redis-server.exe --port "$PORT" --bind "127.0.0.1 ::1" \
  --save "" --appendonly no --protected-mode no > "$REDIS_HOME/redis.log" 2>&1 &
sleep 2
if "$REDIS_HOME/redis-cli.exe" -p "$PORT" ping >/dev/null 2>&1; then
  echo "[start-redis] Redis is up (PING ok). Now restart the backend so it reconnects."
else
  echo "[start-redis] Redis did not respond — check $REDIS_HOME/redis.log" >&2
  exit 1
fi
