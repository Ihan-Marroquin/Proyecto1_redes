import assert from "node:assert/strict";
import test from "node:test";

import { MCPApplication, PROTOCOL_VERSION } from "../src/app.js";

class MemoryStorage {
  constructor() {
    this.values = new Map();
  }

  async get(key) {
    return structuredClone(this.values.get(key));
  }

  async put(key, value) {
    this.values.set(key, structuredClone(value));
  }
}

function request(method, body = null, extraHeaders = {}) {
  const headers = new Headers({
    Accept: "application/json, text/event-stream",
    Authorization: "Bearer test-token",
    ...extraHeaders,
  });
  if (body !== null) headers.set("Content-Type", "application/json");
  return new Request("https://example.workers.dev/mcp", {
    method,
    headers,
    body: body === null ? null : JSON.stringify(body),
  });
}

async function initialize(application) {
  const response = await application.handle(
    request("POST", {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: { name: "test", version: "1.0.0" },
      },
    }),
  );
  assert.equal(response.status, 200);
  const sessionId = response.headers.get("MCP-Session-Id");
  assert.ok(sessionId);
  return sessionId;
}

function sessionHeaders(sessionId) {
  return {
    "MCP-Session-Id": sessionId,
    "MCP-Protocol-Version": PROTOCOL_VERSION,
  };
}

test("health endpoint does not require authentication", async () => {
  const application = new MCPApplication(new MemoryStorage(), { MCP_AUTH_TOKEN: "test-token" });
  const response = await application.handle(new Request("https://example.workers.dev/health"));
  assert.equal(response.status, 200);
  const payload = await response.json();
  assert.equal(payload.status, "ok");
  assert.equal(payload.platform, "cloudflare-workers");
});

test("remote lifecycle lists and calls tools", async () => {
  const application = new MCPApplication(new MemoryStorage(), { MCP_AUTH_TOKEN: "test-token" });
  const sessionId = await initialize(application);

  let response = await application.handle(
    request(
      "POST",
      { jsonrpc: "2.0", method: "notifications/initialized" },
      sessionHeaders(sessionId),
    ),
  );
  assert.equal(response.status, 202);

  response = await application.handle(
    request(
      "POST",
      { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} },
      sessionHeaders(sessionId),
    ),
  );
  assert.equal(response.status, 200);
  let payload = await response.json();
  assert.equal(payload.result.tools.length, 6);

  response = await application.handle(
    request(
      "POST",
      {
        jsonrpc: "2.0",
        id: 3,
        method: "tools/call",
        params: { name: "list_machines", arguments: { status: "warning" } },
      },
      sessionHeaders(sessionId),
    ),
  );
  payload = await response.json();
  assert.equal(payload.result.structuredContent.count, 1);
  assert.equal(payload.result.structuredContent.machines[0].machine_id, "SELL-01");

  response = await application.handle(request("DELETE", null, sessionHeaders(sessionId)));
  assert.equal(response.status, 204);
});

test("tools are rejected until initialization completes", async () => {
  const application = new MCPApplication(new MemoryStorage(), { MCP_AUTH_TOKEN: "test-token" });
  const sessionId = await initialize(application);
  const response = await application.handle(
    request(
      "POST",
      { jsonrpc: "2.0", id: 2, method: "tools/list", params: {} },
      sessionHeaders(sessionId),
    ),
  );
  const payload = await response.json();
  assert.equal(payload.error.code, -32002);
});

test("write tools persist work orders", async () => {
  const storage = new MemoryStorage();
  const application = new MCPApplication(storage, { MCP_AUTH_TOKEN: "test-token" });
  const sessionId = await initialize(application);
  await application.handle(
    request(
      "POST",
      { jsonrpc: "2.0", method: "notifications/initialized" },
      sessionHeaders(sessionId),
    ),
  );

  let response = await application.handle(
    request(
      "POST",
      {
        jsonrpc: "2.0",
        id: 2,
        method: "tools/call",
        params: {
          name: "create_work_order",
          arguments: {
            machine_id: "SELL-01",
            issue: "Inspect sealing resistance",
            priority: "high",
          },
        },
      },
      sessionHeaders(sessionId),
    ),
  );
  let payload = await response.json();
  assert.equal(payload.result.structuredContent.work_order.work_order_id, "WO-0002");

  response = await application.handle(
    request(
      "POST",
      {
        jsonrpc: "2.0",
        id: 3,
        method: "tools/call",
        params: { name: "list_work_orders", arguments: { machine_id: "SELL-01" } },
      },
      sessionHeaders(sessionId),
    ),
  );
  payload = await response.json();
  assert.equal(payload.result.structuredContent.count, 1);
});

test("authentication and browser origin are enforced", async () => {
  const application = new MCPApplication(new MemoryStorage(), {
    MCP_AUTH_TOKEN: "test-token",
    MCP_ALLOWED_ORIGINS: "https://allowed.example",
  });
  let response = await application.handle(
    new Request("https://example.workers.dev/mcp", {
      method: "POST",
      headers: {
        Accept: "application/json, text/event-stream",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ jsonrpc: "2.0", id: 1, method: "initialize", params: {} }),
    }),
  );
  assert.equal(response.status, 401);

  response = await application.handle(
    request(
      "POST",
      { jsonrpc: "2.0", id: 1, method: "initialize", params: {} },
      { Origin: "https://blocked.example" },
    ),
  );
  assert.equal(response.status, 403);
});
