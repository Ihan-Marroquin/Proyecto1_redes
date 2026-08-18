"""Console host that connects Claude to local MCP servers."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .anthropic_client import AnthropicAPIError, AnthropicClient
from .config import PROJECT_ROOT, load_env_file, load_server_config, prepare_demo_workspace
from .mcp_client import MCPError, RegisteredTool, StdioMCPClient, ToolRegistry
from .mcp_logging import MCPInteractionLogger


SYSTEM_PROMPT = """You are a console assistant connected to local MCP tools.
Answer in the same language used by the user. Keep answers clear and concise.
Use tools when the request depends on files, Git repositories, plant machinery,
spare parts, or maintenance work orders. Inspect before modifying whenever possible.
Never claim that an action succeeded until its tool result confirms it.
The host application will ask the user for confirmation before any write action.
"""


WRITE_ACTION_WORDS = {
    "write",
    "edit",
    "move",
    "delete",
    "create",
    "commit",
    "add",
    "checkout",
    "branch",
    "close",
    "remove",
    "mkdir",
}


class ConsoleChatbot:
    def __init__(
        self,
        llm: AnthropicClient,
        logger: MCPInteractionLogger,
        protocol_version: str,
    ) -> None:
        self.llm = llm
        self.logger = logger
        self.protocol_version = protocol_version
        self.clients: dict[str, StdioMCPClient] = {}
        self.failed_servers: dict[str, str] = {}
        self.registry = ToolRegistry()
        self.messages: list[dict[str, Any]] = []

    def connect_servers(self, server_entries: list[dict[str, Any]]) -> None:
        for entry in server_entries:
            name = entry["name"]
            client = StdioMCPClient(
                name=name,
                command=entry["command"],
                args=entry["args"],
                cwd=entry["cwd"],
                env=entry["env"],
                logger=self.logger,
                protocol_version=self.protocol_version,
                timeout=entry["timeout"],
            )
            try:
                client.start()
                tools = client.list_tools()
            except Exception as exc:
                client.close()
                self.failed_servers[name] = str(exc)
                print(f"[warning] {name}: {exc}")
                continue
            self.clients[name] = client
            self.registry.add_server_tools(name, tools)
            title = client.server_info.get("title") or client.server_info.get("name") or name
            print(f"[connected] {name}: {title} ({len(tools)} tools)")

    @staticmethod
    def _tool_requires_confirmation(tool: RegisteredTool) -> bool:
        annotations = tool.definition.get("annotations", {})
        if annotations.get("readOnlyHint") is True:
            return False
        lowered = tool.original_name.lower()
        return any(word in lowered.split("_") or word in lowered for word in WRITE_ACTION_WORDS)

    @staticmethod
    def _confirm(tool: RegisteredTool, arguments: dict[str, Any]) -> bool:
        print("\nAction proposed by the model:")
        print(f"  Server: {tool.server_name}")
        print(f"  Tool:   {tool.original_name}")
        print(f"  Input:  {json.dumps(arguments, ensure_ascii=False)}")
        answer = input("Approve this action? [y/N]: ").strip().lower()
        return answer in {"y", "yes", "s", "si", "sí"}

    def _execute_tool(self, block: dict[str, Any]) -> dict[str, Any]:
        public_name = block.get("name", "")
        arguments = block.get("input", {})
        if not isinstance(arguments, dict):
            arguments = {}
        try:
            tool = self.registry.resolve(public_name)
            if self._tool_requires_confirmation(tool) and not self._confirm(tool, arguments):
                return {
                    "type": "tool_result",
                    "tool_use_id": block["id"],
                    "content": "Action cancelled by the user.",
                    "is_error": True,
                }
            print(f"[tool] {tool.server_name}.{tool.original_name}")
            result = self.clients[tool.server_name].call_tool(tool.original_name, arguments)
            is_error = bool(result.get("isError", False))
            content = json.dumps(result, ensure_ascii=False)
            return {
                "type": "tool_result",
                "tool_use_id": block["id"],
                "content": content,
                "is_error": is_error,
            }
        except Exception as exc:
            return {
                "type": "tool_result",
                "tool_use_id": block.get("id", "unknown"),
                "content": str(exc),
                "is_error": True,
            }

    @staticmethod
    def _text_from(content: list[dict[str, Any]]) -> str:
        return "\n".join(
            block.get("text", "") for block in content if block.get("type") == "text"
        ).strip()

    def ask(self, user_text: str) -> None:
        self.messages.append({"role": "user", "content": user_text})
        for _ in range(8):
            response = self.llm.create_message(
                messages=self.messages,
                tools=self.registry.anthropic_tools(),
                system=SYSTEM_PROMPT,
            )
            content = response["content"]
            self.messages.append({"role": "assistant", "content": content})

            text = self._text_from(content)
            if text:
                print(f"\nAssistant: {text}")

            tool_calls = [block for block in content if block.get("type") == "tool_use"]
            if not tool_calls:
                stop_reason = response.get("stop_reason")
                if stop_reason == "refusal":
                    print("[warning] The model refused this request.")
                elif stop_reason == "max_tokens":
                    print("[warning] The answer reached the configured token limit.")
                return

            results = [self._execute_tool(block) for block in tool_calls]
            self.messages.append({"role": "user", "content": results})

        print("[warning] Maximum of 8 consecutive tool rounds reached.")

    def show_tools(self) -> None:
        if not self.registry.items():
            print("No MCP tools are available.")
            return
        for tool in self.registry.items():
            print(f"- {tool.public_name} -> {tool.server_name}.{tool.original_name}")

    def show_servers(self) -> None:
        for name, client in self.clients.items():
            version = client.server_info.get("version", "unknown")
            print(f"- {name}: connected (server version {version})")
        for name, reason in self.failed_servers.items():
            print(f"- {name}: unavailable ({reason})")

    def show_logs(self, limit: int = 10) -> None:
        events = self.logger.tail(limit)
        if not events:
            print("The MCP log is empty.")
            return
        for event in events:
            message = event["message"]
            method = message.get("method") or (
                "response" if "result" in message else "error" if "error" in message else "event"
            )
            identifier = message.get("id", "-")
            print(
                f"{event['timestamp']} | {event['server']} | {event['direction']} "
                f"| id={identifier} | {method}"
            )

    def close(self) -> None:
        for client in self.clients.values():
            client.close()


HELP_TEXT = """Commands:
  /help          Show these commands
  /servers       Show connected and unavailable MCP servers
  /tools         Show all MCP tools exposed to Claude
  /logs [N]      Show the last N MCP log entries (default: 10)
  /clear         Clear the current conversation context
  /exit          Close the servers and exit
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manual MCP chatbot for CC3067")
    parser.add_argument("--config", type=Path, help="Alternative MCP server JSON config")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    load_env_file()
    prepare_demo_workspace()

    api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not api_key or api_key == "replace_with_your_key":
        print("Missing ANTHROPIC_API_KEY. Copy .env.example to .env and add your key.")
        return 2

    config = load_server_config(args.config)
    log_path = Path(
        os.getenv("MCP_LOG_PATH", str(PROJECT_ROOT / "logs" / "mcp_interactions.jsonl"))
    )
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path

    logger = MCPInteractionLogger(log_path)
    llm = AnthropicClient(
        api_key=api_key,
        model=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
    )
    chatbot = ConsoleChatbot(llm, logger, config["protocol_version"])

    print("Starting local MCP servers...")
    chatbot.connect_servers(config["servers"])
    if not chatbot.clients:
        print("No MCP server could be started. Check /servers and the JSONL log.")
    print("\nCC3067 MCP Chatbot. Type /help for commands.")

    try:
        while True:
            try:
                user_text = input("\nYou: ").strip()
            except EOFError:
                break
            if not user_text:
                continue
            if user_text == "/exit":
                break
            if user_text == "/help":
                print(HELP_TEXT)
                continue
            if user_text == "/servers":
                chatbot.show_servers()
                continue
            if user_text == "/tools":
                chatbot.show_tools()
                continue
            if user_text.startswith("/logs"):
                parts = user_text.split(maxsplit=1)
                try:
                    limit = int(parts[1]) if len(parts) == 2 else 10
                except ValueError:
                    print("Usage: /logs [integer]")
                    continue
                chatbot.show_logs(max(1, min(limit, 100)))
                continue
            if user_text == "/clear":
                chatbot.messages.clear()
                print("Conversation context cleared.")
                continue
            if user_text.startswith("/"):
                print("Unknown command. Type /help.")
                continue

            try:
                chatbot.ask(user_text)
            except (AnthropicAPIError, MCPError) as exc:
                print(f"[error] {exc}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        chatbot.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

