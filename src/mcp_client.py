"""A manual MCP client over stdio using newline-delimited JSON-RPC 2.0."""

from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .mcp_logging import MCPInteractionLogger


class MCPError(RuntimeError):
    """Raised when a server returns a JSON-RPC error or becomes unavailable."""


class StdioMCPClient:
    transport = "stdio"

    def __init__(
        self,
        name: str,
        command: str,
        args: list[str],
        cwd: str,
        logger: MCPInteractionLogger,
        protocol_version: str = "2025-11-25",
        env: dict[str, str] | None = None,
        timeout: float = 45,
    ) -> None:
        self.name = name
        self.command = command
        self.args = args
        self.cwd = cwd
        self.logger = logger
        self.protocol_version = protocol_version
        self.env = {**os.environ, **(env or {})}
        self.timeout = timeout
        self.process: subprocess.Popen[str] | None = None
        self._next_id = 1
        self._pending: dict[int, queue.Queue[dict[str, Any]]] = {}
        self._pending_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self.server_info: dict[str, Any] = {}
        self.capabilities: dict[str, Any] = {}

    def start(self) -> dict[str, Any]:
        if self.process is not None:
            return self.server_info

        try:
            self.process = subprocess.Popen(
                [self.command, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.cwd,
                env=self.env,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise MCPError(f"Command not found for {self.name}: {self.command}") from exc

        self._reader_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._reader_thread.start()
        self._stderr_thread.start()

        result = self.request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": "cc3067-manual-mcp-chatbot",
                    "title": "CC3067 Manual MCP Chatbot",
                    "version": "1.0.0",
                },
            },
            timeout=self.timeout,
        )
        negotiated = result.get("protocolVersion")
        if negotiated != self.protocol_version:
            self.close()
            raise MCPError(
                f"{self.name} negotiated {negotiated!r}; expected {self.protocol_version!r}"
            )
        self.server_info = result.get("serverInfo", {})
        self.capabilities = result.get("capabilities", {})
        self.notify("notifications/initialized")
        return result

    def _read_stdout(self) -> None:
        process = self.process
        if process is None or process.stdout is None:
            return
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                # stdout must contain only valid MCP messages. Preserve the event in the log.
                self.logger.record(
                    self.name,
                    "invalid_server_output",
                    {"raw": line},
                )
                continue

            self.logger.record(self.name, "server_to_client", message)
            response_id = message.get("id")
            if response_id is not None:
                with self._pending_lock:
                    waiter = self._pending.get(response_id)
                if waiter is not None:
                    waiter.put(message)

        self._fail_all_pending("MCP server closed stdout")

    def _read_stderr(self) -> None:
        process = self.process
        if process is None or process.stderr is None:
            return
        for raw_line in process.stderr:
            line = raw_line.rstrip()
            if line:
                self.logger.record(self.name, "server_stderr", {"text": line})

    def _fail_all_pending(self, reason: str) -> None:
        with self._pending_lock:
            pending = list(self._pending.values())
        for waiter in pending:
            waiter.put({"jsonrpc": "2.0", "error": {"code": -32000, "message": reason}})

    def _send(self, message: dict[str, Any]) -> None:
        process = self.process
        if process is None or process.stdin is None or process.poll() is not None:
            raise MCPError(f"MCP server {self.name} is not running")
        serialized = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        self.logger.record(self.name, "client_to_server", message)
        try:
            with self._write_lock:
                process.stdin.write(serialized + "\n")
                process.stdin.flush()
        except (BrokenPipeError, OSError) as exc:
            raise MCPError(f"Could not write to MCP server {self.name}") from exc

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        request_id = self._next_id
        self._next_id += 1
        waiter: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=1)
        with self._pending_lock:
            self._pending[request_id] = waiter

        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params

        try:
            self._send(message)
            response = waiter.get(timeout=timeout or self.timeout)
        except queue.Empty as exc:
            raise MCPError(f"Timeout waiting for {method} from {self.name}") from exc
        finally:
            with self._pending_lock:
                self._pending.pop(request_id, None)

        if "error" in response:
            error = response["error"]
            raise MCPError(
                f"{self.name} returned {error.get('code')}: {error.get('message')}"
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPError(f"Invalid result for {method} from {self.name}")
        return result

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self.request("tools/list", params)
            page = result.get("tools", [])
            if not isinstance(page, list):
                raise MCPError(f"Invalid tools/list response from {self.name}")
            tools.extend(page)
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        process = self.process
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
            process.wait(timeout=3)
        except (subprocess.TimeoutExpired, OSError):
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        finally:
            for stream in (process.stdout, process.stderr):
                if stream is not None and not stream.closed:
                    stream.close()
            for thread in (self._reader_thread, self._stderr_thread):
                if thread is not None and thread.is_alive():
                    thread.join(timeout=1)
            self.process = None


class HttpMCPClient:
    """Manual MCP client for the JSON and SSE forms of Streamable HTTP."""

    transport = "http"

    def __init__(
        self,
        name: str,
        url: str,
        logger: MCPInteractionLogger,
        protocol_version: str = "2025-11-25",
        headers: dict[str, str] | None = None,
        timeout: float = 45,
    ) -> None:
        self.name = name
        self.url = url
        self.logger = logger
        self.protocol_version = protocol_version
        self.headers = dict(headers or {})
        self.timeout = timeout
        self.session_id: str | None = None
        self._next_id = 1
        self.server_info: dict[str, Any] = {}
        self.capabilities: dict[str, Any] = {}

    def _request_headers(self, has_body: bool = True) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "User-Agent": "cc3067-manual-mcp-chatbot/2.0.0",
            **self.headers,
        }
        if has_body:
            headers["Content-Type"] = "application/json"
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
            headers["MCP-Protocol-Version"] = self.protocol_version
        return headers

    @staticmethod
    def _parse_sse(body: str, expected_id: Any) -> dict[str, Any] | None:
        for event in body.replace("\r\n", "\n").split("\n\n"):
            data_lines = [
                line[5:].lstrip()
                for line in event.splitlines()
                if line.startswith("data:")
            ]
            if not data_lines:
                continue
            try:
                message = json.loads("\n".join(data_lines))
            except json.JSONDecodeError:
                continue
            if isinstance(message, dict) and message.get("id") == expected_id:
                return message
        return None

    def _send(self, message: dict[str, Any]) -> dict[str, Any] | None:
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        self.logger.record(self.name, "client_to_server", message)
        request = urllib.request.Request(
            self.url,
            data=encoded,
            headers=self._request_headers(),
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = response.status
                content_type = response.headers.get_content_type()
                body = response.read().decode("utf-8")
                returned_session = response.headers.get("MCP-Session-Id")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body).get("error", {}).get("message", body)
            except json.JSONDecodeError:
                detail = body or exc.reason
            raise MCPError(f"{self.name} returned HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise MCPError(f"Could not connect to MCP server {self.name}: {exc.reason}") from exc

        if returned_session:
            self.session_id = returned_session
        if status == 202:
            return None
        try:
            if content_type == "application/json":
                response_message = json.loads(body)
            elif content_type == "text/event-stream":
                response_message = self._parse_sse(body, message.get("id"))
                if response_message is None:
                    raise MCPError(f"SSE response from {self.name} did not contain the result")
            else:
                raise MCPError(
                    f"Unexpected content type from {self.name}: {content_type or 'missing'}"
                )
        except json.JSONDecodeError as exc:
            raise MCPError(f"MCP server {self.name} returned invalid JSON") from exc
        if not isinstance(response_message, dict):
            raise MCPError(f"MCP server {self.name} returned an invalid response")
        self.logger.record(self.name, "server_to_client", response_message)
        return response_message

    def start(self) -> dict[str, Any]:
        if self.server_info:
            return {
                "protocolVersion": self.protocol_version,
                "serverInfo": self.server_info,
                "capabilities": self.capabilities,
            }
        result = self.request(
            "initialize",
            {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {
                    "name": "cc3067-manual-mcp-chatbot",
                    "title": "CC3067 Manual MCP Chatbot",
                    "version": "2.0.0",
                },
            },
        )
        if not self.session_id:
            raise MCPError(f"MCP server {self.name} did not return MCP-Session-Id")
        negotiated = result.get("protocolVersion")
        if negotiated != self.protocol_version:
            self.close()
            raise MCPError(
                f"{self.name} negotiated {negotiated!r}; expected {self.protocol_version!r}"
            )
        self.server_info = result.get("serverInfo", {})
        self.capabilities = result.get("capabilities", {})
        self.notify("notifications/initialized")
        return result

    def request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        del timeout  # HTTP requests use the client-level timeout.
        request_id = self._next_id
        self._next_id += 1
        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
        }
        if params is not None:
            message["params"] = params
        response = self._send(message)
        if response is None:
            raise MCPError(f"MCP server {self.name} returned no response for {method}")
        if "error" in response:
            error = response["error"]
            raise MCPError(
                f"{self.name} returned {error.get('code')}: {error.get('message')}"
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise MCPError(f"Invalid result for {method} from {self.name}")
        return result

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            params = {"cursor": cursor} if cursor else {}
            result = self.request("tools/list", params)
            page = result.get("tools", [])
            if not isinstance(page, list):
                raise MCPError(f"Invalid tools/list response from {self.name}")
            tools.extend(page)
            cursor = result.get("nextCursor")
            if not cursor:
                return tools

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments})

    def close(self) -> None:
        if not self.session_id:
            return
        request = urllib.request.Request(
            self.url,
            headers=self._request_headers(has_body=False),
            method="DELETE",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout):
                pass
        except (urllib.error.HTTPError, urllib.error.URLError):
            pass
        finally:
            self.session_id = None


