"""Relay pending tenant-scoped outbox rows to Celery."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from adapters.tasks import CeleryTaskPublisher
from apps.web.analysis.services import relay_outbox_for_organization
from apps.web.organizations.models import Organization


class Command(BaseCommand):
    help = "Publish pending outbox work for one explicit organization"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--organization", required=True, help="Organization public UUID")
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args: Any, **options: Any) -> None:
        del args
        organization_id = str(options["organization"])
        limit = int(options["limit"])
        try:
            organization = Organization.objects.active().get(public_id=organization_id)
        except (Organization.DoesNotExist, ValueError) as error:
            raise CommandError("active organization not found") from error
        try:
            result = relay_outbox_for_organization(
                organization=organization,
                publisher=CeleryTaskPublisher(),
                limit=limit,
            )
        except ValueError as error:
            raise CommandError(str(error)) from error
        self.stdout.write(
            self.style.SUCCESS(f"published={result.published} failed={result.failed}")
        )
