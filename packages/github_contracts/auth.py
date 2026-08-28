"""Short-lived GitHub installation-token contracts and bounded memory cache."""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class InstallationToken:
    """A redacted process-memory value; never serialize this object into job payloads."""

    _value: str
    expires_at: datetime

    def __post_init__(self) -> None:
        if len(self._value) < 16 or any(character.isspace() for character in self._value):
            raise ValueError("installation token does not satisfy the bounded token contract")
        if self.expires_at.tzinfo is None:
            raise ValueError("installation token expiry must be timezone-aware")

    def reveal(self) -> str:
        """Reveal only at the provider HTTP authorization boundary."""

        return self._value

    def __repr__(self) -> str:
        return f"InstallationToken(_value=<redacted>, expires_at={self.expires_at!r})"


TokenMinter = Callable[[int, str], InstallationToken]


class InstallationTokenCache:
    """Small process-local LRU cache with expiry skew and no persistence API."""

    def __init__(self, *, maximum_entries: int = 64, expiry_skew: timedelta | None = None) -> None:
        if maximum_entries < 1 or maximum_entries > 1_024:
            raise ValueError("maximum_entries must be between 1 and 1024")
        self._maximum_entries = maximum_entries
        self._expiry_skew = expiry_skew or timedelta(seconds=60)
        self._tokens: OrderedDict[int, InstallationToken] = OrderedDict()

    def get_or_mint(
        self,
        *,
        installation_id: int,
        credential_reference: str,
        now: datetime,
        minter: TokenMinter,
    ) -> InstallationToken:
        if installation_id < 1:
            raise ValueError("installation_id must be positive")
        if not credential_reference or len(credential_reference) > 512:
            raise ValueError("credential_reference must be a bounded non-secret reference")
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")

        cached = self._tokens.get(installation_id)
        if cached is not None and cached.expires_at > now + self._expiry_skew:
            self._tokens.move_to_end(installation_id)
            return cached

        token = minter(installation_id, credential_reference)
        if token.expires_at <= now + self._expiry_skew:
            raise ValueError("minted installation token expires too soon")
        self._tokens[installation_id] = token
        self._tokens.move_to_end(installation_id)
        while len(self._tokens) > self._maximum_entries:
            self._tokens.popitem(last=False)
        return token

    def revoke(self, installation_id: int) -> None:
        self._tokens.pop(installation_id, None)

    def clear(self) -> None:
        self._tokens.clear()
