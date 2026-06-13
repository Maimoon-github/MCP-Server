"""
permissions.py – Fine-grained, per-tool permission control.

Permission levels (ordered – higher includes lower)
---------------------------------------------------
    NONE    – tool is disabled; all callers rejected.
    READ    – safe, idempotent read operations.
    WRITE   – operations that create or mutate data.
    EXECUTE – operations that run code (shell, git commit, etc.).
    ADMIN   – unrestricted; bypasses all checks.

Usage
-----
Each connector tags its tools at registration time:

    from mcp_hub.permissions import load_default_permissions, PermLevel
    load_default_permissions()   # call once at startup

Callers are granted a level tied to their auth token via grant_token_permission().
If no token map is configured, ADMIN is granted to all (local dev mode).
"""
from __future__ import annotations

import enum
import logging
from typing import Final

from .config import settings

logger = logging.getLogger(__name__)


class PermLevel(enum.IntEnum):
    NONE    = 0
    READ    = 1
    WRITE   = 2
    EXECUTE = 3
    ADMIN   = 4


# ── Internal state ────────────────────────────────────────────────────────────

# tool name → minimum required PermLevel
_TOOL_PERMS: dict[str, PermLevel] = {}

# token → granted PermLevel
_TOKEN_PERMS: dict[str, PermLevel] = {}


# ── Registration API ─────────────────────────────────────────────────────────

def register_tool_permission(tool_name: str, level: PermLevel) -> None:
    """Declare the minimum permission level required to call *tool_name*."""
    _TOOL_PERMS[tool_name] = level
    logger.debug("Permission set: %s → %s", tool_name, level.name)


def grant_token_permission(token: str, level: PermLevel) -> None:
    """Assign *level* to *token*."""
    _TOKEN_PERMS[token] = level


# ── Query API ────────────────────────────────────────────────────────────────

def get_tool_permission(tool_name: str) -> PermLevel:
    """Return the minimum level required for *tool_name* (default READ)."""
    return _TOOL_PERMS.get(tool_name, PermLevel.READ)


def check_permission(token: str | None, tool_name: str) -> bool:
    """
    Return True if *token* is allowed to call *tool_name*.

    Dev mode (no token map): every caller is treated as ADMIN.
    """
    required = get_tool_permission(tool_name)
    if required == PermLevel.NONE:
        return False

    # Dev mode: no tokens registered → grant ADMIN to all.
    if not _TOKEN_PERMS:
        return True

    granted = _TOKEN_PERMS.get(token or "", PermLevel.NONE)
    return granted >= required


def assert_permission(token: str | None, tool_name: str) -> None:
    """Raise PermissionError if *token* cannot call *tool_name*."""
    if not check_permission(token, tool_name):
        required = get_tool_permission(tool_name)
        raise PermissionError(
            f"Tool '{tool_name}' requires {required.name} permission. "
            "Contact the server administrator to request access."
        )


# ── Default seed ─────────────────────────────────────────────────────────────

def load_default_permissions() -> None:
    """Register sensible defaults for all built-in tool names."""
    _defaults: dict[str, PermLevel] = {
        # Filesystem
        "read_file":        PermLevel.READ,
        "list_directory":   PermLevel.READ,
        "search_files":     PermLevel.READ,
        "get_file_info":    PermLevel.READ,
        "write_file":       PermLevel.WRITE,
        "move_file":        PermLevel.WRITE,
        "delete_file":      PermLevel.WRITE,
        # SQLite
        "sqlite_query":     PermLevel.READ,
        "sqlite_tables":    PermLevel.READ,
        "sqlite_schema":    PermLevel.READ,
        "sqlite_execute":   PermLevel.WRITE,
        # PostgreSQL
        "pg_query":         PermLevel.READ,
        "pg_tables":        PermLevel.READ,
        "pg_schema":        PermLevel.READ,
        # Git
        "git_status":       PermLevel.READ,
        "git_log":          PermLevel.READ,
        "git_diff":         PermLevel.READ,
        "git_branch":       PermLevel.READ,
        "git_add":          PermLevel.WRITE,
        "git_commit":       PermLevel.EXECUTE,
        # Shell
        "run_command":      PermLevel.EXECUTE,
        "list_env":         PermLevel.READ,
    }
    for name, level in _defaults.items():
        register_tool_permission(name, level)
    logger.info("Default permissions loaded (%d tools).", len(_defaults))


def load_token_permissions() -> None:
    """Parse settings.auth_tokens and populate _TOKEN_PERMS."""
    _TOKEN_PERMS.clear()
    if not settings.auth_enabled or not settings.auth_tokens.strip():
        return

    for item in settings.auth_tokens.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" in item:
            token, level_str = item.split(":", 1)
            token = token.strip()
            level_str = level_str.strip().upper()
            try:
                level = PermLevel[level_str]
            except KeyError:
                logger.warning(
                    "Invalid permission level '%s' for token. Defaulting to ADMIN.",
                    level_str
                )
                level = PermLevel.ADMIN
            grant_token_permission(token, level)
        else:
            grant_token_permission(item, PermLevel.ADMIN)
    if _TOKEN_PERMS:
        logger.info("Token permissions loaded (%d tokens).", len(_TOKEN_PERMS))
