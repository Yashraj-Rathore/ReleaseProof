from __future__ import annotations

from unittest.mock import patch

import pytest
from django.db import DatabaseError
from django.test import Client


def test_liveness_does_not_probe_external_dependencies(client: Client) -> None:
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.django_db
def test_readiness_probes_authoritative_database(client: Client) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_readiness_fails_closed_without_exposing_database_details(client: Client) -> None:
    with patch("apps.web.releaseproof.health.connection.cursor", side_effect=DatabaseError):
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable"}