def client_from_config(
    entry: dict[str, Any],
    logger: MCPInteractionLogger,
    protocol_version: str,
) -> StdioMCPClient | HttpMCPClient:
    """Create the correct manual client for one normalized config entry."""
    if entry.get("transport") == "http":
        return HttpMCPClient(
            name=entry["name"],
            url=entry["url"],
            headers=entry.get("headers", {}),
            logger=logger,
            protocol_version=protocol_version,
            timeout=entry["timeout"],
        )
    return StdioMCPClient(
        name=entry["name"],
        command=entry["command"],
        args=entry["args"],
        cwd=entry["cwd"],
        env=entry["env"],
        logger=logger,
        protocol_version=protocol_version,
        timeout=entry["timeout"],
    )


@dataclass(frozen=True)
class RegisteredTool:
    public_name: str
    server_name: str
    original_name: str
    definition: dict[str, Any]


class ToolRegistry:
    """Namespace MCP tools and convert their schemas to Anthropic tool schemas."""

    def __init__(self) -> None:
        self._tools: dict[str, RegisteredTool] = {}

    @staticmethod
    def _safe_name(server: str, tool: str) -> str:
        candidate = re.sub(r"[^a-zA-Z0-9_-]", "_", f"{server}__{tool}")
        return candidate[:64]

    def add_server_tools(self, server_name: str, tools: list[dict[str, Any]]) -> None:
        for tool in tools:
            original_name = str(tool["name"])
            base = self._safe_name(server_name, original_name)
            public_name = base
            suffix = 2
            while public_name in self._tools:
                marker = f"_{suffix}"
                public_name = base[: 64 - len(marker)] + marker
                suffix += 1
            self._tools[public_name] = RegisteredTool(
                public_name=public_name,
                server_name=server_name,
                original_name=original_name,
                definition=tool,
            )

    def anthropic_tools(self) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        for item in self._tools.values():
            description = item.definition.get("description", "No description provided.")
            converted.append(
                {
                    "name": item.public_name,
                    "description": f"MCP server '{item.server_name}': {description}",
                    "input_schema": item.definition.get(
                        "inputSchema", {"type": "object", "additionalProperties": False}
                    ),
                }
            )
        return converted

    def resolve(self, public_name: str) -> RegisteredTool:
        try:
            return self._tools[public_name]
        except KeyError as exc:
            raise MCPError(f"Unknown tool requested by the LLM: {public_name}") from exc

    def items(self) -> list[RegisteredTool]:
        return list(self._tools.values())
