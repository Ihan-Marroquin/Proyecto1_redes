$ErrorActionPreference = "Stop"

if (-not $env:MAINTENANCE_DATA_PATH) {
    $env:MAINTENANCE_DATA_PATH = "data/maintenance.local.json"
}
if (-not $env:MCP_AUTH_TOKEN) {
    $env:MCP_AUTH_TOKEN = "local-demo-token"
    Write-Host "Using the local demonstration token: local-demo-token"
}

python -m src.http_server
