"""GitHub webhook HTTP boundary."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import HttpRequest, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from adapters.github.runtime import get_github_provider
from apps.web.changes.webhooks import (
    MAX_WEBHOOK_BYTES,
    WebhookError,
    WebhookPayloadTooLargeError,
    ingest_webhook,
    verify_webhook,
)
from packages.github_contracts import GitHubProviderError


def _error(code: str, message: str, status: int) -> JsonResponse:
    return JsonResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "correlation_id": str(uuid.uuid4()),
                "details": {},
            }
        },
        status=status,
    )


@csrf_exempt
@require_POST
def github_webhook(request: HttpRequest) -> JsonResponse:
    content_type = request.headers.get("Content-Type", "").split(";", maxsplit=1)[0].strip()
    if content_type != "application/json":
        return _error("unsupported_media_type", "Content-Type must be application/json", 415)
    content_length = request.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > MAX_WEBHOOK_BYTES:
                raise WebhookPayloadTooLargeError("webhook body exceeds the configured limit")
        except ValueError:
            return _error("invalid_content_length", "Content-Length is invalid", 400)
        except WebhookPayloadTooLargeError as error:
            return _error(error.code, str(error), error.status_code)
    try:
        body = request.body
    except RequestDataTooBig:
        return _error("payload_too_large", "webhook body exceeds the configured limit", 413)
    try:
        webhook = verify_webhook(
            body=body,
            signature_header=request.headers.get("X-Hub-Signature-256", ""),
            delivery_id=request.headers.get("X-GitHub-Delivery", ""),
            event_name=request.headers.get("X-GitHub-Event", ""),
            secret=settings.GITHUB_WEBHOOK_SECRET,
        )
        result = ingest_webhook(webhook=webhook, provider=get_github_provider())
    except WebhookError as error:
        return _error(error.code, str(error), error.status_code)
    except GitHubProviderError:
        return _error("github_unavailable", "GitHub snapshot provider is unavailable", 503)
    return JsonResponse(
        {
            "status": result.status,
            "delivery_id": result.delivery_id,
            "receipt_id": str(result.receipt_id),
            "job_id": str(result.job_id) if result.job_id else None,
            "snapshot_id": str(result.snapshot_id) if result.snapshot_id else None,
        },
        status=200 if result.status == "deduplicated" else 202,
    )
