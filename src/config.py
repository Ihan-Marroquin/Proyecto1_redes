"""Configuration helpers shared by the chatbot and MCP clients."""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEMO_WORKSPACE = PROJECT_ROOT / "demo_workspace"


def load_env_file(path: Path | None = None) -> None:
    """Load simple KEY=VALUE pairs without adding a dotenv dependency."""
    env_path = path or PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _expand(value: str) -> str:
    replacements = {
        "${PROJECT_ROOT}": str(PROJECT_ROOT),
        "${DEMO_WORKSPACE}": str(DEMO_WORKSPACE),
    }
    for marker, replacement in replacements.items():
        value = value.replace(marker, replacement)
    return os.path.expandvars(value)


def _platform_value(entry: dict[str, Any], key: str, default: Any = None) -> Any:
    system = "windows" if platform.system().lower().startswith("win") else "default"
    platform_key = f"{key}_{system}"
    if platform_key in entry:
        return entry[platform_key]
    return entry.get(key, default)


def load_server_config(path: Path | None = None) -> dict[str, Any]:
    """Read and expand the platform-aware MCP server configuration."""
    config_path = path or Path(
        os.getenv("MCP_CONFIG_PATH", str(PROJECT_ROOT / "config" / "servers.json"))
    )
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path

    raw = json.loads(config_path.read_text(encoding="utf-8"))
    normalized: list[dict[str, Any]] = []
    for entry in raw.get("servers", []):
        if not entry.get("enabled", True):
            continue
        command = _platform_value(entry, "command")
        args = _platform_value(entry, "args", [])
        cwd = entry.get("cwd", "${PROJECT_ROOT}")
        env = entry.get("env", {})
        normalized.append(
            {
                "name": entry["name"],
                "command": _expand(command),
                "args": [_expand(str(arg)) for arg in args],
                "cwd": _expand(cwd),
                "env": {key: _expand(str(value)) for key, value in env.items()},
                "timeout": float(entry.get("timeout", 45)),
            }
        )

    return {
        "protocol_version": raw.get("protocol_version", "2025-11-25"),
        "servers": normalized,
    }


def prepare_demo_workspace() -> None:
    """Create the sandbox used by the official Filesystem and Git servers."""
    DEMO_WORKSPACE.mkdir(parents=True, exist_ok=True)
    try:
        if not (DEMO_WORKSPACE / ".git").exists():
            subprocess.run(
                ["git", "init", str(DEMO_WORKSPACE)],
                check=True,
                capture_output=True,
                text=True,
            )
        # Keep the demonstration independent from the user's global Git identity.
        subprocess.run(
            ["git", "-C", str(DEMO_WORKSPACE), "config", "user.name", "CC3067 Student"],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [
                "git",
                "-C",
                str(DEMO_WORKSPACE),
                "config",
                "user.email",
                "cc3067.student@example.com",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        # The Git MCP server will provide a clearer startup error later.
        pass
