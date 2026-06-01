"""
MCP 2026 Stateless Server-to-Client Elicitation JSON-RPC Endpoint.

Implements the full Elicitation workflow:
  1. In-Flight Rule: prompts only during active request processing.
  2. Special Response Rule: returns question + requestState when input needed.
  3. Stateless Resume: any server instance resumes via signed requestState token.

Automatically performs web searches when temporal/latest-update context is detected.
"""
import json
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Callable, Optional
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.conf import settings

from apps.stateless.services.mcp_protocol import MCPError
from apps.stateless.services.web_search import WebSearchService

from .services.elicitation_service import (
    ElicitationService, ElicitationRequired, ElicitationError
)
from .models import ElicitationRecord


# ═══════════════════════════════════════════════════
# Elicitation Registry
# ═══════════════════════════════════════════════════

class ElicitationRegistry:
    """
    Registry-driven operation router with first-class elicitation support.
    Handlers may raise ElicitationRequired to trigger a Special Response.
    """

    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self.elicitation = ElicitationService()

    def register(self, method: str) -> Callable:
        """Decorator to register an operation handler."""
        def decorator(func: Callable) -> Callable:
            self._handlers[method] = func
            return func
        return decorator

    def dispatch(self, method: str, params: dict, meta: dict, request) -> dict:
        """
        Dispatch with elicitation lifecycle awareness.
        Detects retry-with-answer and either resumes or routes to handler.
        """
        state_token = self.elicitation.extract_request_state(params)
        answer = self.elicitation.extract_answer(params)

        # ─── RETRY WITH CONTEXT ───
        if state_token and answer is not None:
            return self._resume_elicitation(state_token, answer, meta, request)

        # ─── FRESH REQUEST ───
        handler = self._handlers.get(method)
        if not handler:
            raise MCPError(-32601, f"Method not found: {method}")

        try:
            return handler(params, meta, request, self.elicitation)
        except ElicitationRequired as e:
            # Encode progress and return Special Response
            token = self.elicitation.encode_state(
                operation_type=e.operation_type,
                original_method=e.original_method,
                original_params=e.original_params,
                progress=e.progress_state,
                question=e.question,
            )
            return self.elicitation.build_special_response(
                question=e.question,
                request_state=token,
                hint=e.hint or (
                    "Please answer the question and retry the same request "
                    "including 'elicitationAnswer' and 'requestState'."
                ),
            )

    def _resume_elicitation(
        self, token: str, answer: dict, meta: dict, request
    ) -> dict:
        """
        Stateless Resume: decode token, restore context, invoke original handler.
        Any server instance can execute this because state is in the token.
        """
        try:
            state = self.elicitation.decode_state(token)
        except ElicitationError as e:
            raise MCPError(e.code, e.message, e.data)

        original_method = state['method']
        handler = self._handlers.get(original_method)
        if not handler:
            raise MCPError(
                -32601,
                f"Original method not found for resume: {original_method}"
            )

        # Reconstruct params with elicitation context injected
        resumed_params = {
            **state['params'],
            '_elicitation': {
                'answer': answer,
                'progress': state['progress'],
                'question': state['question'],
                'state_token': token,
            }
        }

        # Update audit record
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            record = ElicitationRecord.objects.get(state_token_hash=token_hash)
            record.mark_answered(answer)
        except ElicitationRecord.DoesNotExist:
            pass

        return handler(resumed_params, meta, request, self.elicitation)


# Global elicitation registry
registry = ElicitationRegistry()


# ═══════════════════════════════════════════════════
# Server Capability Handlers
# ═══════════════════════════════════════════════════

