#!/usr/bin/env sh
set -eu

: "${MAINTENANCE_DATA_PATH:=data/maintenance.local.json}"
: "${MCP_AUTH_TOKEN:=local-demo-token}"
export MAINTENANCE_DATA_PATH MCP_AUTH_TOKEN

if [ "$MCP_AUTH_TOKEN" = "local-demo-token" ]; then
  echo "Using the local demonstration token: local-demo-token"
fi

python3 -m src.http_server
