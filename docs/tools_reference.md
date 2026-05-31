# Tools Reference

> Auto-generated catalog of all built-in tools available in the Universal MCP Server.

---

## Overview

Tools are **actions** the AI host can execute. Each tool has a name, description, JSON Schema input validation, and an async execution handler.

| Category | Tools | Description |
|----------|-------|-------------|
| **Filesystem** | `read_file`, `write_file`, `list_dir`, `search_files` | Local file system operations |
| **System** | `execute_command`, `get_env`, `get_processes` | Shell and environment access |
| **Web** | `fetch_url`, `search_web`, `parse_html` | HTTP and web scraping |
| **Code** | `run_python`, `lint_code`, `format_code` | Code execution and analysis |
| **Database** | `query_sql`, `migrate_db`, `backup_db` | Database operations |

---

## Filesystem Tools

### `read_file`

Read the contents of a file from the sandboxed filesystem.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Absolute path to the file"
    },
    "offset": {
      "type": "integer",
      "description": "Line offset to start reading from",
      "default": 0
    },
    "limit": {
      "type": "integer",
      "description": "Maximum lines to read",
      "default": 100
    }
  },
  "required": ["path"]
}
```

**Example:**
```json
{
  "name": "read_file",
  "arguments": {
    "path": "/home/user/project/main.py",
    "offset": 0,
    "limit": 50
  }
}
```

**Returns:** `TextContent` with file contents (truncated if exceeds limit).

**Security:** Path must be within configured `sandbox_paths`. Max file size: 10MB.

---

### `write_file`

Write or append content to a file within the sandbox.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Absolute path to write to"
    },
    "content": {
      "type": "string",
      "description": "Content to write"
    },
    "append": {
      "type": "boolean",
      "description": "Append instead of overwrite",
      "default": false
    }
  },
  "required": ["path", "content"]
}
```

**Security:** Path must be within `sandbox_paths`. Cannot overwrite system files.

---

### `list_dir`

List contents of a directory.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Directory path"
    }
  },
  "required": ["path"]
}
```

**Returns:** Array of `{name, type, size, modified}` entries.

---

### `search_files`

Search for files by name pattern or content regex.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "path": {
      "type": "string",
      "description": "Root directory to search"
    },
    "pattern": {
      "type": "string",
      "description": "Glob pattern (e.g., '*.py')"
    },
    "content_regex": {
      "type": "string",
      "description": "Optional regex to match file contents"
    },
    "max_results": {
      "type": "integer",
      "default": 50
    }
  },
  "required": ["path", "pattern"]
}
```

---

## System Tools

### `execute_command`

Execute a shell command from the allow-list.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "command": {
      "type": "string",
      "description": "Command to execute (must be in allowed_commands)"
    },
    "args": {
      "type": "array",
      "items": {"type": "string"},
      "description": "Command arguments"
    },
    "cwd": {
      "type": "string",
      "description": "Working directory",
      "default": "/tmp"
    },
    "timeout": {
      "type": "integer",
      "description": "Timeout in seconds",
      "default": 30
    }
  },
  "required": ["command"]
}
```

**Security:**
- Command must be in `allowed_commands` config (e.g., `ls`, `cat`, `grep`, `python`, `git`)
- Arguments are sanitized against shell injection
- `cwd` must be within `sandbox_paths`
- Timeout prevents runaway processes

**Returns:** `{stdout, stderr, returncode, duration_ms}`

---

### `get_env`

Read an environment variable.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "name": {
      "type": "string",
      "description": "Variable name"
    }
  },
  "required": ["name"]
}
```

**Security:** Secrets (keys, tokens, passwords) are redacted from output.

---

### `get_processes`

List running processes.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "filter": {
      "type": "string",
      "description": "Optional process name filter"
    }
  }
}
```

**Returns:** Array of `{pid, name, cpu_percent, memory_percent}`.

---

## Web Tools

### `fetch_url`

Fetch a URL via HTTP GET.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "url": {
      "type": "string",
      "description": "URL to fetch"
    },
    "headers": {
      "type": "object",
      "description": "Optional request headers"
    },
    "timeout": {
      "type": "integer",
      "default": 30
    }
  },
  "required": ["url"]
}
```

**Security:**
- URL must use HTTP/HTTPS scheme
- Internal/private IPs blocked by default (configurable)
- Max response size: 5MB

**Returns:** `{status, headers, body, content_type}`

---

### `search_web`

Perform a web search (requires search API key).

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "Search query"
    },
    "num_results": {
      "type": "integer",
      "default": 10
    }
  },
  "required": ["query"]
}
```

**Returns:** Array of `{title, url, snippet}` results.

---

### `parse_html`

Extract structured data from HTML.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "html": {
      "type": "string",
      "description": "Raw HTML string"
    },
    "selector": {
      "type": "string",
      "description": "CSS selector to extract"
    }
  },
  "required": ["html"]
}
```

**Returns:** Extracted text or structured elements.

---

## Code Tools

### `run_python`

Execute Python code in a sandboxed environment.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "code": {
      "type": "string",
      "description": "Python code to execute"
    },
    "timeout": {
      "type": "integer",
      "default": 10
    }
  },
  "required": ["code"]
}
```

**Security:**
- Runs in restricted subprocess with limited imports
- No network access by default
- No filesystem access outside `/tmp`
- Timeout prevents infinite loops

**Returns:** `{stdout, stderr, result, execution_time_ms}`

---

### `lint_code`

Lint code using configured linters.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "code": {
      "type": "string",
      "description": "Code to lint"
    },
    "language": {
      "type": "string",
      "enum": ["python", "javascript", "typescript"]
    }
  },
  "required": ["code", "language"]
}
```

**Returns:** Array of `{line, column, severity, message, rule}` issues.

---

### `format_code`

Format code using standard formatters.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "code": {
      "type": "string"
    },
    "language": {
      "type": "string",
      "enum": ["python", "javascript", "json", "markdown"]
    }
  },
  "required": ["code", "language"]
}
```

---

## Database Tools

### `query_sql`

Execute a read-only SQL query.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "connection_string": {
      "type": "string",
      "description": "Database connection string"
    },
    "query": {
      "type": "string",
      "description": "SELECT query only"
    }
  },
  "required": ["connection_string", "query"]
}
```

**Security:**
- Only `SELECT` statements allowed (read-only)
- Connection strings validated against allow-list
- Query timeout: 30s
- Max rows returned: 1000

**Returns:** `{columns, rows, row_count, execution_time_ms}`

---

### `migrate_db`

Apply database migrations.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "connection_string": {
      "type": "string"
    },
    "direction": {
      "type": "string",
      "enum": ["up", "down"]
    },
    "steps": {
      "type": "integer",
      "default": 1
    }
  },
  "required": ["connection_string", "direction"]
}
```

---

### `backup_db`

Create a database backup.

**Input Schema:**
```json
{
  "type": "object",
  "properties": {
    "connection_string": {
      "type": "string"
    },
    "output_path": {
      "type": "string",
      "description": "Backup file destination"
    }
  },
  "required": ["connection_string", "output_path"]
}
```

---

## Tool Registration API

```python
from universal_mcp.primitives.tools.base import BaseTool
from universal_mcp.primitives.tools.registry import tool_registry

class MyTool(BaseTool):
    name = "my_tool"
    description = "Custom tool"
    input_schema = {...}

    async def execute(self, arguments: dict):
        return [{"type": "text", "text": "Done"}]

tool_registry.register(MyTool())
```

---

*Auto-generated from source. Last updated: 2026-06-01*
