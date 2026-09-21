# CC3067 Project 1 - Manual MCP Chatbot

This project is a console chatbot that connects an Anthropic language model to local
and remote Model Context Protocol (MCP) servers. The MCP lifecycle and JSON-RPC 2.0
messages are implemented manually with the Python standard library; the project does
not use FastMCP or an MCP SDK.

The custom server models an industrial maintenance system for a beverage plant. It can
inspect machines, spare parts, and work orders. Actions that change data require user
confirmation in the chatbot.

## Features

- Anthropic Messages API integration and in-session conversation context.
- Manual MCP clients for local `stdio` and remote Streamable HTTP transports.
- Official Filesystem and Git MCP servers for local demonstrations.
- A custom maintenance server with six tools.
- JSON Lines logs for MCP requests, notifications, responses, and diagnostics.
- Bearer authentication, Origin validation, sessions, and protocol-version checks for
  the remote server.
- Docker and Google Cloud Run deployment files.
- Automated tests that do not consume Anthropic API credits.
- A reproducible Wireshark procedure for application and network-layer analysis.

## Architecture

```text
                         Anthropic Messages API
                                  |
                         Console chatbot host
                         /                  \
              manual stdio client      manual HTTP client
                  /      |      \                |
       maintenance  filesystem  git    maintenance server
          local       official official     remote /mcp
```

The local and remote maintenance entry points share the same `MaintenanceService` and
JSON-RPC `MCPServer` implementation. Only their transport layer differs.

## Requirements

- Python 3.11 or newer.
- Git.
- Node.js 22 or newer and `npx` for the official Filesystem server.
- `uvx` for the official Git server.
- An Anthropic API key for the interactive chatbot.
- Docker only when building the remote container locally.
- Wireshark with Npcap loopback support for the packet-analysis evidence.

This repository intentionally has no Python package dependencies at runtime.

## Initial setup

Create a local environment file and add your Anthropic key:

```powershell
Copy-Item .env.example .env
notepad .env
```

```env
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-haiku-4-5-20251001
```

Never commit `.env`; it is already ignored by Git.

## Run the chatbot with local MCP servers

```powershell
python -m src.chatbot
```

or:

```powershell
./run.ps1
```

The default configuration starts:

- `maintenance`: this project's custom stdio server.
- `filesystem`: the official Filesystem server restricted to `demo_workspace/`.
- `git`: the official Git server restricted to the same demonstration repository.

Available chatbot commands:

- `/servers`: show connected and unavailable MCP servers.
- `/tools`: show tools exposed to the model.
- `/logs 20`: show the latest MCP log entries.
- `/clear`: clear conversation context.
- `/exit`: close connections and exit.

## Run the Streamable HTTP server locally

Terminal 1:

```powershell
./run_http.ps1
```

The script uses `http://127.0.0.1:8000/mcp`, an ignored local data file, and the
disposable token `local-demo-token`.

Terminal 2:

```powershell
$env:MCP_REMOTE_URL = "http://127.0.0.1:8000/mcp"
$env:MCP_AUTH_TOKEN = "local-demo-token"
python -m scripts.verify_remote
```

Expected output:

```text
PASS initialize: MCP 2025-11-25
PASS tools/list: 6 tools
PASS tools/call: 1 warning machine(s)
```

To connect the chatbot to this remote transport instead of the local servers:

```powershell
python -m src.chatbot --config config/servers_remote.json
```

## Remote MCP endpoint

The server implements the JSON response form of MCP Streamable HTTP:

| Method and path | Purpose |
| --- | --- |
| `GET /health` | Deployment health check |
| `POST /mcp` | Send one JSON-RPC request or notification |
| `GET /mcp` | Returns `405`; a standalone SSE stream is not needed |
| `DELETE /mcp` | Terminate the current MCP session |

Initialization returns `MCP-Session-Id`. Later requests must include that value and
`MCP-Protocol-Version: 2025-11-25`. The server accepts a native client without an
`Origin` header, but a browser Origin must appear in `MCP_ALLOWED_ORIGINS`.

For any non-local deployment, set a long random `MCP_AUTH_TOKEN`. The client sends it
as `Authorization: Bearer <token>`.

## Deploy to Google Cloud Run

The root `Dockerfile` runs the HTTP service as a non-root user and listens on Cloud
Run's `PORT`. Follow [`deploy/cloud-run.md`](deploy/cloud-run.md) to deploy from Cloud
Shell, configure the token, retrieve the URL, and verify the live endpoint.

The demonstration stores work orders in the container's ephemeral filesystem. A
production version should use a transactional database before enabling multiple
instances.

## Maintenance tools

| Tool | Purpose | Writes data |
| --- | --- | --- |
| `list_machines` | List all machines or filter by status | No |
| `get_machine_status` | Read one machine record | No |
| `list_work_orders` | List and filter maintenance orders | No |
| `check_spare_part` | Search inventory and calculate reorder status | No |
| `create_work_order` | Create a maintenance order | Yes |
| `close_work_order` | Close an open order with a resolution | Yes |

Example prompts:

```text
Which machines have a warning?
Is a sealing resistance available for SELL-01?
Create a high-priority order to inspect the resistance on SELL-01.
```

## Tests and verification

Run the complete standard-library test suite:

```powershell
python -m unittest discover -s tests -v
```

Verify every server in a configuration without using the LLM API:

```powershell
python -m scripts.verify_servers
python -m scripts.verify_remote
```

The local official-server check requires both `npx` and `uvx`. The remote verifier only
requires Python and a running endpoint.

## Wireshark analysis

[`docs/WIRESHARK_ANALYSIS.md`](docs/WIRESHARK_ANALYSIS.md) provides the exact capture
setup, display filters, deterministic message sequence, JSON-RPC classification, and
analysis of the link, network, transport, and application layers.

Use a local loopback capture to inspect unencrypted JSON-RPC and a separate Cloud Run
capture to demonstrate DNS, TCP, and TLS. Never publish a production token in a packet
capture.

## Reports

- [`docs/Reporte_Proyecto_1.pdf`](docs/Reporte_Proyecto_1.pdf): final technical report
  covering the server specification, Wireshark analysis, and conclusions.
- [`docs/Reporte_Entrega_1.pdf`](docs/Reporte_Entrega_1.pdf): original first-delivery
  report retained for history.
- [`ENTREGA_1.md`](ENTREGA_1.md): detailed notes for the first delivery.

## Repository safety

- `.env`, local data, MCP logs, virtual environments, and the demo Git repository are
  ignored.
- Filesystem and Git demonstrations are restricted to `demo_workspace/`.
- The host asks for confirmation before write-oriented tools.
- Remote sessions use a cryptographically random identifier and can be terminated with
  `DELETE /mcp`.
