"""Bounded Markdown-, Python-AST-, and fallback-aware evidence chunking."""

from __future__ import annotations

import ast
import hashlib
import re

from packages.retrieval_core.config import CHUNKING_VERSION
from packages.retrieval_core.contracts import EvidenceDocumentInput, EvidenceSourceType, SourceChunk
from packages.retrieval_core.normalization import normalize_fts_text, normalize_source_text

MAX_CHUNK_CHARS = 4_000
MAX_CHUNKS = 128
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def _split_bounded(
    content: str, *, heading: str, start_line: int
) -> list[tuple[str, str, int, int]]:
    lines = content.splitlines() or [content]
    pieces: list[tuple[str, str, int, int]] = []
    current: list[str] = []
    current_start = start_line
    current_size = 0
    for offset, line in enumerate(lines):
        projected = current_size + len(line) + (1 if current else 0)
        if current and projected > MAX_CHUNK_CHARS:
            pieces.append((heading, "\n".join(current), current_start, start_line + offset - 1))
            current = []
            current_start = start_line + offset
            current_size = 0
        if len(line) > MAX_CHUNK_CHARS:
            if current:
                pieces.append((heading, "\n".join(current), current_start, start_line + offset - 1))
                current = []
            for index in range(0, len(line), MAX_CHUNK_CHARS):
                pieces.append(
                    (
                        heading,
                        line[index : index + MAX_CHUNK_CHARS],
                        start_line + offset,
                        start_line + offset,
                    )
                )
            current_start = start_line + offset + 1
            current_size = 0
            continue
        current.append(line)
        current_size = projected
    if current:
        pieces.append((heading, "\n".join(current), current_start, start_line + len(lines) - 1))
    return pieces


def _markdown_sections(content: str) -> list[tuple[str, str, int, int]]:
    sections: list[tuple[str, str, int, int]] = []
    heading = "Document"
    start_line = 1
    lines: list[str] = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        match = _HEADING.match(line)
        if match and lines:
            sections.extend(
                _split_bounded("\n".join(lines), heading=heading, start_line=start_line)
            )
            lines = []
        if match:
            heading = match.group(2)[:256]
            start_line = line_number
        lines.append(line)
    if lines:
        sections.extend(_split_bounded("\n".join(lines), heading=heading, start_line=start_line))
    return sections


def _python_sections(content: str) -> list[tuple[str, str, int, int]]:
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return _split_bounded(content, heading="Python source (parse fallback)", start_line=1)
    lines = content.splitlines()
    sections: list[tuple[str, str, int, int]] = []
    first_node_line = len(lines) + 1
    nodes = [
        node
        for node in tree.body
        if isinstance(node, (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef))
    ]
    if nodes:
        first_node_line = min(node.lineno for node in nodes)
    if first_node_line > 1:
        preamble = "\n".join(lines[: first_node_line - 1]).strip()
        if preamble:
            sections.extend(_split_bounded(preamble, heading="Module preamble", start_line=1))
    for node in nodes:
        end_line = getattr(node, "end_lineno", node.lineno)
        segment = "\n".join(lines[node.lineno - 1 : end_line])
        kind = "class" if isinstance(node, ast.ClassDef) else "function"
        sections.extend(
            _split_bounded(segment, heading=f"{kind} {node.name}", start_line=node.lineno)
        )
    if not sections:
        return _split_bounded(content, heading="Python module", start_line=1)
    return sections


def chunk_document(document: EvidenceDocumentInput) -> tuple[SourceChunk, ...]:
    content = normalize_source_text(document.content)
    if document.source_type is EvidenceSourceType.PYTHON_SOURCE or document.source_id.endswith(
        ".py"
    ):
        sections = _python_sections(content)
        strategy = f"{CHUNKING_VERSION}:python-ast"
    elif document.source_id.endswith((".md", ".markdown")) or document.source_type in {
        EvidenceSourceType.ADR,
        EvidenceSourceType.DOCUMENTATION,
        EvidenceSourceType.INCIDENT,
        EvidenceSourceType.POSTMORTEM,
        EvidenceSourceType.PR_SUMMARY,
        EvidenceSourceType.RUNBOOK,
    }:
        sections = _markdown_sections(content)
        strategy = f"{CHUNKING_VERSION}:markdown-heading"
    else:
        sections = _split_bounded(content, heading=document.title, start_line=1)
        strategy = f"{CHUNKING_VERSION}:bounded-fallback"
    if not sections or len(sections) > MAX_CHUNKS:
        raise ValueError("chunk count is empty or exceeds the ingestion limit")
    chunks: list[SourceChunk] = []
    for sequence, (heading, chunk_content, start_line, end_line) in enumerate(sections):
        normalized = normalize_fts_text(f"{document.title}\n{heading}\n{chunk_content}")
        chunks.append(
            SourceChunk(
                sequence=sequence,
                heading=heading,
                content=chunk_content,
                normalized_text=normalized,
                start_line=start_line,
                end_line=end_line,
                strategy=strategy,
                content_sha256=hashlib.sha256(chunk_content.encode("utf-8")).hexdigest(),
            )
        )
    return tuple(chunks)
