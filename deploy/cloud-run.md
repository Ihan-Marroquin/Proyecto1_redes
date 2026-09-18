# Google Cloud Run deployment

The remote server is a standard-library Python service packaged by the root
`Dockerfile`. It exposes:

- `GET /health`: deployment health check.
- `POST /mcp`: MCP Streamable HTTP messages.
- `GET /mcp`: returns `405` because this server does not need a standalone SSE stream.
- `DELETE /mcp`: closes the session identified by `MCP-Session-Id`.

## Deploy from Cloud Shell

Choose a project and a region, then create a strong application token. The service is
public at the Cloud Run network layer so that the course chatbot can reach it, while
the MCP endpoint itself requires the Bearer token.

```bash
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

export MCP_TOKEN="$(openssl rand -hex 32)"
gcloud run deploy industrial-maintenance-mcp \
  --source . \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "MCP_AUTH_TOKEN=${MCP_TOKEN}" \
  --memory 256Mi \
  --min-instances 0 \
  --max-instances 1
```

Keep the generated token private. Obtain the service URL with:

```bash
gcloud run services describe industrial-maintenance-mcp \
  --region us-central1 \
  --format='value(status.url)'
```

The MCP URL is the returned service URL plus `/mcp`. Verify it before configuring the
chatbot:

```bash
export MCP_REMOTE_URL="https://YOUR_SERVICE_URL/mcp"
export MCP_AUTH_TOKEN="$MCP_TOKEN"
python -m scripts.verify_remote
python -m src.chatbot --config config/servers_remote.json
```

## Persistence note

The demonstration container initializes the sample dataset in `/tmp` on first start.
Cloud Run's writable filesystem is ephemeral, so created work orders survive requests
to the same warm instance but not an instance replacement. That behavior is sufficient
for the class demonstration. A production implementation should replace the JSON file
with a transactional database and allow more than one instance.

## Local container check

```bash
docker build -t maintenance-mcp .
docker run --rm -p 8080:8080 \
  -e MCP_AUTH_TOKEN=local-container-token \
  maintenance-mcp
```

In another terminal:

```bash
MCP_REMOTE_URL=http://127.0.0.1:8080/mcp \
MCP_AUTH_TOKEN=local-container-token \
python -m scripts.verify_remote
```
