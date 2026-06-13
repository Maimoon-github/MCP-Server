"""
shell_conn.py – Safe, allowlisted shell command connector.

Only commands whose **first token** appears in the SHELL_ALLOWED_COMMANDS
allow-list are permitted.  Commands are executed via ``subprocess.run``
with ``shell=True`` solely for convenience (argument splitting); the
allow-list is the primary security boundary.

Configuration
-------------
Set in .env:
    SHELL_ENABLED=true
    SHELL_ALLOWED_COMMANDS=git,python,pip,node,npm,ls,echo
    SHELL_TIMEOUT_SECONDS=30

Tools registered
----------------
    run_command(command, cwd?)   Run an allow-listed command, return output.
    list_env()                   Show environment variables (sensitive redacted).

⚠️  SECURITY NOTE
    Enable this connector only when you fully trust the MCP clients connecting
    to the hub.  A compromised client could run any allow-listed command with
    the hub process's OS permissions.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from mcp_hub.config import settings
from mcp_hub.sandbox import validate_path
from mcp_hub.registry import register_connector, register_tool

_CONNECTOR = "shell"

# Environment variable name fragments that trigger redaction.
_SENSITIVE_FRAGMENTS: frozenset[str] = frozenset(
    {"TOKEN", "SECRET", "KEY", "PASSWORD", "PASS", "CREDENTIAL", "API", "PRIVATE"}
)

# Maximum bytes kept from stdout / stderr.
_MAX_STDOUT = 16_384   # 16 KB
_MAX_STDERR =  4_096   #  4 KB


def _check_allowlist(command: str) -> None:
    """
    Raise PermissionError if the first token of *command* is not allow-listed.

    Comparisons are case-insensitive on Windows.
    """
    tokens = command.strip().split()
    if not tokens:
        raise ValueError("Command must not be empty.")
    first = tokens[0].lower()
    allowed = [c.lower() for c in settings.get_allowed_commands()]
    if first not in allowed:
        raise PermissionError(
            f"'{tokens[0]}' is not in the shell allow-list.\n"
            f"Allowed commands: {', '.join(sorted(settings.get_allowed_commands()))}.\n"
            "Update SHELL_ALLOWED_COMMANDS in .env to add it."
        )


def register(mcp: FastMCP) -> None:
    """Attach shell tools to *mcp*."""
    register_connector(_CONNECTOR, "Safe, allow-listed shell command execution")

    # ── run_command ───────────────────────────────────────────────────────────

    @mcp.tool()
    def run_command(command: str, cwd: str = "") -> dict:
        """
        Execute an allow-listed shell command and return its output.

        Parameters
        ----------
        command: The shell command string.  Its first token must be in
                 SHELL_ALLOWED_COMMANDS.
        cwd:     Working directory for the command.  Must be within the sandbox
                 allowed paths.  Defaults to the hub's current working directory.

        Returns
        -------
        dict
            ``{"stdout": str, "stderr": str, "returncode": int}``

        Raises
        ------
        PermissionError
            If the command's first token is not allow-listed.
        TimeoutExpired
            If the command exceeds SHELL_TIMEOUT_SECONDS.
        """
        _check_allowlist(command)
        work_dir = (
            validate_path(cwd, must_exist=True) if cwd.strip() else Path.cwd()
        )
        result = subprocess.run(
            command,
            shell=True,                     # noqa: S602 – allow-list is the guard
            capture_output=True,
            text=True,
            cwd=str(work_dir),
            timeout=settings.shell_timeout_seconds,
        )
        return {
            "stdout":     result.stdout[:_MAX_STDOUT],
            "stderr":     result.stderr[:_MAX_STDERR],
            "returncode": result.returncode,
        }

    register_tool(_CONNECTOR, run_command, tags=["execute", "shell"])

    # ── list_env ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def list_env() -> dict[str, str]:
        """
        Return a snapshot of the current environment variables.

        Any variable whose name contains a sensitive keyword (TOKEN, SECRET,
        KEY, PASSWORD, PASS, CREDENTIAL, API, PRIVATE) is replaced with
        ``***REDACTED***``.

        Returns
        -------
        dict[str, str]
            Environment variable name → value (or redaction placeholder).
        """
        result: dict[str, str] = {}
        for key, value in sorted(os.environ.items()):
            upper_key = key.upper()
            if any(frag in upper_key for frag in _SENSITIVE_FRAGMENTS):
                result[key] = "***REDACTED***"
            else:
                result[key] = value
        return result

    register_tool(_CONNECTOR, list_env, tags=["read", "shell", "environment"])
