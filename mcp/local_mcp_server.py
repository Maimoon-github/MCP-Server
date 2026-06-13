#!/usr/bin/env python3
"""
local_mcp_server.py – Single-file Model Context Protocol (MCP) server.

Provides safe, local read/write access to the user's filesystem over stdio.
Designed for 100% local, zero-cost operation under the MCP standard protocol.
"""
from __future__ import annotations

import logging
import os
import sys
import stat as stat_mod
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

# Set up logging to stderr so it does not interfere with stdout (used by stdio transport)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("local-filesystem")

# Initialize FastMCP server
mcp = FastMCP(name="local-filesystem")
mcp._mcp_server.version = "1.0.0"

# Windows reserved device names (checked case-insensitively)
_WIN_RESERVED: frozenset[str] = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


def _validate_path(raw_path: str, *, must_exist: bool = False) -> Path:
    """
    Validate path according to security guidelines:
      - Null-byte rejection
      - Windows device name component blocking
      - Path resolution (expands ~ and resolves symlinks)
    """
    if not raw_path or not raw_path.strip():
        raise ValueError("Path must not be empty.")
    
    if "\x00" in raw_path:
        raise ValueError("Path contains an illegal null byte (\\x00).")
    
    # Expand and resolve path
    resolved = Path(raw_path).expanduser().resolve()
    
    # Reject Windows reserved device names in any component of the path
    for part in resolved.parts:
        stem = Path(part).stem.upper()
        if stem in _WIN_RESERVED:
            raise PermissionError(
                f"Path component '{part}' is a Windows reserved device name and cannot be accessed."
            )
            
    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"No such file or directory: '{resolved}'")
        
    return resolved


@mcp.tool()
def read_file(path: str) -> str:
    """
    Read and return the UTF-8 text content of a file.

    Parameters
    ----------
    path: Absolute or relative path to the file.
    """
    resolved = _validate_path(path, must_exist=True)
    if resolved.is_dir():
        raise IsADirectoryError(f"'{resolved}' is a directory. Use list_directory() instead.")
    if not resolved.is_file():
        raise ValueError(f"'{resolved}' is not a regular file.")
        
    return resolved.read_text(encoding="utf-8", errors="replace")


@mcp.tool()
def write_file(path: str, content: str) -> str:
    """
    Write or overwrite text content to a file, creating parent directories if needed.

    Parameters
    ----------
    path:    Target file path.
    content: UTF-8 text content to write.
    """
    resolved = _validate_path(path)
    if resolved.is_dir():
        raise IsADirectoryError(f"'{resolved}' is a directory. Specify a file path.")
        
    if resolved.exists():
        s = resolved.stat()
        if not (s.st_mode & stat_mod.S_IWRITE):
            raise PermissionError(
                f"'{resolved}' is read-only. Change the file permissions first."
            )
            
    # Auto-create parent directories if they do not exist
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(content, encoding="utf-8")
    return f"✓ Successfully wrote to '{resolved}'."


@mcp.tool()
def list_directory(path: str) -> list[dict[str, Any]]:
    """
    List files & folders with type, size, and absolute path.

    Parameters
    ----------
    path: Path to the directory.
    """
    resolved = _validate_path(path, must_exist=True)
    if not resolved.is_dir():
        raise NotADirectoryError(f"'{resolved}' is not a directory.")
        
    entries: list[dict[str, Any]] = []
    for entry in sorted(resolved.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
        try:
            size = entry.stat().st_size if entry.is_file() else None
        except OSError:
            size = None
            
        entry_type = (
            "symlink" if entry.is_symlink()
            else "directory" if entry.is_dir()
            else "file" if entry.is_file()
            else "other"
        )
        entries.append({
            "name": entry.name,
            "type": entry_type,
            "size": size,
            "path": str(entry),
        })
    return entries


if __name__ == "__main__":
    logger.info("Starting local-filesystem MCP server on stdio transport...")
    mcp.run(transport="stdio")
