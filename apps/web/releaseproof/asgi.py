"""ASGI config for ReleaseProof."""

from __future__ import annotations

import os

from django.core.asgi import get_asgi_application

from packages.observability.telemetry import instrument_django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apps.web.releaseproof.settings.production")
instrument_django()

application = get_asgi_application()
