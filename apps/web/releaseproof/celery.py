"""Celery application; PostgreSQL remains authoritative for product job state."""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "apps.web.releaseproof.settings.production")

app = Celery("releaseproof")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
