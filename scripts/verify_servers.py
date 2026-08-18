"""Start every configured MCP server without using an LLM API key."""

from __future__ import annotations

from src.config import PROJECT_ROOT, load_server_config, prepare_demo_workspace
from src.mcp_client import StdioMCPClient
from src.mcp_logging import MCPInteractionLogger


def main() -> int:
    prepare_demo_workspace()
    config = load_server_config()
    logger = MCPInteractionLogger(PROJECT_ROOT / "logs" / "server_verification.jsonl")
    failures = 0

    for entry in config["servers"]:
        client = StdioMCPClient(
            name=entry["name"],
            command=entry["command"],
            args=entry["args"],
            cwd=entry["cwd"],
            env=entry["env"],
            logger=logger,
            protocol_version=config["protocol_version"],
            timeout=entry["timeout"],
        )
        try:
            result = client.start()
            tools = client.list_tools()
            tool_names = ", ".join(tool["name"] for tool in tools)
            print(
                f"PASS {entry['name']}: MCP {result['protocolVersion']}, "
                f"{len(tools)} tools"
            )
            print(f"     {tool_names}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {entry['name']}: {exc}")
        finally:
            client.close()

    if failures:
        print(f"\nVerification finished with {failures} unavailable server(s).")
        return 1
    print("\nAll configured MCP servers passed verification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

