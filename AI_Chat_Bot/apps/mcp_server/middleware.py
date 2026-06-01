"""
MCP 2026 Stateless Protocol Middleware.
- Validates routing headers (Mcp-Method, Mcp-Name)
- Injects request context WITHOUT sessions
- Propagates trace context
"""
from django.conf import settings


class MCPProtocolMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Only process MCP endpoints
        if not request.path.startswith('/mcp'):
            return self.get_response(request)

        # STATELESS: Explicitly ensure no session is loaded or created
        request.session = None

        # Extract MCP 2026 routing headers (SEP-2243)
        request.mcp_method = request.headers.get('Mcp-Method', '')
        request.mcp_name = request.headers.get('Mcp-Name', '')
        request.mcp_protocol_version = request.headers.get('Mcp-Protocol-Version', '')

        # W3C Trace Context propagation (SEP-414)
        request.traceparent = request.headers.get('traceparent', '')
        request.tracestate = request.headers.get('tracestate', '')

        response = self.get_response(request)

        # Add MCP protocol version to response headers
        response['Mcp-Protocol-Version'] = settings.MCP_PROTOCOL_VERSION
        return response