#!/usr/bin/env bash
set -euo pipefail

# Push secrets to Doppler for fx-swarm
# Usage: ./push.sh <environment>
# Example: ./push.sh dev

ENV="${1:?Usage: ./push.sh <dev|prd>}"
ENV_FILE="env.${ENV}"

if [ ! -f "$ENV_FILE" ]; then
    echo "Error: $ENV_FILE not found"
    echo "Copy env.example to $ENV_FILE and fill in values"
    exit 1
fi

doppler secrets upload "$ENV_FILE" \
    --project data-science-swarm \
    --config "$ENV"

echo "Secrets pushed to Doppler (data-science-swarm / $ENV)"
