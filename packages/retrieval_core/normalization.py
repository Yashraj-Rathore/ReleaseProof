"""Source-safe normalization and deterministic lexical/vector helpers."""

from __future__ import annotations

import math
import re
import unicodedata

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_./:-]+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_SEPARATOR_PATTERN = re.compile(r"[_./:-]+")
_WHITESPACE = re.compile(r"[ \t]+")


def normalize_source_text(value: str) -> str:
    if "\x00" in value:
        raise ValueError("source text cannot contain NUL")
    normalized = unicodedata.normalize("NFKC", value).replace("\r\n", "\n").replace("\r", "\n")
    cleaned: list[str] = []
    for character in normalized:
        if character in {"\n", "\t"} or unicodedata.category(character) != "Cc":
            cleaned.append(character)
    lines = [_WHITESPACE.sub(" ", line).rstrip() for line in "".join(cleaned).split("\n")]
    return "\n".join(lines).strip()


def code_tokens(value: str) -> tuple[str, ...]:
    tokens: list[str] = []
    seen: set[str] = set()
    for match in _TOKEN_PATTERN.finditer(value):
        original = match.group(0)
        candidates = [original]
        for part in _SEPARATOR_PATTERN.split(original):
            candidates.extend(_CAMEL_BOUNDARY.sub(" ", part).split())
        for candidate in candidates:
            lowered = candidate.casefold()
            if lowered and lowered not in seen:
                tokens.append(lowered)
                seen.add(lowered)
    return tuple(tokens)


def normalize_fts_text(value: str) -> str:
    source = normalize_source_text(value)
    return " ".join(code_tokens(source))


def lexical_score(query: str, document: str) -> float:
    query_tokens = code_tokens(query)
    if not query_tokens:
        return 0.0
    document_tokens = code_tokens(document)
    if not document_tokens:
        return 0.0
    document_counts = {token: document_tokens.count(token) for token in set(document_tokens)}
    matched = sum(min(document_counts.get(token, 0), 3) for token in query_tokens)
    coverage = sum(token in document_counts for token in query_tokens) / len(query_tokens)
    phrase_bonus = 0.25 if query.casefold() in document.casefold() else 0.0
    return round(coverage + matched / (3.0 * len(query_tokens)) + phrase_bonus, 12)


def cosine_similarity(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if not left or len(left) != len(right):
        raise ValueError("vectors must be non-empty and dimension compatible")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)
