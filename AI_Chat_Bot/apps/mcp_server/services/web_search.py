"""
Stateless Web Search Service.
Pluggable provider architecture supporting DuckDuckGo, SerpAPI, Tavily, Mock.
Dependency inversion: endpoint logic never depends on specific engines.
"""
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from django.conf import settings


class BaseSearchProvider(ABC):
    """Abstract base for all search providers."""

    @abstractmethod
    def search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        """
        Execute search and return normalized results.
        Each call is independent; no session state.
        """
        pass


class DuckDuckGoProvider(BaseSearchProvider):
    """DuckDuckGo search provider."""

    def search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
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


class SerpAPIProvider(BaseSearchProvider):
    """SerpAPI (Google) search provider."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.WEB_SEARCH_API_KEY

    def search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
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


class TavilyProvider(BaseSearchProvider):
    """Tavily AI search provider."""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.WEB_SEARCH_API_KEY

    def search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        if not self.api_key:
            return [{"error": "TAVILY_API_KEY not configured", "source": "tavily"}]

        try:
            import requests
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "query": query,
                    "search_depth": "basic",
                    "max_results": num_results,
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=15
            )
            data = resp.json()
            results = []
            for r in data.get('results', [])[:num_results]:
                results.append({
                    "title": r.get('title'),
                    "link": r.get('url'),
                    "snippet": r.get('content'),
                    "source": "tavily",
                })
            return results
        except Exception as e:
            return [{"error": str(e), "source": "tavily"}]


class MockSearchProvider(BaseSearchProvider):
    """Mock provider for demos, CI, and offline development."""

    MOCK_DB = [
        {
            "title": "MCP 2026-07-28 Release Candidate: Stateless Protocol",
            "link": "https://modelcontextprotocol.io/specification/draft",
            "snippet": (
                "The 2026-07-28 release candidate removes sessions and "
                "initialize handshake. Every request now carries protocol version in _meta."
            ),
            "source": "mock",
        },
        {
            "title": "Building Stateless MCP Servers with Django",
            "link": "https://example.com/django-mcp-stateless",
            "snippet": (
                "A complete guide to deploying stateless MCP servers using Django. "
                "Simple. Scalable. Reliable."
            ),
            "source": "mock",
        },
        {
            "title": "MCP Apps Extension: Server-Rendered UI (SEP-1865)",
            "link": "https://modelcontextprotocol.io/extensions/apps",
            "snippet": (
                "MCP Apps allow servers to transmit lightweight UI "
                "directly to clients via HTML sandboxed iframes."
            ),
            "source": "mock",
        },
        {
            "title": "Tasks Extension for Long-Running Operations (SEP-2663)",
            "link": "https://modelcontextprotocol.io/extensions/tasks",
            "snippet": (
                "Official extension replaces blocking tasks with polling "
                "via tasks/get and tasks/update."
            ),
            "source": "mock",
        },
        {
            "title": "OAuth 2.1 and OpenID Connect in MCP 2026",
            "link": "https://modelcontextprotocol.io/auth",
            "snippet": (
                "Six SEPs align MCP authorization with mainstream "
                "OAuth 2.1 and OpenID Connect deployments."
            ),
            "source": "mock",
        },
        {
            "title": "Stateless Streamable HTTP: No More Sticky Sessions",
            "link": "https://modelcontextprotocol.io/blog/stateless-http",
            "snippet": (
                "Run MCP behind a plain round-robin load balancer. "
                "No Mcp-Session-Id required. Route on Mcp-Method header."
            ),
            "source": "mock",
        },
    ]

    def search(self, query: str, num_results: int) -> List[Dict[str, Any]]:
        random.seed(len(query))
        return random.sample(self.MOCK_DB, min(num_results, len(self.MOCK_DB)))


class SearchProviderRegistry:
    """
    Registry for search providers.
    Enables configuration-driven selection without endpoint modification.
    """

    def __init__(self):
        self._providers: Dict[str, BaseSearchProvider] = {}

    def register(self, name: str, provider: BaseSearchProvider) -> None:
        self._providers[name] = provider

    def get(self, name: str) -> BaseSearchProvider:
        if name not in self._providers:
            available = list(self._providers.keys())
            raise ValueError(f"Unknown search provider: {name}. Available: {available}")
        return self._providers[name]

    def list_providers(self) -> List[str]:
        return list(self._providers.keys())


# Initialize global registry with default providers
_search_registry = SearchProviderRegistry()
_search_registry.register('duckduckgo', DuckDuckGoProvider())
_search_registry.register('serpapi', SerpAPIProvider())
_search_registry.register('tavily', TavilyProvider())
_search_registry.register('mock', MockSearchProvider())


class WebSearchService:
    """
    Stateless web search facade.
    No session state; each search is independent.
    """

    def __init__(self, registry: SearchProviderRegistry = None):
        self.registry = registry or _search_registry
        self.default_provider = settings.WEB_SEARCH_BACKEND

    def search(
        self,
        query: str,
        provider: str = None,
        num_results: int = None
    ) -> List[Dict[str, Any]]:
        """
        Execute search via configured or specified provider.

        Args:
            query: Search query string.
            provider: Provider name override (duckduckgo, serpapi, tavily, mock).
            num_results: Maximum results to return.
        """
        provider_name = provider or self.default_provider
        num_results = num_results or settings.WEB_SEARCH_MAX_RESULTS

        provider_instance = self.registry.get(provider_name)
        return provider_instance.search(query, num_results)