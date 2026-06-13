# 🗂️ Local MCP File System Server

A **100% local, zero-cost** Model Context Protocol (MCP) server that gives any MCP-compatible client (Claude Desktop, Cursor, etc.) safe read/write access to your file system — no API keys, no cloud calls, no telemetry.

---

## ✅ Requirements

| Requirement | Version |
|---|---|
| Python | 3.10 + |
| `mcp` SDK | Latest |

---

## 📦 Install dependencies

```bash
pip install mcp
```

> **Tip:** Use a virtual environment to keep things tidy:
> ```bash
> python -m venv .venv
> # Windows
> .venv\Scripts\activate
> # macOS / Linux
> source .venv/bin/activate
>
> pip install mcp
> ```

---

## ▶️ Run the server

```bash
python local_mcp_server.py
```

The server communicates over **stdio** (standard input/output) and produces no visible output when idle — this is normal. MCP clients launch and communicate with it automatically.

---

## 🔧 Configure Claude Desktop

Open (or create) the Claude Desktop config file:

| Platform | Path |
|---|---|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux | `~/.config/Claude/claude_desktop_config.json` |

Add the following entry inside the `mcpServers` object (adjust the path to wherever you saved the script):

```json
{
  "mcpServers": {
    "local-filesystem": {
      "command": "python",
      "args": ["C:/Users/YourName/path/to/local_mcp_server.py"]
    }
  }
}
```

> **Windows note:** If `python` is not on your PATH, use the full path to the interpreter, e.g.:
> ```json
> "command": "C:/Users/YourName/.venv/Scripts/python.exe"
> ```

Restart Claude Desktop — the **local-filesystem** server will appear in the tools panel. ✅

---

## 🔧 Configure any other MCP client

Most MCP clients (Cursor, Continue, Zed, etc.) use the same JSON convention.  Point `command` at `python` and `args` at the absolute path of `local_mcp_server.py`.

Example for **Cursor** (`~/.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "local-filesystem": {
      "command": "python",
      "args": ["/absolute/path/to/local_mcp_server.py"]
    }
  }
}
```

---

## 🛠️ Available tools

| Tool | Signature | Description |
|---|---|---|
| `read_file` | `read_file(path: str) → str` | Returns UTF-8 content of a file |
| `write_file` | `write_file(path: str, content: str) → str` | Writes text to a file (creates parent dirs automatically) |
| `list_directory` | `list_directory(path: str) → list` | Lists files & folders with type, size, and absolute path |

---

## 🔒 Security model

- **Path resolution** – all paths are expanded (`~`) and resolved to absolute form before any I/O.
- **Null-byte rejection** – paths containing `\x00` are rejected outright.
- **Windows device names** – `CON`, `NUL`, `COM1`…`COM9`, `LPT1`…`LPT9` are blocked in every path component.
- **Read-only protection** – `write_file` refuses to overwrite files that have the read-only bit set.
- **No shell execution** – the server never spawns subprocesses or evaluates strings as code.

---

## 📂 Project structure

```
mcp/
├── local_mcp_server.py   # The MCP server (single file, no build step)
└── README.md             # This file
```

---

## 💡 Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: mcp` | Run `pip install mcp` in the same Python environment Claude Desktop launches |
| Server not appearing in Claude | Double-check the JSON path has forward slashes and no trailing comma |
| `PermissionError` on write | Run as a user with write access, or change the file's permissions first |
| Blank output when running manually | Expected — the server waits silently for MCP messages on stdin |
