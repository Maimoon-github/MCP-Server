"""
MCP 2026-07-28 Stateless JSON-RPC Endpoint.
Registry-driven operation dispatch. No initialize handshake. No session IDs.
Every request is complete in itself.
"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Callable, Optional
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from .services.mcp_protocol import (
    MCPProtocolService, MCPError,
    BaseAuthProvider, BearerTokenAuthProvider, APIKeyAuthProvider,
    CompositeAuthProvider
)
from .services.web_search import WebSearchService
from .models import Task


# ═══════════════════════════════════════════════════
# Registry-Driven Operation Router
# ═══════════════════════════════════════════════════

class MCPRegistry:
    """
    Registry-driven operation router.
    Maps JSON-RPC method names to handler functions without hardcoded branching.
    """

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}

    def register(self, method: str) -> Callable:
        """Decorator to register an operation handler."""
        def decorator(func: Callable) -> Callable:
            self._handlers[method] = func
            return func
        return decorator

    def dispatch(self, method: str, params: dict, meta: dict, request) -> dict:
        """
        Dispatch to registered handler.
        Supports tools/call compatibility by resolving tool name to direct method.
        """
        handler = self._handlers.get(method)

        # Compatibility: tools/call with name -> tools/{name}
        if not handler and method == 'tools/call':
            tool_name = params.get('name', '')
            direct_method = f"tools/{tool_name}"
            handler = self._handlers.get(direct_method)

        if not handler:
            raise MCPError(-32601, f"Method not found: {method}")

        return handler(params, meta, request)


# Global registry instance
registry = MCPRegistry()


# ═══════════════════════════════════════════════════
# Server Capability Handlers
# ═══════════════════════════════════════════════════

@registry.register('server/discover')
def handle_discover(params: dict, meta: dict, request) -> dict:
    """Stateless capability advertisement (SEP-2575)."""
    return {
        "protocolVersion": settings.MCP_PROTOCOL_VERSION,
        "serverInfo": {
            "name": settings.MCP_SERVER_NAME,
            "version": settings.MCP_SERVER_VERSION,
        },
        "capabilities": settings.MCP_SERVER_CAPABILITIES,
        "supportedVersions": settings.MCP_PROTOCOL_VERSIONS_SUPPORTED,
    }


# ═══════════════════════════════════════════════════
# Tools Handlers
# ═══════════════════════════════════════════════════

@registry.register('tools/list')
def handle_tools_list(params: dict, meta: dict, request) -> dict:
    """Return extensible tool registry with cache metadata."""
    tools = [
        {
            "name": "search_web",
            "description": (
                "Perform a web search across configured providers. "
                "Auto-enhances temporal queries when auto_context=True."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query string"
                    },
                    "provider": {
                        "type": "string",
                        "enum": ["duckduckgo", "serpapi", "tavily", "mock"],
                        "description": "Search provider override"
                    },
                    "num_results": {"type": "integer", "default": 5},
                    "auto_context": {
                        "type": "boolean",
                        "default": True,
                        "description": "Auto-detect temporal needs and enhance query"
                    },
                },
                "required": ["query"]
            },
            "annotations": {
                "readOnly": True,
                "destructive": False,
                "idempotent": True,
            }
        },
        {
            "name": "fetch_url",
            "description": "Fetch content from a URL via HTTP.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Target URL"},
                    "method": {"type": "string", "default": "GET"},
                },
                "required": ["url"]
            },
            "annotations": {"readOnly": True, "destructive": False}
        },
        {
            "name": "read_resource",
            "description": "Read a registered MCP resource by URI.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "uri": {"type": "string", "description": "Resource URI"}
                },
                "required": ["uri"]
            },
            "annotations": {"readOnly": True, "destructive": False}
        },
        {
            "name": "execute_task",
            "description": "Execute a long-running task asynchronously via Tasks extension.",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_type": {"type": "string", "description": "Task category"},
                    "payload": {"type": "object", "description": "Task input data"}
                },
                "required": ["task_type"]
            },
            "annotations": {"readOnly": False, "destructive": False}
        }
    ]

    return {
        "tools": tools,
        "ttlMs": settings.MCP_LIST_CACHE_TTL,
        "cacheScope": "global",
    }


@registry.register('tools/search_web')
def handle_search_web(params: dict, meta: dict, request) -> dict:
    """
    Execute web search with automatic context enhancement.
    Detects temporal keywords and auto-appends recency modifiers.
    """
    arguments = params.get('arguments', params)
    query = arguments.get('query', '')
    provider = arguments.get('provider', settings.WEB_SEARCH_BACKEND)
    num_results = arguments.get('num_results', settings.WEB_SEARCH_MAX_RESULTS)
    auto_context = arguments.get('auto_context', True)

    # Automatic context detection and enhancement
    if auto_context and _needs_latest_context(query):
        query = _enhance_query_for_latest(query)

    service = WebSearchService()
    results = service.search(query, provider=provider, num_results=num_results)

    return {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "query": query,
                "provider": provider,
                "results": results,
                "searched_at": datetime.now(timezone.utc).isoformat(),
                "auto_context_applied": auto_context,
                "request_id": getattr(request, 'mcp_request_id', ''),
            }, indent=2, ensure_ascii=False)
        }],
        "isError": False,
    }


@registry.register('tools/web_search')
def handle_web_search_legacy(params: dict, meta: dict, request) -> dict:
    """Backward compatibility alias for search_web."""
    return handle_search_web(params, meta, request)


@registry.register('tools/call')
def handle_tools_call(params: dict, meta: dict, request) -> dict:
    """
    Legacy tools/call compatibility handler.
    Routes to the correct tool based on name parameter.
    """
    tool_name = params.get('name', '')
    arguments = params.get('arguments', {})
    
    # Map legacy tool names to registry names
    name_map = {
        'web_search': 'search_web',
        'get_latest_updates': 'search_web',  # or create a dedicated handler
    }
    
    mapped_name = name_map.get(tool_name, tool_name)
    direct_method = f"tools/{mapped_name}"
    
    handler = registry._handlers.get(direct_method)
    if not handler:
        raise MCPError(-32601, f"Tool not found: {tool_name}")
    
    # Call the handler with the arguments as params
    return handler({'arguments': arguments}, meta, request)


@registry.register('tools/fetch_url')
def handle_fetch_url(params: dict, meta: dict, request) -> dict:
    """Fetch URL content via HTTP."""
    import requests
    arguments = params.get('arguments', params)
    url = arguments.get('url', '')
    method = arguments.get('method', 'GET')

    try:
        resp = requests.request(method, url, timeout=15)
        return {
            "content": [{"type": "text", "text": resp.text[:8000]}],
            "isError": False,
        }
    except Exception as e:
        return {
            "content": [{"type": "text", "text": f"Fetch error: {str(e)}"}],
            "isError": True,
        }


@registry.register('tools/read_resource')
def handle_read_resource_tool(params: dict, meta: dict, request) -> dict:
    """Tool wrapper for resources/read."""
    arguments = params.get('arguments', params)
    return handle_resources_read({"uri": arguments.get('uri', '')}, meta, request)


@registry.register('tools/execute_task')
def handle_execute_task(params: dict, meta: dict, request) -> dict:
    """Create and execute a distributed task."""
    arguments = params.get('arguments', params)
    task_type = arguments.get('task_type', 'generic')
    payload = arguments.get('payload', {})

    task = Task.objects.create(
        task_type=task_type,
        name=arguments.get('name', f'task_{task_type}'),
        status='pending',
        input_payload=payload,
    )
    # Production: enqueue to Celery/RQ worker here
    return {
        "taskId": str(task.task_id),
        "status": task.status,
        "createdAt": task.created_at.isoformat(),
    }


# ═══════════════════════════════════════════════════
# Resources Handlers
# ═══════════════════════════════════════════════════

@registry.register('resources/list')
def handle_resources_list(params: dict, meta: dict, request) -> dict:
    """Stateless resource advertisement with cache metadata."""
    resources = [
        {
            "uri": "mcp://docs/mcp-2026-spec",
            "name": "MCP 2026-07-28 Specification",
            "mimeType": "text/markdown",
            "description": "Latest stateless protocol documentation",
        },
        {
            "uri": "mcp://docs/stateless-guide",
            "name": "Stateless Architecture Guide",
            "mimeType": "text/markdown",
            "description": "Har request apne aap mein poori hai",
        },
        {
            "uri": "mcp://data/search-results",
            "name": "Search Results Cache",
            "mimeType": "application/json",
            "description": "Dynamically generated search result context",
        }
    ]
    return {
        "resources": resources,
        "ttlMs": settings.MCP_RESOURCE_CACHE_TTL,
        "cacheScope": "global",
    }


@registry.register('resources/read')
def handle_resources_read(params: dict, meta: dict, request) -> dict:
    """Read resource by URI."""
    uri = params.get('uri', '')

    content_map = {
        'mcp://docs/mcp-2026-spec': (
            "# MCP 2026-07-28 Specification\n\n"
            "## Stateless Core\n"
            "- No `initialize` handshake\n"
            "- No `Mcp-Session-Id` header\n"
            "- Protocol version, client info, capabilities in `_meta` per request\n"
            "- Load balancers route on `Mcp-Method` and `Mcp-Name` headers\n"
        ),
        'mcp://docs/stateless-guide': (
            "# Stateless Architecture Guide\n\n"
            "## Key Takeaway\n"
            "Stateless = Har request apne aap mein poori.\n"
            "Koi session, koi yaad-dasht store karne ki zaroorat nahi.\n"
            "Simple. Scalable. Reliable.\n"
        ),
        'mcp://data/search-results': json.dumps({
            "note": "Populate via tools/search_web",
            "ttlMs": settings.MCP_RESOURCE_CACHE_TTL,
        }),
    }

    content = content_map.get(uri, "Resource not found")
    mime = "text/markdown" if uri.startswith('mcp://docs') else "application/json"

    return {
        "contents": [{
            "uri": uri,
            "mimeType": mime,
            "text": content,
        }]
    }


# ═══════════════════════════════════════════════════
# Prompts Handlers
# ═══════════════════════════════════════════════════

@registry.register('prompts/list')
def handle_prompts_list(params: dict, meta: dict, request) -> dict:
    """Return available prompt templates."""
    prompts = [
        {
            "name": "summarize_results",
            "description": "Summarize search or resource results into key points.",
            "arguments": [
                {"name": "content", "description": "Content to summarize", "required": True}
            ]
        },
        {
            "name": "research_topic",
            "description": "Deep research assistant for a given topic with citations.",
            "arguments": [
                {"name": "topic", "description": "Research topic", "required": True}
            ]
        },
        {
            "name": "analyze_problem",
            "description": "Analyze a technical problem and propose ranked solutions.",
            "arguments": [
                {"name": "problem", "description": "Problem description", "required": True}
            ]
        }
    ]
    return {"prompts": prompts}


@registry.register('prompts/generate')
def handle_prompts_generate(params: dict, meta: dict, request) -> dict:
    """Generate prompt response from template."""
    arguments = params.get('arguments', {})
    prompt_name = arguments.get('name', '')
    prompt_args = arguments.get('arguments', {})

    templates = {
        "summarize_results": (
            f"Please summarize the following content into 3-5 concise key points, "
            f"preserving technical accuracy:\n\n{prompt_args.get('content', '')}"
        ),
        "research_topic": (
            f"Conduct comprehensive research on: {prompt_args.get('topic', '')}. "
            f"Include: (1) Latest developments, (2) Key players/technologies, "
            f"(3) Critical analysis, (4) Future outlook."
        ),
        "analyze_problem": (
            f"Analyze this technical problem and propose 3 ranked solutions "
            f"with trade-offs:\n\n{prompt_args.get('problem', '')}"
        ),
    }

    description = templates.get(prompt_name, "Unknown prompt template")

    return {
        "description": description,
        "messages": [{
            "role": "assistant",
            "content": {"type": "text", "text": description}
        }]
    }


# ═══════════════════════════════════════════════════
# MCP Apps Handlers
# ═══════════════════════════════════════════════════

@registry.register('apps/render')
def handle_apps_render(params: dict, meta: dict, request) -> dict:
    """Return MCP App screen definition as JSON structure."""
    arguments = params.get('arguments', {})
    screen_type = arguments.get('screen', 'dashboard')

    screens = {
        "dashboard": {
            "type": "screen",
            "title": "MCP Server Dashboard",
            "components": [
                {"type": "header", "text": settings.MCP_SERVER_NAME},
                {"type": "status", "label": "Protocol", "value": settings.MCP_PROTOCOL_VERSION},
                {"type": "status", "label": "Stateless", "value": True},
                {"type": "status", "label": "Request ID", "value": getattr(request, 'mcp_request_id', '')},
            ]
        },
        "search": {
            "type": "screen",
            "title": "Web Search",
            "components": [
                {"type": "input", "name": "query", "placeholder": "Enter search query..."},
                {"type": "select", "name": "provider", "options": ["duckduckgo", "serpapi", "tavily", "mock"]},
                {"type": "button", "action": "tools/search_web", "label": "Search"},
                {"type": "results", "binding": "search_results"}
            ]
        },
        "task_progress": {
            "type": "screen",
            "title": "Task Progress Monitor",
            "components": [
                {"type": "task_list", "endpoint": "tasks/get", "pollInterval": 3000},
                {"type": "refresh", "interval": 5000}
            ]
        }
    }

    return {
        "app": screens.get(screen_type, {"type": "screen", "title": "Unknown", "components": []}),
        "screenType": screen_type,
    }


# ═══════════════════════════════════════════════════
# Tasks Extension Handlers
# ═══════════════════════════════════════════════════

@registry.register('tasks/create')
def handle_tasks_create(params: dict, meta: dict, request) -> dict:
    """Create a long-running task in shared persistence."""
    task_type = params.get('task_type', 'generic')
    input_payload = params.get('payload', params.get('arguments', {}))
    name = params.get('name', f'task_{task_type}')

    task = Task.objects.create(
        task_type=task_type,
        name=name,
        status='pending',
        input_payload=input_payload,
    )
    return {
        "taskId": str(task.task_id),
        "taskType": task.task_type,
        "status": task.status,
        "createdAt": task.created_at.isoformat(),
    }


@registry.register('tasks/get')
def handle_tasks_get(params: dict, meta: dict, request) -> dict:
    """Poll task status. Any server instance can handle via shared DB."""
    task_id = params.get('taskId', '')
    try:
        task = Task.objects.get(task_id=task_id)
        return {
            "taskId": str(task.task_id),
            "taskType": task.task_type,
            "status": task.status,
            "inputPayload": task.input_payload,
            "outputPayload": task.output_payload,
            "errorPayload": task.error_payload,
            "createdAt": task.created_at.isoformat(),
            "updatedAt": task.updated_at.isoformat(),
            "completedAt": task.completed_at.isoformat() if task.completed_at else None,
        }
    except Task.DoesNotExist:
        raise MCPError(-32004, "Task not found", data={"taskId": task_id})


@registry.register('tasks/cancel')
def handle_tasks_cancel(params: dict, meta: dict, request) -> dict:
    """Cancel a pending or running task."""
    task_id = params.get('taskId', '')
    try:
        task = Task.objects.get(task_id=task_id)
        if task.status in ('pending', 'running'):
            task.status = 'cancelled'
            task.save(update_fields=['status', 'updated_at'])
        return {
            "taskId": str(task.task_id),
            "taskType": task.task_type,
            "status": task.status,
            "updatedAt": task.updated_at.isoformat(),
        }
    except Task.DoesNotExist:
        raise MCPError(-32004, "Task not found", data={"taskId": task_id})


# ═══════════════════════════════════════════════════
# Context Analysis Helpers
# ═══════════════════════════════════════════════════

def _needs_latest_context(query: str) -> bool:
    """Analyze query to detect temporal information needs."""
    temporal_keywords = [
        'latest', 'recent', 'update', 'news', '2026', '2025',
        'today', 'now', 'current', 'new', 'just released',
        'breaking', 'this week', 'this month'
    ]
    return any(kw in query.lower() for kw in temporal_keywords)


def _enhance_query_for_latest(query: str) -> str:
    """Enhance query to retrieve latest information."""
    if '2026' not in query and '2025' not in query:
        return f"{query} latest 2026"
    return query


# ═══════════════════════════════════════════════════
# JSON-RPC Endpoint View
# ═══════════════════════════════════════════════════

@method_decorator(csrf_exempt, name='dispatch')
class MCPStatelessEndpoint(View):
    """
    Single POST endpoint handling all JSON-RPC methods.
    Har request apne aap mein poori hai:
    - Protocol version in header or _meta
    - Client info in _meta
    - Auth in Authorization header
    - No Mcp-Session-Id
    """

    http_method_names = ['post', 'get', 'options']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.protocol = MCPProtocolService()
        # Composite auth: Bearer OR API Key
        self.auth_provider: BaseAuthProvider = CompositeAuthProvider([
            BearerTokenAuthProvider(settings.MCP_API_KEY),
            APIKeyAuthProvider(settings.MCP_API_KEY),
        ])

    def post(self, request, *args, **kwargs) -> JsonResponse:
        """Handle JSON-RPC POST requests."""
        # DEBUG bypass: skip auth entirely in development
        debug_bypass = settings.DEBUG

        # Parse JSON-RPC body
        try:
            body = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return self._error_response(-32700, "Parse error", None)

        rpc_id = body.get('id')
        rpc_method = body.get('method', '')
        params = body.get('params', {})

        # Protocol Version Validation (SEP-2575)
        meta = self.protocol.extract_meta(params)
        header_version = getattr(request, 'mcp_protocol_version', '')
        meta_version = meta.get('io.modelcontextprotocol/protocolVersion', '')
        protocol_version = header_version or meta_version

        if protocol_version and not self.protocol.validate_version(protocol_version):
            return self._error_response(
                -32001,
                "UnsupportedProtocolVersionError",
                rpc_id,
                data={"supported": settings.MCP_PROTOCOL_VERSIONS_SUPPORTED}
            )

        # Stateless Authentication
        if not debug_bypass and not self.auth_provider.authenticate(request):
            return self._error_response(-32002, "Unauthorized", rpc_id)

        # Registry-driven dispatch
        try:
            result = registry.dispatch(rpc_method, params, meta, request)
            # Inject response _meta with tracking IDs
            result['_meta'] = self.protocol.build_meta_response({
                "io.modelcontextprotocol/requestId": getattr(request, 'mcp_request_id', ''),
                "io.modelcontextprotocol/correlationId": getattr(request, 'mcp_correlation_id', ''),
            })
            return JsonResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result
            })
        except MCPError as e:
            return self._error_response(e.code, e.message, rpc_id, data=e.data)
        except Exception as e:
            return self._error_response(-32603, f"Internal error: {str(e)}", rpc_id)

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """Health check / server discovery."""
        return JsonResponse({
            "jsonrpc": "2.0",
            "result": {
                "status": "ok",
                "protocolVersion": settings.MCP_PROTOCOL_VERSION,
                "server": settings.MCP_SERVER_NAME,
                "stateless": True,
                "requestId": getattr(request, 'mcp_request_id', ''),
                "correlationId": getattr(request, 'mcp_correlation_id', ''),
            }
        })

    def _error_response(
        self,
        code: int,
        message: str,
        rpc_id: Any,
        data: Optional[Dict[str, Any]] = None
    ) -> JsonResponse:
        """Construct MCP-compliant error response."""
        error = {"code": code, "message": message}
        if data:
            error["data"] = data
        return JsonResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": error
        }, status=400 if code == -32700 else 200)