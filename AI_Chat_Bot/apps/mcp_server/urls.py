from django.urls import path
from . import views

urlpatterns = [
    path('', views.MCPStatelessEndpoint.as_view(), name='mcp_endpoint'),
]