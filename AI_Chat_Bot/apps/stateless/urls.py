"""
MCP 2026 Stateless URL Configuration.
Single endpoint handling all JSON-RPC operations.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.MCPStatelessEndpoint.as_view(), name='mcp_endpoint'),
]