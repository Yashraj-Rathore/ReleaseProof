"""Fail-closed production settings."""

import os

from django.core.exceptions import ImproperlyConfigured

from apps.web.releaseproof.settings.base import *  # noqa: F403
from apps.web.releaseproof.settings.base import LOCAL_SECRET_KEY, env_list

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
if not SECRET_KEY or SECRET_KEY == LOCAL_SECRET_KEY or len(SECRET_KEY) < 32:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be a non-local value of at least 32 characters"
    )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS is required")

DEBUG = False
if len(GITHUB_WEBHOOK_SECRET) < 32:  # noqa: F405
    raise ImproperlyConfigured("GITHUB_WEBHOOK_SECRET must contain at least 32 characters")
if not GITHUB_APP_CREDENTIAL_REFERENCE:  # noqa: F405
    raise ImproperlyConfigured("GITHUB_APP_CREDENTIAL_REFERENCE is required")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
