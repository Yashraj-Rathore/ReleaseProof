"""Database tenant consistency and immutability for M7 LLM policies."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_TABLE = "organizations_hostedllmpolicy"
_CONSTRAINT = "rp_llm_policy_repository_org_fk"


def create_llm_policy_integrity(
    apps: Apps,
    schema_editor: BaseDatabaseSchemaEditor,
) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f'ALTER TABLE "{_TABLE}" ADD CONSTRAINT "{_CONSTRAINT}" '
            'FOREIGN KEY ("organization_id", "repository_id") '
            'REFERENCES "repositories_repository" ("organization_id", "id") '
            "DEFERRABLE INITIALLY IMMEDIATE"
        )
        schema_editor.execute(
            f'CREATE TRIGGER "rp_{_TABLE}_immutable" '
            f'BEFORE UPDATE OR DELETE ON "{_TABLE}" FOR EACH ROW '
            "EXECUTE FUNCTION releaseproof_reject_immutable()"
        )
    elif schema_editor.connection.vendor == "sqlite":
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(
                f'CREATE TRIGGER "{_CONSTRAINT}_{operation.lower()}" '
                f'BEFORE {operation} ON "{_TABLE}" '
                'WHEN NEW."repository_id" IS NOT NULL AND NOT EXISTS ('
                'SELECT 1 FROM "repositories_repository" AS parent '
                'WHERE parent."organization_id" = NEW."organization_id" '
                'AND parent."id" = NEW."repository_id") '
                "BEGIN SELECT RAISE(ABORT, 'tenant relationship mismatch'); END"
            )
        for operation in ("UPDATE", "DELETE"):
            schema_editor.execute(
                f'CREATE TRIGGER "rp_{_TABLE}_immutable_{operation.lower()}" '
                f'BEFORE {operation} ON "{_TABLE}" '
                "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
            )
    else:
        raise RuntimeError("ReleaseProof LLM policy constraints require PostgreSQL or test SQLite")


def drop_llm_policy_integrity(
    apps: Apps,
    schema_editor: BaseDatabaseSchemaEditor,
) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{_TABLE}_immutable" ON "{_TABLE}"')
        schema_editor.execute(f'ALTER TABLE "{_TABLE}" DROP CONSTRAINT IF EXISTS "{_CONSTRAINT}"')
    elif schema_editor.connection.vendor == "sqlite":
        for operation in ("insert", "update"):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "{_CONSTRAINT}_{operation}"')
        for operation in ("update", "delete"):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{_TABLE}_immutable_{operation}"')


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0002_tenant_integrity"),
        ("organizations", "0002_hostedllmpolicy"),
    ]
    operations = [
        migrations.RunPython(
            create_llm_policy_integrity,
            drop_llm_policy_integrity,
        )
    ]
