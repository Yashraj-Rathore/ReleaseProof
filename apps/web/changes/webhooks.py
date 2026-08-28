"""Signed, bounded and transactionally durable GitHub webhook ingestion."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import uuid
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404
from django.utils import timezone

from apps.web.analysis.models import AnalysisJob, JobType
from apps.web.analysis.services import create_job_with_outbox
from apps.web.audit.services import record_audit
from apps.web.changes.models import PullRequestSnapshot, WebhookReceipt
from apps.web.repositories.models import (
    GitHubInstallation,
    InstallationLifecycle,
    Repository,
    RepositoryLifecycle,
)
from apps.web.repositories.services import bind_repository, get_installation_by_github_id
from packages.github_contracts import GitHubProvider
from packages.github_contracts import PullRequestSnapshot as ProviderSnapshot

MAX_WEBHOOK_BYTES = 1_048_576
MAX_JSON_DEPTH = 20
MAX_JSON_NODES = 10_000
_DELIVERY_PATTERN = re.compile(r"^[A-Za-z0-9-]{1,100}$")
_EVENT_PATTERN = re.compile(r"^[a-z_]{1,64}$")
_SIGNATURE_PATTERN = re.compile(r"^sha256=([0-9a-f]{64})$")
_ALLOWED_ACTIONS = {
    "pull_request": {"opened", "synchronize", "reopened"},
    "installation": {"created", "deleted", "suspend", "unsuspend"},
    "installation_repositories": {"added", "removed"},
}


class WebhookError(RuntimeError):
    code = "invalid_webhook"
    status_code = 400


class WebhookSignatureError(WebhookError):
    code = "invalid_signature"
    status_code = 401


class WebhookPayloadTooLargeError(WebhookError):
    code = "payload_too_large"
    status_code = 413


class WebhookUnsupportedError(WebhookError):
    code = "unsupported_event"
    status_code = 400


class WebhookTenantNotFoundError(WebhookError):
    code = "installation_not_found"
    status_code = 404


class WebhookConflictError(WebhookError):
    code = "delivery_conflict"
    status_code = 409


@dataclass(frozen=True, slots=True)
class VerifiedWebhook:
    delivery_id: str
    event_name: str
    action: str
    installation_id: int
    payload: dict[str, Any]
    payload_sha256: str
    payload_size: int


@dataclass(frozen=True, slots=True)
class IngestionResult:
    status: str
    delivery_id: str
    receipt_id: uuid.UUID
    job_id: uuid.UUID | None
    snapshot_id: uuid.UUID | None


def _validate_json_shape(value: object, *, depth: int = 0) -> int:
    if depth > MAX_JSON_DEPTH:
        raise WebhookError("JSON nesting exceeds the webhook limit")
    if isinstance(value, dict):
        nodes = 1
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 256:
                raise WebhookError("JSON object key is invalid")
            nodes += _validate_json_shape(item, depth=depth + 1)
            if nodes > MAX_JSON_NODES:
                raise WebhookError("JSON node count exceeds the webhook limit")
        return nodes
    if isinstance(value, list):
        nodes = 1
        for item in value:
            nodes += _validate_json_shape(item, depth=depth + 1)
            if nodes > MAX_JSON_NODES:
                raise WebhookError("JSON node count exceeds the webhook limit")
        return nodes
    if value is None or isinstance(value, (str, int, float, bool)):
        return 1
    raise WebhookError("JSON value type is invalid")


def _mapping(value: object, *, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WebhookError(f"{field} must be an object")
    return value


def _positive_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise WebhookError(f"{field} must be a positive integer")
    return value


def verify_webhook(
    *,
    body: bytes,
    signature_header: str,
    delivery_id: str,
    event_name: str,
    secret: str,
) -> VerifiedWebhook:
    if len(body) > MAX_WEBHOOK_BYTES:
        raise WebhookPayloadTooLargeError("webhook body exceeds the configured limit")
    if not secret or len(secret) < 16:
        raise WebhookSignatureError("webhook verification is unavailable")
    signature_match = _SIGNATURE_PATTERN.fullmatch(signature_header)
    if signature_match is None:
        raise WebhookSignatureError("signature header is invalid")
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature_match.group(1)):
        raise WebhookSignatureError("signature does not match")
    if not _DELIVERY_PATTERN.fullmatch(delivery_id):
        raise WebhookError("delivery header is invalid")
    if not _EVENT_PATTERN.fullmatch(event_name):
        raise WebhookError("event header is invalid")
    try:
        decoded = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise WebhookError("webhook body must be valid UTF-8 JSON") from error
    _validate_json_shape(decoded)
    payload = _mapping(decoded, field="payload")
    action = payload.get("action")
    if not isinstance(action, str) or action not in _ALLOWED_ACTIONS.get(event_name, set()):
        raise WebhookUnsupportedError("event/action is not allowlisted")
    installation = _mapping(payload.get("installation"), field="installation")
    installation_id = _positive_int(installation.get("id"), field="installation.id")
    return VerifiedWebhook(
        delivery_id=delivery_id,
        event_name=event_name,
        action=action,
        installation_id=installation_id,
        payload=payload,
        payload_sha256=hashlib.sha256(body).hexdigest(),
        payload_size=len(body),
    )


def _existing_result(webhook: VerifiedWebhook) -> IngestionResult | None:
    """Audited global lookup: GitHub delivery IDs are globally unique and signed."""

    receipt = WebhookReceipt.objects.filter(delivery_id=webhook.delivery_id).first()
    if receipt is None:
        return None
    if receipt.payload_sha256 != webhook.payload_sha256:
        raise WebhookConflictError("delivery ID was reused with a different payload")
    job = (
        AnalysisJob.objects.for_organization(receipt.organization)
        .filter(correlation_id=receipt.correlation_id)
        .first()
    )
    snapshot = PullRequestSnapshot.objects.filter(
        organization=receipt.organization,
        first_receipt=receipt,
    ).first()
    return IngestionResult(
        status="deduplicated",
        delivery_id=receipt.delivery_id,
        receipt_id=receipt.public_id,
        job_id=job.public_id if job else None,
        snapshot_id=snapshot.public_id if snapshot else None,
    )


def _new_receipt(
    webhook: VerifiedWebhook,
    installation: GitHubInstallation,
) -> WebhookReceipt:
    receipt = WebhookReceipt(
        organization=installation.organization,
        installation=installation,
        delivery_id=webhook.delivery_id,
        event_name=webhook.event_name,
        action=webhook.action,
        payload_sha256=webhook.payload_sha256,
        payload_size=webhook.payload_size,
    )
    receipt.full_clean()
    receipt.save()
    return receipt


def _serialize_changed_files(snapshot: ProviderSnapshot) -> list[dict[str, object]]:
    return [
        {
            "path": item.path,
            "additions": item.additions,
            "deletions": item.deletions,
            "status": item.status,
            "previous_path": item.previous_path,
            "patch": item.patch,
        }
        for item in snapshot.changed_files
    ]


def _serialize_checks(snapshot: ProviderSnapshot) -> list[dict[str, str | None]]:
    return [
        {"name": item.name, "status": item.status, "conclusion": item.conclusion}
        for item in snapshot.checks
    ]


def _snapshot_checksum(snapshot: ProviderSnapshot) -> str:
    normalized = {
        "base_ref": snapshot.base_ref,
        "base_sha": snapshot.base_sha,
        "author_key": snapshot.author_key,
        "body": snapshot.body,
        "changed_files": _serialize_changed_files(snapshot),
        "checks": _serialize_checks(snapshot),
        "commit_count": snapshot.commit_count,
        "head_ref": snapshot.head_ref,
        "head_sha": snapshot.head_sha,
        "number": snapshot.number,
        "repository": snapshot.repository,
        "repository_id": snapshot.repository_id,
        "schema_version": PullRequestSnapshot.SCHEMA_VERSION,
        "title": snapshot.title,
    }
    encoded = json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ingest_pull_request(
    *,
    webhook: VerifiedWebhook,
    installation: GitHubInstallation,
    provider: GitHubProvider,
) -> IngestionResult:
    repository_payload = _mapping(webhook.payload.get("repository"), field="repository")
    repository_id = _positive_int(repository_payload.get("id"), field="repository.id")
    full_name = repository_payload.get("full_name")
    if not isinstance(full_name, str) or len(full_name) > 201:
        raise WebhookError("repository.full_name is invalid")
    pull_request = _mapping(webhook.payload.get("pull_request"), field="pull_request")
    number = _positive_int(pull_request.get("number"), field="pull_request.number")
    try:
        repository = (
            Repository.objects.active()
            .for_organization(installation.organization)
            .get(
                installation=installation,
                github_repository_id=repository_id,
            )
        )
    except Repository.DoesNotExist as error:
        raise WebhookTenantNotFoundError("repository binding not found") from error
    if repository.full_name != full_name:
        raise WebhookConflictError("repository identity does not match its server binding")

    provider_snapshot = provider.get_pull_request(
        repository.full_name,
        number,
        installation_id=installation.github_installation_id,
    )
    if provider_snapshot.repository != repository.full_name or provider_snapshot.number != number:
        raise WebhookConflictError("provider snapshot identity does not match the webhook")
    if provider_snapshot.repository_id not in {None, repository.github_repository_id}:
        raise WebhookConflictError("provider repository ID does not match the server binding")
    checksum = _snapshot_checksum(provider_snapshot)

    with transaction.atomic():
        duplicate = _existing_result(webhook)
        if duplicate is not None:
            return duplicate
        receipt = _new_receipt(webhook, installation)
        existing_snapshot = PullRequestSnapshot.objects.filter(
            organization=installation.organization,
            repository=repository,
            pull_request_number=number,
            base_sha=provider_snapshot.base_sha,
            head_sha=provider_snapshot.head_sha,
            schema_version=PullRequestSnapshot.SCHEMA_VERSION,
        ).first()
        if existing_snapshot is not None and existing_snapshot.snapshot_checksum != checksum:
            raise WebhookConflictError("immutable snapshot identity has conflicting content")
        if existing_snapshot is None:
            snapshot = PullRequestSnapshot(
                organization=installation.organization,
                repository=repository,
                first_receipt=receipt,
                pull_request_number=number,
                title=provider_snapshot.title,
                body=provider_snapshot.body,
                base_ref=provider_snapshot.base_ref,
                head_ref=provider_snapshot.head_ref,
                base_sha=provider_snapshot.base_sha,
                head_sha=provider_snapshot.head_sha,
                author_key=provider_snapshot.author_key,
                commit_count=provider_snapshot.commit_count,
                changed_files=_serialize_changed_files(provider_snapshot),
                checks=_serialize_checks(provider_snapshot),
                snapshot_checksum=checksum,
            )
            snapshot.full_clean()
            snapshot.save()
        else:
            snapshot = existing_snapshot
        job, _ = create_job_with_outbox(
            organization=installation.organization,
            job_type=JobType.PULL_REQUEST_SNAPSHOT,
            idempotency_key=f"snapshot:{snapshot.snapshot_checksum}",
            correlation_id=receipt.correlation_id,
            snapshot=snapshot,
        )
        record_audit(
            organization=installation.organization,
            action="github.pull_request.accepted",
            resource_type="pull_request_snapshot",
            resource_public_id=snapshot.public_id,
            correlation_id=receipt.correlation_id,
            metadata={"event": webhook.event_name, "action": webhook.action},
        )
        return IngestionResult(
            status="accepted",
            delivery_id=receipt.delivery_id,
            receipt_id=receipt.public_id,
            job_id=job.public_id,
            snapshot_id=snapshot.public_id,
        )


def _ingest_installation_lifecycle(
    *,
    webhook: VerifiedWebhook,
    installation: GitHubInstallation,
) -> IngestionResult:
    with transaction.atomic():
        duplicate = _existing_result(webhook)
        if duplicate is not None:
            return duplicate
        receipt = _new_receipt(webhook, installation)
        if webhook.action in {"created", "unsuspend"}:
            installation.lifecycle = InstallationLifecycle.ACTIVE
            installation.revoked_at = None
        elif webhook.action == "suspend":
            installation.lifecycle = InstallationLifecycle.SUSPENDED
        else:
            installation.lifecycle = InstallationLifecycle.REVOKED
            installation.revoked_at = timezone.now()
        installation.save(update_fields=("lifecycle", "revoked_at", "updated_at"))
        job, _ = create_job_with_outbox(
            organization=installation.organization,
            job_type=JobType.INSTALLATION_LIFECYCLE,
            idempotency_key=f"delivery:{receipt.delivery_id}",
            correlation_id=receipt.correlation_id,
        )
        record_audit(
            organization=installation.organization,
            action=f"github.installation.{webhook.action}",
            resource_type="github_installation",
            resource_public_id=installation.public_id,
            correlation_id=receipt.correlation_id,
        )
        return IngestionResult(
            "accepted", receipt.delivery_id, receipt.public_id, job.public_id, None
        )


def _repository_items(payload: dict[str, Any], action: str) -> list[dict[str, Any]]:
    key = "repositories_added" if action == "added" else "repositories_removed"
    value = payload.get(key)
    if not isinstance(value, list) or len(value) > 100:
        raise WebhookError("repository lifecycle list is invalid")
    return [_mapping(item, field=key) for item in value]


def _ingest_repository_lifecycle(
    *,
    webhook: VerifiedWebhook,
    installation: GitHubInstallation,
) -> IngestionResult:
    items = _repository_items(webhook.payload, webhook.action)
    with transaction.atomic():
        duplicate = _existing_result(webhook)
        if duplicate is not None:
            return duplicate
        receipt = _new_receipt(webhook, installation)
        for item in items:
            repository_id = _positive_int(item.get("id"), field="repository.id")
            full_name = item.get("full_name")
            if not isinstance(full_name, str) or full_name.count("/") != 1:
                raise WebhookError("repository.full_name is invalid")
            owner, name = full_name.split("/", maxsplit=1)
            if webhook.action == "added":
                try:
                    bind_repository(
                        organization=installation.organization,
                        installation=installation,
                        github_repository_id=repository_id,
                        owner=owner,
                        name=name,
                        default_branch=str(item.get("default_branch") or "main"),
                    )
                except ValidationError as error:
                    raise WebhookConflictError(
                        "repository binding conflicts with authoritative tenant state"
                    ) from error
            else:
                Repository.objects.for_organization(installation.organization).filter(
                    installation=installation,
                    github_repository_id=repository_id,
                ).update(lifecycle=RepositoryLifecycle.REMOVED)
        job, _ = create_job_with_outbox(
            organization=installation.organization,
            job_type=JobType.REPOSITORY_LIFECYCLE,
            idempotency_key=f"delivery:{receipt.delivery_id}",
            correlation_id=receipt.correlation_id,
        )
        record_audit(
            organization=installation.organization,
            action=f"github.repositories.{webhook.action}",
            resource_type="github_installation",
            resource_public_id=installation.public_id,
            correlation_id=receipt.correlation_id,
            metadata={"repository_count": len(items)},
        )
        return IngestionResult(
            "accepted", receipt.delivery_id, receipt.public_id, job.public_id, None
        )


def ingest_webhook(
    *,
    webhook: VerifiedWebhook,
    provider: GitHubProvider,
) -> IngestionResult:
    duplicate = _existing_result(webhook)
    if duplicate is not None:
        return duplicate
    try:
        installation = get_installation_by_github_id(webhook.installation_id)
    except Http404 as error:
        raise WebhookTenantNotFoundError("installation binding not found") from error
    try:
        if webhook.event_name == "pull_request":
            if installation.lifecycle != InstallationLifecycle.ACTIVE:
                raise WebhookTenantNotFoundError("installation is not active")
            return _ingest_pull_request(
                webhook=webhook,
                installation=installation,
                provider=provider,
            )
        if webhook.event_name == "installation":
            return _ingest_installation_lifecycle(
                webhook=webhook,
                installation=installation,
            )
        return _ingest_repository_lifecycle(
            webhook=webhook,
            installation=installation,
        )
    except IntegrityError:
        duplicate = _existing_result(webhook)
        if duplicate is not None:
            return duplicate
        raise
