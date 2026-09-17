from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

from src.http_server import create_http_server
from src.mcp_client import HttpMCPClient
from src.mcp_logging import MCPInteractionLogger


class HTTPMCPClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        temp_path = Path(self.temp_dir.name)
        self.server = create_http_server(
            "127.0.0.1",
            0,
            data_path=temp_path / "maintenance.json",
            auth_token="integration-token",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        host, port = self.server.server_address[:2]
        self.logger = MCPInteractionLogger(temp_path / "http_interactions.jsonl")
        self.client = HttpMCPClient(
            name="maintenance-remote-test",
            url=f"http://{host}:{port}/mcp",
            headers={"Authorization": "Bearer integration-token"},
            logger=self.logger,
            timeout=3,
        )
        self.addCleanup(self.client.close)

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_client_completes_lifecycle_and_tool_call(self) -> None:
        initialized = self.client.start()
        self.assertEqual(initialized["protocolVersion"], "2025-11-25")
        self.assertTrue(self.client.session_id)

        tools = self.client.list_tools()
        self.assertIn("list_machines", {tool["name"] for tool in tools})
        result = self.client.call_tool("list_machines", {"status": "warning"})
        self.assertEqual(result["structuredContent"]["count"], 1)

        events = self.logger.tail(100)
        directions = {event["direction"] for event in events}
        self.assertEqual(directions, {"client_to_server", "server_to_client"})


if __name__ == "__main__":
    unittest.main()
