"""
MCP 2026 Stateless S2C Elicitation URL Configuration.
Single endpoint handling all JSON-RPC operations with elicitation support.
"""
from django.urls import path
from . import views

urlpatterns = [
    path('', views.MCPS2CEndpoint.as_view(), name='mcp_s2c_endpoint'),
]
