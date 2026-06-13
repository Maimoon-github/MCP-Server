"""
base.py – Abstract base class that all connectors must subclass.

Connector contract
------------------
Every connector module must expose a top-level ``register(mcp)`` function
that attaches the connector's tools to the shared FastMCP instance:

    from mcp.server.fastmcp import FastMCP

    def register(mcp: FastMCP) -> None:
        @mcp.tool()
        def my_tool(arg: str) -> str:
            ...

The :class:`BaseConnector` class is provided for connectors that prefer an
OOP style.  Stateless connectors can skip inheritance and just export
``register`` directly (see the other connector modules for examples).
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from mcp.server.fastmcp import FastMCP


class BaseConnector(ABC):
    """
    Optional base class for object-oriented connectors.

    Attributes
    ----------
    name:        Short connector identifier (e.g. "filesystem").
    description: One-line description shown in hub_info output.
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    def register(self, mcp: FastMCP) -> None:
        """Attach this connector's tools to *mcp*."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r}>"
