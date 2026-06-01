"""
Stateless Web Search Service.
Automatically retrieves latest updates based on query context.
Supports: duckduckgo, serpapi, mock (for demo).
"""
import random
from typing import List, Dict, Any
from django.conf import settings


class WebSearchService:
    """
    Har request apne aap mein poori hai.
    No session state; each search is independent.
    """

    def __init__(self):
        self.backend = settings.WEB_SEARCH_BACKEND
        self.api_key = settings.WEB_SEARCH_API_KEY
        self.max_results = settings.WEB_SEARCH_MAX_RESULTS

    def search(self, query: str, num_results: int = None) -> List[Dict[str, Any]]:
        num_results = num_results or self.max_results

        if self.backend == 'duckduckgo':
            return self._search_duckduckgo(query, num_results)
        elif self.backend == 'serpapi':
            return self._search_serpapi(query, num_results)
        else:
            return self._search_mock(query, num_results)

    def _search_duckduckgo(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = []
                for r in ddgs.text(query, max_results=num_results):
                    results.append({
                        "title": r.get('title'),
                        "link": r.get('href'),
                        "snippet": r.get('body'),
                        "source": "duckduckgo",
                    })
                return results
        except Exception as e:
            return [{"error": str(e), "source": "duckduckgo"}]

    def _search_serpapi(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        if not self.api_key:
            return [{"error": "SERPAPI_KEY not configured", "source": "serpapi"}]

        try:
            import requests
            resp = requests.get(
                "https://serpapi.com/search",
                params={
                    "q": query,
                    "api_key": self.api_key,
                    "engine": "google",
                    "num": num_results,
                },
                timeout=10
            )
            data = resp.json()
            results = []
            for r in data.get('organic_results', [])[:num_results]:
                results.append({
                    "title": r.get('title'),
                    "link": r.get('link'),
                    "snippet": r.get('snippet'),
                    "source": "serpapi",
                })
            return results
        except Exception as e:
            return [{"error": str(e), "source": "serpapi"}]

    def _search_mock(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """Mock search returning realistic MCP 2026 results."""
        mock_db = [
            {
                "title": "MCP 2026-07-28 Release Candidate: Stateless Protocol",
                "link": "https://modelcontextprotocol.io/specification/draft",
                "snippet": "The 2026-07-28 release candidate removes sessions and initialize handshake. Every request now carries protocol version in _meta.",
                "source": "mock",
            },
            {
                "title": "Building Stateless MCP Servers with Django",
                "link": "https://example.com/django-mcp-stateless",
                "snippet": "A complete guide to deploying stateless MCP servers using Django without session middleware. Simple. Scalable. Reliable.",
                "source": "mock",
            },
            {
                "title": "MCP Apps Extension: Server-Rendered UI (SEP-1865)",
                "link": "https://modelcontextprotocol.io/extensions/apps",
                "snippet": "MCP Apps allow servers to transmit lightweight UI directly to clients via HTML sandboxed iframes.",
                "source": "mock",
            },
            {
                "title": "Tasks Extension for Long-Running Operations (SEP-2663)",
                "link": "https://modelcontextprotocol.io/extensions/tasks",
                "snippet": "Official extension replaces blocking tasks/result with polling via tasks/get and tasks/update.",
                "source": "mock",
            },
            {
                "title": "OAuth 2.1 and OpenID Connect in MCP 2026",
                "link": "https://modelcontextprotocol.io/auth",
                "snippet": "Six SEPs align MCP authorization with mainstream OAuth 2.1 and OpenID Connect deployments.",
                "source": "mock",
            },
            {
                "title": "Stateless Streamable HTTP: No More Sticky Sessions",
                "link": "https://modelcontextprotocol.io/blog/stateless-http",
                "snippet": "Run MCP behind a plain round-robin load balancer. No Mcp-Session-Id required. Route on Mcp-Method header.",
                "source": "mock",
            },
        ]
        # Deterministic selection for demo consistency
        random.seed(len(query))
        return random.sample(mock_db, min(num_results, len(mock_db)))