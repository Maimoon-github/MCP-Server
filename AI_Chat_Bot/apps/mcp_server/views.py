"""
MCP 2026-07-28 Stateless JSON-RPC Endpoint.
No initialize handshake. No session IDs. Every request is complete in itself.
Automatically performs web searches for latest updates based on context.
"""
import json
import uuid
from datetime import datetime, timezone
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from .services.mcp_protocol import MCPProtocolHandler
from .services.web_search import WebSearchService


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
        self.protocol = MCPProtocolHandler()
        self.search_service = WebSearchService()

    def post(self, request, *args, **kwargs):
        # Parse JSON-RPC body
        try:
            body = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return self._error_response(-32700, "Parse error", None)

        rpc_id = body.get('id')
        rpc_method = body.get('method', '')
        params = body.get('params', {})

        # ─── Protocol Version Validation (SEP-2575) ───
        meta = self.protocol.extract_meta(params)
        header_version = request.mcp_protocol_version
        meta_version = meta.get('io.modelcontextprotocol/protocolVersion', '')
        protocol_version = header_version or meta_version

        if protocol_version and not self.protocol.validate_version(protocol_version):
            return self._error_response(
                -32001,
                "UnsupportedProtocolVersionError",
                rpc_id,
                data={"supported": settings.MCP_PROTOCOL_VERSIONS_SUPPORTED}
            )

        # ─── Stateless Authentication ───
        if not self._authenticate(request):
            return self._error_response(-32002, "Unauthorized", rpc_id)

        # ─── JSON-RPC Method Dispatch ───
        handlers = {
            'server/discover': self._handle_discover,
            'tools/list': self._handle_tools_list,
            'tools/call': self._handle_tools_call,
            'resources/list': self._handle_resources_list,
            'resources/read': self._handle_resources_read,
            'tasks/create': self._handle_tasks_create,
            'tasks/get': self._handle_tasks_get,
            'tasks/cancel': self._handle_tasks_cancel,
        }

        handler = handlers.get(rpc_method)
        if not handler:
            return self._error_response(-32601, "Method not found", rpc_id)

        try:
            result = handler(params, meta, request)
            # Inject response _meta
            result['_meta'] = self.protocol.build_meta_response()
            return JsonResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result
            })
        except Exception as e:
            return self._error_response(-32603, str(e), rpc_id)

    def get(self, request, *args, **kwargs):
        """Health check / SSE stream placeholder."""
        return JsonResponse({
            "jsonrpc": "2.0",
            "result": {
                "status": "ok",
                "protocolVersion": settings.MCP_PROTOCOL_VERSION,
                "server": settings.MCP_SERVER_NAME,
                "stateless": True,
            }
        })

    def _authenticate(self, request) -> bool:
        """Stateless auth: Bearer token or X-Api-Key. No session lookup."""
        auth_header = request.headers.get('Authorization', '')
        api_key = request.headers.get('X-Api-Key', '')
        expected = settings.MCP_API_KEY

        if auth_header.startswith('Bearer '):
            return auth_header[7:] == expected
        return api_key == expected

    def _error_response(self, code, message, rpc_id, data=None):
        error = {"code": code, "message": message}
        if data:
            error["data"] = data
        return JsonResponse({
            "jsonrpc": "2.0",
            "id": rpc_id,
            "error": error
        }, status=400 if code == -32700 else 200)

    # ═══════════════════════════════════════════════════
    # MCP Method Handlers
    # ═══════════════════════════════════════════════════

    def _handle_discover(self, params, meta, request):
        """server/discover: Stateless capability advertisement (SEP-2575)."""
        return {
            "protocolVersion": settings.MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": settings.MCP_SERVER_NAME,
                "version": settings.MCP_SERVER_VERSION,
            },
            "capabilities": settings.MCP_SERVER_CAPABILITIES,
            "supportedVersions": settings.MCP_PROTOCOL_VERSIONS_SUPPORTED,
        }

    def _handle_tools_list(self, params, meta, request):
        """
        tools/list: Returns tools with caching metadata (ttlMs, cacheScope).
        Any server instance can serve this — no session state.
        """
        tools = [
            {
                "name": "web_search",
                "description": (
                    "Perform a web search to retrieve latest information. "
                    "Automatically enhances queries with temporal context when auto_context=True."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query string"},
                        "num_results": {"type": "integer", "default": 5},
                        "auto_context": {
                            "type": "boolean",
                            "default": True,
                            "description": "Automatically detect need for latest updates and enhance query"
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
                "name": "get_latest_updates",
                "description": (
                    "Automatically retrieve latest updates for a topic using web search. "
                    "Based on request context, this tool infers the need for current data."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "Topic to retrieve latest updates for"},
                        "source": {"type": "string", "enum": ["news", "docs", "all"], "default": "all"},
                    },
                    "required": ["topic"]
                },
                "annotations": {
                    "readOnly": True,
                    "destructive": False,
                }
            }
        ]

        return {
            "tools": tools,
            "ttlMs": settings.MCP_LIST_CACHE_TTL,
            "cacheScope": "global",
        }

    def _handle_tools_call(self, params, meta, request):
        """
        tools/call: Execute tool with automatic web search based on request context.
        If the query implies temporal needs ('latest', '2026', 'update'), auto-enhance.
        """
        tool_name = params.get('name')
        arguments = params.get('arguments', {})
        client_info = meta.get('io.modelcontextprotocol/clientInfo', {})

        if tool_name == 'web_search':
            query = arguments.get('query', '')
            num_results = arguments.get('num_results', settings.WEB_SEARCH_MAX_RESULTS)
            auto_context = arguments.get('auto_context', True)

            # ─── Automatic Context Detection ───
            # Based on request context: if query asks for latest/updates, enhance it
            if auto_context and self._needs_latest_context(query):
                query = self._enhance_query_for_latest(query)

            results = self.search_service.search(query, num_results)

            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "query": query,
                            "client": client_info.get('name', 'unknown'),
                            "results": results,
                            "searched_at": datetime.now(timezone.utc).isoformat(),
                            "auto_context_applied": auto_context,
                        }, indent=2, ensure_ascii=False)
                    }
                ],
                "isError": False,
            }

        elif tool_name == 'get_latest_updates':
            topic = arguments.get('topic', '')
            source = arguments.get('source', 'all')

            # Automatically construct a search query for latest updates
            enhanced_query = f"latest updates {topic} 2026"
            if source == 'news':
                enhanced_query += " news"
            elif source == 'docs':
                enhanced_query += " documentation"

            results = self.search_service.search(enhanced_query, settings.WEB_SEARCH_MAX_RESULTS)

            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "topic": topic,
                            "source_filter": source,
                            "query_used": enhanced_query,
                            "latest_results": results,
                            "retrieved_at": datetime.now(timezone.utc).isoformat(),
                            "note": "Automatically retrieved based on request context for latest updates",
                        }, indent=2, ensure_ascii=False)
                    }
                ],
                "isError": False,
            }

        return {
            "content": [{"type": "text", "text": f"Unknown tool: {tool_name}"}],
            "isError": True,
        }

    def _handle_resources_list(self, params, meta, request):
        """resources/list: Stateless resource advertisement with cache metadata."""
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
            }
        ]
        return {
            "resources": resources,
            "ttlMs": settings.MCP_RESOURCE_CACHE_TTL,
            "cacheScope": "global",
        }

    def _handle_resources_read(self, params, meta, request):
        uri = params.get('uri', '')
        if uri == 'mcp://docs/mcp-2026-spec':
            content = (
                "# MCP 2026-07-28 Specification\n\n"
                "## Stateless Core\n"
                "- No `initialize` handshake\n"
                "- No `Mcp-Session-Id` header\n"
                "- Protocol version, client info, capabilities in `_meta` per request\n"
                "- Load balancers route on `Mcp-Method` and `Mcp-Name` headers\n"
            )
        elif uri == 'mcp://docs/stateless-guide':
            content = (
                "# Stateless Architecture Guide\n\n"
                "## Key Takeaway\n"
                "Stateless = Har request apne aap mein poori.\n"
                "Koi session, koi yaad-dasht store karne ki zaroorat nahi.\n"
                "Simple. Scalable. Reliable.\n"
            )
        else:
            content = "Resource not found"

        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "text/markdown",
                    "text": content,
                }
            ]
        }

    def _handle_tasks_create(self, params, meta, request):
        """Tasks extension: Create long-running task. Stored in shared DB."""
        from .models import Task
        task = Task.objects.create(
            name=params.get('name', 'auto_search_task'),
            status='pending',
            result={
                "tool": params.get('arguments', {}).get('name'),
                "arguments": params.get('arguments', {})
            }
        )
        return {
            "taskId": str(task.task_id),
            "status": task.status,
            "createdAt": task.created_at.isoformat(),
        }

    def _handle_tasks_get(self, params, meta, request):
        """Tasks extension: Poll task status. Any server can handle."""
        from .models import Task
        task_id = params.get('taskId', '')
        try:
            task = Task.objects.get(task_id=task_id)
            return {
                "taskId": str(task.task_id),
                "status": task.status,
                "result": task.result,
                "createdAt": task.created_at.isoformat(),
                "updatedAt": task.updated_at.isoformat(),
            }
        except Task.DoesNotExist:
            return {"taskId": task_id, "status": "unknown", "error": "Task not found"}

    def _handle_tasks_cancel(self, params, meta, request):
        from .models import Task
        task_id = params.get('taskId', '')
        try:
            task = Task.objects.get(task_id=task_id)
            task.status = 'cancelled'
            task.save()
            return {"taskId": str(task.task_id), "status": task.status}
        except Task.DoesNotExist:
            return {"taskId": task_id, "status": "unknown", "error": "Task not found"}

    # ═══════════════════════════════════════════════════
    # Context Analysis Helpers
    # ═══════════════════════════════════════════════════

    def _needs_latest_context(self, query: str) -> bool:
        """Analyze query to detect temporal information needs."""
        temporal_keywords = [
            'latest', 'recent', 'update', 'news', '2026', '2025',
            'today', 'now', 'current', 'new', 'just released',
            'breaking', 'this week', 'this month'
        ]
        query_lower = query.lower()
        return any(kw in query_lower for kw in temporal_keywords)

    def _enhance_query_for_latest(self, query: str) -> str:
        """Enhance query to retrieve latest information."""
        if '2026' not in query and '2025' not in query:
            return f"{query} latest 2026"
        return query