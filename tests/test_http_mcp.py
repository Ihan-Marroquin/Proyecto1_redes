from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from src.http_server import create_http_server


class StreamableHTTPTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.server = create_http_server(
            "127.0.0.1",
            0,
            data_path=Path(self.temp_dir.name) / "maintenance.json",
            allowed_origins={"https://allowed.example"},
            auth_token="test-token",
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self._stop_server)
        host, port = self.server.server_address[:2]
        self.base_url = f"http://{host}:{port}"

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(
        self,
        payload: dict,
        *,
        session_id: str | None = None,
        origin: str | None = None,
    ) -> tuple[int, dict | None, dict]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer test-token",
        }
        if session_id:
            headers["MCP-Session-Id"] = session_id
            headers["MCP-Protocol-Version"] = "2025-11-25"
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(
            f"{self.base_url}/mcp",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as exc:
            response = exc
        body = response.read()
        decoded = json.loads(body) if body else None
        return response.status, decoded, dict(response.headers.items())

    def test_health_endpoint(self) -> None:
        with urllib.request.urlopen(f"{self.base_url}/health", timeout=3) as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["protocolVersion"], "2025-11-25")

    def test_rejects_untrusted_browser_origin(self) -> None:
        status, payload, _ = self.request(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
            origin="https://evil.example",
        )
        self.assertEqual(status, 403)
        self.assertEqual(payload["error"]["message"], "Origin is not allowed")

    def test_initialize_list_and_call_tools_over_http(self) -> None:
        status, initialized, headers = self.request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "test", "version": "1.0"},
                },
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(initialized["result"]["protocolVersion"], "2025-11-25")
        session_id = headers["MCP-Session-Id"]

        status, body, _ = self.request(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            session_id=session_id,
        )
        self.assertEqual(status, 202)
        self.assertIsNone(body)

        status, listed, _ = self.request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            session_id=session_id,
        )
        self.assertEqual(status, 200)
        names = {tool["name"] for tool in listed["result"]["tools"]}
        self.assertIn("get_machine_status", names)

        status, called, _ = self.request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_machine_status",
                    "arguments": {"machine_id": "SELL-01"},
                },
            },
            session_id=session_id,
        )
        self.assertEqual(status, 200)
        machine = called["result"]["structuredContent"]["machine"]
        self.assertEqual(machine["machine_id"], "SELL-01")

        delete = urllib.request.Request(
            f"{self.base_url}/mcp",
            headers={
                "Authorization": "Bearer test-token",
                "MCP-Session-Id": session_id,
            },
            method="DELETE",
        )
        with urllib.request.urlopen(delete, timeout=3) as response:
            self.assertEqual(response.status, 204)


if __name__ == "__main__":
    unittest.main()
