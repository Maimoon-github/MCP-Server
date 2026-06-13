"""
auth.py – Token-based authentication for the Local MCP Hub.

How it works
------------
Clients pass a bearer token as the `_token` keyword argument when calling
any tool.  The hub validates it against the AUTH_TOKENS allow-list using
constant-time comparison (to prevent timing-based token enumeration).

Configuration
-------------
Set in .env:
    AUTH_ENABLED=true
    AUTH_TOKENS=<hex32>,<hex32>,...

Generate a token:
    python -c "import secrets; print(secrets.token_hex(32))"

Development mode
----------------
Leave AUTH_ENABLED=false to skip auth entirely (all calls allowed).
"""
from __future__ import annotations

import functools
import hmac
import logging
from typing import Callable

from .config import settings

logger = logging.getLogger(__name__)


class AuthError(PermissionError):
    """Raised when a request cannot be authenticated."""


def verify_token(token: str | None) -> bool:
    """
    Return True if *token* is valid (or auth is disabled).

    Uses :func:`hmac.compare_digest` for constant-time comparison.
    """
    if not settings.auth_enabled:
        return True
    if not token:
        return False
    valid_tokens = settings.get_auth_tokens()
    if not valid_tokens:
        # Auth enabled but no tokens configured – block everything.
        logger.error(
            "AUTH_ENABLED=true but AUTH_TOKENS is empty; all requests blocked."
        )
        return False
    return any(hmac.compare_digest(token.encode(), t.encode()) for t in valid_tokens)


def require_auth(fn: Callable) -> Callable:
    """
    Decorator – enforce token authentication before calling *fn*.

    The wrapped function must accept a keyword argument ``_token`` (string).
    The argument is consumed here and never forwarded to the real function.

    Example
    -------
        @mcp.tool()
        @require_auth
        def read_file(path: str, _token: str = "") -> str:
            ...
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        token: str | None = kwargs.pop("_token", None)
        if not verify_token(token):
            logger.warning(
                "Auth failure – tool '%s' called without a valid token.",
                fn.__name__,
            )
            raise AuthError(
                "Unauthorized: supply a valid bearer token via the '_token' parameter. "
                "See README for configuration instructions."
            )
        return fn(*args, **kwargs)

    return wrapper
