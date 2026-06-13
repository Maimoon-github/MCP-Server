"""
postgres_conn.py – PostgreSQL connector.

Requires: ``pip install psycopg2-binary``

Configuration
-------------
Set in .env:
    POSTGRES_URL=postgresql://user:password@localhost:5432/dbname

Tools registered
----------------
    pg_query(sql, params?)   SELECT → list of row dicts.
    pg_tables()              List tables in the public schema.
    pg_schema(table)         Column definitions for a table.

Notes
-----
- Only SELECT is allowed via pg_query.  There is intentionally no pg_execute
  to prevent unintentional data mutations; add one if your use-case requires it.
- Connections are opened per-request (psycopg2 is thread-safe at module level).
"""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_hub.config import settings
from mcp_hub.sandbox import trim_rows
from mcp_hub.registry import register_connector, register_tool

_CONNECTOR = "postgresql"


def _get_psycopg2():
    """Import psycopg2 or raise a helpful error."""
    try:
        import psycopg2
        import psycopg2.extras
        return psycopg2
    except ImportError as exc:
        raise ImportError(
            "psycopg2-binary is required for the PostgreSQL connector.\n"
            "Install it with:  pip install psycopg2-binary"
        ) from exc


def _connect():
    """Return a new psycopg2 connection using the configured URL."""
    psycopg2 = _get_psycopg2()
    url = settings.postgres_url
    if not url:
        raise RuntimeError(
            "POSTGRES_URL is not set.  Configure it in .env to enable this connector."
        )
    return psycopg2.connect(url)


def _parse_params(params: str) -> list[Any]:
    try:
        parsed = json.loads(params or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"'params' must be a valid JSON array.  Error: {exc}"
        ) from exc
    if not isinstance(parsed, list):
        raise ValueError("'params' must be a JSON array.")
    return parsed


def register(mcp: FastMCP) -> None:
    """Attach all PostgreSQL tools to *mcp*."""
    register_connector(_CONNECTOR, "Local PostgreSQL database read-only tools")

    # ── pg_query ──────────────────────────────────────────────────────────────

    @mcp.tool()
    def pg_query(sql: str, params: str = "[]") -> list[dict[str, Any]]:
        """
        Execute a read-only PostgreSQL SELECT and return rows as a list of dicts.

        Parameters
        ----------
        sql:    A SELECT query.
        params: JSON array of positional parameters (uses ``%s`` placeholders).
                Example: ``[42, "Alice"]``

        Returns
        -------
        list[dict]
            Each dict maps column names to Python values.
            JSON, UUID, and timestamp columns are automatically coerced.
            Results capped at MAX_OUTPUT_ROWS.
        """
        if not sql.strip().upper().startswith("SELECT"):
            raise ValueError(
                "pg_query only accepts SELECT statements.  "
                "Connect directly via psql for write operations."
            )
        import psycopg2.extras  # noqa: PLC0415

        p = _parse_params(params)
        conn = _connect()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, p)
                rows = [dict(r) for r in cur.fetchall()]
        finally:
            conn.close()
        return trim_rows(rows)

    register_tool(_CONNECTOR, pg_query, tags=["read", "sql", "postgres"])

    # ── pg_tables ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def pg_tables() -> list[str]:
        """
        List all table names in the ``public`` schema of the configured database.

        Returns
        -------
        list[str]
            Table names sorted alphabetically.
        """
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = 'public' ORDER BY tablename"
                )
                return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    register_tool(_CONNECTOR, pg_tables, tags=["read", "schema", "postgres"])

    # ── pg_schema ─────────────────────────────────────────────────────────────

    @mcp.tool()
    def pg_schema(table: str) -> list[dict[str, Any]]:
        """
        Return the column definitions for a table in the public schema.

        Parameters
        ----------
        table: Table name.

        Returns
        -------
        list[dict]
            Each dict has keys:
            ``column_name``, ``data_type``, ``is_nullable``, ``column_default``.
            Ordered by ordinal position (i.e., as declared in CREATE TABLE).
        """
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        column_name,
                        data_type,
                        is_nullable,
                        column_default
                    FROM information_schema.columns
                    WHERE table_schema = 'public'
                      AND table_name   = %s
                    ORDER BY ordinal_position
                    """,
                    (table,),
                )
                keys = ["column_name", "data_type", "is_nullable", "column_default"]
                rows = [dict(zip(keys, row)) for row in cur.fetchall()]
        finally:
            conn.close()

        if not rows:
            raise ValueError(
                f"Table '{table}' not found in the public schema.  "
                "Call pg_tables() to see available tables."
            )
        return rows

    register_tool(_CONNECTOR, pg_schema, tags=["read", "schema", "postgres"])
