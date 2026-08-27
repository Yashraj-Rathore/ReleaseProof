from __future__ import annotations

import pytest

from adapters.object_storage import S3Settings


def test_s3_settings_hide_credentials_from_representation() -> None:
    settings = S3Settings(
        endpoint_url="http://localhost:8333",
        bucket="releaseproof-local",
        access_key_id="local-access-key",
        secret_access_key="local-secret-key",  # noqa: S106 - synthetic test credential
    )

    rendered = repr(settings)
    assert "local-access-key" not in rendered
    assert "local-secret-key" not in rendered


@pytest.mark.parametrize(
    ("endpoint", "bucket"),
    [
        ("http://user:secret@localhost:8333", "releaseproof-local"),
        ("http://localhost:8333/path", "releaseproof-local"),
        ("http://localhost:8333", "ReleaseProof_Local"),
        ("http://localhost:8333", "releaseproof..local"),
    ],
)
def test_s3_settings_reject_ambiguous_endpoints_and_bucket_names(
    endpoint: str, bucket: str
) -> None:
    with pytest.raises(ValueError, match=r"S3 (endpoint|bucket)"):
        S3Settings(
            endpoint_url=endpoint,
            bucket=bucket,
            access_key_id="local-access-key",
            secret_access_key="local-secret-key",  # noqa: S106 - synthetic test credential
        )
