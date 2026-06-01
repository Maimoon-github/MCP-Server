"""
S2C (Server-to-Client) Elicitation Service.

Handles encoding/decoding of requestState tokens, special response construction,
and mid-operation resume logic. All state travels in the token; shared DB is only
for audit and monitoring.
"""
import json
import base64
import hashlib
import zlib
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from django.conf import settings
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.utils import timezone as django_timezone

from apps.s2c.models import ElicitationRecord


class ElicitationError(Exception):
    """Structured elicitation error with MCP-compatible code."""

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


class ElicitationRequired(ElicitationError):
    """
    Raised by handlers when mid-operation client input is required.
    Triggers the Special Response per In-Flight Rule.
    """
    def __init__(
        self,
        question: str,
        original_method: str,
        original_params: dict,
        progress_state: dict,
        operation_type: str = 'generic',
        hint: Optional[str] = None
    ):
        self.question = question
        self.original_method = original_method
        self.original_params = original_params
        self.progress_state = progress_state
        self.operation_type = operation_type
        self.hint = hint
        super().__init__(-32010, f"Elicitation required: {question}")


class ElicitationService:
    """
    Stateless Server-to-Client Elicitation engine.

    Encodes operation progress into signed, timestamped requestState tokens.
    Any server instance with the same SECRET_KEY can verify and resume.
    """

    TOKEN_MAX_AGE = 3600  # 1 hour

    def __init__(self):
        self.signer = TimestampSigner(
            key=settings.SECRET_KEY,
            salt='mcp-s2c-elicitation-v1'
        )

    def encode_state(
        self,
        operation_type: str,
        original_method: str,
        original_params: dict,
        progress: dict,
        question: str
    ) -> str:
        """
        Encode current operation state into a compact, signed token.
        The token is self-contained; no DB lookup is required to resume.
        """
        payload = {
            'op': operation_type,
            'method': original_method,
            'params': original_params,
            'progress': progress,
            'question': question,
            'iat': datetime.now(timezone.utc).isoformat(),
            'exp': (
                datetime.now(timezone.utc) + timedelta(seconds=self.TOKEN_MAX_AGE)
            ).isoformat(),
        }

        # Compress + sign for compactness and integrity
        json_bytes = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        compressed = zlib.compress(json_bytes, level=9)
        token = self.signer.sign(
            base64.urlsafe_b64encode(compressed).decode('ascii')
        )

        # Audit record (optional, for monitoring/horizontal scaling visibility)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        ElicitationRecord.objects.create(
            state_token_hash=token_hash,
            operation_type=operation_type,
            original_method=original_method,
            original_params=original_params,
            question=question,
            status='pending',
            expires_at=django_timezone.now() + timedelta(seconds=self.TOKEN_MAX_AGE),
        )

        return token

    def decode_state(self, token: str) -> dict:
        """
        Decode and verify a requestState token.
        Raises ElicitationError if signature invalid or expired.
        """
        try:
            unsigned = self.signer.unsign(token, max_age=self.TOKEN_MAX_AGE)
            compressed = base64.urlsafe_b64decode(unsigned.encode('ascii'))
            json_bytes = zlib.decompress(compressed)
            payload = json.loads(json_bytes.decode('utf-8'))

            # Double-check explicit expiry
            exp = datetime.fromisoformat(payload['exp'])
            if django_timezone.now() > exp:
                raise ElicitationError(
                    -32011, "Elicitation state token has expired."
                )
            return payload

        except SignatureExpired:
            raise ElicitationError(
                -32011, "Elicitation state token has expired."
            )
        except BadSignature:
            raise ElicitationError(
                -32012, "Invalid elicitation state token."
            )
        except Exception as e:
            raise ElicitationError(
                -32013, f"Failed to decode elicitation state: {str(e)}"
            )

    def build_special_response(
        self,
        question: str,
        request_state: str,
        hint: Optional[str] = None
    ) -> dict:
        """
        Build the Special Response payload per MCP Stateless Elicitation protocol.
        """
        response = {
            "elicitationRequired": True,
            "question": question,
            "requestState": request_state,
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": getattr(
                    settings, 'MCP_PROTOCOL_VERSION', '2026-07-28'
                ),
                "io.modelcontextprotocol/elicitationVersion": "1.0",
                "io.modelcontextprotocol/elicitationRule": "In-Flight",
            }
        }
        if hint:
            response["hint"] = hint
        return response

    def extract_answer(self, params: dict) -> Optional[dict]:
        """
        Extract client answer from retry request.
        Searches _meta.elicitationAnswer and top-level elicitationAnswer.
        """
        meta = params.get('_meta', {})
        answer = meta.get('elicitationAnswer')
        if answer is None:
            answer = params.get('elicitationAnswer')
        return answer

    def extract_request_state(self, params: dict) -> Optional[str]:
        """
        Extract requestState token from retry request.
        Searches _meta.requestState and top-level requestState.
        """
        meta = params.get('_meta', {})
        state = meta.get('requestState')
        if state is None:
            state = params.get('requestState')
        return state
