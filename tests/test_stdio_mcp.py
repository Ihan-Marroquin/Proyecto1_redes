from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from src.config import PROJECT_ROOT
from src.mcp_client import StdioMCPClient, ToolRegistry
from src.mcp_logging import MCPInteractionLogger


class StdioMCPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        temp_path = Path(self.temp_dir.name)
        self.logger = MCPInteractionLogger(temp_path / "interactions.jsonl")
        self.client = StdioMCPClient(
            name="maintenance-test",
            command=sys.executable,
            args=["-m", "src.maintenance_server"],
            cwd=str(PROJECT_ROOT),
            logger=self.logger,
            env={"MAINTENANCE_DATA_PATH": str(temp_path / "data.json")},
            timeout=5,
        )
        self.addCleanup(self.client.close)

    def test_initialization_tools_and_call(self) -> None:
        result = self.client.start()
        self.assertEqual(result["protocolVersion"], "2025-11-25")

        tools = self.client.list_tools()
        names = {tool["name"] for tool in tools}
        self.assertIn("get_machine_status", names)
        self.assertIn("create_work_order", names)

        call = self.client.call_tool("get_machine_status", {"machine_id": "SELL-01"})
        self.assertFalse(call["isError"])
        self.assertEqual(call["structuredContent"]["machine"]["status"], "warning")

        events = self.logger.tail(100)
        directions = {event["direction"] for event in events}
        self.assertIn("client_to_server", directions)
        self.assertIn("server_to_client", directions)

    def test_tool_names_are_namespaced_for_the_llm(self) -> None:
        self.client.start()
        registry = ToolRegistry()
        registry.add_server_tools("maintenance", self.client.list_tools())
        public_names = {tool["name"] for tool in registry.anthropic_tools()}
        self.assertIn("maintenance__get_machine_status", public_names)


if __name__ == "__main__":
    unittest.main()

