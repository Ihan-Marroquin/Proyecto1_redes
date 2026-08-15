"""Industrial maintenance MCP server implemented manually with JSON-RPC 2.0.

Transport: stdio, one UTF-8 JSON object per line.
MCP protocol version: 2025-11-25.
No MCP SDK or framework is used.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


PROTOCOL_VERSION = "2025-11-25"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_DATA: dict[str, Any] = {
    "machines": [
        {
            "machine_id": "SELL-01",
            "name": "Beverage cup sealer",
            "area": "Packaging line 1",
            "status": "warning",
            "temperature_c": 184.5,
            "cycles": 18427,
            "last_maintenance": "2026-08-02",
            "next_maintenance": "2026-08-25",
            "notes": "Inspect sealing resistance before the next production shift.",
        },
        {
            "machine_id": "PUMP-02",
            "name": "Sanitary transfer pump",
            "area": "Mixing area",
            "status": "operational",
            "temperature_c": 42.1,
            "hours": 730,
            "last_maintenance": "2026-07-28",
            "next_maintenance": "2026-09-28",
            "notes": "No active alerts.",
        },
        {
            "machine_id": "COMP-01",
            "name": "Pneumatic line compressor",
            "area": "Utilities room",
            "status": "maintenance",
            "temperature_c": 51.8,
            "hours": 1520,
            "last_maintenance": "2026-08-18",
            "next_maintenance": "2026-10-18",
            "notes": "Oil filter replacement in progress.",
        },
    ],
    "spare_parts": [
        {
            "part_number": "RES-220V-400W",
            "name": "Sealing resistance 220 V / 400 W",
            "quantity": 2,
            "minimum_stock": 1,
            "location": "Shelf A-03",
            "compatible_machines": ["SELL-01"],
        },
        {
            "part_number": "GASKET-P02",
            "name": "Food-grade pump gasket",
            "quantity": 5,
            "minimum_stock": 3,
            "location": "Shelf B-07",
            "compatible_machines": ["PUMP-02"],
        },
        {
            "part_number": "FILTER-C01",
            "name": "Compressor oil filter",
            "quantity": 0,
            "minimum_stock": 2,
            "location": "Shelf C-02",
            "compatible_machines": ["COMP-01"],
        },
    ],
    "work_orders": [
        {
            "work_order_id": "WO-0001",
            "machine_id": "COMP-01",
            "issue": "Replace oil filter and inspect lubrication circuit.",
            "priority": "high",
            "status": "open",
            "created_at": "2026-08-18T14:00:00+00:00",
            "resolution": None,
            "closed_at": None,
        }
    ],
}


TOOLS: list[dict[str, Any]] = [
    {
        "name": "list_machines",
        "title": "List industrial machines",
        "description": (
            "Lists the machines registered in the plant. Use it to discover valid machine "
            "identifiers or obtain a quick overview. The optional status filter accepts "
            "operational, warning, stopped, or maintenance. This tool does not modify data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["operational", "warning", "stopped", "maintenance"],
                    "description": "Optional machine status filter.",
                }
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "get_machine_status",
        "title": "Get machine status",
        "description": (
            "Returns the complete operational record for one machine, including status, area, "
            "measurements, maintenance dates, and notes. Call list_machines first if the machine "
            "identifier is unknown. This tool does not modify data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "machine_id": {
                    "type": "string",
                    "description": "Plant machine identifier, for example SELL-01.",
                }
            },
            "required": ["machine_id"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "list_work_orders",
        "title": "List maintenance work orders",
        "description": (
            "Lists maintenance work orders. Results may be filtered by machine_id and by status "
            "(open or closed). Use it before creating an order to avoid duplicates. This tool "
            "does not modify data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "machine_id": {"type": "string"},
                "status": {"type": "string", "enum": ["open", "closed"]},
            },
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "check_spare_part",
        "title": "Check spare-part inventory",
        "description": (
            "Searches spare parts by exact or partial part number, name, or compatible machine. "
            "It returns stock quantity, minimum stock, physical location, and whether a reorder "
            "is recommended. This tool does not reserve or consume inventory."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "minLength": 1,
                    "description": "Part number, name fragment, or machine identifier.",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "create_work_order",
        "title": "Create a maintenance work order",
        "description": (
            "Creates and stores a work order for a registered machine. Use it only after the user "
            "confirms the action. The issue should describe the observed problem and requested "
            "work; priority must be low, medium, high, or critical."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "machine_id": {"type": "string"},
                "issue": {"type": "string", "minLength": 5},
                "priority": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                },
            },
            "required": ["machine_id", "issue", "priority"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    },
    {
        "name": "close_work_order",
        "title": "Close a maintenance work order",
        "description": (
            "Marks an existing open work order as closed and stores a resolution note. Use it "
            "only after the user confirms that the maintenance work is complete. This changes "
            "persistent maintenance data."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "work_order_id": {"type": "string"},
                "resolution": {"type": "string", "minLength": 5},
            },
            "required": ["work_order_id", "resolution"],
            "additionalProperties": False,
        },
        "annotations": {
            "readOnlyHint": False,
            "destructiveHint": False,
            "idempotentHint": False,
        },
    },
]


class ToolInputError(ValueError):
    pass


class MaintenanceService:
    """Persistence and business rules for the maintenance use case."""

    def __init__(self, data_path: Path) -> None:
        self.data_path = data_path
        self.data_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.data_path.exists():
            self._save(copy.deepcopy(DEFAULT_DATA))

    def _load(self) -> dict[str, Any]:
        return json.loads(self.data_path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        temporary = self.data_path.with_suffix(self.data_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.data_path)

    @staticmethod
    def _required_string(arguments: dict[str, Any], name: str, minimum: int = 1) -> str:
        value = arguments.get(name)
        if not isinstance(value, str) or len(value.strip()) < minimum:
            raise ToolInputError(f"'{name}' must be a string of at least {minimum} characters")
        return value.strip()

    @staticmethod
    def _reject_extra(arguments: dict[str, Any], allowed: set[str]) -> None:
        extra = set(arguments) - allowed
        if extra:
            raise ToolInputError(f"Unexpected parameters: {', '.join(sorted(extra))}")

    def list_machines(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._reject_extra(arguments, {"status"})
        status = arguments.get("status")
        valid = {"operational", "warning", "stopped", "maintenance"}
        if status is not None and status not in valid:
            raise ToolInputError(f"Invalid status: {status}")
        machines = self._load()["machines"]
        if status:
            machines = [machine for machine in machines if machine["status"] == status]
        return {"count": len(machines), "machines": machines}

    def get_machine_status(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._reject_extra(arguments, {"machine_id"})
        machine_id = self._required_string(arguments, "machine_id").upper()
        for machine in self._load()["machines"]:
            if machine["machine_id"].upper() == machine_id:
                return {"machine": machine}
        raise ToolInputError(f"Machine not found: {machine_id}")

    def list_work_orders(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._reject_extra(arguments, {"machine_id", "status"})
        machine_id = arguments.get("machine_id")
        status = arguments.get("status")
        if machine_id is not None and not isinstance(machine_id, str):
            raise ToolInputError("'machine_id' must be a string")
        if status is not None and status not in {"open", "closed"}:
            raise ToolInputError("'status' must be 'open' or 'closed'")
        work_orders = self._load()["work_orders"]
        if machine_id:
            machine_id = machine_id.upper()
            work_orders = [
                order for order in work_orders if order["machine_id"].upper() == machine_id
            ]
        if status:
            work_orders = [order for order in work_orders if order["status"] == status]
        return {"count": len(work_orders), "work_orders": work_orders}

    def check_spare_part(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._reject_extra(arguments, {"query"})
        query = self._required_string(arguments, "query").casefold()
        matches = []
        for part in self._load()["spare_parts"]:
            searchable = " ".join(
                [part["part_number"], part["name"], *part["compatible_machines"]]
            ).casefold()
            if query in searchable:
                result = dict(part)
                result["reorder_recommended"] = part["quantity"] <= part["minimum_stock"]
                matches.append(result)
        return {"count": len(matches), "parts": matches}

    def create_work_order(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._reject_extra(arguments, {"machine_id", "issue", "priority"})
        machine_id = self._required_string(arguments, "machine_id").upper()
        issue = self._required_string(arguments, "issue", 5)
        priority = self._required_string(arguments, "priority").lower()
        if priority not in {"low", "medium", "high", "critical"}:
            raise ToolInputError("Invalid priority")

        data = self._load()
        known_ids = {machine["machine_id"].upper() for machine in data["machines"]}
        if machine_id not in known_ids:
            raise ToolInputError(f"Machine not found: {machine_id}")

        numeric_ids = []
        for order in data["work_orders"]:
            try:
                numeric_ids.append(int(order["work_order_id"].split("-")[-1]))
            except (KeyError, TypeError, ValueError):
                continue
        order_id = f"WO-{max(numeric_ids, default=0) + 1:04d}"
        order = {
            "work_order_id": order_id,
            "machine_id": machine_id,
            "issue": issue,
            "priority": priority,
            "status": "open",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "resolution": None,
            "closed_at": None,
        }
        data["work_orders"].append(order)
        self._save(data)
        return {"created": True, "work_order": order}

    def close_work_order(self, arguments: dict[str, Any]) -> dict[str, Any]:
        self._reject_extra(arguments, {"work_order_id", "resolution"})
        work_order_id = self._required_string(arguments, "work_order_id").upper()
        resolution = self._required_string(arguments, "resolution", 5)
        data = self._load()
        for order in data["work_orders"]:
            if order["work_order_id"].upper() != work_order_id:
                continue
            if order["status"] == "closed":
                raise ToolInputError(f"Work order is already closed: {work_order_id}")
            order["status"] = "closed"
            order["resolution"] = resolution
            order["closed_at"] = datetime.now(timezone.utc).isoformat()
            self._save(data)
            return {"closed": True, "work_order": order}
        raise ToolInputError(f"Work order not found: {work_order_id}")

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        handlers: dict[str, Callable[[dict[str, Any]], dict[str, Any]]] = {
            "list_machines": self.list_machines,
            "get_machine_status": self.get_machine_status,
            "list_work_orders": self.list_work_orders,
            "check_spare_part": self.check_spare_part,
            "create_work_order": self.create_work_order,
            "close_work_order": self.close_work_order,
        }
        if name not in handlers:
            raise ToolInputError(f"Unknown tool: {name}")
        if not isinstance(arguments, dict):
            raise ToolInputError("Tool arguments must be a JSON object")
        return handlers[name](arguments)


def _response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def _tool_result(payload: dict[str, Any], is_error: bool = False) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ],
        "structuredContent": payload,
        "isError": is_error,
    }


class MCPServer:
    def __init__(self, service: MaintenanceService) -> None:
        self.service = service
        self.initialize_requested = False
        self.initialized = False

    def handle(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")

        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params", {})
        is_notification = "id" not in message

        if not isinstance(method, str) or not isinstance(params, dict):
            return None if is_notification else _error(request_id, -32600, "Invalid Request")

        if method == "initialize":
            self.initialize_requested = True
            return _response(
                request_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "industrial-maintenance-server",
                        "title": "Industrial Maintenance MCP Server",
                        "version": "1.0.0",
                        "description": "Local tools for machinery, spare parts, and work orders.",
                    },
                    "instructions": (
                        "Inspect data with read-only tools first. Creating or closing a work order "
                        "requires explicit user confirmation in the host application."
                    ),
                },
            )

        if method == "notifications/initialized":
            if self.initialize_requested:
                self.initialized = True
            return None

        if method == "ping":
            return None if is_notification else _response(request_id, {})

        if not self.initialized:
            return None if is_notification else _error(request_id, -32002, "Server not initialized")

        if method == "tools/list":
            return None if is_notification else _response(request_id, {"tools": TOOLS})

        if method == "tools/call":
            if is_notification:
                return None
            name = params.get("name")
            arguments = params.get("arguments", {})
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return _error(request_id, -32602, "Invalid tool call parameters")
            try:
                payload = self.service.call(name, arguments)
                return _response(request_id, _tool_result(payload))
            except ToolInputError as exc:
                return _response(request_id, _tool_result({"error": str(exc)}, is_error=True))
            except Exception as exc:  # Keep protocol errors on stderr, never stdout.
                print(f"Internal tool error: {exc}", file=sys.stderr, flush=True)
                return _response(
                    request_id,
                    _tool_result({"error": "Internal server error"}, is_error=True),
                )

        return None if is_notification else _error(request_id, -32601, "Method not found")


def main() -> None:
    data_path = Path(
        os.getenv("MAINTENANCE_DATA_PATH", str(PROJECT_ROOT / "data" / "maintenance.json"))
    )
    server = MCPServer(MaintenanceService(data_path))
    print("Industrial Maintenance MCP Server running on stdio", file=sys.stderr, flush=True)

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            response = _error(None, -32700, "Parse error")
        else:
            response = server.handle(message)
        if response is not None:
            print(
                json.dumps(response, ensure_ascii=False, separators=(",", ":")),
                flush=True,
            )


if __name__ == "__main__":
    main()
