"""
filesystem.py – Enhanced local file-system connector.

Tools registered
----------------
    read_file(path)                  Read a file as UTF-8 text.
    write_file(path, content)        Write / overwrite a file.
    list_directory(path)             List directory entries with metadata.
    search_files(root, pattern)      Glob for files recursively.
    get_file_info(path)              Return stat metadata.
    move_file(src, dst)              Move or rename a file.
    delete_file(path)                Delete a single file (not directories).

Security
--------
All paths go through :func:`mcp_hub.sandbox.validate_path` which enforces
the ALLOWED_PATHS allowlist and rejects path traversal, null bytes, and
Windows reserved device names.
"""
from __future__ import annotations

import datetime
import os
import shutil
import stat as stat_mod
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_hub.sandbox import validate_path, check_file_size
from mcp_hub.registry import register_connector, register_tool
from mcp_hub.config import settings

_CONNECTOR = "filesystem"


def register(mcp: FastMCP) -> None:
    """Attach all filesystem tools to *mcp*."""
    register_connector(_CONNECTOR, "Local file-system read/write/search tools")

    # ── read_file ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def read_file(path: str) -> str:
        """
        Read and return the UTF-8 text content of a file.

        Parameters
        ----------
        path: Absolute or relative path to the file.

        Returns
        -------
        str
            The full UTF-8 text of the file.  Non-decodable bytes are replaced
            with the Unicode replacement character (U+FFFD).

        Raises
        ------
        FileNotFoundError   If the path does not exist.
        IsADirectoryError   If the path is a directory.
        PermissionError     If the process cannot read the file.
        SandboxError        If the path escapes the allowed roots.
        SandboxError        If the file exceeds the size limit.
        """
        resolved = validate_path(path, must_exist=True)
        if resolved.is_dir():
            raise IsADirectoryError(
                f"'{resolved}' is a directory.  Use list_directory() instead."
            )
        if not resolved.is_file():
            raise ValueError(
                f"'{resolved}' is not a regular file (device / socket / pipe?)."
            )
        check_file_size(resolved)
        return resolved.read_text(encoding="utf-8", errors="replace")

    register_tool(_CONNECTOR, read_file, tags=["read", "text"])

    # ── write_file ────────────────────────────────────────────────────────────

    @mcp.tool()
    def write_file(path: str, content: str) -> str:
        """
        Write *content* to a file, creating parent directories as needed.

        Overwrites the file if it already exists.  Raises PermissionError for
        read-only files so data is never silently discarded.

        Parameters
        ----------
        path:    Target file path.
        content: UTF-8 text to write.

        Returns
        -------
        str
            Confirmation message with byte count.
        """
        resolved = validate_path(path)
        if resolved.is_dir():
            raise ValueError(f"'{resolved}' is a directory.  Specify a file path.")
        if resolved.exists():
            s = resolved.stat()
            if not (s.st_mode & stat_mod.S_IWRITE):
                raise PermissionError(
                    f"'{resolved}' is read-only.  Change the file permissions first."
                )
        resolved.parent.mkdir(parents=True, exist_ok=True)
        n = resolved.write_text(content, encoding="utf-8")
        return f"✓ Wrote {n:,} bytes to '{resolved}'."

    register_tool(_CONNECTOR, write_file, tags=["write", "text"])

    # ── list_directory ────────────────────────────────────────────────────────

    @mcp.tool()
    def list_directory(path: str) -> list[dict[str, Any]]:
        """
        List entries in a directory.

        Each entry dict contains:
        - ``name``  – file/folder name
        - ``type``  – "file" | "directory" | "symlink" | "other"
        - ``size``  – size in bytes for files; null for directories
        - ``path``  – absolute path as a string

        Parameters
        ----------
        path: Path to the directory.
        """
        resolved = validate_path(path, must_exist=True)
        if not resolved.is_dir():
            raise NotADirectoryError(
                f"'{resolved}' is not a directory.  Use read_file() to read a file."
            )
        entries: list[dict[str, Any]] = []
        for entry in sorted(
            resolved.iterdir(),
            key=lambda e: (e.is_file(), e.name.lower()),
        ):
            try:
                size: int | None = entry.stat().st_size if entry.is_file() else None
            except OSError:
                size = None

            entry_type = (
                "symlink"   if entry.is_symlink() else
                "directory" if entry.is_dir()     else
                "file"      if entry.is_file()     else
                "other"
            )
            entries.append(
                {"name": entry.name, "type": entry_type, "size": size, "path": str(entry)}
            )
        return entries

    register_tool(_CONNECTOR, list_directory, tags=["read", "directory"])

    # ── search_files ──────────────────────────────────────────────────────────

    @mcp.tool()
    def search_files(root: str, pattern: str = "**/*") -> list[str]:
        """
        Return a list of file paths matching a glob *pattern* under *root*.

        Parameters
        ----------
        root:    Directory to search from.
        pattern: Glob pattern (default: ``**/*`` — all files recursively).
                 Use ``*.py`` for Python files, ``**/*.json`` for nested JSON, etc.

        Returns
        -------
        list[str]
            Sorted absolute paths of matching files (capped at MAX_OUTPUT_ROWS).
        """
        resolved = validate_path(root, must_exist=True)
        if not resolved.is_dir():
            raise NotADirectoryError(f"'{resolved}' is not a directory.")
        matches = sorted(p for p in resolved.glob(pattern) if p.is_file())
        return [str(p) for p in matches[: settings.max_output_rows]]

    register_tool(_CONNECTOR, search_files, tags=["read", "search"])

    # ── get_file_info ─────────────────────────────────────────────────────────

    @mcp.tool()
    def get_file_info(path: str) -> dict[str, Any]:
        """
        Return stat metadata for a file or directory.

        Returned dict keys:
        ``path``, ``type``, ``size_bytes``, ``readable``, ``writable``,
        ``created`` (ISO-8601), ``modified`` (ISO-8601).

        Parameters
        ----------
        path: Path to inspect.
        """
        resolved = validate_path(path, must_exist=True)
        s = resolved.stat()
        return {
            "path":       str(resolved),
            "type":       "directory" if resolved.is_dir() else "file",
            "size_bytes": s.st_size,
            "readable":   os.access(resolved, os.R_OK),
            "writable":   os.access(resolved, os.W_OK),
            "created":    datetime.datetime.fromtimestamp(s.st_ctime).isoformat(),
            "modified":   datetime.datetime.fromtimestamp(s.st_mtime).isoformat(),
        }

    register_tool(_CONNECTOR, get_file_info, tags=["read", "metadata"])

    # ── move_file ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def move_file(src: str, dst: str) -> str:
        """
        Move or rename a file from *src* to *dst*.

        Creates destination parent directories automatically.  Both paths must
        satisfy the sandbox allowlist.

        Parameters
        ----------
        src: Source path.
        dst: Destination path.
        """
        src_p = validate_path(src, must_exist=True)
        dst_p = validate_path(dst)
        dst_p.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src_p), str(dst_p))
        return f"✓ Moved '{src_p}' → '{dst_p}'."

    register_tool(_CONNECTOR, move_file, tags=["write", "rename"])

    # ── delete_file ───────────────────────────────────────────────────────────

    @mcp.tool()
    def delete_file(path: str) -> str:
        """
        Delete a single file.

        For safety, this tool refuses to remove directories.  Use the shell
        connector with an allow-listed ``rm -r`` (or ``rd /s``) if directory
        removal is required.

        Parameters
        ----------
        path: Path to the file to delete.
        """
        resolved = validate_path(path, must_exist=True)
        if resolved.is_dir():
            raise IsADirectoryError(
                f"'{resolved}' is a directory.  delete_file() only removes files."
            )
        resolved.unlink()
        return f"✓ Deleted '{resolved}'."

    register_tool(_CONNECTOR, delete_file, tags=["write", "delete"])
