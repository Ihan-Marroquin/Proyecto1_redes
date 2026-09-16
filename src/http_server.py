"""Manual MCP Streamable HTTP transport for the maintenance server.

This module intentionally uses only the Python standard library.  It implements
the JSON response form of Streamable HTTP; server-initiated SSE streams are not
needed by this tool-only server, so GET /mcp returns 405 as allowed by MCP.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import threading
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .maintenance_server import (
    PROTOCOL_VERSION,
    MCPServer,
    MaintenanceService,
    _error,
    configured_data_path,
)


MAX_REQUEST_BYTES = 1_048_576


@dataclass
class RemoteSession:
    server: MCPServer


class RemoteMCPApplication:
    """Own the shared maintenance service and isolated MCP client sessions."""

    def __init__(
        self,
        data_path: Path,
        endpoint: str = "/mcp",
        allowed_origins: set[str] | None = None,
        auth_token: str | None = None,
    ) -> None:
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        self.endpoint = endpoint.rstrip("/") or "/mcp"
        self.allowed_origins = allowed_origins or set()
        self.auth_token = auth_token
        self.service = MaintenanceService(data_path)
        self.sessions: dict[str, RemoteSession] = {}
        self._lock = threading.Lock()

    def new_session(self) -> tuple[str, RemoteSession]:
        session_id = secrets.token_urlsafe(32)
        session = RemoteSession(MCPServer(self.service))
        with self._lock:
            self.sessions[session_id] = session
        return session_id, session

    def get_session(self, session_id: str) -> RemoteSession | None:
        with self._lock:
            return self.sessions.get(session_id)

    def delete_session(self, session_id: str) -> bool:
        with self._lock:
            return self.sessions.pop(session_id, None) is not None


class MCPHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        application: RemoteMCPApplication,
    ) -> None:
        self.application = application
        super().__init__(server_address, MCPRequestHandler)


class MCPRequestHandler(BaseHTTPRequestHandler):
    server: MCPHTTPServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: Any) -> None:
        print(
            f'{self.address_string()} - [{self.log_date_time_string()}] {format % args}',
            file=sys.stderr,
            flush=True,
        )

    @property
    def application(self) -> RemoteMCPApplication:
        return self.server.application

    def _send_json(
        self,
        status: HTTPStatus,
        payload: dict[str, Any],
        *,
        session_id: str | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if session_id:
            self.send_header("MCP-Session-Id", session_id)
        self.end_headers()
        self.wfile.write(body)

    def _send_empty(
        self,
        status: HTTPStatus,
        *,
        session_id: str | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        if session_id:
            self.send_header("MCP-Session-Id", session_id)
        self.end_headers()

    def _path_matches(self) -> bool:
        return urlsplit(self.path).path.rstrip("/") == self.application.endpoint

    def _authorized(self) -> bool:
        expected = self.application.auth_token
        if not expected:
            return True
        supplied = self.headers.get("Authorization", "")
        return secrets.compare_digest(supplied, f"Bearer {expected}")

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in self.application.allowed_origins

    def _security_checks(self) -> bool:
        if not self._origin_allowed():
            self._send_json(
                HTTPStatus.FORBIDDEN,
                _error(None, -32000, "Origin is not allowed"),
            )
            return False
        if not self._authorized():
            self._send_json(
                HTTPStatus.UNAUTHORIZED,
                _error(None, -32001, "Authentication required"),
            )
            return False
        return True

    def do_GET(self) -> None:
        path = urlsplit(self.path).path.rstrip("/")
        if path == "/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "service": "industrial-maintenance-server",
                    "protocolVersion": PROTOCOL_VERSION,
                },
            )
            return
        if not self._path_matches():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        if not self._security_checks():
            return
        self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
        self.send_header("Allow", "POST, DELETE")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_DELETE(self) -> None:
        if not self._path_matches():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        if not self._security_checks():
            return
        session_id = self.headers.get("MCP-Session-Id", "")
        if not session_id or not self.application.delete_session(session_id):
            self._send_json(
                HTTPStatus.NOT_FOUND,
                _error(None, -32001, "MCP session not found"),
            )
            return
        self._send_empty(HTTPStatus.NO_CONTENT)

    def do_POST(self) -> None:
        if not self._path_matches():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "Not found"})
            return
        if not self._security_checks():
            return

        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip()
        if content_type != "application/json":
            self._send_json(
                HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                _error(None, -32700, "Content-Type must be application/json"),
            )
            return
        accepted = {item.split(";", 1)[0].strip() for item in self.headers.get("Accept", "").split(",")}
        if not {"application/json", "text/event-stream"}.issubset(accepted):
            self._send_json(
                HTTPStatus.NOT_ACCEPTABLE,
                _error(None, -32000, "Accept must include application/json and text/event-stream"),
            )
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = -1
        if content_length < 1 or content_length > MAX_REQUEST_BYTES:
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _error(None, -32700, "Invalid request body length"),
            )
            return
        try:
            message = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send_json(HTTPStatus.BAD_REQUEST, _error(None, -32700, "Parse error"))
            return
        if not isinstance(message, dict):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                _error(None, -32600, "Batch requests are not supported"),
            )
            return

        is_initialize = message.get("method") == "initialize" and "id" in message
        session_id = self.headers.get("MCP-Session-Id", "")
        if is_initialize and not session_id:
            session_id, session = self.application.new_session()
        else:
            session = self.application.get_session(session_id)
            if session is None:
                self._send_json(
                    HTTPStatus.NOT_FOUND,
                    _error(message.get("id"), -32001, "MCP session not found"),
                )
                return
            supplied_version = self.headers.get("MCP-Protocol-Version")
            if supplied_version != PROTOCOL_VERSION:
                self._send_json(
                    HTTPStatus.BAD_REQUEST,
                    _error(message.get("id"), -32602, "Unsupported MCP protocol version"),
                    session_id=session_id,
                )
                return

        response = session.server.handle(message)
        if "id" not in message:
            self._send_empty(HTTPStatus.ACCEPTED, session_id=session_id)
        elif response is None:
            self._send_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                _error(message.get("id"), -32603, "Request produced no response"),
                session_id=session_id,
            )
        else:
            self._send_json(HTTPStatus.OK, response, session_id=session_id)


def _origins_from_env() -> set[str]:
    return {
        origin.strip()
        for origin in os.getenv("MCP_ALLOWED_ORIGINS", "").split(",")
        if origin.strip()
    }


def create_http_server(
    host: str,
    port: int,
    *,
    data_path: Path | None = None,
    endpoint: str = "/mcp",
    allowed_origins: set[str] | None = None,
    auth_token: str | None = None,
) -> MCPHTTPServer:
    application = RemoteMCPApplication(
        data_path or configured_data_path(),
        endpoint=endpoint,
        allowed_origins=allowed_origins,
        auth_token=auth_token,
    )
    return MCPHTTPServer((host, port), application)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Industrial maintenance MCP HTTP server")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PORT", "8000")))
    parser.add_argument("--endpoint", default=os.getenv("MCP_ENDPOINT", "/mcp"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    token = os.getenv("MCP_AUTH_TOKEN") or None
    server = create_http_server(
        args.host,
        args.port,
        endpoint=args.endpoint,
        allowed_origins=_origins_from_env(),
        auth_token=token,
    )
    address, port = server.server_address[:2]
    print(
        f"Industrial Maintenance MCP Server listening on http://{address}:{port}{args.endpoint}",
        file=sys.stderr,
        flush=True,
    )
    if not token:
        print(
            "Warning: MCP_AUTH_TOKEN is not configured; use this mode only for local testing.",
            file=sys.stderr,
            flush=True,
        )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
