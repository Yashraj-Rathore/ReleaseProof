"""Minimal liveness and PostgreSQL readiness endpoints."""

from __future__ import annotations

from django.db import DatabaseError, connection
from django.http import HttpRequest, JsonResponse


def live(_request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def ready(_request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ready"})
