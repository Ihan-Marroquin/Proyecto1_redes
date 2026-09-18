export const PROTOCOL_VERSION = "2025-11-25";

const MAX_REQUEST_BYTES = 1_048_576;
const DATA_KEY = "maintenance-data";
const SESSIONS_KEY = "mcp-sessions";

const DEFAULT_DATA = {
  machines: [
    {
      machine_id: "SELL-01",
      name: "Beverage cup sealer",
      area: "Packaging line 1",
      status: "warning",
      temperature_c: 184.5,
      cycles: 18427,
      last_maintenance: "2026-08-02",
      next_maintenance: "2026-08-25",
      notes: "Inspect sealing resistance before the next production shift.",
    },
    {
      machine_id: "PUMP-02",
      name: "Sanitary transfer pump",
      area: "Mixing area",
      status: "operational",
      temperature_c: 42.1,
      hours: 730,
      last_maintenance: "2026-07-28",
      next_maintenance: "2026-09-28",
      notes: "No active alerts.",
    },
    {
      machine_id: "COMP-01",
      name: "Pneumatic line compressor",
      area: "Utilities room",
      status: "maintenance",
      temperature_c: 51.8,
      hours: 1520,
      last_maintenance: "2026-08-18",
      next_maintenance: "2026-10-18",
      notes: "Oil filter replacement in progress.",
    },
  ],
  spare_parts: [
    {
      part_number: "RES-220V-400W",
      name: "Sealing resistance 220 V / 400 W",
      quantity: 2,
      minimum_stock: 1,
      location: "Shelf A-03",
      compatible_machines: ["SELL-01"],
    },
    {
      part_number: "GASKET-P02",
      name: "Food-grade pump gasket",
      quantity: 5,
      minimum_stock: 3,
      location: "Shelf B-07",
      compatible_machines: ["PUMP-02"],
    },
    {
      part_number: "FILTER-C01",
      name: "Compressor oil filter",
      quantity: 0,
      minimum_stock: 2,
      location: "Shelf C-02",
      compatible_machines: ["COMP-01"],
    },
  ],
  work_orders: [
    {
      work_order_id: "WO-0001",
      machine_id: "COMP-01",
      issue: "Replace oil filter and inspect lubrication circuit.",
      priority: "high",
      status: "open",
      created_at: "2026-08-18T14:00:00+00:00",
      resolution: null,
      closed_at: null,
    },
  ],
};

