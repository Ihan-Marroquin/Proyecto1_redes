from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.maintenance_server import MCPServer, MaintenanceService


class MCPProtocolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        data_path = Path(self.temp_dir.name) / "maintenance.json"
        self.server = MCPServer(MaintenanceService(data_path))

    def request(self, request_id: int, method: str, params: dict | None = None) -> dict:
        message = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        response = self.server.handle(message)
        self.assertIsNotNone(response)
        return response

    def test_lifecycle_must_be_initialized_before_tools(self) -> None:
        response = self.request(1, "tools/list", {})
        self.assertEqual(response["error"]["code"], -32002)

        initialized = self.request(
            2,
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"},
            },
        )
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(initialized["result"]["serverInfo"]["version"], "2.0.0")

        notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        }
        self.assertIsNone(self.server.handle(notification))
        tools = self.request(3, "tools/list", {})
        self.assertGreaterEqual(len(tools["result"]["tools"]), 6)

    def test_invalid_and_unknown_requests_return_json_rpc_errors(self) -> None:
        invalid = self.server.handle({"jsonrpc": "1.0", "id": 1, "method": "ping"})
        self.assertEqual(invalid["error"]["code"], -32600)

        self.request(2, "initialize", {"protocolVersion": "2025-11-25"})
        self.server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        unknown = self.request(3, "does/not/exist", {})
        self.assertEqual(unknown["error"]["code"], -32601)


if __name__ == "__main__":
    unittest.main()
