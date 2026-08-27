"""WSGI config for ReleaseProof."""

from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apps.web.releaseproof.settings.production")

application = get_wsgi_application()