export const TOOLS = [
  {
    name: "list_machines",
    title: "List industrial machines",
    description:
      "Lists registered machines and optionally filters by status. This tool does not modify data.",
    inputSchema: {
      type: "object",
      properties: {
        status: {
          type: "string",
          enum: ["operational", "warning", "stopped", "maintenance"],
        },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false },
  },
  {
    name: "get_machine_status",
    title: "Get machine status",
    description: "Returns the complete operational record for one machine.",
    inputSchema: {
      type: "object",
      properties: { machine_id: { type: "string" } },
      required: ["machine_id"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false },
  },
  {
    name: "list_work_orders",
    title: "List maintenance work orders",
    description: "Lists maintenance work orders and optionally filters them.",
    inputSchema: {
      type: "object",
      properties: {
        machine_id: { type: "string" },
        status: { type: "string", enum: ["open", "closed"] },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false },
  },
  {
    name: "check_spare_part",
    title: "Check spare-part inventory",
    description: "Searches spare parts and indicates whether a reorder is recommended.",
    inputSchema: {
      type: "object",
      properties: { query: { type: "string", minLength: 1 } },
      required: ["query"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true, destructiveHint: false },
  },
  {
    name: "create_work_order",
    title: "Create a maintenance work order",
    description: "Creates a work order after explicit user confirmation in the host.",
    inputSchema: {
      type: "object",
      properties: {
        machine_id: { type: "string" },
        issue: { type: "string", minLength: 5 },
        priority: {
          type: "string",
          enum: ["low", "medium", "high", "critical"],
        },
      },
      required: ["machine_id", "issue", "priority"],
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
    },
  },
  {
    name: "close_work_order",
    title: "Close a maintenance work order",
    description: "Closes an open work order and stores its resolution.",
    inputSchema: {
      type: "object",
      properties: {
        work_order_id: { type: "string" },
        resolution: { type: "string", minLength: 5 },
      },
      required: ["work_order_id", "resolution"],
      additionalProperties: false,
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
    },
  },
];

function clone(value) {
  return structuredClone(value);
}

function isObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function rpcResponse(id, result) {
  return { jsonrpc: "2.0", id, result };
}

function rpcError(id, code, message) {
  return { jsonrpc: "2.0", id, error: { code, message } };
}

function toolResult(payload, isError = false) {
  return {
    content: [{ type: "text", text: JSON.stringify(payload, null, 2) }],
    structuredContent: payload,
    isError,
  };
}

function headers(sessionId = null) {
  const result = new Headers({
    "Cache-Control": "no-store",
    "Content-Type": "application/json; charset=utf-8",
  });
  if (sessionId) result.set("MCP-Session-Id", sessionId);
  return result;
}

function jsonResponse(status, payload, sessionId = null) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: headers(sessionId),
  });
}

function emptyResponse(status, sessionId = null, extraHeaders = {}) {
  const responseHeaders = new Headers({
    "Cache-Control": "no-store",
    ...extraHeaders,
  });
  if (sessionId) responseHeaders.set("MCP-Session-Id", sessionId);
  return new Response(null, { status, headers: responseHeaders });
}

function timingSafeEqual(left, right) {
  const encoder = new TextEncoder();
  const leftBytes = encoder.encode(left);
  const rightBytes = encoder.encode(right);
  let different = leftBytes.length ^ rightBytes.length;
  const length = Math.max(leftBytes.length, rightBytes.length);
  for (let index = 0; index < length; index += 1) {
    different |= (leftBytes[index] ?? 0) ^ (rightBytes[index] ?? 0);
  }
  return different === 0;
}

function rejectExtra(argumentsObject, allowed) {
  const extra = Object.keys(argumentsObject).filter((key) => !allowed.has(key));
  if (extra.length) throw new Error(`Unexpected parameters: ${extra.sort().join(", ")}`);
}

function requiredString(argumentsObject, name, minimum = 1) {
  const value = argumentsObject[name];
  if (typeof value !== "string" || value.trim().length < minimum) {
    throw new Error(`'${name}' must be a string of at least ${minimum} characters`);
  }
  return value.trim();
}

export class MCPApplication {
  constructor(storage, env = {}) {
    this.storage = storage;
    this.env = env;
  }

  async loadData() {
    const stored = await this.storage.get(DATA_KEY);
    if (stored) return stored;
    const initial = clone(DEFAULT_DATA);
    await this.storage.put(DATA_KEY, initial);
    return initial;
  }

  async loadSessions() {
    return (await this.storage.get(SESSIONS_KEY)) ?? {};
  }

  async saveSessions(sessions) {
    await this.storage.put(SESSIONS_KEY, sessions);
  }

  originAllowed(request) {
    const origin = request.headers.get("Origin");
    if (!origin) return true;
    const allowed = String(this.env.MCP_ALLOWED_ORIGINS ?? "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    return allowed.includes(origin);
  }

  authorized(request) {
    const configured = String(this.env.MCP_AUTH_TOKEN ?? "");
    if (!configured) return false;
    const supplied = request.headers.get("Authorization") ?? "";
    return timingSafeEqual(supplied, `Bearer ${configured}`);
  }

  securityError(request) {
    if (!this.env.MCP_AUTH_TOKEN) {
      return jsonResponse(503, rpcError(null, -32001, "MCP_AUTH_TOKEN is not configured"));
    }
    if (!this.originAllowed(request)) {
      return jsonResponse(403, rpcError(null, -32000, "Origin is not allowed"));
    }
    if (!this.authorized(request)) {
      return jsonResponse(401, rpcError(null, -32001, "Authentication required"));
    }
    return null;
  }

  async callTool(name, argumentsObject) {
    if (!isObject(argumentsObject)) throw new Error("Tool arguments must be a JSON object");
    const data = await this.loadData();

    if (name === "list_machines") {
      rejectExtra(argumentsObject, new Set(["status"]));
      const status = argumentsObject.status;
      const valid = new Set(["operational", "warning", "stopped", "maintenance"]);
      if (status !== undefined && !valid.has(status)) throw new Error(`Invalid status: ${status}`);
      const machines = status
        ? data.machines.filter((machine) => machine.status === status)
        : data.machines;
      return { count: machines.length, machines };
    }

    if (name === "get_machine_status") {
      rejectExtra(argumentsObject, new Set(["machine_id"]));
      const machineId = requiredString(argumentsObject, "machine_id").toUpperCase();
      const machine = data.machines.find(
        (candidate) => candidate.machine_id.toUpperCase() === machineId,
      );
      if (!machine) throw new Error(`Machine not found: ${machineId}`);
      return { machine };
    }

    if (name === "list_work_orders") {
      rejectExtra(argumentsObject, new Set(["machine_id", "status"]));
      const machineId = argumentsObject.machine_id;
      const status = argumentsObject.status;
      if (machineId !== undefined && typeof machineId !== "string") {
        throw new Error("'machine_id' must be a string");
      }
      if (status !== undefined && !new Set(["open", "closed"]).has(status)) {
        throw new Error("'status' must be 'open' or 'closed'");
      }
      let workOrders = data.work_orders;
      if (machineId) {
        const normalized = machineId.toUpperCase();
        workOrders = workOrders.filter(
          (order) => order.machine_id.toUpperCase() === normalized,
        );
      }
      if (status) workOrders = workOrders.filter((order) => order.status === status);
      return { count: workOrders.length, work_orders: workOrders };
    }

    if (name === "check_spare_part") {
      rejectExtra(argumentsObject, new Set(["query"]));
      const query = requiredString(argumentsObject, "query").toLocaleLowerCase();
      const parts = data.spare_parts
        .filter((part) =>
          [part.part_number, part.name, ...part.compatible_machines]
            .join(" ")
            .toLocaleLowerCase()
            .includes(query),
        )
        .map((part) => ({
          ...part,
          reorder_recommended: part.quantity <= part.minimum_stock,
        }));
      return { count: parts.length, parts };
    }

    if (name === "create_work_order") {
      rejectExtra(argumentsObject, new Set(["machine_id", "issue", "priority"]));
      const machineId = requiredString(argumentsObject, "machine_id").toUpperCase();
      const issue = requiredString(argumentsObject, "issue", 5);
      const priority = requiredString(argumentsObject, "priority").toLowerCase();
      if (!new Set(["low", "medium", "high", "critical"]).has(priority)) {
        throw new Error("Invalid priority");
      }
      if (!data.machines.some((machine) => machine.machine_id.toUpperCase() === machineId)) {
        throw new Error(`Machine not found: ${machineId}`);
      }
      const numericIds = data.work_orders
        .map((order) => Number.parseInt(order.work_order_id.split("-").at(-1), 10))
        .filter(Number.isFinite);
      const nextNumber = Math.max(0, ...numericIds) + 1;
      const workOrder = {
        work_order_id: `WO-${String(nextNumber).padStart(4, "0")}`,
        machine_id: machineId,
        issue,
        priority,
        status: "open",
        created_at: new Date().toISOString(),
        resolution: null,
        closed_at: null,
      };
      data.work_orders.push(workOrder);
      await this.storage.put(DATA_KEY, data);
      return { created: true, work_order: workOrder };
    }

    if (name === "close_work_order") {
      rejectExtra(argumentsObject, new Set(["work_order_id", "resolution"]));
      const workOrderId = requiredString(argumentsObject, "work_order_id").toUpperCase();
      const resolution = requiredString(argumentsObject, "resolution", 5);
      const workOrder = data.work_orders.find(
        (order) => order.work_order_id.toUpperCase() === workOrderId,
      );
      if (!workOrder) throw new Error(`Work order not found: ${workOrderId}`);
      if (workOrder.status === "closed") {
        throw new Error(`Work order is already closed: ${workOrderId}`);
      }
      workOrder.status = "closed";
      workOrder.resolution = resolution;
      workOrder.closed_at = new Date().toISOString();
      await this.storage.put(DATA_KEY, data);
      return { closed: true, work_order: workOrder };
    }

    throw new Error(`Unknown tool: ${name}`);
  }

  async handleMessage(message, session) {
    const requestId = message?.id ?? null;
    if (!isObject(message) || message.jsonrpc !== "2.0") {
      return rpcError(requestId, -32600, "Invalid Request");
    }
    const method = message.method;
    const params = message.params ?? {};
    const notification = !("id" in message);
    if (typeof method !== "string" || !isObject(params)) {
      return notification ? null : rpcError(requestId, -32600, "Invalid Request");
    }

    if (method === "initialize") {
      session.initializeRequested = true;
      return rpcResponse(requestId, {
        protocolVersion: PROTOCOL_VERSION,
        capabilities: { tools: { listChanged: false } },
        serverInfo: {
          name: "industrial-maintenance-server",
          title: "Industrial Maintenance MCP Server",
          version: "2.0.0",
          description: "Tools for machinery, spare parts, and work orders.",
        },
        instructions:
          "Inspect data with read-only tools first. Creating or closing a work order requires explicit user confirmation in the host application.",
      });
    }

    if (method === "notifications/initialized") {
      if (session.initializeRequested) session.initialized = true;
      return null;
    }

    if (method === "ping") return notification ? null : rpcResponse(requestId, {});
    if (!session.initialized) {
      return notification ? null : rpcError(requestId, -32002, "Server not initialized");
    }
    if (method === "tools/list") {
      return notification ? null : rpcResponse(requestId, { tools: TOOLS });
    }
    if (method === "tools/call") {
      if (notification) return null;
      const name = params.name;
      const argumentsObject = params.arguments ?? {};
      if (typeof name !== "string" || !isObject(argumentsObject)) {
        return rpcError(requestId, -32602, "Invalid tool call parameters");
      }
      try {
        return rpcResponse(requestId, toolResult(await this.callTool(name, argumentsObject)));
      } catch (error) {
        return rpcResponse(requestId, toolResult({ error: error.message }, true));
      }
    }
    return notification ? null : rpcError(requestId, -32601, "Method not found");
  }

  async handlePost(request) {
    const contentType = (request.headers.get("Content-Type") ?? "").split(";", 1)[0].trim();
    if (contentType !== "application/json") {
      return jsonResponse(415, rpcError(null, -32700, "Content-Type must be application/json"));
    }
    const accepted = new Set(
      (request.headers.get("Accept") ?? "")
        .split(",")
        .map((item) => item.split(";", 1)[0].trim()),
    );
    if (!accepted.has("application/json") || !accepted.has("text/event-stream")) {
      return jsonResponse(
        406,
        rpcError(null, -32000, "Accept must include application/json and text/event-stream"),
      );
    }

    const body = await request.text();
    const length = new TextEncoder().encode(body).byteLength;
    if (length < 1 || length > MAX_REQUEST_BYTES) {
      return jsonResponse(400, rpcError(null, -32700, "Invalid request body length"));
    }
    let message;
    try {
      message = JSON.parse(body);
    } catch {
      return jsonResponse(400, rpcError(null, -32700, "Parse error"));
    }
    if (!isObject(message)) {
      return jsonResponse(400, rpcError(null, -32600, "Batch requests are not supported"));
    }

    const sessions = await this.loadSessions();
    const isInitialize = message.method === "initialize" && "id" in message;
    let sessionId = request.headers.get("MCP-Session-Id") ?? "";
    let session;
    if (isInitialize && !sessionId) {
      sessionId = crypto.randomUUID();
      session = { initializeRequested: false, initialized: false };
      sessions[sessionId] = session;
    } else {
      session = sessions[sessionId];
      if (!session) {
        return jsonResponse(
          404,
          rpcError(message.id ?? null, -32001, "MCP session not found"),
        );
      }
      if (request.headers.get("MCP-Protocol-Version") !== PROTOCOL_VERSION) {
        return jsonResponse(
          400,
          rpcError(message.id ?? null, -32602, "Unsupported MCP protocol version"),
          sessionId,
        );
      }
    }

    const response = await this.handleMessage(message, session);
    sessions[sessionId] = session;
    await this.saveSessions(sessions);
    if (!("id" in message)) return emptyResponse(202, sessionId);
    if (response === null) {
      return jsonResponse(
        500,
        rpcError(message.id ?? null, -32603, "Request produced no response"),
        sessionId,
      );
    }
    return jsonResponse(200, response, sessionId);
  }

  async handle(request) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "") || "/";

    if (request.method === "GET" && path === "/health") {
      return jsonResponse(200, {
        status: "ok",
        service: "industrial-maintenance-server",
        platform: "cloudflare-workers",
        protocolVersion: PROTOCOL_VERSION,
      });
    }
    if (path !== "/mcp") return jsonResponse(404, { error: "Not found" });

    const securityError = this.securityError(request);
    if (securityError) return securityError;

    if (request.method === "GET") {
      return emptyResponse(405, null, { Allow: "POST, DELETE" });
    }
    if (request.method === "POST") return this.handlePost(request);
    if (request.method === "DELETE") {
      const sessionId = request.headers.get("MCP-Session-Id") ?? "";
      const sessions = await this.loadSessions();
      if (!sessionId || !sessions[sessionId]) {
        return jsonResponse(404, rpcError(null, -32001, "MCP session not found"));
      }
      delete sessions[sessionId];
      await this.saveSessions(sessions);
      return emptyResponse(204);
    }
    return emptyResponse(405, null, { Allow: "GET, POST, DELETE" });
  }
}
