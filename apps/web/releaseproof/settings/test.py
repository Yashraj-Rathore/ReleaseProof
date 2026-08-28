"""Fast deterministic test settings; integration tests opt into real services."""

from apps.web.releaseproof.settings.base import *  # noqa: F403

SECRET_KEY = "releaseproof-test-key-not-for-production"  # noqa: S105
DEBUG = False
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
GITHUB_WEBHOOK_SECRET = "releaseproof-test-webhook-secret"  # noqa: S105