@registry.register('server/discover')
def handle_discover(params: dict, meta: dict, request, elicitation: ElicitationService) -> dict:
    """Stateless capability advertisement with elicitation extension."""
    return {
        "protocolVersion": getattr(settings, 'MCP_PROTOCOL_VERSION', '2026-07-28'),
        "serverInfo": {
            "name": getattr(settings, 'MCP_SERVER_NAME', 'mcp-s2c'),
            "version": getattr(settings, 'MCP_SERVER_VERSION', '1.0.0'),
        },
        "capabilities": {
            **getattr(settings, 'MCP_SERVER_CAPABILITIES', {}),
            "elicitation": {
                "version": "1.0",
                "inFlightRule": True,
                "specialResponseRule": True,
            },
        },
        "supportedVersions": getattr(
            settings, 'MCP_PROTOCOL_VERSIONS_SUPPORTED', ['2026-07-28']
        ),
    }


# ═══════════════════════════════════════════════════
# Tools Handlers (Elicitation-Aware)
# ═══════════════════════════════════════════════════

@registry.register('tools/list')
def handle_tools_list(params: dict, meta: dict, request, elicitation: ElicitationService) -> dict:
    """Return extensible tool registry with elicitation-aware tools."""
    tools = [
        {
            "name": "search_web",
            "description": (
                "Perform a web search with automatic latest-update detection. "
                "Triggers elicitation if the query is ambiguous for temporal context."
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
                    "num_results": {
                        "type": "integer",
                        "default": getattr(settings, 'WEB_SEARCH_MAX_RESULTS', 5)
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
                "Retrieve latest updates on a topic via automatic web search. "
                "Uses elicitation to narrow specificity before searching."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "Topic to get latest updates for"
                    },
                    "num_results": {"type": "integer", "default": 5},
                },
                "required": ["topic"]
            },
            "annotations": {"readOnly": True, "destructive": False}
        },
        {
            "name": "confirm_and_execute",
            "description": (
                "Execute a sensitive action with mid-operation confirmation. "
                "Demonstrates the core elicitation In-Flight Rule."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "description": "Action to perform"
                    },
                    "target": {
                        "type": "string",
                        "description": "Target of the action"
                    },
                },
                "required": ["action", "target"]
            },
            "annotations": {"readOnly": False, "destructive": True}
        },
    ]

    return {
        "tools": tools,
        "ttlMs": getattr(settings, 'MCP_LIST_CACHE_TTL', 300000),
        "cacheScope": "global",
    }


@registry.register('tools/search_web')
def handle_search_web(params: dict, meta: dict, request, elicitation: ElicitationService) -> dict:
    """
    Web search with automatic latest-update detection and elicitation support.

    Flow:
      1. Fresh call with ambiguous temporal query -> Special Response (clarify).
      2. Retry with answer -> performs targeted search and returns results.
    """
    arguments = params.get('arguments', params)
    query = arguments.get('query', '')

    # ─── RESUME PATH ───
    elicitation_ctx = params.get('_elicitation')
    if elicitation_ctx:
        answer = elicitation_ctx['answer']
        progress = elicitation_ctx['progress']

        original_query = progress.get('original_query', query)
        clarification = answer.get('text', answer.get('choice', ''))

        if clarification:
            refined_query = f"{original_query} {clarification}"
        else:
            refined_query = original_query

        # Auto-enhance for latest context
        if _needs_latest_context(refined_query):
            refined_query = _enhance_query_for_latest(refined_query)

        service = WebSearchService()
        results = service.search(
            refined_query,
            provider=arguments.get('provider', getattr(settings, 'WEB_SEARCH_BACKEND', 'mock')),
            num_results=arguments.get('num_results', getattr(settings, 'WEB_SEARCH_MAX_RESULTS', 5))
        )

        # Mark audit complete
        state_token = elicitation_ctx.get('state_token', '')
        if state_token:
            try:
                token_hash = hashlib.sha256(state_token.encode()).hexdigest()
                record = ElicitationRecord.objects.get(state_token_hash=token_hash)
                record.mark_completed()
            except ElicitationRecord.DoesNotExist:
                pass

        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "query": refined_query,
                    "original_query": original_query,
                    "clarification": clarification,
                    "results": results,
                    "searched_at": datetime.now(timezone.utc).isoformat(),
                    "elicitation_resolved": True,
                    "request_id": getattr(request, 'mcp_request_id', ''),
                }, indent=2, ensure_ascii=False)
            }],
            "isError": False,
        }

    # ─── FRESH CALL PATH ───
    needs_latest = _needs_latest_context(query)

    if needs_latest and _is_ambiguous_for_latest(query):
        raise ElicitationRequired(
            question=(
                f'Your query "{query}" requests latest updates. '
                f'What specific aspect would you like updates on? '
                f'(e.g., features, security, releases, community news)'
            ),
            original_method='tools/search_web',
            original_params=params,
            progress_state={
                'original_query': query,
                'needs_latest': True,
                'step': 'awaiting_clarification'
            },
            operation_type='web_search',
            hint="Reply with a short clarification text."
        )

    # No elicitation needed – search directly
    service = WebSearchService()
    results = service.search(
        query,
        provider=arguments.get('provider', getattr(settings, 'WEB_SEARCH_BACKEND', 'mock')),
        num_results=arguments.get('num_results', getattr(settings, 'WEB_SEARCH_MAX_RESULTS', 5))
    )

    return {
        "content": [{
            "type": "text",
            "text": json.dumps({
                "query": query,
                "results": results,
                "searched_at": datetime.now(timezone.utc).isoformat(),
                "auto_context_applied": needs_latest,
                "elicitation_required": False,
                "request_id": getattr(request, 'mcp_request_id', ''),
            }, indent=2, ensure_ascii=False)
        }],
        "isError": False,
    }


