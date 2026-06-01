"""
MCP 2026-07-28 Protocol Helpers.
Handles _meta validation and version negotiation per SEP-2575.
"""
from django.conf import settings


class MCPProtocolHandler:
    SUPPORTED_VERSIONS = settings.MCP_PROTOCOL_VERSIONS_SUPPORTED

    def validate_version(self, version: str) -> bool:
        return version in self.SUPPORTED_VERSIONS

    def extract_meta(self, params: dict) -> dict:
        """Extract _meta from request params. All state travels here."""
        return params.get('_meta', {})

    def build_meta_response(self, extra: dict = None) -> dict:
        """Build _meta for server responses."""
        meta = {
            "io.modelcontextprotocol/protocolVersion": settings.MCP_PROTOCOL_VERSION,
            "io.modelcontextprotocol/serverInfo": {
                "name": settings.MCP_SERVER_NAME,
                "version": settings.MCP_SERVER_VERSION,
            },
        }
        if extra:
            meta.update(extra)
        return meta