# Architecture Overview

> Mental model and design decisions for the Universal MCP Server.

---

## Mental Model

```
┌─────────────────────────────────────────────────────────────────┐
│                         HOST (AI Application)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Claude       │  │ Cursor       │  │ VS Code / Custom     │  │
│  │ Desktop      │  │ IDE          │  │ AI Host              │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         │                 │                     │               │
│  ┌──────▼─────────────────▼─────────────────────▼───────────┐  │
│  │              CLIENT (Built into Host)                    │  │
│  │  • JSON-RPC 2.0 protocol handler                        │  │
│  │  • Request/response lifecycle management                │  │
│  │  • You DO NOT build this — it's part of the host      │  │
│  └──────┬───────────────────────────────────────────────────┘  │
│         │                                                      │
│         │  STDIO  │  HTTP/SSE  │  WebSocket                   │
│         │                                                      │
│  ┌──────▼───────────────────────────────────────────────────┐  │
│  │              SERVER (Universal MCP — YOU BUILD THIS)      │  │
│  │                                                           │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │  │
│  │  │   TOOLS      │  │  RESOURCES   │  │   PROMPTS    │  │  │
│  │  │  (Hands)     │  │ (Knowledge)  │  │ (Templates)  │  │  │
│  │  │              │  │              │  │              │  │  │
│  │  │ • read_file  │  │ • file://    │  │ • code_review│  │  │
│  │  │ • execute_cmd│  │ • env://     │  │ • debug      │  │  │
│  │  │ • query_db   │  │ • system://  │  │ • project    │  │  │
│  │  │ • fetch_url  │  │ • log://     │  │ • docs       │  │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │              TRANSPORT LAYER                        │  │  │
│  │  │  • STDIO: stdin/stdout JSON-RPC (local desktop)      │  │  │
│  │  │  • HTTP/SSE: REST + Server-Sent Events (network)     │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  │                                                           │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │              SECURITY LAYER                         │  │  │
│  │  │  • Auth (OAuth2, API Key, Bearer)                   │  │  │
│  │  │  • Sandbox (path restriction, cmd allow-list)       │  │  │
│  │  │  • Rate Limiting (token bucket per client)          │  │  │
│  │  │  • Audit Logging (immutable request/response logs)  │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Design Principles

### 1. Separation of Concerns

| Layer | Responsibility | Files |
|-------|---------------|-------|
| **Transport** | Protocol encoding, connection lifecycle | `transports/*.py` |
| **Primitives** | Business logic for Tools, Resources, Prompts | `primitives/*/*.py` |
| **Security** | Auth, sandboxing, rate limits, audit | `security/*.py` |
| **Config** | Environment, secrets, feature flags | `config.py` |
| **Utils** | Logging, validation, helpers | `utils/*.py` |
| **Connectors** | External service adapters | `connectors/*.py` |

### 2. Plugin Architecture

Every primitive (Tool, Resource, Prompt) follows the **Registry Pattern**:

```python
# tools/registry.py
class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise DuplicateToolError(tool.name)
        self._tools[tool.name] = tool

    def get(self, name: str) -> BaseTool:
        if name not in self._tools:
            raise ToolNotFoundError(name)
        return self._tools[name]

    def list(self) -> list[ToolInfo]:
        return [t.info for t in self._tools.values()]
```

This allows:
- **Built-in primitives**: Ship with the server (`primitives/*/builtin/`)
- **Custom primitives**: Load from external packages at runtime
- **Hot-swapping**: Disable/enable primitives via config without code changes

### 3. Transport Abstraction

```python
# transports/base.py
from abc import ABC, abstractmethod

class Transport(ABC):
    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def stop(self) -> None: ...

    @abstractmethod
    async def send(self, message: JSONRPCMessage) -> None: ...

    @abstractmethod
    async def receive(self) -> JSONRPCMessage: ...
```

**STDIO Transport** (`transports/stdio.py`):
- Reads JSON-RPC messages from `sys.stdin`
- Writes responses to `sys.stdout`
- **Critical**: All logging MUST go to files — stdout is reserved for protocol messages
- Used by: Claude Desktop, Cursor, local AI hosts

**HTTP/SSE Transport** (`transports/http_sse.py`):
- Exposes REST endpoints for tool/resource/prompt discovery
- Uses Server-Sent Events for streaming responses
- Supports Bearer token, API key, and OAuth2 authentication
- Used by: Remote hosts, web-based AI applications, microservices

### 4. Security by Default

Every tool execution flows through the **Security Pipeline**:

```
Incoming Request
      │
      ▼
┌─────────────┐
│  Auth Check │  ← Reject if invalid/missing credentials
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Rate Limiter│  ← Reject if quota exceeded (429)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Sandbox   │  ← Reject if path/cmd outside allow-list
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Execute   │  ← Run the tool/resource/prompt
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Audit     │  ← Log request + response to immutable log
└─────────────┘
```

### 5. Async-First Design

All primitives use `async/await` to handle concurrent requests efficiently:

```python
# primitives/tools/base.py
class BaseTool(ABC):
    name: str
    description: str
    input_schema: dict  # JSON Schema

    @abstractmethod
    async def execute(self, arguments: dict) -> list[TextContent | ImageContent]:
        """Execute the tool with validated arguments."""
        ...
```

---

## Data Flow

### Tool Invocation Flow

```
Host sends JSON-RPC:
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "read_file",
    "arguments": {"path": "/etc/passwd"}
  }
}

        │
        ▼
