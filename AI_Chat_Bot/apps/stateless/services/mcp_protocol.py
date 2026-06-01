"""
MCP 2026 Protocol Service.
Handles version negotiation, meta validation, response construction,
structured error handling, and authorization abstractions.
"""
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from django.conf import settings


class MCPError(Exception):
    """Structured MCP error with code, message, and optional data."""

    def __init__(
        self,
        code: int,
        message: str,
        data: Optional[Dict[str, Any]] = None
    ):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class MCPProtocolService:
    """
    MCP 2026 protocol validation and response construction.
    Stateless: all state travels in _meta per request.
    """

    SUPPORTED_VERSIONS = settings.MCP_PROTOCOL_VERSIONS_SUPPORTED

    def validate_version(self, version: str) -> bool:
        """Validate protocol version against supported list."""
        return version in self.SUPPORTED_VERSIONS

    def extract_meta(self, params: dict) -> dict:
        """Extract _meta from request params. All state travels here."""
        return params.get('_meta', {})

    def build_meta_response(self, extra: Optional[dict] = None) -> dict:
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


# ═══════════════════════════════════════════════════
# Authorization Abstractions
# ═══════════════════════════════════════════════════

class BaseAuthProvider(ABC):
    """Abstract base for MCP 2026 authorization providers."""

    @abstractmethod
    def authenticate(self, request) -> bool:
        """
        Validate request authentication.
        Must not depend on sessions or server-side state.
        """
        pass


class BearerTokenAuthProvider(BaseAuthProvider):
    """Bearer token validation. Stateless: token compared directly."""

    def __init__(self, expected_token: str):
        self.expected_token = expected_token

    def authenticate(self, request) -> bool:
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:] == self.expected_token
        return False


class APIKeyAuthProvider(BaseAuthProvider):
    """X-Api-Key validation. Stateless."""

    def __init__(self, expected_key: str):
        self.expected_key = expected_key

    def authenticate(self, request) -> bool:
        api_key = request.headers.get('X-Api-Key', '')
        return api_key == self.expected_key


class OAuth2AuthProvider(BaseAuthProvider):
    """
    OAuth 2.0 validation interface.
    Production implementation should validate JWT signature,
    check expiration, introspect at authorization server, etc.
    """

    def __init__(self, introspection_url: Optional[str] = None):
        self.introspection_url = introspection_url

    def authenticate(self, request) -> bool:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        token = auth_header[7:]
        # Production: validate JWT, check scopes, introspect token
        return len(token) > 0  # Interface placeholder


class OIDCAuthProvider(BaseAuthProvider):
    """
    OpenID Connect validation interface.
    Production implementation should verify id_token,
    validate issuer, audience, and signature via JWKS.
    """

    def __init__(
        self,
        issuer_url: Optional[str] = None,
        client_id: Optional[str] = None
    ):
        self.issuer_url = issuer_url
        self.client_id = client_id

    def authenticate(self, request) -> bool:
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return False
        # Production: verify ID token with JWKS endpoint, check iss/aud
        return True  # Interface placeholder


class CompositeAuthProvider(BaseAuthProvider):
    """Try multiple auth providers in sequence. First match wins."""

    def __init__(self, providers: List[BaseAuthProvider]):
        self.providers = providers

    def authenticate(self, request) -> bool:
        return any(p.authenticate(request) for p in self.providers)


# ═══════════════════════════════════════════════════
# Role-Based Permission Architecture
# ═══════════════════════════════════════════════════

class BasePermissionProvider(ABC):
    """Abstract base for MCP 2026 permission providers."""

    @abstractmethod
    def has_permission(self, request, operation: str) -> bool:
        """
        Check if the authenticated principal may execute the operation.
        Stateless: derive role from request metadata or token claims.
        """
        pass


class RoleBasedPermissionProvider(BasePermissionProvider):
    """
    Role-based permission provider.
    Maps roles to allowed operations. Extensible via configuration.
    """

    def __init__(self, role_map: Dict[str, List[str]] = None):
        self.role_map = role_map or {}

    def has_permission(self, request, operation: str) -> bool:
        # Production: extract role from JWT claims or request metadata
        # This is an extensible interface; default permissive for demo
        return True  # Interface placeholder