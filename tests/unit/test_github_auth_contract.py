from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from packages.github_contracts import InstallationToken, InstallationTokenCache


def test_installation_tokens_are_redacted_cached_and_evicted_without_persistence() -> None:
    now = datetime(2026, 8, 28, tzinfo=UTC)
    minted: list[int] = []

    def mint(installation_id: int, credential_reference: str) -> InstallationToken:
        assert credential_reference == "env:GITHUB_APP_PRIVATE_KEY_PATH"
        minted.append(installation_id)
        return InstallationToken(
            f"installation-token-{installation_id}",
            now + timedelta(minutes=30),
        )

    cache = InstallationTokenCache(maximum_entries=1)
    first = cache.get_or_mint(
        installation_id=1,
        credential_reference="env:GITHUB_APP_PRIVATE_KEY_PATH",
        now=now,
        minter=mint,
    )
    assert "installation-token-1" not in repr(first)
    assert first.reveal() == "installation-token-1"
    assert (
        cache.get_or_mint(
            installation_id=1,
            credential_reference="env:GITHUB_APP_PRIVATE_KEY_PATH",
            now=now,
            minter=mint,
        )
        is first
    )

    cache.get_or_mint(
        installation_id=2,
        credential_reference="env:GITHUB_APP_PRIVATE_KEY_PATH",
        now=now,
        minter=mint,
    )
    cache.get_or_mint(
        installation_id=1,
        credential_reference="env:GITHUB_APP_PRIVATE_KEY_PATH",
        now=now,
        minter=mint,
    )
    assert minted == [1, 2, 1]
    assert not hasattr(cache, "save")


def test_installation_token_cache_rejects_immediately_expiring_token() -> None:
    now = datetime(2026, 8, 28, tzinfo=UTC)
    cache = InstallationTokenCache()

    with pytest.raises(ValueError, match="expires too soon"):
        cache.get_or_mint(
            installation_id=1,
            credential_reference="env:GITHUB_APP_PRIVATE_KEY_PATH",
            now=now,
            minter=lambda _installation, _reference: InstallationToken(
                "installation-token-short",
                now + timedelta(seconds=30),
            ),
        )
