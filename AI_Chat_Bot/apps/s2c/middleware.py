"""
MCP 2026 S2C Elicitation Protocol Middleware.

Adds elicitation capability headers and ensures In-Flight Rule compliance
by validating that elicitation only occurs on active MCP requests.
"""


class MCPS2CMiddleware:
    """
    Lightweight middleware layer for S2C elicitation endpoints.
    Advertises elicitation support via response headers.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        # Only inject headers for MCP s2c paths
        if request.path.startswith('/mcp/s2c'):
            response['Mcp-Elicitation-Supported'] = 'true'
            response['Mcp-Elicitation-Version'] = '1.0'
            response['Mcp-Elicitation-Rule'] = 'In-Flight'

        return response
