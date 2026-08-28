"""Bounded login throttling without retaining raw identifiers in cache keys."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.core.cache import cache
from django.http import HttpRequest
from redis.exceptions import RedisError


class LoginThrottleUnavailableError(RuntimeError):
    """The throttle store failed; authentication must fail closed."""


def _client_address(request: HttpRequest) -> str:
    value = request.META.get("REMOTE_ADDR", "unknown")
    return value if isinstance(value, str) and len(value) <= 64 else "unknown"


def _throttle_key(request: HttpRequest, username: str) -> str:
    material = f"{_client_address(request)}\x00{username.strip().casefold()}".encode()
    return f"releaseproof:login:{hashlib.sha256(material).hexdigest()}"


@dataclass(frozen=True, slots=True)
class LoginThrottle:
    maximum_failures: int = 5
    window_seconds: int = 300

    def __post_init__(self) -> None:
        if self.maximum_failures < 1 or self.window_seconds < 1:
            raise ValueError("login throttle bounds must be positive")

    def is_blocked(self, request: HttpRequest, username: str) -> bool:
        try:
            value = cache.get(_throttle_key(request, username), 0)
        except (RedisError, OSError, TimeoutError) as error:
            raise LoginThrottleUnavailableError("login throttle is unavailable") from error
        return isinstance(value, int) and value >= self.maximum_failures

    def record_failure(self, request: HttpRequest, username: str) -> None:
        key = _throttle_key(request, username)
        try:
            if cache.add(key, 1, timeout=self.window_seconds):
                return
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=self.window_seconds)
        except (RedisError, OSError, TimeoutError) as error:
            raise LoginThrottleUnavailableError("login throttle is unavailable") from error

    def clear(self, request: HttpRequest, username: str) -> None:
        try:
            cache.delete(_throttle_key(request, username))
        except (RedisError, OSError, TimeoutError) as error:
            raise LoginThrottleUnavailableError("login throttle is unavailable") from error
