"""Authentication for control-plane/runner messages without persisting signing keys."""

from __future__ import annotations

import hashlib
import hmac


def _valid_key(key: bytes) -> None:
    if len(key) < 32:
        raise ValueError("execution signing keys must contain at least 32 bytes")


def sign_payload(payload: bytes, *, key: bytes) -> str:
    _valid_key(key)
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_payload_signature(payload: bytes, *, signature: str, key: bytes) -> bool:
    _valid_key(key)
    if len(signature) != 64 or any(character not in "0123456789abcdef" for character in signature):
        return False
    return hmac.compare_digest(sign_payload(payload, key=key), signature)
