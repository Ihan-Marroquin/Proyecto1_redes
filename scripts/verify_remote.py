"""Verify a remote maintenance MCP endpoint without calling the LLM API."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from src.config import PROJECT_ROOT
from src.mcp_client import HttpMCPClient
from src.mcp_logging import MCPInteractionLogger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the remote maintenance MCP server")
    parser.add_argument(
        "--url",
        default=os.getenv("MCP_REMOTE_URL", "http://127.0.0.1:8000/mcp"),
    )
    parser.add_argument("--token", default=os.getenv("MCP_AUTH_TOKEN", "local-demo-token"))
    parser.add_argument("--timeout", type=float, default=15)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    headers = {"Authorization": f"Bearer {args.token}"} if args.token else {}
    logger = MCPInteractionLogger(
        Path(os.getenv("MCP_LOG_PATH", PROJECT_ROOT / "logs" / "remote_verification.jsonl"))
    )
    client = HttpMCPClient(
        name="maintenance-remote",
        url=args.url,
        headers=headers,
        logger=logger,
        timeout=args.timeout,
    )
    try:
        initialized = client.start()
        tools = client.list_tools()
        result = client.call_tool("list_machines", {"status": "warning"})
        print(f"PASS initialize: MCP {initialized['protocolVersion']}")
        print(f"PASS tools/list: {len(tools)} tools")
        print(
            "PASS tools/call: "
            f"{result['structuredContent']['count']} warning machine(s)"
        )
        print(f"Log: {logger.path}")
        return 0
    except Exception as exc:
        print(f"FAIL remote verification: {exc}")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
