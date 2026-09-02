from __future__ import annotations

import ast
from pathlib import Path

from django.apps import apps

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_APPS = {
    "analysis",
    "audit",
    "changes",
    "evidence",
    "identity",
    "organizations",
    "repositories",
    "retrieval",
    "risk",
    "verification",
}
CANONICAL_PACKAGES = {
    "agent_core",
    "ai_core",
    "change_intel",
    "dataset_core",
    "domain",
    "execution_contracts",
    "github_contracts",
    "ml_core",
    "observability",
    "recommendation_core",
    "retrieval_core",
}
FORBIDDEN_CORE_IMPORTS = {"celery", "django"}


def test_canonical_django_apps_are_registered_without_an_extra_policy_app() -> None:
    registered = {
        config.label for config in apps.get_app_configs() if config.name.startswith("apps.web.")
    }

    assert registered == CANONICAL_APPS


def test_canonical_framework_light_packages_exist() -> None:
    existing = {
        path.name
        for path in (ROOT / "packages").iterdir()
        if path.is_dir() and not path.name.startswith("_")
    }

    assert existing == CANONICAL_PACKAGES


def test_core_packages_do_not_import_django_or_celery() -> None:
    violations: list[str] = []
    for source_path in (ROOT / "packages").rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            imported: str | None = None
            if isinstance(node, ast.Import):
                imported = node.names[0].name.split(".", maxsplit=1)[0]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module.split(".", maxsplit=1)[0]
            if imported in FORBIDDEN_CORE_IMPORTS:
                violations.append(f"{source_path.relative_to(ROOT)} imports {imported}")

    assert violations == []


def test_control_plane_and_runner_do_not_cross_import_the_execution_boundary() -> None:
    violations: list[str] = []
    for root, forbidden in ((ROOT / "apps", "runner"), (ROOT / "runner", "apps")):
        for source_path in root.rglob("*.py"):
            tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
            for node in ast.walk(tree):
                imported: str | None = None
                if isinstance(node, ast.Import):
                    imported = node.names[0].name.split(".", maxsplit=1)[0]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = node.module.split(".", maxsplit=1)[0]
                if imported == forbidden:
                    violations.append(f"{source_path.relative_to(ROOT)} imports {forbidden}")

    assert violations == []
