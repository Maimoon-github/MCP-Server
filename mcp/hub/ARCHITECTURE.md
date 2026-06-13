# Local MCP Hub – Architecture & Developer Guide

> **100 % local · Zero-cost · No API keys · No telemetry · Open source only**

---

## Table of Contents

1. [Overview](#1-overview)
2. [Folder Structure](#2-folder-structure)
3. [System Architecture Diagram](#3-system-architecture-diagram)
4. [Core Subsystems](#4-core-subsystems)
5. [Connector Model](#5-connector-model)
6. [Security Model](#6-security-model)
7. [Installation – Native](#7-installation--native)
8. [Installation – Docker](#8-installation--docker)
9. [Connecting MCP Clients](#9-connecting-mcp-clients)
10. [Adding a Custom Connector](#10-adding-a-custom-connector)
11. [All Available Tools](#11-all-available-tools)
12. [Environment Variable Reference](#12-environment-variable-reference)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Overview

The **Local MCP Hub** is a production-ready [Model Context Protocol](https://modelcontextprotocol.io/) server that exposes a unified set of tools to any MCP-compatible client (Claude Desktop, Cursor, Continue, Zed …) over **stdio transport** — no TCP ports, no cloud endpoints.

Key properties:

| Property | Detail |
|---|---|
| **Transport** | stdio (stdin / stdout) |
| **Language** | Python 3.10+ |
| **Dependencies** | `mcp`, `pydantic-settings` (+ optional `psycopg2-binary`) |
| **Cost** | Free — zero paid APIs |
| **Cloud calls** | None |
| **Deployment** | Native `python main.py` or `docker compose up` |

---

## 2. Folder Structure

```
hub/
├── main.py                    Entry point – wires everything and runs hub.run()
├── requirements.txt
├── Dockerfile
├── docker-compose.yml         Hub + optional PostgreSQL
├── .env.example               Template for all config
├── ARCHITECTURE.md            ← this file
│
├── mcp_hub/                   Core infrastructure package
│   ├── __init__.py
│   ├── config.py              Pydantic-settings (reads from .env / env vars)
│   ├── auth.py                HMAC-safe token authentication
│   ├── permissions.py         Per-tool READ/WRITE/EXECUTE/ADMIN levels
│   ├── sandbox.py             Path allowlist, file-size cap, timeouts
│   ├── registry.py            Lightweight connector/tool metadata catalogue
│   └── hub.py                 FastMCP assembly – loads connectors conditionally
│
├── connectors/                Pluggable connector package
│   ├── __init__.py
│   ├── base.py                Abstract BaseConnector (OOP style optional)
│   ├── filesystem.py          7 FS tools
│   ├── sqlite_conn.py         4 SQLite tools (stdlib only)
│   ├── postgres_conn.py       3 PostgreSQL tools (requires psycopg2-binary)
│   ├── git_conn.py            6 Git tools (requires git on PATH)
│   └── shell_conn.py          2 Shell tools (opt-in, allow-listed)
│
└── configs/
    ├── claude_desktop.json    Claude Desktop mcpServers snippet
    ├── cursor.json            Cursor mcp.json snippet
    └── permissions.yaml       Human-readable permission reference
```

---

## 3. System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       MCP Client Layer                          │
│  Claude Desktop │ Cursor │ Continue │ Zed │ any MCP client      │
└────────────┬────────────────────────────────────────────────────┘
             │  stdio (stdin / stdout)  — MCP JSON-RPC protocol
             ▼
┌─────────────────────────────────────────────────────────────────┐
│                        Local MCP Hub                            │
│                                                                 │
│  main.py ──► build_hub()                                        │
│                   │                                             │
│       ┌───────────▼───────────┐                                 │
│       │   FastMCP instance    │  hub_info meta-tool             │
│       └───────────┬───────────┘                                 │
│                   │  register(mcp) calls                        │
│      ┌────────────┼──────────────────────┐                      │
│      ▼            ▼            ▼         ▼                      │
│  filesystem   sqlite_conn  git_conn  shell_conn                 │
│  (always)    (if SQLITE_   (if      (if SHELL_                  │
│               DB_PATH)    GIT_ROOT)  ENABLED)                   │
│                                                                 │
│  ┌──────────────────────────────────────────┐                   │
│  │          Security Layer                  │                   │
│  │  auth.py → permissions.py → sandbox.py   │                   │
│  └──────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
             │               │               │
             ▼               ▼               ▼
      Local FS          SQLite /         Git repos /
      (path-sandboxed)  PostgreSQL       shell cmds
```

---

## 4. Core Subsystems

### 4.1 `config.py` — Settings

Uses **pydantic-settings** to load configuration from environment variables or a `.env` file.  Every connector and limit is configurable without touching source code.

```python
from mcp_hub.config import settings

print(settings.server_name)       # "local-mcp-hub"
print(settings.get_allowed_paths()) # [PosixPath('/home/alice/projects')]
```

### 4.2 `auth.py` — Authentication

- **Off by default** (`AUTH_ENABLED=false`) for local development convenience.
- When enabled, clients pass `_token=<hex32>` as a tool argument.
- Uses `hmac.compare_digest` (constant-time) to prevent timing attacks.
- Multiple tokens supported (comma-separated in `AUTH_TOKENS`).

```bash
# Generate a token
python -c "import secrets; print(secrets.token_hex(32))"
```

### 4.3 `permissions.py` — Permission Levels

```
NONE < READ < WRITE < EXECUTE < ADMIN
```

Each tool is assigned a minimum required level at startup via `load_default_permissions()`.  In dev mode (no token map configured) every caller is treated as ADMIN.  In production, use `grant_token_permission(token, PermLevel.READ)` to assign levels per-token.

### 4.4 `sandbox.py` — Sandboxing

| Constraint | Mechanism |
|---|---|
| Path traversal | `Path.resolve()` + `relative_to()` against ALLOWED_PATHS |
| Windows devices | Reject `CON`, `NUL`, `COM1`…`COM9`, `LPT1`…`LPT9` anywhere in path |
| Null bytes | Explicit `\x00` rejection |
| File size | `stat().st_size` check before reading |
| Execution timeout | `threading.Thread` with `join(timeout)` |
| Output size | List slicing with warning sentinel |

### 4.5 `registry.py` — Tool Catalogue

A lightweight metadata store (separate from FastMCP's internal registry).
Used by the `hub_info` meta-tool to return a JSON inventory of all
connectors and tools to clients.

### 4.6 `hub.py` — FastMCP Assembly

Creates a single shared `FastMCP` instance.  Calls each enabled connector's `register(mcp)` function.  Wraps failures gracefully so one bad connector doesn't block the others.

---

## 5. Connector Model

Every connector is a Python module with **one required export**:

```python
def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def my_tool(arg: str) -> str:
        """Tool description shown in hub_info and client UIs."""
        ...
```

The hub calls `register(mcp)` after import.  Connectors are **stateless** by default — they open connections on demand rather than keeping long-lived sockets (except SQLite's `check_same_thread=False` setting).

To add a new connector:
1. Create `connectors/my_connector.py` with a `register(mcp)` function.
2. Add a conditional `_load("connectors.my_connector", "name")` call in `hub.py`.
3. Add a config flag in `config.py` if the connector is optional.

---

## 6. Security Model

### What is protected

| Threat | Mitigation |
|---|---|
| Path traversal (`../../etc/passwd`) | `validate_path()` resolves symlinks and enforces ALLOWED_PATHS |
| Windows device file attacks (`CON`, `NUL`) | Rejected in every path component |
| Token enumeration (timing) | `hmac.compare_digest` constant-time comparison |
| Large file DoS | `MAX_FILE_SIZE_BYTES` (default 10 MB) |
| Runaway queries | `MAX_OUTPUT_ROWS` (default 500) + `TOOL_TIMEOUT_SECONDS` |
| Shell injection | Command allow-list (first token only; `shell_conn` off by default) |
| Secret leakage via env | `list_env` redacts TOKEN, SECRET, KEY, PASSWORD … |
| Dependency confusion | Zero external package calls at runtime |

### What is NOT protected (known limitations)

- The hub runs with the same OS user as the launching process.  Use a dedicated low-privilege OS account for production.
- `shell_conn` with `shell=True` is inherently dangerous if the allow-list is too broad.  Keep it disabled unless needed.
- There is no rate-limiting; a misbehaving client can call tools in a tight loop.

---

## 7. Installation – Native

### Prerequisites

- Python 3.10 or later
- `git` on PATH (for the git connector)
- (Optional) `psycopg2-binary` for PostgreSQL

### Steps

```bash
# 1. Clone / navigate to the hub directory
cd path/to/mcp/hub

# 2. Create and activate a virtual environment (recommended)
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure
cp .env.example .env
# Edit .env with your ALLOWED_PATHS, SQLITE_DB_PATH, etc.

# 5. Run
python main.py
# The server waits silently for an MCP client on stdin.
```

### Verify with MCP Inspector

```bash
pip install mcp[cli]
mcp dev main.py
# Opens a browser-based inspector to call tools manually.
```

---

## 8. Installation – Docker

### Quick start (filesystem + SQLite only)

```bash
cd path/to/mcp/hub

# Copy and edit config
cp .env.example .env

# Create a data directory
mkdir -p data

# Build and run
docker compose up --build
```

### With PostgreSQL

```bash
docker compose --profile postgres up --build
```

Set `POSTGRES_URL=postgresql://mcp:mcp_local@postgres:5432/mcp_db` in `.env`.

> **Note:** Docker deployment is best for running the hub as a background service.
> For Claude Desktop integration, the native install is simpler because Claude Desktop
> launches the server as a child process over stdio.

---

## 9. Connecting MCP Clients

### Claude Desktop

Edit `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "local-mcp-hub": {
      "command": "python",
      "args": ["C:/Users/YourName/Desktop/maimoon/mcp/hub/main.py"]
    }
  }
}
```

Restart Claude Desktop.  The hammer icon in the chat toolbar will show
`local-mcp-hub` tools.

> **Windows tip:** If `python` is not on your PATH, use the full path to the
> Python executable:
> ```json
> "command": "C:/Users/YourName/Desktop/maimoon/mcp/hub/.venv/Scripts/python.exe"
> ```

### Cursor

Edit `~/.cursor/mcp.json` (create it if missing):

```json
{
  "mcpServers": {
    "local-mcp-hub": {
      "command": "python",
      "args": ["/absolute/path/to/mcp/hub/main.py"]
    }
  }
}
```

Reload the Cursor window (Ctrl+Shift+P → "Reload Window").

### Other Clients (Continue, Zed, etc.)

Most MCP-compatible editors use the same `{"command": …, "args": […]}` format.
Check the client's MCP documentation for the exact config file location.

---

## 10. Adding a Custom Connector

```python
# connectors/my_connector.py
from __future__ import annotations
from mcp.server.fastmcp import FastMCP
from mcp_hub.sandbox import validate_path
from mcp_hub.registry import register_connector, register_tool

_CONNECTOR = "my_connector"

def register(mcp: FastMCP) -> None:
    register_connector(_CONNECTOR, "My custom connector")

    @mcp.tool()
    def my_custom_tool(input: str) -> str:
        """One-line description shown in the client UI."""
        # ... your logic here ...
        return f"Processed: {input}"

    register_tool(_CONNECTOR, my_custom_tool, tags=["custom"])
```

Then in `mcp_hub/hub.py`, add inside `build_hub()`:

```python
_load("connectors.my_connector", "my_connector")
```

That's it — no other changes needed.

---

## 11. All Available Tools

### Hub (always on)

| Tool | Description |
|---|---|
| `hub_info()` | Server version, loaded connectors, all tool names |

### Filesystem (always on)

| Tool | Level | Description |
|---|---|---|
| `read_file(path)` | READ | Read file as UTF-8 text |
| `write_file(path, content)` | WRITE | Write text to file |
| `list_directory(path)` | READ | List directory with type/size |
| `search_files(root, pattern)` | READ | Glob for files |
| `get_file_info(path)` | READ | Stat metadata |
| `move_file(src, dst)` | WRITE | Move / rename |
| `delete_file(path)` | WRITE | Delete single file |

### SQLite (if `SQLITE_DB_PATH` set)

| Tool | Level | Description |
|---|---|---|
| `sqlite_query(sql, params?)` | READ | SELECT → list of row dicts |
| `sqlite_tables()` | READ | List tables |
| `sqlite_schema(table)` | READ | CREATE TABLE statement |
| `sqlite_execute(sql, params?)` | WRITE | INSERT/UPDATE/DELETE/DDL |

### PostgreSQL (if `POSTGRES_URL` set)

| Tool | Level | Description |
|---|---|---|
| `pg_query(sql, params?)` | READ | SELECT → list of row dicts |
| `pg_tables()` | READ | List tables in public schema |
| `pg_schema(table)` | READ | Column definitions |

### Git (if `GIT_ROOT` set)

| Tool | Level | Description |
|---|---|---|
| `git_status(repo?)` | READ | Working-tree status |
| `git_log(repo?, n?)` | READ | Recent commits |
| `git_diff(repo?, staged?)` | READ | Diff (unstaged or staged) |
| `git_branch(repo?)` | READ | Local branches |
| `git_add(paths, repo?)` | WRITE | Stage files |
| `git_commit(message, repo?)` | EXECUTE | Create commit |

### Shell (if `SHELL_ENABLED=true`)

| Tool | Level | Description |
|---|---|---|
| `run_command(command, cwd?)` | EXECUTE | Run allow-listed command |
| `list_env()` | READ | Env vars (sensitive redacted) |

---

## 12. Environment Variable Reference

| Variable | Default | Description |
|---|---|---|
| `SERVER_NAME` | `local-mcp-hub` | Server identity name |
| `SERVER_VERSION` | `1.0.0` | Version string |
| `LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING / ERROR |
| `AUTH_ENABLED` | `false` | Enable token auth |
| `AUTH_TOKENS` | _(empty)_ | Comma-separated bearer tokens |
| `ALLOWED_PATHS` | CWD | Comma-separated sandbox roots |
| `SQLITE_DB_PATH` | _(empty)_ | SQLite database path |
| `POSTGRES_URL` | _(empty)_ | PostgreSQL connection URL |
| `GIT_ROOT` | _(empty)_ | Default git repository root |
| `SHELL_ENABLED` | `false` | Enable shell connector |
| `SHELL_ALLOWED_COMMANDS` | `git,python,…` | Allow-listed command prefixes |
| `SHELL_TIMEOUT_SECONDS` | `30` | Shell command timeout |
| `MAX_FILE_SIZE_BYTES` | `10485760` | 10 MB read limit |
| `MAX_OUTPUT_ROWS` | `500` | DB / search result cap |
| `TOOL_TIMEOUT_SECONDS` | `60` | Wall-clock timeout per tool |

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: mcp` | Package not installed | `pip install -r requirements.txt` |
| `ModuleNotFoundError: pydantic_settings` | Package not installed | `pip install pydantic-settings` |
| Hub not appearing in Claude Desktop | Wrong path in config JSON | Use the absolute path, forward slashes |
| `PermissionError` on file read/write | Path outside ALLOWED_PATHS | Add the directory to `ALLOWED_PATHS` in `.env` |
| `FileNotFoundError` for SQLite | Wrong `SQLITE_DB_PATH` | Verify the path exists and is readable |
| `ImportError: psycopg2` | Optional dep not installed | `pip install psycopg2-binary` |
| Git tools fail with "not a git repo" | GIT_ROOT not set / wrong | Set `GIT_ROOT` to the repo root in `.env` |
| Blank output when running `python main.py` manually | Expected — server waits on stdin | Use `mcp dev main.py` for interactive testing |
| Hub slow to start | Connector import overhead | Normal; subsequent calls are fast |
