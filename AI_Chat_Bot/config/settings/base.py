"""
Base settings for MCP Server – shared between environments.
"""

import os
from pathlib import Path

# -------------------------------------------------------------------
# Paths & Core
# -------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Secrets are loaded from environment – no defaults in production!
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY')
DEBUG = False  # Must be explicitly set to True in development

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', '').split(',')

# -------------------------------------------------------------------
# Installed Apps – stateless, no admin, no auth, no sessions
# -------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.staticfiles',
    'apps.stateless',
]

# -------------------------------------------------------------------
# Middleware – no session, no CSRF, no authentication
# -------------------------------------------------------------------
MIDDLEWARE = [
    'apps.stateless.middleware.MCPStatelessMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

# -------------------------------------------------------------------
# Templates
# -------------------------------------------------------------------
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

# -------------------------------------------------------------------
# Database – can be overridden by environment (e.g. DATABASE_URL)
# -------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'stateless_shared.sqlite3',
    }
}

# -------------------------------------------------------------------
# Sessions – explicitly disabled
# -------------------------------------------------------------------
SESSION_ENGINE = None

# -------------------------------------------------------------------
# Internationalization
# -------------------------------------------------------------------
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# -------------------------------------------------------------------
# Static & Media Files
# -------------------------------------------------------------------
STATIC_URL = 'static/'

MEDIA_ROOT = BASE_DIR / 'media'
MEDIA_URL = '/media/'

# -------------------------------------------------------------------
# File Storage – local filesystem (Django 4.2+)
# -------------------------------------------------------------------
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
# MEDIA_ROOT = BASE_DIR / "media"
# MEDIA_URL = "/media/"

# -------------------------------------------------------------------
# MCP Protocol Configuration
# -------------------------------------------------------------------
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

# Stateless Authentication: API Key
MCP_API_KEY = os.getenv('MCP_API_KEY', '')

# Web Search Service Configuration
WEB_SEARCH_BACKEND = os.getenv('WEB_SEARCH_BACKEND', 'mock')
WEB_SEARCH_API_KEY = os.getenv('WEB_SEARCH_API_KEY', '')
WEB_SEARCH_MAX_RESULTS = int(os.getenv('WEB_SEARCH_MAX_RESULTS', '5'))

# Caching metadata (milliseconds)
MCP_LIST_CACHE_TTL = 300000
MCP_RESOURCE_CACHE_TTL = 600000