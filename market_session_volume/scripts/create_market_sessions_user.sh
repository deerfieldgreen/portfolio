#!/usr/bin/env bash
# Create ClickHouse user for market session volume pipeline.
# Generates a secure password, outputs CREATE USER SQL, and pushes to Doppler.
#
# Usage: CLICKHOUSE_DATABASE=... CLICKHOUSE_USERNAME=... ./scripts/create_market_sessions_user.sh [dev|prd]
# Run from argo_pipelines/market_session_volume or repo root.
#
# 1. Run this script - it generates a password and CREATE USER SQL
# 2. Execute the SQL against your ClickHouse (clickhouse-client or HTTP)
# 3. Script pushes CLICKHOUSE_USERNAME and CLICKHOUSE_PASSWORD to Doppler

set -euo pipefail

CONFIG="${1:-dev}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PIPELINE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT="market_session_volume"

: "${CLICKHOUSE_DATABASE:?CLICKHOUSE_DATABASE required}"
: "${CLICKHOUSE_USERNAME:?CLICKHOUSE_USERNAME required}"

if [[ "$CONFIG" != "dev" && "$CONFIG" != "prd" ]]; then
  echo "Usage: $0 [dev|prd]"
  exit 1
fi

# Generate 32-byte base64 password (URL-safe, no special chars that need escaping)
PASSWORD=$(openssl rand -base64 32 | tr -d '\n/+=' | head -c 40)

echo "=============================================="
echo "ClickHouse user: $CLICKHOUSE_USERNAME"
echo "Database: $CLICKHOUSE_DATABASE"
echo "=============================================="
echo ""
echo "1. Run this SQL in ClickHouse (as admin):"
echo ""
cat <<SQL
CREATE USER IF NOT EXISTS ${CLICKHOUSE_USERNAME}
  IDENTIFIED BY '${PASSWORD}';

-- Read ohlcv_data, insert into ml_* tables (run create_ml_tables.sql first)
GRANT SELECT, INSERT ON ${CLICKHOUSE_DATABASE}.* TO ${CLICKHOUSE_USERNAME};

SQL
echo ""
echo "2. Pushing to Doppler (project=$PROJECT config=$CONFIG)..."
echo ""

if ! command -v doppler >/dev/null 2>&1; then
  echo "Doppler CLI not found. Install: brew install dopplerhq/cli/doppler"
  echo ""
  echo "Then run manually:"
  echo "  export CLICKHOUSE_USERNAME=$CLICKHOUSE_USERNAME"
  echo "  export CLICKHOUSE_PASSWORD='${PASSWORD}'"
  echo "  cd $PIPELINE_DIR && ./doppler/push.sh $CONFIG"
  exit 0
fi

if echo "$PASSWORD" | doppler secrets set CLICKHOUSE_PASSWORD --project "$PROJECT" --config "$CONFIG" 2>/dev/null && \
   echo "$CLICKHOUSE_USERNAME" | doppler secrets set CLICKHOUSE_USERNAME --project "$PROJECT" --config "$CONFIG" 2>/dev/null; then
  echo ""
  echo "Done. CLICKHOUSE_USERNAME=$CLICKHOUSE_USERNAME and CLICKHOUSE_PASSWORD have been set in Doppler."
else
  echo "Doppler push failed (token not configured?). Run manually:"
  echo "  export CLICKHOUSE_USERNAME=$CLICKHOUSE_USERNAME"
  echo "  export CLICKHOUSE_PASSWORD='${PASSWORD}'"
  echo "  cd $PIPELINE_DIR && ./doppler/push.sh $CONFIG"
fi
echo ""
echo "Run run_create_ml_tables.py (with CLICKHOUSE_DATABASE set) if the ml_* tables do not exist yet."