@registry.register('tools/get_latest_updates')
def handle_get_latest_updates(params: dict, meta: dict, request, elicitation: ElicitationService) -> dict:
    """
    Dedicated latest-update tool with mandatory specificity elicitation.
    Always performs automatic web search after clarification.
    """
    arguments = params.get('arguments', params)
    topic = arguments.get('topic', '')

    # ─── RESUME PATH ───
    elicitation_ctx = params.get('_elicitation')
    if elicitation_ctx:
        answer = elicitation_ctx['answer']
        progress = elicitation_ctx['progress']

        original_topic = progress.get('topic', topic)
        specificity = answer.get('text', answer.get('specificity', ''))

        enhanced_query = f"latest updates {original_topic} {specificity} 2026".strip()

        service = WebSearchService()
        results = service.search(
            enhanced_query,
            num_results=arguments.get('num_results', 5)
        )

        state_token = elicitation_ctx.get('state_token', '')
        if state_token:
            try:
                token_hash = hashlib.sha256(state_token.encode()).hexdigest()
                record = ElicitationRecord.objects.get(state_token_hash=token_hash)
                record.mark_completed()
            except ElicitationRecord.DoesNotExist:
                pass

        return {
            "content": [{
                "type": "text",
                "text": json.dumps({
                    "topic": original_topic,
                    "specificity": specificity,
                    "enhanced_query": enhanced_query,
                    "results": results,
                    "searched_at": datetime.now(timezone.utc).isoformat(),
                    "source": "auto_web_search",
                    "elicitation_resolved": True,
                }, indent=2, ensure_ascii=False)
            }],
            "isError": False,
        }

    # ─── FRESH CALL PATH ───
    if not topic or len(topic.strip()) < 3:
        raise ElicitationRequired(
            question=(
                "What topic would you like the latest updates for? "
                "Please be specific (e.g., 'Python programming language', "
                "'Django web framework', 'React JavaScript library')."
            ),
            original_method='tools/get_latest_updates',
            original_params=params,
            progress_state={'topic': topic, 'step': 'awaiting_topic'},
            operation_type='latest_updates',
            hint="Provide the topic name."
        )

    # Topic provided – elicit for specificity aspect
    raise ElicitationRequired(
        question=(
            f"You asked for latest updates on '{topic}'. "
            f"What specific aspect interests you?\n"
            f"(a) New features / releases\n"
            f"(b) Security updates\n"
            f"(c) Community / ecosystem news\n"
            f"(d) All of the above"
        ),
        original_method='tools/get_latest_updates',
        original_params=params,
        progress_state={'topic': topic, 'step': 'awaiting_specificity'},
        operation_type='latest_updates',
        hint="Reply with the letter (a, b, c, or d) or a short description."
    )


