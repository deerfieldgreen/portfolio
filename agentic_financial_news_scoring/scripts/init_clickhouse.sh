#!/usr/bin/env bash
# Initialize ClickHouse for news_agent: user, database, tables.
# Requires CLICKHOUSE_PASSWORD in env (same value the app uses). No secrets in repo.
#
# Mode 1 – Remote: set CLICKHOUSE_HOST (and PORT, USERNAME, PASSWORD, SECURE) in env
#   (e.g. via Doppler). Script connects to that host and runs the SQL. No Docker.
# Mode 2 – Local: unset or localhost/clickhouse. Starts Docker Compose, then runs SQL in container.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT_DIR"

if [[ -z "${CLICKHOUSE_PASSWORD:-}" ]]; then
  echo "CLICKHOUSE_PASSWORD must be set (same value as for the app)."
  exit 1
fi

# Use remote ClickHouse from env when host is set and not local/docker
USE_REMOTE=
if [[ -n "${CLICKHOUSE_HOST:-}" ]]; then
  case "${CLICKHOUSE_HOST}" in
    localhost|127.0.0.1|clickhouse) ;;
    *) USE_REMOTE=1 ;;
  esac
fi

if [[ -n "$USE_REMOTE" ]]; then
  for v in CLICKHOUSE_HOST CLICKHOUSE_PORT CLICKHOUSE_USERNAME CLICKHOUSE_PASSWORD; do
    if [[ -z "${!v:-}" ]]; then
      echo "Remote mode requires $v in env."
      exit 1
    fi
  done
  SCHEME="http"
  if [[ "${CLICKHOUSE_SECURE:-}" =~ ^(true|1|yes)$ ]]; then
    SCHEME="https"
  fi
  PORT="${CLICKHOUSE_PORT:-8123}"
  BASE_URL="${SCHEME}://${CLICKHOUSE_HOST}:${PORT}"
  echo "Connecting to ClickHouse at $BASE_URL (user: $CLICKHOUSE_USERNAME)"

  # ClickHouse HTTP does not allow multi-statement; send one statement per request.
  # Split when a non-comment line ends with ";".
  run_sql_remote() {
    local f="$1"
    echo "Running $f..."
    local sql
    sql=$(envsubst < "$f")
    local stmt=""
    while IFS= read -r line; do
      [[ -n "$stmt" ]] && stmt+=$'\n'
      stmt+="$line"
      local trimmed
      trimmed=$(echo "$line" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
      if [[ -n "$trimmed" && "$trimmed" != --* && "$trimmed" == *";" ]]; then
        echo "$stmt" | curl -sS -f --connect-timeout 10 --max-time 60 \
          -u "${CLICKHOUSE_USERNAME}:${CLICKHOUSE_PASSWORD}" \
          -X POST "${BASE_URL}/" \
          --data-binary @- || { echo "Statement failed."; return 1; }
        stmt=""
      fi
    done < <(echo "$sql")
    if [[ -n "${stmt}" ]]; then
      trimmed=$(echo "$stmt" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
      if [[ -n "$trimmed" && "$trimmed" != --* ]]; then
        echo "$stmt" | curl -sS -f --connect-timeout 10 --max-time 60 \
          -u "${CLICKHOUSE_USERNAME}:${CLICKHOUSE_PASSWORD}" \
          -X POST "${BASE_URL}/" \
          --data-binary @- || { echo "Statement failed."; return 1; }
      fi
    fi
  }

  run_sql_remote "$SCRIPT_DIR/01_create_user_database.sql"
  run_sql_remote "$SCRIPT_DIR/02_create_tables.sql"
  run_sql_remote "$SCRIPT_DIR/03_add_score_columns.sql"
  echo "news_agent ClickHouse init complete (remote)."
  exit 0
fi

# Local: Docker Compose
COMPOSE="${COMPOSE_CMD:-docker compose}"
echo "Starting ClickHouse..."
$COMPOSE up -d clickhouse

echo "Waiting for ClickHouse..."
until curl -sf http://localhost:8123 > /dev/null 2>&1; do
  sleep 2
done
echo "ClickHouse is up."

export CLICKHOUSE_PASSWORD
run_sql() {
  local f="$1"
  echo "Running $f..."
  envsubst < "$f" | $COMPOSE exec -T clickhouse clickhouse-client --multiquery
}

run_sql "$SCRIPT_DIR/01_create_user_database.sql"
run_sql "$SCRIPT_DIR/02_create_tables.sql"
run_sql "$SCRIPT_DIR/03_add_score_columns.sql"

echo "news_agent ClickHouse init complete (local)."
