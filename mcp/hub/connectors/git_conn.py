"""
git_conn.py – Git repository connector.

Requires ``git`` to be installed and on the system PATH.

Configuration
-------------
Set in .env:
    GIT_ROOT=/absolute/path/to/your/repo

Tools registered
----------------
    git_status(repo?)           Working-tree status (--short --branch).
    git_log(repo?, n?)          Recent commit log (oneline).
    git_diff(repo?, staged?)    Unstaged or staged diff.
    git_branch(repo?)           Local branch list.
    git_add(paths, repo?)       Stage one or more files.
    git_commit(message, repo?)  Commit staged changes.

Security
--------
- ``subprocess.run`` is used with ``shell=False`` and an explicit argument
  list to prevent shell-injection attacks.
- The repo directory is validated against the sandbox allowlist.
- Commit messages are length-capped and stripped of leading/trailing whitespace.
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_hub.config import settings
from mcp_hub.sandbox import validate_path
from mcp_hub.registry import register_connector, register_tool

_CONNECTOR = "git"
_MAX_MSG_LEN = 500       # Maximum commit message length
_MAX_DIFF_BYTES = 65_536  # 64 KB diff cap


def _git(args: list[str], cwd: str, timeout: int = 30) -> str:
    """
    Run ``git <args>`` in *cwd* and return stdout.

    Raises RuntimeError on non-zero exit codes with stderr as the message.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        err = result.stderr.strip() or f"git {args[0]!r} exited with code {result.returncode}."
        raise RuntimeError(err)
    return result.stdout.strip()


def _resolve_repo(repo: str | None) -> str:
    """Return the absolute path to the git repository to operate on."""
    target = repo or settings.git_root
    if not target:
        raise ValueError(
            "No 'repo' path provided and GIT_ROOT is not set in .env.\n"
            "Either pass 'repo' to the tool call or set GIT_ROOT."
        )
    resolved = validate_path(target, must_exist=True)
    return str(resolved)


def register(mcp: FastMCP) -> None:
    """Attach all Git tools to *mcp*."""
    register_connector(_CONNECTOR, "Git repository inspection and commit tools")

    # ── git_status ────────────────────────────────────────────────────────────

    @mcp.tool()
    def git_status(repo: str = "") -> str:
        """
        Return the working-tree status of a Git repository.

        Equivalent to ``git status --short --branch``.

        Parameters
        ----------
        repo: Repository root directory.  Defaults to GIT_ROOT from .env.
        """
        return _git(["status", "--short", "--branch"], _resolve_repo(repo or None))

    register_tool(_CONNECTOR, git_status, tags=["read", "git"])

    # ── git_log ───────────────────────────────────────────────────────────────

    @mcp.tool()
    def git_log(repo: str = "", n: int = 10) -> str:
        """
        Return the last *n* commits in a compact one-line format.

        Parameters
        ----------
        repo: Repository root.  Defaults to GIT_ROOT.
        n:    Number of commits to show (1 – 100, default 10).
        """
        n = max(1, min(int(n), 100))
        return _git(
            ["log", f"-{n}", "--oneline", "--decorate", "--graph"],
            _resolve_repo(repo or None),
        )

    register_tool(_CONNECTOR, git_log, tags=["read", "git", "history"])

    # ── git_diff ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def git_diff(repo: str = "", staged: bool = False) -> str:
        """
        Return the diff of changes in the working tree.

        Parameters
        ----------
        repo:   Repository root.  Defaults to GIT_ROOT.
        staged: If True, show the diff of staged (``--cached``) changes.
                If False (default), show unstaged changes.

        Returns
        -------
        str
            Unified diff text (capped at 64 KB).
        """
        args = ["diff"]
        if staged:
            args.append("--cached")
        output = _git(args, _resolve_repo(repo or None))
        if len(output) > _MAX_DIFF_BYTES:
            output = output[:_MAX_DIFF_BYTES] + "\n… [diff truncated at 64 KB] …"
        return output or "(no changes)"

    register_tool(_CONNECTOR, git_diff, tags=["read", "git", "diff"])

    # ── git_branch ────────────────────────────────────────────────────────────

    @mcp.tool()
    def git_branch(repo: str = "") -> str:
        """
        List local branches with their tip commit summaries.

        Equivalent to ``git branch -v``.

        Parameters
        ----------
        repo: Repository root.  Defaults to GIT_ROOT.
        """
        return _git(["branch", "-v"], _resolve_repo(repo or None))

    register_tool(_CONNECTOR, git_branch, tags=["read", "git"])

    # ── git_add ───────────────────────────────────────────────────────────────

    @mcp.tool()
    def git_add(paths: str, repo: str = "") -> str:
        """
        Stage one or more files for the next commit.

        Parameters
        ----------
        paths: Space-separated relative paths inside the repository to stage.
               Use ``.`` to stage all changes.
        repo:  Repository root.  Defaults to GIT_ROOT.

        Returns
        -------
        str
            Confirmation or git output.
        """
        path_list = paths.split()
        if not path_list:
            raise ValueError("'paths' must not be empty.  Provide at least one path.")
        result = _git(["add", "--verbose", "--"] + path_list, _resolve_repo(repo or None))
        return result or f"✓ Staged: {paths}"

    register_tool(_CONNECTOR, git_add, tags=["write", "git"])

    # ── git_commit ────────────────────────────────────────────────────────────

    @mcp.tool()
    def git_commit(message: str, repo: str = "") -> str:
        """
        Create a commit with *message* for currently staged changes.

        Parameters
        ----------
        message: Commit message (required, max 500 characters).
        repo:    Repository root.  Defaults to GIT_ROOT.

        Returns
        -------
        str
            Git output including the new commit hash.

        Raises
        ------
        ValueError
            If *message* is empty or exceeds the length limit.
        RuntimeError
            If there is nothing to commit or git returns a non-zero exit code.
        """
        message = message.strip()
        if not message:
            raise ValueError("Commit message must not be empty.")
        if len(message) > _MAX_MSG_LEN:
            raise ValueError(
                f"Commit message too long ({len(message)} chars).  "
                f"Keep it under {_MAX_MSG_LEN} characters."
            )
        return _git(["commit", "-m", message], _resolve_repo(repo or None))

    register_tool(_CONNECTOR, git_commit, tags=["execute", "git", "write"])
