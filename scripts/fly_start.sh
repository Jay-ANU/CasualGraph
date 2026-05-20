#!/bin/sh
set -eu

PORT="${PORT:-8000}"

if [ "${REDIS_ENABLED:-false}" = "true" ]; then
  if [ -z "${REDIS_PASSWORD:-}" ]; then
    echo "REDIS_ENABLED=true requires REDIS_PASSWORD" >&2
    exit 1
  fi

  REDIS_DATA_DIR="${REDIS_DATA_DIR:-/data/redis}"
  REDIS_BIND="${REDIS_BIND:-127.0.0.1}"
  REDIS_PORT="${REDIS_PORT:-6379}"
  mkdir -p "$REDIS_DATA_DIR"

  redis-server \
    --appendonly yes \
    --appendfilename appendonly.aof \
    --dir "$REDIS_DATA_DIR" \
    --bind "$REDIS_BIND" \
    --port "$REDIS_PORT" \
    --protected-mode yes \
    --requirepass "$REDIS_PASSWORD" \
    --daemonize yes

  export REDIS_URL="${REDIS_URL:-redis://:${REDIS_PASSWORD}@127.0.0.1:${REDIS_PORT}/0}"

  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if redis-cli -h "$REDIS_BIND" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" ping >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
fi

exec uvicorn app:app --host 0.0.0.0 --port "$PORT"