@registry.register('tools/confirm_and_execute')
def handle_confirm_and_execute(params: dict, meta: dict, request, elicitation: ElicitationService) -> dict:
    """
    Generic confirmation elicitation handler.
    Classic example: Delete 3 files -> Confirm? -> Execute/Cancel.
    """
    arguments = params.get('arguments', params)
    action = arguments.get('action', '')
    target = arguments.get('target', '')

    elicitation_ctx = params.get('_elicitation')
    if elicitation_ctx:
        answer = elicitation_ctx['answer']
        progress = elicitation_ctx['progress']

        confirmed = answer.get('confirmed', False)
        if isinstance(confirmed, str):
            confirmed = confirmed.lower() in ('yes', 'true', '1', 'y')

        if not confirmed:
            return {
                "content": [{"type": "text", "text": "Operation cancelled by user."}],
                "isError": False,
                "cancelled": True,
            }

        # Simulate execution
        action_desc = progress.get('action_description', f"{action} {target}".strip())
        return {
            "content": [{
                "type": "text",
                "text": f"Executed: {action_desc}"
            }],
            "isError": False,
            "executed": True,
        }

    # First call – ask for confirmation
    action_desc = f"{action} {target}".strip()
    raise ElicitationRequired(
        question=f"Confirm execution: {action_desc}?",
        original_method='tools/confirm_and_execute',
        original_params=params,
        progress_state={
            'action_description': action_desc,
            'action': action,
            'target': target,
            'step': 'awaiting_confirmation'
        },
        operation_type='confirmation',
        hint="Reply with confirmed=true to proceed, confirmed=false to cancel."
    )


# ═══════════════════════════════════════════════════
# Elicitation Management / Monitoring
# ═══════════════════════════════════════════════════

@registry.register('elicitation/list_pending')
def handle_list_pending(params: dict, meta: dict, request, elicitation: ElicitationService) -> dict:
    """List pending elicitation records (useful for distributed monitoring)."""
    records = ElicitationRecord.objects.filter(status='pending')[:50]
    return {
        "records": [
            {
                "recordId": str(r.record_id),
                "operationType": r.operation_type,
                "question": r.question,
                "createdAt": r.created_at.isoformat(),
                "expiresAt": r.expires_at.isoformat(),
            }
            for r in records
        ],
        "count": len(records),
    }


@registry.register('elicitation/get_status')
def handle_get_status(params: dict, meta: dict, request, elicitation: ElicitationService) -> dict:
    """Get status of a specific elicitation by token hash."""
    token_hash = params.get('tokenHash', '')
    try:
        record = ElicitationRecord.objects.get(state_token_hash=token_hash)
        return {
            "recordId": str(record.record_id),
            "status": record.status,
            "question": record.question,
            "answer": record.answer_payload,
            "createdAt": record.created_at.isoformat(),
            "answeredAt": record.answered_at.isoformat() if record.answered_at else None,
            "completedAt": record.completed_at.isoformat() if record.completed_at else None,
        }
    except ElicitationRecord.DoesNotExist:
        raise MCPError(-32004, "Elicitation record not found")


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


def _is_ambiguous_for_latest(query: str) -> bool:
    """
    Determine if a latest-context query is too ambiguous.
    Short queries or purely temporal terms benefit from elicitation.
    """
    words = query.strip().split()
    temporal_only = all(
        w.lower() in ['latest', 'recent', 'updates', 'news', 'current', 'new', 'today']
        for w in words
    )
    return len(words) <= 3 or temporal_only