┌──────────────────┐
│ Transport Layer  │  Parse raw message
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Server Router    │  Route to tools/call handler
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ ToolRegistry     │  Look up "read_file"
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Security Pipeline│  Auth → Rate Limit → Sandbox check
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ read_file Tool   │  Execute (blocked by sandbox for /etc/passwd)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Audit Logger     │  Log: {client, tool, args, result, timestamp}
└──────┬───────────┘
       │
       ▼
Transport sends JSON-RPC response:
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [{"type": "text", "text": "Error: Path not in sandbox"}],
    "isError": true
  }
}
```

### Resource Access Flow

```
Host sends: resources/read
URI: file:///home/user/project/main.py

        │
        ▼
┌──────────────────┐
│ URI Router       │  Parse scheme (file://)
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Resource Handler │  file_content.py handler
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Sandbox Check    │  Is /home/user/project within allowed paths?
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│ Read File        │  Return contents as TextResourceContents
└──────────────────┘
```

---

## Configuration Hierarchy

Settings are loaded in this priority (highest wins):

```
1. Environment variables (MCP_* prefix)
2. .env file (loaded by python-dotenv)
3. Config file (JSON/YAML path via --config)
4. Default values in Pydantic model
```

```python
# config.py
from pydantic_settings import BaseSettings

class MCPSettings(BaseSettings):
    transport: str = "stdio"           # stdio | http
    http_port: int = 3000
    http_host: str = "0.0.0.0"
    log_level: str = "INFO"
    log_path: str = "/var/log/universal_mcp/"
    sandbox_paths: list[str] = ["/tmp", "/home"]
    allowed_commands: list[str] = ["ls", "cat", "grep", "python"]
    rate_limit_rpm: int = 60         # Requests per minute
    auth_mode: str = "none"          # none | api_key | oauth2 | bearer
    api_key: str | None = None

    class Config:
        env_prefix = "MCP_"
```

---

## Error Handling Strategy

All errors are mapped to MCP-compatible JSON-RPC error codes:

| Error | Code | Description |
|-------|------|-------------|
| `ToolNotFoundError` | -32602 | Invalid params — tool does not exist |
| `ResourceNotFoundError` | -32602 | Invalid params — URI not registered |
| `PromptNotFoundError` | -32602 | Invalid params — prompt not registered |
| `ValidationError` | -32602 | Invalid params — schema mismatch |
| `AuthError` | -32001 | Unauthorized — invalid/missing credentials |
| `RateLimitError` | -32002 | Rate limit exceeded |
| `SandboxError` | -32003 | Forbidden — sandbox violation |
| `ExecutionError` | -32004 | Tool execution failed |
| `InternalError` | -32603 | Internal server error |

---

## Extension Points

### Adding a Custom Tool

```python
# my_custom_tool.py
from universal_mcp.primitives.tools.base import BaseTool
from universal_mcp.primitives.tools.registry import tool_registry

class MyTool(BaseTool):
    name = "my_tool"
    description = "Does something custom"
    input_schema = {
        "type": "object",
        "properties": {
            "input": {"type": "string"}
        },
        "required": ["input"]
    }

    async def execute(self, arguments: dict):
        result = f"Processed: {arguments['input']}"
        return [{"type": "text", "text": result}]

# Register at startup
tool_registry.register(MyTool())
```

### Adding a Custom Resource

```python
# my_custom_resource.py
from universal_mcp.primitives.resources.base import BaseResource
from universal_mcp.primitives.resources.registry import resource_registry

class MyResource(BaseResource):
    uri = "custom://data"
    name = "My Custom Data"
    description = "Returns custom data"
    mime_type = "application/json"

    async def read(self):
        return b'{'"key": "value"}'

resource_registry.register(MyResource())
```

### Adding a Custom Prompt

```python
# my_custom_prompt.py
from universal_mcp.primitives.prompts.base import BasePrompt
from universal_mcp.primitives.prompts.registry import prompt_registry

class MyPrompt(BasePrompt):
    name = "my_prompt"
    description = "A reusable template"
    arguments = [
        {"name": "language", "description": "Programming language", "required": True}
    ]

    def render(self, arguments: dict) -> str:
        return f"Review this {arguments['language']} code for security issues..."

prompt_registry.register(MyPrompt())
```

---

## Deployment Patterns

### Local Development (STDIO)
```
Host (Claude Desktop)
    │
    └── subprocess: python -m universal_mcp --transport stdio
```

### Remote Service (HTTP/SSE)
```
Host (Web AI)
    │
    └── HTTP GET /sse → Server (Docker container, K8s pod, VM)
```

### Multi-Host Gateway
```
                    ┌─────────────────┐
Claude Desktop ─────┤                 │
                    │  MCP Gateway    │──────┐
Cursor ─────────────┤  (HTTP/SSE)     │      │
                    │                 │      ▼
VS Code ────────────┤                 │   ┌─────────────┐
                    └─────────────────┘   │  Universal  │
                                          │  MCP Server │
                                          │  (Docker)   │
                                          └─────────────┘
```

---

## Performance Considerations

| Concern | Strategy |
|---------|----------|
| **Concurrency** | Asyncio event loop + thread pool for blocking I/O |
| **Tool caching** | LRU cache for expensive operations (DB queries, API calls) |
| **Resource streaming** | SSE for large files; pagination for lists |
| **Memory limits** | Configurable max file size (default 10MB) |
| **Timeout** | Per-tool timeout (default 30s, configurable) |

---

*Last updated: 2026-06-01*
