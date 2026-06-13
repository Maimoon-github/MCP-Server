"""
hub.py – Central FastMCP assembly for the Local MCP Hub.

This module creates the single shared :class:`~mcp.server.fastmcp.FastMCP`
instance and conditionally loads each connector based on environment
configuration.  It also registers a built-in ``hub_info`` meta-tool that
lets clients discover available tools and connector status.

Import and run
--------------
    from mcp_hub.hub import build_hub
    hub = build_hub()
    hub.run(transport="stdio")
"""
from __future__ import annotations

import inspect
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import settings
from .permissions import load_default_permissions, load_token_permissions, assert_permission
from .auth import verify_token, AuthError
from .registry import register_connector, register_tool, summary

logger = logging.getLogger(__name__)

# ── Shared FastMCP instance ────────────────────────────────────────────────────

mcp = FastMCP(name=settings.server_name)
mcp._mcp_server.version = settings.server_version

# Apply monkeypatch to mcp.tool to enforce authentication and fine-grained permissions
_original_tool_decorator = mcp.tool

def secure_tool_decorator(*args, **kwargs):
    decorator = _original_tool_decorator(*args, **kwargs)
    
    def secure_decorator(func):
        # hub_info does not require auth/permissions, and we do not patch if auth is disabled.
        if func.__name__ == "hub_info" or not settings.auth_enabled:
            return decorator(func)
            
        # 1. Modify signature to include token parameter
        sig = inspect.signature(func)
        params = list(sig.parameters.values())
        
        if not any(p.name == 'token' for p in params):
            new_param = inspect.Parameter(
                'token',
                inspect.Parameter.KEYWORD_ONLY,
                default='',
                annotation=str
            )
            params.append(new_param)
            
        new_sig = sig.replace(parameters=params)
        
        # 2. Create the secure wrapper
        def secure_wrapper(*w_args, **w_kwargs):
            token = w_kwargs.pop('token', '')
            if not verify_token(token):
                raise AuthError("Unauthorized: invalid or missing token.")
            assert_permission(token, func.__name__)
            return func(*w_args, **w_kwargs)
            
        secure_wrapper.__signature__ = new_sig
        secure_wrapper.__name__ = func.__name__
        secure_wrapper.__doc__ = func.__doc__
        secure_wrapper.__annotations__ = dict(func.__annotations__)
        secure_wrapper.__annotations__['token'] = str
        
        return decorator(secure_wrapper)
        
    return secure_decorator

mcp.tool = secure_tool_decorator

# Track which connectors loaded successfully.
_loaded: list[str] = []
_failed: list[dict[str, str]] = []


# ── Meta-tool: hub_info ────────────────────────────────────────────────────────

@mcp.tool()
def hub_info() -> dict[str, Any]:
    """
    Return metadata about the hub: version, loaded connectors, and all
    available tools grouped by connector.

    This tool is always available and requires no authentication.
    """
    return {
        "server_name":    settings.server_name,
        "server_version": settings.server_version,
        "auth_enabled":   settings.auth_enabled,
        "connectors_ok":  _loaded,
        "connectors_err": _failed,
        "tools":          summary(),
    }


# ── Connector loader ───────────────────────────────────────────────────────────

def _load(module_path: str, connector_name: str) -> bool:
    """
    Import *module_path* and call its ``register(mcp)`` function.

    Returns True on success, False on any failure (logged as WARNING).
    """
    from importlib import import_module

    try:
        mod = import_module(module_path)
        mod.register(mcp)
        _loaded.append(connector_name)
        logger.info("✓ Connector loaded: %s", connector_name)
        return True
    except ImportError as exc:
        msg = f"Missing dependency – {exc}"
        _failed.append({"connector": connector_name, "error": msg})
        logger.warning("✗ Connector '%s' skipped: %s", connector_name, msg)
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        _failed.append({"connector": connector_name, "error": msg})
        logger.error("✗ Connector '%s' failed: %s", connector_name, msg, exc_info=True)
    return False


def build_hub() -> FastMCP:
    """
    Initialise permissions, load all enabled connectors, and return the
    configured :class:`~mcp.server.fastmcp.FastMCP` instance.

    Call this once at startup, then pass the result to ``hub.run()``.
    """
    load_default_permissions()
    load_token_permissions()

    # ── Always-on connectors ──────────────────────────────────────────────────
    _load("connectors.filesystem", "filesystem")

    # ── Conditional connectors (controlled by .env) ───────────────────────────
    if settings.sqlite_db_path.strip():
        _load("connectors.sqlite_conn", "sqlite")

    if settings.postgres_url.strip():
        _load("connectors.postgres_conn", "postgresql")

    if settings.git_root.strip():
        _load("connectors.git_conn", "git")

    if settings.shell_enabled:
        _load("connectors.shell_conn", "shell")

    total_tools = sum(len(v) for v in summary().values())
    logger.info(
        "Hub ready: %d connector(s) loaded, %d tool(s) registered.",
        len(_loaded),
        total_tools,
    )
    return mcp