def _enhance_query_for_latest(query: str) -> str:
    """Enhance query to retrieve latest information."""
    if '2026' not in query and '2025' not in query:
        return f"{query} latest 2026"
    return query


# ═══════════════════════════════════════════════════
# JSON-RPC Endpoint View
# ═══════════════════════════════════════════════════

@method_decorator(csrf_exempt, name='dispatch')
class MCPS2CEndpoint(View):
    """
    Single POST endpoint handling all JSON-RPC methods with elicitation support.

    Har request apne aap mein poori hai:
      - Protocol version in header or _meta
      - Auth in Authorization header
      - No Mcp-Session-Id
      - Elicitation state travels in requestState token
    """

    http_method_names = ['post', 'get', 'options']

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.elicitation = ElicitationService()

    def post(self, request, *args, **kwargs) -> JsonResponse:
        """Handle JSON-RPC POST requests."""
        try:
            body = json.loads(request.body.decode('utf-8'))
        except json.JSONDecodeError:
            return self._error_response(-32700, "Parse error", None)

        rpc_id = body.get('id')
        rpc_method = body.get('method', '')
        params = body.get('params', {})
        meta = params.get('_meta', {})

        # Protocol version validation
        header_version = getattr(request, 'mcp_protocol_version', '')
        meta_version = meta.get('io.modelcontextprotocol/protocolVersion', '')
        protocol_version = header_version or meta_version

        supported = getattr(settings, 'MCP_PROTOCOL_VERSIONS_SUPPORTED', ['2026-07-28'])
        if protocol_version and protocol_version not in supported:
            return self._error_response(
                -32001,
                "UnsupportedProtocolVersionError",
                rpc_id,
                data={"supported": supported}
            )

        # Stateless authentication (composite: Bearer OR API Key)
        debug_bypass = getattr(settings, 'DEBUG', True)
        if not debug_bypass:
            auth_ok = self._authenticate(request)
            if not auth_ok:
                return self._error_response(-32002, "Unauthorized", rpc_id)

        # Elicitation-aware dispatch
        try:
            result = registry.dispatch(rpc_method, params, meta, request)

            # Inject response _meta with tracking IDs
            result['_meta'] = {
                "io.modelcontextprotocol/protocolVersion": getattr(
                    settings, 'MCP_PROTOCOL_VERSION', '2026-07-28'
                ),
                "io.modelcontextprotocol/requestId": getattr(
                    request, 'mcp_request_id', ''
                ),
                "io.modelcontextprotocol/correlationId": getattr(
                    request, 'mcp_correlation_id', ''
                ),
            }

            return JsonResponse({
                "jsonrpc": "2.0",
                "id": rpc_id,
                "result": result
            })

        except MCPError as e:
            return self._error_response(e.code, e.message, rpc_id, e.data)
        except ElicitationError as e:
            return self._error_response(e.code, e.message, rpc_id, e.data)
        except Exception as e:
            return self._error_response(-32603, f"Internal error: {str(e)}", rpc_id)

    def get(self, request, *args, **kwargs) -> JsonResponse:
        """Health check with elicitation capability advertisement."""
        return JsonResponse({
            "jsonrpc": "2.0",
            "result": {
                "status": "ok",
                "protocolVersion": getattr(settings, 'MCP_PROTOCOL_VERSION', '2026-07-28'),
                "server": getattr(settings, 'MCP_SERVER_NAME', 'mcp-s2c'),
                "stateless": True,
                "elicitationSupported": True,
                "elicitationVersion": "1.0",
                "requestId": getattr(request, 'mcp_request_id', ''),
                "correlationId": getattr(request, 'mcp_correlation_id', ''),
            }
        })

    def _authenticate(self, request) -> bool:
        """Bearer token or API key validation. Stateless."""
        expected = getattr(settings, 'MCP_API_KEY', 'dev-api-key-change-me')
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            return auth_header[7:] == expected
        api_key = request.headers.get('X-Api-Key', '')
        return api_key == expected

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
        })
