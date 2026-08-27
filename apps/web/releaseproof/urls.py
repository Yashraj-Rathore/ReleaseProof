"""Root URL configuration."""

from __future__ import annotations

from django.urls import path

from apps.web.releaseproof import health

urlpatterns = [
    path("health/live", health.live, name="health-live"),
    path("health/ready", health.ready, name="health-ready"),
]
