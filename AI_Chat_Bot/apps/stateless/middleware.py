"""
MCP 2026 Stateless Protocol Middleware.
Enforces stateless architecture, validates protocol headers,
and generates non-persistent request tracking IDs.
"""
import uuid
from django.http import JsonResponse
from django.conf import settings


class MCPStatelessMiddleware:
    """
    Stateless enforcement layer.
    Rejects sessions, cookies, and Mcp-Session-Id.
    Generates correlation/trace IDs without persistence.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only process MCP endpoints
        if not request.path.startswith('/mcp'):
            return self.get_response(request)

        # ─── STATELESS ENFORCEMENT ───
        # Explicitly nullify session to prevent any session loading
        request.session = None

        # Reject Mcp-Session-Id header (MCP 2026 stateless violation)
        if request.headers.get('Mcp-Session-Id'):
            return JsonResponse({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32003,
                    "message": (
                        "Mcp-Session-Id is not supported in MCP 2026 stateless mode. "
                        "All state must travel in the request body."
                    )
                }
            }, status=400)

        # Reject cookie-based state
        if request.COOKIES:
            return JsonResponse({
                "jsonrpc": "2.0",
                "error": {
                    "code": -32003,
                    "message": (
                        "Cookie-based state is not supported. "
                        "MCP 2026 requires fully stateless requests."
                    )
                }
            }, status=400)

        # ─── REQUEST TRACKING (Non-persistent) ───
        request.mcp_request_id = str(uuid.uuid4())
        request.mcp_correlation_id = (
            request.headers.get('X-Correlation-Id')
            or request.headers.get('x-correlation-id')
            or str(uuid.uuid4())
        )
        request.mcp_trace_id = (
            request.headers.get('traceparent')
            or str(uuid.uuid4())
        )

        # ─── PROTOCOL HEADER EXTRACTION ───
        request.mcp_protocol_version = request.headers.get('Mcp-Protocol-Version', '')
        request.mcp_method = request.headers.get('Mcp-Method', '')
        request.mcp_name = request.headers.get('Mcp-Name', '')

        # W3C Trace Context propagation
        request.traceparent = request.headers.get('traceparent', '')
        request.tracestate = request.headers.get('tracestate', '')

        # ─── RESPONSE PROCESSING ───
        response = self.get_response(request)

        # Inject MCP protocol version and tracking IDs into response
        response['Mcp-Protocol-Version'] = settings.MCP_PROTOCOL_VERSION
        response['X-Request-Id'] = request.mcp_request_id
        response['X-Correlation-Id'] = request.mcp_correlation_id

        return response