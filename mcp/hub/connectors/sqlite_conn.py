"""
sqlite_conn.py – SQLite database connector.

Requires only the Python standard-library ``sqlite3`` module — no extra
packages needed.

Configuration
-------------
Set in .env:
    SQLITE_DB_PATH=/absolute/path/to/database.sqlite3

Tools registered
----------------
    sqlite_query(sql, params?)   Run a SELECT → list of row dicts.
    sqlite_tables()              List all user-defined tables.
    sqlite_schema(table)         Return the CREATE TABLE statement.
    sqlite_execute(sql, params?) INSERT / UPDATE / DELETE / DDL; returns row count.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_hub.config import settings
from mcp_hub.sandbox import trim_rows
from mcp_hub.registry import register_connector, register_tool

_CONNECTOR = "sqlite"


def _connect() -> sqlite3.Connection:
    """Open the configured SQLite database and return a connection."""
    db_path = Path(settings.sqlite_db_path).expanduser().resolve()
    if not db_path.exists():
        raise FileNotFoundError(
            f"SQLite database not found: '{db_path}'.\n"
            "Check SQLITE_DB_PATH in your .env file."
        )
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_params(params: str) -> list[Any]:
    """Parse a JSON-encoded parameter list, defaulting to []."""
    try:
        parsed = json.loads(params or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"'params' must be a valid JSON array (e.g. '[1, \"foo\"]'). Error: {exc}"
        ) from exc
    if not isinstance(parsed, list):
        raise ValueError("'params' must be a JSON array, not an object or scalar.")
    return parsed


def register(mcp: FastMCP) -> None:
    """Attach all SQLite tools to *mcp*."""
    register_connector(_CONNECTOR, "SQLite local database query and management")

    # ── sqlite_query ──────────────────────────────────────────────────────────

    @mcp.tool()
    def sqlite_query(sql: str, params: str = "[]") -> list[dict[str, Any]]:
        """
        Execute a read-only SELECT statement and return rows as a list of dicts.

        Parameters
        ----------
        sql:    A SELECT query.  Only SELECT is accepted; use sqlite_execute for writes.
        params: JSON array of positional parameters.  Example: ``[42, "Alice"]``.

        Returns
        -------
        list[dict]
            Each dict maps column names to values.
            Results are capped at MAX_OUTPUT_ROWS (configurable in .env).
        """
        if not sql.strip().upper().startswith("SELECT"):
            raise ValueError(
                "sqlite_query only accepts SELECT statements.  "
                "Use sqlite_execute() for INSERT/UPDATE/DELETE/DDL."
            )
        p = _parse_params(params)
        with _connect() as conn:
            cur = conn.execute(sql, p)
            rows = [dict(row) for row in cur.fetchall()]
        return trim_rows(rows)

    register_tool(_CONNECTOR, sqlite_query, tags=["read", "sql"])

    # ── sqlite_tables ─────────────────────────────────────────────────────────

    @mcp.tool()
    def sqlite_tables() -> list[str]:
        """
        Return the names of all user-defined tables in the SQLite database.

        Returns
        -------
        list[str]
            Table names sorted alphabetically.
        """
        with _connect() as conn:
            cur = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' "
                "ORDER BY name"
            )
            return [row[0] for row in cur.fetchall()]

    register_tool(_CONNECTOR, sqlite_tables, tags=["read", "schema"])

    # ── sqlite_schema ─────────────────────────────────────────────────────────

    @mcp.tool()
    def sqlite_schema(table: str) -> str:
        """
        Return the ``CREATE TABLE`` statement for *table*.

        Parameters
        ----------
        table: Name of the table to inspect.

        Returns
        -------
        str
            The original DDL statement stored in ``sqlite_master``.

        Raises
        ------
        ValueError
            If *table* does not exist.
        """
        with _connect() as conn:
            cur = conn.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type='table' AND name=?",
                (table,),
            )
            row = cur.fetchone()
        if row is None:
            raise ValueError(
                f"Table '{table}' not found in the database.  "
                "Call sqlite_tables() to see available tables."
            )
        return row[0]

    register_tool(_CONNECTOR, sqlite_schema, tags=["read", "schema"])

    # ── sqlite_execute ────────────────────────────────────────────────────────

    @mcp.tool()
    def sqlite_execute(sql: str, params: str = "[]") -> dict[str, Any]:
        """
        Execute a write SQL statement (INSERT, UPDATE, DELETE, CREATE TABLE, …).

        Parameters
        ----------
        sql:    Any SQL statement (except SELECT — use sqlite_query for reads).
        params: JSON array of positional parameters.

        Returns
        -------
        dict
            ``{"rowcount": int, "lastrowid": int | None}``
        """
        p = _parse_params(params)
        with _connect() as conn:
            cur = conn.execute(sql, p)
            conn.commit()
            return {"rowcount": cur.rowcount, "lastrowid": cur.lastrowid}

    register_tool(_CONNECTOR, sqlite_execute, tags=["write", "sql"])
