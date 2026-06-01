"""
Stateless Authentication — API Key in Header
No session cookies. No session IDs. 
Every request: "Yeh lo API key, yeh lo kaam karo."
"""
from django.conf import settings
from rest_framework import authentication, exceptions
from django.contrib.auth.models import AnonymousUser

class StatelessUser(AnonymousUser):
    """A user-like object that doesn't need a session."""
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    def __str__(self):
        return "stateless_user"

class APIKeyAuthentication(authentication.BaseAuthentication):
    """
    Stateless auth: API Key must be sent in EVERY request.
    Header: X-API-Key: <your-key>
    No session store. No "remember me". Each request is independent.
    """
    def authenticate(self, request):
        api_key = request.headers.get('X-API-Key')

        if not api_key:
            raise exceptions.AuthenticationFailed(
                'X-API-Key header missing. Har request mein bhejo!'
            )

        # In production: check against DB / Redis / Vault
        expected_key = getattr(settings, 'STATELESS_API_KEY', None)

        if api_key != expected_key:
            raise exceptions.AuthenticationFailed('Invalid API Key.')

        # Return user-like object + None (no auth token needed)
        return (StatelessUser(), None)
