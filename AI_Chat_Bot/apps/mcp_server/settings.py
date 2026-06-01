"""
Django settings for MCP 2026 Stateless Server.
"""
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'mcp-stateless-dev-key-change-in-production')

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() == 'true'

ALLOWED_HOSTS = ['*']

# ═══════════════════════════════════════════════════
# INSTALLED APPS
# ═══════════════════════════════════════════════════
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'mcp_server',
]

# ═══════════════════════════════════════════════════
# MIDDLEWARE — NO SESSION MIDDLEWARE
# ═══════════════════════════════════════════════════
MIDDLEWARE = [
    'mcp_server.middleware.MCPProtocolMiddleware',
    'django.middleware.common.CommonMiddleware',
]

# Explicitly remove session middleware
SESSION_ENGINE = None

ROOT_URLCONF = 'mcp_server.urls'

# ═══════════════════════════════════════════════════
# DATABASE — Shared storage for Tasks extension
# ═══════════════════════════════════════════════════
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# ═══════════════════════════════════════════════════
# INTERNATIONALIZATION
# ═══════════════════════════════════════════════════
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# ═══════════════════════════════════════════════════
# STATIC FILES
# ═══════════════════════════════════════════════════
STATIC_URL = 'static/'

# ═══════════════════════════════════════════════════
# DEFAULT PRIMARY KEY
# ═══════════════════════════════════════════════════
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ═══════════════════════════════════════════════════
# MCP 2026 PROTOCOL CONFIGURATION
# ═══════════════════════════════════════════════════
MCP_PROTOCOL_VERSION = '2026-07-28'
MCP_PROTOCOL_VERSIONS_SUPPORTED = ['2026-07-28', '2026-07-28-draft']
MCP_SERVER_NAME = 'mcp-stateless-django'
MCP_SERVER_VERSION = '1.0.0'

MCP_SERVER_CAPABILITIES = {
    "tools": {"listChanged": False},
    "resources": {"listChanged": False, "subscribe": False},
    "tasks": {},
    "stateless": True,
}

# ═══════════════════════════════════════════════════
# WEB SEARCH CONFIGURATION
# ═══════════════════════════════════════════════════
WEB_SEARCH_BACKEND = os.environ.get('WEB_SEARCH_BACKEND', 'mock')
WEB_SEARCH_API_KEY = os.environ.get('WEB_SEARCH_API_KEY', '')
WEB_SEARCH_MAX_RESULTS = int(os.environ.get('WEB_SEARCH_MAX_RESULTS', '5'))

# ═══════════════════════════════════════════════════
# AUTHENTICATION
# ═══════════════════════════════════════════════════
MCP_API_KEY = os.environ.get('MCP_API_KEY', 'dev-api-key-change-me')

# ═══════════════════════════════════════════════════
# CACHE TTL
# ═══════════════════════════════════════════════════
MCP_LIST_CACHE_TTL = 300000   # 5 minutes in ms
MCP_RESOURCE_CACHE_TTL = 600000  # 10 minutes in ms
