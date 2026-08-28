"""Bounded static Python import graph and reverse-reachability blast radius."""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from pathlib import PurePosixPath

from packages.change_intel.contracts import (
    GRAPH_SCHEMA_VERSION,
    BlastPath,
    BlastRadius,
    GraphFinding,
    ImportGraph,
    NormalizedDiff,
    SourceTree,
    canonical_hash,
)

MAX_SOURCE_FILES = 5_000
MAX_SOURCE_FILE_BYTES = 262_144
MAX_SOURCE_TREE_BYTES = 5_242_880
MAX_GRAPH_EDGES = 25_000
MAX_BLAST_NODES = 1_000
DEFAULT_BLAST_DEPTH = 5


def _normalized_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip("/")
    parts = PurePosixPath(normalized).parts
    if not normalized or any(part in {"", ".", ".."} for part in parts):
        raise ValueError("source path must be repository-relative")
    return "/".join(parts)


def _module_name(path: str) -> str | None:
    pure = PurePosixPath(path)
    if pure.suffix.casefold() != ".py":
        return None
    parts = list(pure.with_suffix("").parts)
    if parts and parts[0] in {"src", "lib"}:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return None
    return ".".join(parts)


def _resolve_relative(module: str, imported: str | None, level: int) -> str:
    package = module.split(".")[:-1]
    keep = max(0, len(package) - max(0, level - 1))
    prefix = package[:keep]
    if imported:
        prefix.extend(imported.split("."))
    return ".".join(prefix)


def _internal_target(candidate: str, modules: set[str]) -> str | None:
    if candidate in modules:
        return candidate
    parts = candidate.split(".")
    while len(parts) > 1:
        parts.pop()
        parent = ".".join(parts)
        if parent in modules:
            return parent
    return None


def _import_targets(tree: ast.AST, module: str, modules: set[str]) -> tuple[set[str], list[str]]:
    targets: set[str] = set()
    external: list[str] = []
    for node in ast.walk(tree):
        candidates: list[str] = []
        if isinstance(node, ast.Import):
            candidates.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = (
                _resolve_relative(module, node.module, node.level)
                if node.level
                else (node.module or "")
            )
            for alias in node.names:
                expanded = f"{base}.{alias.name}" if base and alias.name != "*" else base
                candidates.extend(candidate for candidate in (expanded, base) if candidate)
        for candidate in candidates:
            target = _internal_target(candidate, modules)
            if target is not None and target != module:
                targets.add(target)
            elif target is None:
                external.append(candidate.split(".", maxsplit=1)[0])
    return targets, sorted(set(external))


