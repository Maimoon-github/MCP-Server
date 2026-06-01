"""
Production settings – security focused, environment‑only secrets.
"""

from .base import *

# -------------------------------------------------------------------
# Debug must be False
# -------------------------------------------------------------------
DEBUG = False

# -------------------------------------------------------------------
# Allowed hosts – comma‑separated list from environment
# -------------------------------------------------------------------
if not ALLOWED_HOSTS or ALLOWED_HOSTS == ['']:
    raise ValueError("ALLOWED_HOSTS must be set in production environment")

# -------------------------------------------------------------------
# Secret key – required
# -------------------------------------------------------------------
if not SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY must be set in production")

# -------------------------------------------------------------------
# Security middleware and headers
# -------------------------------------------------------------------
# Add security middleware if not already present (order matters)
SECURITY_MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
]
for m in reversed(SECURITY_MIDDLEWARE):
    if m not in MIDDLEWARE:
        MIDDLEWARE.insert(0, m)

SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# -------------------------------------------------------------------
# Database – support optional PostgreSQL via DATABASE_URL
# -------------------------------------------------------------------
import dj_database_url  # Requires `pip install dj-database-url`
db_from_env = dj_database_url.config(conn_max_age=500)
if db_from_env:
    DATABASES['default'].update(db_from_env)

# -------------------------------------------------------------------
# Static & media – use WhiteNoise for static files (if desired)
# -------------------------------------------------------------------
# STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
# MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')

# -------------------------------------------------------------------
# Logging – minimal, to stdout
# -------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': os.getenv('DJANGO_LOG_LEVEL', 'INFO'),
            'propagate': False,
        },
    },
}