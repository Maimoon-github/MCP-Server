# S2C — Stateless Server-to-Client Elicitation App

## Overview

This Django app (`apps.s2c`) implements the **MCP 2026 Stateless Server-to-Client Elicitation** protocol. It enables a stateless server to pause mid-operation, ask the client a question, and resume processing on any server instance once the client replies — **without persistent connections** like SSE.

### Key Principles (from `3.png`)

| Rule | Description |
|------|-------------|
| **In-Flight Rule** | Server may prompt the client **only while already processing** an active request. No unsolicited prompts. |
| **Special Response Rule** | When input is required, server returns a payload containing `question` + `requestState`. |
| **Stateless Resume** | `requestState` is a signed, self-contained token. Any server instance can resume. |

### Automatic Web Search

When a query contains temporal keywords (`latest`, `recent`, `2026`, `today`, etc.), the app **automatically performs web searches** to retrieve the most current information. If the query is ambiguous, it uses **elicitation** to ask for clarification before searching.

---

## File Structure

```
apps/s2c/
├── __init__.py
├── apps.py
├── middleware.py
├── models.py
├── urls.py
├── views.py
├── services/
│   ├── __init__.py
│   └── elicitation_service.py
└── migrations/
    ├── __init__.py
    └── 0001_initial.py
```

---

## Installation & Integration

### 1. Add to `INSTALLED_APPS`

In `AI_Chat_Bot/config/settings/settings.py` (or your settings module):

```python
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'mcp_server',
    'apps.stateless',
    'apps.s2c',  # <-- ADD THIS
]
```

### 2. Add URL Route

In `AI_Chat_Bot/config/urls.py` (or root `urls.py`):

```python
from django.urls import path, include

urlpatterns = [
    path('mcp/', include('apps.stateless.urls')),
    path('mcp/s2c/', include('apps.s2c.urls')),  # <-- ADD THIS
]
```

### 3. Add Middleware (Optional)

In `MIDDLEWARE` settings:

```python
MIDDLEWARE = [
    'mcp_server.middleware.MCPProtocolMiddleware',
    'apps.s2c.middleware.MCPS2CMiddleware',  # <-- ADD THIS
    'django.middleware.common.CommonMiddleware',
]
```

### 4. Run Migrations

```bash
cd AI_Chat_Bot
python manage.py migrate s2c
```

---

## API Reference

### Endpoint

```
POST /mcp/s2c/
GET  /mcp/s2c/
```

### Methods

#### `server/discover`
Returns server capabilities including `elicitation: true`.

#### `tools/list`
Lists elicitation-aware tools:
- `search_web` — Web search with automatic latest-update detection.
- `get_latest_updates` — Always elicits for specificity, then auto-searches.
- `confirm_and_execute` — Generic confirmation flow (delete files, etc.).

#### `tools/search_web`
**Fresh call** (ambiguous temporal query):
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/search_web",
  "params": {
    "arguments": {"query": "latest updates"}
  }
}
```
**Special Response**:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "elicitationRequired": true,
    "question": "Your query 'latest updates' requests latest updates. What specific aspect would you like updates on?",
    "requestState": "eyJhbGciOiJIUzI1NiIs...",
    "hint": "Reply with a short clarification text."
  }
}
```

**Retry with Context**:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/search_web",
  "params": {
    "arguments": {"query": "latest updates"},
    "requestState": "eyJhbGciOiJIUzI1NiIs...",
    "elicitationAnswer": {"text": "Python programming language"}
  }
}
```

**Final Response**:
```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "result": {
    "content": [{"type": "text", "text": "{\"query\": "...\", "results\": [...]}"}],
    "isError": false
  }
}
```

#### `tools/get_latest_updates`
Always performs **two-step elicitation**:
1. Asks for topic (if missing).
2. Asks for specificity (features, security, news, or all).
3. Auto-searches web with enhanced query.

#### `tools/confirm_and_execute`
Demonstrates classic confirmation flow:
1. Client sends action + target.
2. Server asks: "Confirm execution: delete 3 files?"
3. Client retries with `confirmed: true/false`.
4. Server executes or cancels.

#### `elicitation/list_pending`
Admin/monitoring endpoint. Lists pending elicitation records across all server instances (uses shared DB).

#### `elicitation/get_status`
Retrieve audit status for a specific elicitation by `tokenHash`.

---

## Architecture

### ElicitationService

- **`encode_state(...)`** → Signs and compresses operation progress into a `requestState` token.
- **`decode_state(token)`** → Verifies signature and expiry; returns payload.
- **`build_special_response(...)`** → Constructs the Special Response JSON.
- **`extract_answer(params)` / `extract_request_state(params)`** → Parses retry requests.

### ElicitationRegistry

- Wraps handlers with elicitation lifecycle management.
- Detects retry-with-answer and routes to `_resume_elicitation(...)`.
- Catches `ElicitationRequired` exceptions and converts them to Special Responses.

### ElicitationRecord (Model)

- **Not required for resumption** — state is in the token.
- Used for **audit, monitoring, and horizontal scaling visibility**.
- Any server instance can query `s2c_elicitation_records` table to see pending questions.

---

## Security & Stateless Compliance

- **No sessions** — `request.session = None` is enforced by base middleware.
- **No cookies** — Cookie-based state is rejected.
- **No `Mcp-Session-Id`** — Rejected with error `-32003`.
- **Signed tokens** — `requestState` uses Django `TimestampSigner` with `SECRET_KEY`.
- **Expiry** — Tokens expire after 1 hour (configurable via `TOKEN_MAX_AGE`).
- **In-Flight only** — Elicitation only triggers inside active JSON-RPC method handlers.

---

## Example: Full Delete-Files Flow

```
Step 1: Client → Server
  {"method": "tools/confirm_and_execute", "params": {"action": "delete", "target": "3 files"}}

Step 2: Server → Client (Special Response)
  {
    "result": {
      "elicitationRequired": true,
      "question": "Confirm execution: delete 3 files?",
      "requestState": "<signed-token>"
    }
  }

Step 3: Client → Server (Retry + Answer)
  {
    "method": "tools/confirm_and_execute",
    "params": {
      "action": "delete",
      "target": "3 files",
      "requestState": "<signed-token>",
      "elicitationAnswer": {"confirmed": true}
    }
  }

Step 4: Server → Client (Final Response)
  {
    "result": {
      "content": [{"text": "Executed: delete 3 files"}],
      "executed": true
    }
  }
```

**Any server instance** can handle Step 3 and Step 4 because the full state is in `requestState`.

---

## Environment Variables

The app inherits all settings from `apps.stateless`:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Used to sign `requestState` tokens |
| `MCP_PROTOCOL_VERSION` | Advertised protocol version |
| `MCP_API_KEY` | Bearer / API-Key auth validation |
| `WEB_SEARCH_BACKEND` | Default search provider (`mock`, `duckduckgo`, `serpapi`, `tavily`) |
| `WEB_SEARCH_MAX_RESULTS` | Default result count |
| `DEBUG` | When `True`, auth bypass is enabled |

---

## Testing

```bash
# Health check
curl http://localhost:8000/mcp/s2c/

# Discover
curl -X POST http://localhost:8000/mcp/s2c/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{}}'

# Search with elicitation
curl -X POST http://localhost:8000/mcp/s2c/ \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/search_web","params":{"arguments":{"query":"latest news"}}}'
```