def _dynamic_findings(tree: ast.AST, path: str) -> list[GraphFinding]:
    findings: list[GraphFinding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        code: str | None = None
        if isinstance(node.func, ast.Name) and node.func.id == "__import__":
            code = "dynamic_import_builtin"
        elif (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "importlib"
        ):
            code = "dynamic_import_importlib"
        if code:
            findings.append(
                GraphFinding(
                    code=code,
                    path=path,
                    detail=f"dynamic import at line {getattr(node, 'lineno', 0)} is not resolved",
                )
            )
    return findings


def unavailable_graph(code: str) -> ImportGraph:
    payload = {
        "available": False,
        "edges": [],
        "findings": [{"code": code, "detail": "base source tree unavailable", "path": ""}],
        "modules": [],
        "schema_version": GRAPH_SCHEMA_VERSION,
    }
    return ImportGraph(
        schema_version=GRAPH_SCHEMA_VERSION,
        available=False,
        modules=(),
        edges=(),
        findings=(GraphFinding(code, "", "base source tree unavailable"),),
        graph_hash=canonical_hash(payload),
    )


def build_python_import_graph(source_tree: SourceTree) -> ImportGraph:
    if len(source_tree.files) > MAX_SOURCE_FILES:
        raise ValueError("source tree exceeds the file-count limit")
    paths: dict[str, str] = {}
    total_bytes = 0
    findings: list[GraphFinding] = []
    for source_file in source_tree.files:
        path = _normalized_path(source_file.path)
        if path in paths:
            raise ValueError("source-tree paths must be unique")
        content_bytes = len(source_file.content.encode("utf-8"))
        if content_bytes > MAX_SOURCE_FILE_BYTES:
            findings.append(GraphFinding("source_file_too_large", path, "file was not parsed"))
            continue
        total_bytes += content_bytes
        if total_bytes > MAX_SOURCE_TREE_BYTES:
            raise ValueError("source tree exceeds the total-byte limit")
        paths[path] = source_file.content

    module_paths = sorted(
        (module, path) for path in paths if (module := _module_name(path)) is not None
    )
    module_names = {module for module, _path in module_paths}
    path_by_module = dict(module_paths)
    edges: set[tuple[str, str]] = set()
    for path, content in sorted(paths.items()):
        module = _module_name(path)
        if module is None:
            suffix = PurePosixPath(path).suffix.casefold() or "none"
            findings.append(
                GraphFinding("unsupported_language", path, f"no graph adapter for suffix {suffix}")
            )
            continue
        try:
            tree = ast.parse(content, filename=path)
        except (SyntaxError, ValueError):
            findings.append(GraphFinding("python_parse_error", path, "Python source did not parse"))
            continue
        findings.extend(_dynamic_findings(tree, path))
        targets, external = _import_targets(tree, module, module_names)
        edges.update((module, target) for target in targets)
        for imported in external:
            findings.append(GraphFinding("external_import", path, imported))
        if len(edges) > MAX_GRAPH_EDGES:
            raise ValueError("import graph exceeds the edge limit")

    sorted_edges = tuple(sorted(edges))
    sorted_findings = tuple(sorted(findings, key=lambda item: (item.path, item.code, item.detail)))
    payload = {
        "available": True,
        "edges": [list(edge) for edge in sorted_edges],
        "findings": [finding.as_dict() for finding in sorted_findings],
        "modules": [[module, path_by_module[module]] for module in sorted(path_by_module)],
        "schema_version": GRAPH_SCHEMA_VERSION,
    }
    return ImportGraph(
        schema_version=GRAPH_SCHEMA_VERSION,
        available=True,
        modules=tuple((module, path_by_module[module]) for module in sorted(path_by_module)),
        edges=sorted_edges,
        findings=sorted_findings,
        graph_hash=canonical_hash(payload),
    )


def compute_blast_radius(
    normalized_diff: NormalizedDiff,
    graph: ImportGraph,
    *,
    max_depth: int = DEFAULT_BLAST_DEPTH,
) -> BlastRadius:
    if max_depth < 1 or max_depth > 20:
        raise ValueError("blast-radius depth must be between 1 and 20")
    module_by_path = {path: module for module, path in graph.modules}
    changed_modules = tuple(
        sorted(
            {
                module_by_path[file.path]
                for file in normalized_diff.files
                if file.path in module_by_path
            }
        )
    )
    missing_paths = tuple(
        sorted(file.path for file in normalized_diff.files if file.path not in module_by_path)
    )
    tags = tuple(
        sorted(
            {tag for changed_file in normalized_diff.files for tag in changed_file.sensitive_tags}
        )
    )
    if not graph.available:
        return BlastRadius(
            graph_schema_version=graph.schema_version,
            available=False,
            changed_modules=(),
            direct_modules=(),
            transitive_modules=(),
            impacted_tests=(),
            max_depth=None,
            evidence_paths=(),
            missing_changed_paths=tuple(sorted(file.path for file in normalized_diff.files)),
            sensitive_tags=tags,
            truncated=False,
        )

    reverse_edges: dict[str, set[str]] = defaultdict(set)
    for importer, imported in graph.edges:
        reverse_edges[imported].add(importer)
    paths: dict[str, BlastPath] = {}
    queue: deque[tuple[str, tuple[str, ...], int]] = deque(
        (module, (module,), 0) for module in changed_modules
    )
    truncated = False
    while queue:
        current, current_path, distance = queue.popleft()
        if distance >= max_depth:
            if reverse_edges.get(current):
                truncated = True
            continue
        for dependent in sorted(reverse_edges.get(current, set())):
            next_distance = distance + 1
            if dependent in changed_modules or dependent in paths:
                continue
            paths[dependent] = BlastPath(
                changed_module=current_path[0],
                affected_module=dependent,
                distance=next_distance,
                modules=(*current_path, dependent),
            )
            if len(paths) >= MAX_BLAST_NODES:
                truncated = True
                queue.clear()
                break
            queue.append((dependent, (*current_path, dependent), next_distance))
    direct = tuple(sorted(module for module, path in paths.items() if path.distance == 1))
    transitive = tuple(sorted(module for module, path in paths.items() if path.distance > 1))
    path_by_module = dict(graph.modules)
    impacted_tests = tuple(
        sorted(
            module
            for module in paths
            if "/tests/" in f"/{path_by_module.get(module, '')}"
            or PurePosixPath(path_by_module.get(module, "")).name.startswith("test_")
        )
    )
    return BlastRadius(
        graph_schema_version=graph.schema_version,
        available=True,
        changed_modules=changed_modules,
        direct_modules=direct,
        transitive_modules=transitive,
        impacted_tests=impacted_tests,
        max_depth=max((path.distance for path in paths.values()), default=0),
        evidence_paths=tuple(paths[module] for module in sorted(paths)),
        missing_changed_paths=missing_paths,
        sensitive_tags=tags,
        truncated=truncated,
    )
