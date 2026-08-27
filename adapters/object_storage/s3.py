"""Boto3 implementation of ReleaseProof's deliberately bounded S3 subset."""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from packages.domain.object_storage import (
    MAX_OBJECT_SIZE_BYTES,
    ObjectChecksumMismatchError,
    ObjectConflictError,
    ObjectNotFoundError,
    ObjectStorageUnavailableError,
    StoredObjectMetadata,
    validate_object_input,
    validate_storage_key,
)

_BUCKET_PATTERN = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")


def _required_environment(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _environment_bool(name: str, *, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True, slots=True)
class S3Settings:
    endpoint_url: str
    bucket: str
    access_key_id: str = field(repr=False)
    secret_access_key: str = field(repr=False)
    region: str = "us-east-1"
    force_path_style: bool = True
    connect_timeout_seconds: int = 2
    read_timeout_seconds: int = 5

    def __post_init__(self) -> None:
        endpoint = urlparse(self.endpoint_url)
        if (
            endpoint.scheme not in {"http", "https"}
            or not endpoint.hostname
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
            or endpoint.path not in {"", "/"}
        ):
            raise ValueError("S3 endpoint must be an absolute HTTP(S) URL")
        if (
            not _BUCKET_PATTERN.fullmatch(self.bucket)
            or ".." in self.bucket
            or ".-" in self.bucket
            or "-." in self.bucket
        ):
            raise ValueError("S3 bucket must be a normalized DNS-style name")
        if not self.access_key_id or not self.secret_access_key or not self.region:
            raise ValueError("S3 credentials and region cannot be empty")
        if self.connect_timeout_seconds < 1 or self.read_timeout_seconds < 1:
            raise ValueError("S3 timeouts must be positive")

    @classmethod
    def from_environment(cls) -> S3Settings:
        return cls(
            endpoint_url=_required_environment("S3_ENDPOINT_URL"),
            bucket=_required_environment("S3_BUCKET"),
            access_key_id=_required_environment("S3_ACCESS_KEY_ID"),
            secret_access_key=_required_environment("S3_SECRET_ACCESS_KEY"),
            region=_required_environment("S3_REGION"),
            force_path_style=_environment_bool("S3_FORCE_PATH_STYLE", default=True),
        )


def _error_code(error: ClientError) -> str:
    response: Any = error.response
    return str(response.get("Error", {}).get("Code", ""))


def _is_missing(error: ClientError) -> bool:
    return _error_code(error) in {"404", "NoSuchBucket", "NoSuchKey", "NotFound"}


class S3ObjectStorage:
    def __init__(self, settings: S3Settings) -> None:
        self._settings = settings
        addressing_style = "path" if settings.force_path_style else "virtual"
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.endpoint_url,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            region_name=settings.region,
            config=Config(
                signature_version="s3v4",
                connect_timeout=settings.connect_timeout_seconds,
                read_timeout=settings.read_timeout_seconds,
                retries={"max_attempts": 2, "mode": "standard"},
                s3={"addressing_style": addressing_style},
            ),
        )

    def ensure_bucket(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._settings.bucket)
            return
        except ClientError as error:
            if not _is_missing(error):
                raise ObjectStorageUnavailableError("S3 bucket readiness check failed") from error
        except BotoCoreError as error:
            raise ObjectStorageUnavailableError("S3 bucket readiness check failed") from error

        create_arguments: dict[str, object] = {"Bucket": self._settings.bucket}
        if self._settings.region != "us-east-1":
            create_arguments["CreateBucketConfiguration"] = {
                "LocationConstraint": self._settings.region
            }
        try:
            self._client.create_bucket(**create_arguments)
            self._client.head_bucket(Bucket=self._settings.bucket)
        except ClientError as error:
            if _error_code(error) != "BucketAlreadyOwnedByYou":
                raise ObjectStorageUnavailableError("S3 bucket bootstrap failed") from error
        except BotoCoreError as error:
            raise ObjectStorageUnavailableError("S3 bucket bootstrap failed") from error

    def put(self, key: str, data: bytes, *, content_type: str, sha256: str) -> StoredObjectMetadata:
        validate_storage_key(key)
        validate_object_input(data, content_type, sha256)
        if hashlib.sha256(data).hexdigest() != sha256:
            raise ObjectChecksumMismatchError("supplied object checksum does not match bytes")
        expected = StoredObjectMetadata(
            key=key, size=len(data), content_type=content_type, sha256=sha256
        )
        try:
            existing = self.head(key)
        except ObjectNotFoundError:
            existing = None
        if existing is not None:
            if existing == expected:
                return existing
            raise ObjectConflictError("immutable object key already contains different metadata")

        try:
            self._client.put_object(
                Bucket=self._settings.bucket,
                Key=key,
                Body=data,
                ContentLength=len(data),
                ContentType=content_type,
                IfNoneMatch="*",
                Metadata={"sha256": sha256},
            )
        except ClientError as error:
            if _error_code(error) in {"412", "ConditionalRequestConflict", "PreconditionFailed"}:
                concurrent = self.head(key)
                if concurrent == expected:
                    return concurrent
                raise ObjectConflictError(
                    "immutable object key was created concurrently with different metadata"
                ) from error
            raise ObjectStorageUnavailableError("S3 put failed") from error
        except BotoCoreError as error:
            raise ObjectStorageUnavailableError("S3 put failed") from error
        return self.head(key)

    def head(self, key: str) -> StoredObjectMetadata:
        validate_storage_key(key)
        try:
            response: Any = self._client.head_object(Bucket=self._settings.bucket, Key=key)
        except ClientError as error:
            if _is_missing(error):
                raise ObjectNotFoundError("object does not exist") from error
            raise ObjectStorageUnavailableError("S3 head failed") from error
        except BotoCoreError as error:
            raise ObjectStorageUnavailableError("S3 head failed") from error
        checksum = str(response.get("Metadata", {}).get("sha256", ""))
        if len(checksum) != 64:
            raise ObjectChecksumMismatchError("S3 object is missing ReleaseProof SHA-256 metadata")
        try:
            return StoredObjectMetadata(
                key=key,
                size=int(response["ContentLength"]),
                content_type=str(response["ContentType"]),
                sha256=checksum,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ObjectStorageUnavailableError("S3 head returned invalid metadata") from error

    def get(self, key: str) -> bytes:
        metadata = self.head(key)
        try:
            response: Any = self._client.get_object(Bucket=self._settings.bucket, Key=key)
            body: Any = response["Body"]
            try:
                data = bytes(body.read(MAX_OBJECT_SIZE_BYTES + 1))
            finally:
                body.close()
        except ClientError as error:
            if _is_missing(error):
                raise ObjectNotFoundError("object does not exist") from error
            raise ObjectStorageUnavailableError("S3 get failed") from error
        except (BotoCoreError, KeyError, TypeError) as error:
            raise ObjectStorageUnavailableError("S3 get returned an invalid response") from error
        if len(data) != metadata.size or hashlib.sha256(data).hexdigest() != metadata.sha256:
            raise ObjectChecksumMismatchError(
                "downloaded S3 bytes do not match authoritative metadata"
            )
        return data

    def delete(self, key: str) -> None:
        validate_storage_key(key)
        try:
            self._client.delete_object(Bucket=self._settings.bucket, Key=key)
        except (BotoCoreError, ClientError) as error:
            raise ObjectStorageUnavailableError("S3 delete failed") from error
