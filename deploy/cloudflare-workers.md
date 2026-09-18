# Cloudflare Workers deployment

This deployment target exposes the same manual MCP server through a free
`workers.dev` URL. It uses a SQLite-backed Durable Object for MCP sessions and
maintenance data. No MCP SDK is used.

## Requirements

- A Cloudflare account on the Workers Free plan.
- Node.js 20 or newer.
- The repository cloned locally.

## Install and authenticate

From PowerShell:

```powershell
cd cloudflare
npm install
npm test
npx wrangler login
```

The login command opens a browser. Approve Wrangler's access to the Cloudflare
account, then return to PowerShell.

## First deployment

```powershell
npx wrangler deploy
```

On the first deployment, Cloudflare may ask to create a free `workers.dev`
subdomain. Accept the prompt and copy the deployed URL.

## Configure the Bearer token

Generate a private token without printing it:

```powershell
$McpToken = [Convert]::ToHexString(
  [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
).ToLower()
Set-Clipboard $McpToken
```

Store it as an encrypted Worker secret:

```powershell
npx wrangler secret put MCP_AUTH_TOKEN
```

Paste the token when Wrangler prompts for the secret value. Do not commit it.

## Verify the deployed service

Set the URL returned by Wrangler, without a trailing slash:

```powershell
$WorkerUrl = "https://industrial-maintenance-mcp.YOUR_SUBDOMAIN.workers.dev"
Invoke-RestMethod "$WorkerUrl/health"

cd ..
$env:MCP_REMOTE_URL = "$WorkerUrl/mcp"
$env:MCP_AUTH_TOKEN = $McpToken
python -m scripts.verify_remote
```

Expected verification output:

```text
PASS initialize: MCP 2025-11-25
PASS tools/list: 6 tools
PASS tools/call: 1 warning machine(s)
```

The same environment variables allow the chatbot to use the remote Worker:

```powershell
python -m src.chatbot --config config/servers_remote.json
```

## Endpoints and persistence

- `GET /health`: public health check.
- `POST /mcp`: authenticated JSON-RPC messages.
- `GET /mcp`: returns `405` because this server does not need a standalone SSE stream.
- `DELETE /mcp`: closes the session from `MCP-Session-Id`.

MCP sessions and maintenance data are stored in one SQLite-backed Durable Object.
The token is stored as a Cloudflare encrypted secret. The Worker also supports an
optional comma-separated `MCP_ALLOWED_ORIGINS` variable for browser clients.

## Local checks

The protocol and persistence tests do not require a Cloudflare account:

```powershell
cd cloudflare
npm test
npm run check
```
