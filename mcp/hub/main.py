"""
main.py – Entry point for the Local MCP Hub.

Usage
-----
    # Native (recommended for development)
    python main.py

    # Docker
    docker compose up

The hub auto-discovers and loads connectors based on environment variables
(see .env.example).  All communication happens over stdio — no TCP ports
are opened.
"""
from __future__ import annotations

import logging
import os
import sys

# ── Ensure 'hub/' is on sys.path regardless of launch directory ───────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from mcp_hub.config import settings
from mcp_hub.hub import build_hub

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stderr,   # keep stdout clean for MCP protocol messages
)

logger = logging.getLogger(__name__)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info(
        "Starting %s v%s  |  auth=%s  |  log=%s",
        settings.server_name,
        settings.server_version,
        "on" if settings.auth_enabled else "off (dev mode)",
        settings.log_level,
    )
    hub = build_hub()
    logger.info("Hub is running on stdio transport.  Waiting for MCP client…")
    hub.run(transport="stdio")
