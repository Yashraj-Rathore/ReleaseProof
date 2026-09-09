"""Tenant-scoped M14 operational-policy and retention endpoints."""

from __future__ import annotations

import uuid
from typing import cast

from django.contrib.auth.models import AbstractBaseUser
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.web.organizations.models import MembershipRole, Organization
from apps.web.organizations.operational_services import (
    OperationalPolicyError,
    RetentionWorkflowError,
    S3ArtifactPurger,
    create_operational_policy,
    create_retention_deletion_plan,
    execute_retention_deletion_plan,
    resolve_operational_policy,
)
from apps.web.organizations.services import require_minimum_role
from apps.web.organizations.views import active_organization


def _operator(request: Request) -> tuple[Organization, AbstractBaseUser]:
    organization = active_organization(request._request)
    require_minimum_role(
        user=request.user,
        organization=organization,
        minimum_role=MembershipRole.ADMIN,
    )
    return organization, cast(AbstractBaseUser, request.user)


class OperationalPolicyView(APIView):  # type: ignore[misc]
    def get(self, request: Request) -> Response:
        organization = active_organization(request._request)
        policy = resolve_operational_policy(organization=organization)
        return Response(
            {
                "schema_version": policy.schema_version,
                "version": policy.version,
                "policy_sha256": policy.policy_sha256,
                "quota_limits": dict(policy.quota_limits),
                "retention_days": dict(policy.retention_days),
                "persisted": policy.record is not None,
            }
        )

    def post(self, request: Request) -> Response:
        organization, actor = _operator(request)
        if not isinstance(request.data, dict) or set(request.data) != {
            "quota_limits",
            "retention_days",
        }:
            raise ValidationError("exact quota_limits and retention_days are required")
        try:
            policy = create_operational_policy(
                organization=organization,
                actor=actor,
                quota_limits=request.data["quota_limits"],
                retention_days=request.data["retention_days"],
            )
        except (OperationalPolicyError, TypeError, ValueError) as error:
            raise ValidationError("operational policy is invalid") from error
        return Response(
            {
                "id": str(policy.public_id),
                "schema_version": policy.schema_version,
                "version": policy.version,
                "policy_sha256": policy.policy_sha256,
            },
            status=201,
        )


class RetentionPlanView(APIView):  # type: ignore[misc]
    def post(self, request: Request) -> Response:
        organization, actor = _operator(request)
        if not isinstance(request.data, dict) or not set(request.data).issubset({"dry_run"}):
            raise ValidationError("retention plan request is invalid")
        dry_run = request.data.get("dry_run", True)
        if not isinstance(dry_run, bool):
            raise ValidationError("dry_run must be a boolean")
        plan = create_retention_deletion_plan(
            organization=organization,
            actor=actor,
            dry_run=dry_run,
        )
        return Response(
            {
                "id": str(plan.public_id),
                "dry_run": plan.dry_run,
                "policy_sha256": plan.policy.policy_sha256,
                "candidate_counts": {
                    key: len(items) for key, items in plan.candidate_public_ids.items()
                },
                "plan_sha256": plan.plan_sha256,
            },
            status=201,
        )


class RetentionExecuteView(APIView):  # type: ignore[misc]
    def post(self, request: Request, public_id: uuid.UUID) -> Response:
        organization, actor = _operator(request)
        if request.data not in ({}, None):
            raise ValidationError("retention execution request must be empty")
        try:
            purger = S3ArtifactPurger()
        except ValueError:
            purger = None
        try:
            result = execute_retention_deletion_plan(
                organization=organization,
                plan_public_id=public_id,
                actor=actor,
                artifact_purger=purger,
            )
        except RetentionWorkflowError as error:
            raise ValidationError("retention plan cannot be executed") from error
        return Response(
            {
                "id": str(result.execution.public_id),
                "created": result.created,
                "deleted_counts": result.execution.deleted_counts,
                "blocked_counts": result.execution.blocked_counts,
                "result_sha256": result.execution.result_sha256,
            }
        )
