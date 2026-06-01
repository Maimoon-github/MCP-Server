"""
Stateless Django Settings for MCP 2026-07-28 Server.
NO sessions. NO session middleware. NO CSRF for API.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'stateless-mcp-2026-secret')
DEBUG = os.getenv('DEBUG', 'True').lower() == 'true'
ALLOWED_HOSTS = ['*']

# ───────────────────────────────────────────────
# STATELESS CORE: Minimal apps, NO sessions, NO messages, NO admin
# ───────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'apps.mcp_server',
]

# STATELESS CORE: No SessionMiddleware, no AuthenticationMiddleware, no CsrfViewMiddleware
MIDDLEWARE = [
    'apps.mcp_server.middleware.MCPProtocolMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
            ],
        },
    },
]

# Shared database for tasks/resources only — NOT for session storage
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'stateless_shared.sqlite3',
    }
}

# EXPLICITLY DISABLE SESSIONS
SESSION_ENGINE = None

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ───────────────────────────────────────────────
# MCP 2026-07-28 STATELESS CONFIGURATION
# ───────────────────────────────────────────────
MCP_PROTOCOL_VERSION = "2026-07-28"
MCP_PROTOCOL_VERSIONS_SUPPORTED = ["2026-07-28", "2025-11-25"]
MCP_SERVER_NAME = "ai-chat-bot-mcp"
MCP_SERVER_VERSION = "1.0.0"
MCP_SERVER_CAPABILITIES = {
    "tools": {"listChanged": True},
    "resources": {"listChanged": True, "subscribe": False},
    "prompts": {"listChanged": False},
    "tasks": {},
}

# Stateless Authentication: API Key via Authorization or X-Api-Key header
MCP_API_KEY = os.getenv('MCP_API_KEY', 'mcp-dev-key-2026')

# Web Search Service Configuration
WEB_SEARCH_BACKEND = os.getenv('WEB_SEARCH_BACKEND', 'mock')
WEB_SEARCH_API_KEY = os.getenv('WEB_SEARCH_API_KEY', '')
WEB_SEARCH_MAX_RESULTS = int(os.getenv('WEB_SEARCH_MAX_RESULTS', '5'))

# Caching metadata for stateless list responses (milliseconds)
MCP_LIST_CACHE_TTL = 300000
MCP_RESOURCE_CACHE_TTL = 600000