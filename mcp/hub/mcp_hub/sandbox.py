"""
sandbox.py – Sandboxing and resource-limit utilities.

Provides
--------
validate_path(raw, must_exist)   Resolve path and verify it is inside an allowed root.
check_file_size(path)            Reject files exceeding MAX_FILE_SIZE_BYTES.
with_timeout(seconds, fn, ...)   Run a callable with a wall-clock timeout.
trim_rows(data, label)           Truncate lists to MAX_OUTPUT_ROWS.

Security model
--------------
- Paths are fully resolved (symlinks followed) before comparison.
- The resolved path must sit *under* one of the configured ALLOWED_PATHS roots.
- Windows reserved device names (CON, NUL, COM1–COM9, LPT1–LPT9) are rejected
  anywhere in the path, even inside sub-components.
- Null bytes in path strings are rejected outright.
"""
from __future__ import annotations

import os
import stat
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

from .config import settings

T = TypeVar("T")

# Windows reserved device names (checked case-insensitively)
_WIN_RESERVED: frozenset[str] = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


class SandboxError(ValueError):
    """Raised when a sandboxing constraint is violated."""


# ── Path validation ───────────────────────────────────────────────────────────

def validate_path(raw_path: str, *, must_exist: bool = False) -> Path:
    """
    Resolve *raw_path* to an absolute :class:`~pathlib.Path` and verify that
    it resides under one of the configured ALLOWED_PATHS roots.

    Parameters
    ----------
    raw_path:   User-supplied path string.
    must_exist: If True, raise :exc:`FileNotFoundError` when missing.

    Returns
    -------
    Path
        The fully resolved, validated path.

    Raises
    ------
    SandboxError
        On null bytes, empty input, or a Windows reserved device name.
    PermissionError
        If the resolved path escapes the allowed roots.
    FileNotFoundError
        If *must_exist* is True and the path does not exist.
    """
    if not raw_path or not raw_path.strip():
        raise SandboxError("Path must not be empty.")
    if "\x00" in raw_path:
        raise SandboxError("Path contains an illegal null byte (\\x00).")

    resolved = Path(raw_path).expanduser().resolve()

    # Reject Windows reserved device names in every path component.
    for part in resolved.parts:
        stem = Path(part).stem.upper()
        if stem in _WIN_RESERVED:
            raise SandboxError(
                f"Path component '{part}' is a Windows reserved device name "
                "and cannot be used."
            )

    # Allowlist check: resolved path must be under at least one allowed root.
    allowed_roots = settings.get_allowed_paths()
    if not any(_is_descendant(resolved, root) for root in allowed_roots):
        roots_str = "\n  ".join(str(r) for r in allowed_roots)
        raise PermissionError(
            f"Access denied: '{resolved}' is outside the allowed paths:\n"
            f"  {roots_str}\n"
            "Update ALLOWED_PATHS in your .env to grant access."
        )

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"No such file or directory: '{resolved}'")

    return resolved


def _is_descendant(path: Path, root: Path) -> bool:
    """Return True if *path* equals *root* or is inside it."""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


# ── File-size guard ───────────────────────────────────────────────────────────

def check_file_size(path: Path) -> None:
    """
    Raise :exc:`SandboxError` if *path* exceeds the configured size limit.

    Does nothing for directories or non-existent paths.
    """
    if not path.is_file():
        return
    size = path.stat().st_size
    limit = settings.max_file_size_bytes
    if size > limit:
        raise SandboxError(
            f"File '{path.name}' is {size:,} bytes, which exceeds the "
            f"{limit:,}-byte limit (MAX_FILE_SIZE_BYTES). "
            "Read a smaller slice or increase the limit in .env."
        )


# ── Execution timeout ─────────────────────────────────────────────────────────

def with_timeout(seconds: int, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """
    Execute *fn*(*args*, **kwargs) on a daemon thread and block for at most
    *seconds* wall-clock seconds.

    Raises
    ------
    TimeoutError
        If the function does not return within the allotted time.
    Exception
        Any exception raised inside *fn* is re-raised in the caller's thread.
    """
    result: list[T] = []
    error: list[BaseException] = []

    def _target() -> None:
        try:
            result.append(fn(*args, **kwargs))
        except BaseException as exc:  # noqa: BLE001
            error.append(exc)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join(seconds)

    if thread.is_alive():
        raise TimeoutError(
            f"Tool execution timed out after {seconds} second(s). "
            "Increase TOOL_TIMEOUT_SECONDS in .env if needed."
        )
    if error:
        raise error[0]
    return result[0]


# ── Output truncation ─────────────────────────────────────────────────────────

def trim_rows(data: list[Any], label: str = "rows") -> list[Any]:
    """
    Truncate *data* to at most MAX_OUTPUT_ROWS entries.

    Appends a sentinel ``{"__warning__": "…"}`` dict when trimming occurs
    so the caller knows the result set was cut.
    """
    limit = settings.max_output_rows
    if len(data) <= limit:
        return data
    trimmed = data[:limit]
    trimmed.append(
        {
            "__warning__": (
                f"Result truncated: showing {limit} of {len(data)} {label}. "
                "Narrow your query or increase MAX_OUTPUT_ROWS in .env."
            )
        }
    )
    return trimmed
