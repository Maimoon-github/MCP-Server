"""
Development settings – debug on, local SQLite, relaxed security.
"""

from .base import *

# -------------------------------------------------------------------
# Debug & Hosts
# -------------------------------------------------------------------
DEBUG = True
ALLOWED_HOSTS = ['*']  # Allow all hosts during development

# -------------------------------------------------------------------
# Secret key – fallback only for development (never in production)
# -------------------------------------------------------------------
if not SECRET_KEY:
    SECRET_KEY = 'django-insecure-dev-key-do-not-use-in-production'

# -------------------------------------------------------------------
# Database – keep SQLite (or use environment)
# -------------------------------------------------------------------
# No change – base SQLite is fine for development.

# -------------------------------------------------------------------
# Additional development tools (optional)
# -------------------------------------------------------------------
# Uncomment if you want Django Debug Toolbar or similar:
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
# INTERNAL_IPS = ['127.0.0.1']

# -------------------------------------------------------------------
# Email backend – console for development
# -------------------------------------------------------------------
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
}