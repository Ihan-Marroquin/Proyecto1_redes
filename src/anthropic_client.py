"""Small Anthropic Messages API client implemented with the standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class AnthropicAPIError(RuntimeError):
    pass


class AnthropicClient:
    API_URL = "https://api.anthropic.com/v1/messages"

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = 1500,
        timeout: float = 90,
    ) -> None:
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY is required")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.timeout = timeout

    def create_message(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        system: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
        }
        if tools:
            payload["tools"] = tools

        request = urllib.request.Request(
            self.API_URL,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "content-type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "user-agent": "cc3067-manual-mcp-chatbot/1.0.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            try:
                detail = json.loads(body).get("error", {}).get("message", body)
            except json.JSONDecodeError:
                detail = body
            raise AnthropicAPIError(f"Anthropic API HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise AnthropicAPIError(f"Could not connect to the Anthropic API: {exc.reason}") from exc

        try:
            result = json.loads(body)
        except json.JSONDecodeError as exc:
            raise AnthropicAPIError("Anthropic API returned invalid JSON") from exc
        if not isinstance(result, dict) or not isinstance(result.get("content"), list):
            raise AnthropicAPIError("Anthropic API returned an unexpected response")
        return result

