"""
registry.py – Connector and tool metadata registry.

This module maintains a lightweight catalogue of connectors and their
tools, separate from FastMCP's internal tool list.  It provides a
human-readable inventory that the hub can expose via a `list_tools` meta-tool.

Usage
-----
    from mcp_hub.registry import register_connector, register_tool, list_tools

    # At connector load time:
    register_connector("filesystem", "Local file-system read/write tools")
    register_tool("filesystem", read_file_fn, description="...", tags=["fs", "read"])
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass(frozen=False)
class ToolEntry:
    """Lightweight metadata for one registered tool."""
    name: str
    connector: str
    description: str
    tags: list[str] = field(default_factory=list)
    enabled: bool = True


@dataclass(frozen=False)
class ConnectorEntry:
    """Lightweight metadata for one registered connector."""
    name: str
    description: str
    tools: list[ToolEntry] = field(default_factory=list)
    enabled: bool = True


# ── Internal registry ─────────────────────────────────────────────────────────

_CONNECTORS: dict[str, ConnectorEntry] = {}


# ── Public API ────────────────────────────────────────────────────────────────

def register_connector(name: str, description: str = "") -> ConnectorEntry:
    """
    Register (or retrieve) a connector entry by *name*.

    Idempotent – calling twice with the same name returns the existing entry.
    """
    if name not in _CONNECTORS:
        _CONNECTORS[name] = ConnectorEntry(name=name, description=description)
        logger.info("Connector registered: %s", name)
    return _CONNECTORS[name]


def register_tool(
    connector_name: str,
    fn: Callable,
    *,
    description: str = "",
    tags: list[str] | None = None,
) -> ToolEntry:
    """
    Add *fn* as a tool belonging to *connector_name*.

    Parameters
    ----------
    connector_name: Name of the owning connector (auto-created if missing).
    fn:             The callable tool function (used to derive the name).
    description:    Short description; falls back to the first line of ``fn.__doc__``.
    tags:           Optional topic tags (e.g. ["read", "filesystem"]).
    """
    connector = _CONNECTORS.get(connector_name) or register_connector(connector_name)
    doc = (fn.__doc__ or "").strip().splitlines()
    entry = ToolEntry(
        name=fn.__name__,
        connector=connector_name,
        description=description or (doc[0] if doc else ""),
        tags=tags or [],
    )
    connector.tools.append(entry)
    logger.debug("Tool registered: %s / %s", connector_name, fn.__name__)
    return entry


def list_connectors() -> list[ConnectorEntry]:
    """Return all registered connectors (enabled or not)."""
    return list(_CONNECTORS.values())


def list_tools(only_enabled: bool = True) -> list[ToolEntry]:
    """Return all tools across all connectors."""
    return [
        tool
        for conn in _CONNECTORS.values()
        if not only_enabled or conn.enabled
        for tool in conn.tools
        if not only_enabled or tool.enabled
    ]


def get_tool(name: str) -> ToolEntry | None:
    """Look up a tool entry by function name."""
    return next((t for t in list_tools() for t in [t] if t.name == name), None)


def summary() -> dict[str, list[str]]:
    """Return a {connector: [tool_name, …]} summary dict."""
    return {
        c.name: [t.name for t in c.tools]
        for c in _CONNECTORS.values()
    }
