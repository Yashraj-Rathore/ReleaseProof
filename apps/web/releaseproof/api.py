"""Safe DRF error envelopes without source/provider detail leakage."""

from __future__ import annotations

import uuid
from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler


def safe_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    response = exception_handler(exc, context)
    if response is None:
        return None
    status_code = int(response.status_code)
    code = {
        400: "invalid_request",
        401: "authentication_required",
        403: "permission_denied",
        404: "not_found",
        405: "method_not_allowed",
        429: "rate_limited",
    }.get(status_code, "request_failed")
    message = {
        400: "The request is invalid.",
        401: "Authentication is required.",
        403: "The requested action is not allowed.",
        404: "The requested resource was not found.",
        405: "The request method is not allowed.",
        429: "Too many requests.",
    }.get(status_code, "The request could not be completed.")
    response.data = {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": str(uuid.uuid4()),
            "details": {},
        }
    }
    return response
