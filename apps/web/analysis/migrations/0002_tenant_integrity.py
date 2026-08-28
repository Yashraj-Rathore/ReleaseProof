"""Database-enforced tenant consistency and append-only ingestion records."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_RELATIONS = (
    (
        "repositories_repository",
        "installation_id",
        "repositories_githubinstallation",
        "rp_repo_installation_org_fk",
    ),
    (
        "changes_webhookreceipt",
        "installation_id",
        "repositories_githubinstallation",
        "rp_receipt_installation_org_fk",
    ),
    (
        "changes_pullrequestsnapshot",
        "repository_id",
        "repositories_repository",
        "rp_snapshot_repository_org_fk",
    ),
    (
        "changes_pullrequestsnapshot",
        "first_receipt_id",
        "changes_webhookreceipt",
        "rp_snapshot_receipt_org_fk",
    ),
    (
        "analysis_analysisjob",
        "snapshot_id",
        "changes_pullrequestsnapshot",
        "rp_job_snapshot_org_fk",
    ),
    ("analysis_outboxevent", "job_id", "analysis_analysisjob", "rp_outbox_job_org_fk"),
)
_IMMUTABLE_TABLES = ("changes_webhookreceipt", "changes_pullrequestsnapshot", "audit_auditlog")


def _create_postgresql(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, parent_column, parent, constraint in _RELATIONS:
        schema_editor.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT "{constraint}" '
            f'FOREIGN KEY ("organization_id", "{parent_column}") '
            f'REFERENCES "{parent}" ("organization_id", "id") NOT DEFERRABLE'
        )
    schema_editor.execute(
        "CREATE FUNCTION releaseproof_reject_immutable() RETURNS trigger AS $$ "
        "BEGIN RAISE EXCEPTION 'immutable ReleaseProof record'; END; $$ LANGUAGE plpgsql"
    )
    for table in _IMMUTABLE_TABLES:
        schema_editor.execute(
            f'CREATE TRIGGER "rp_{table}_immutable" BEFORE UPDATE OR DELETE ON "{table}" '
            "FOR EACH ROW EXECUTE FUNCTION releaseproof_reject_immutable()"
        )


def _create_sqlite(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, parent_column, parent, constraint in _RELATIONS:
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(
                f'CREATE TRIGGER "{constraint}_{operation.lower()}" BEFORE {operation} ON "{child}" '
                f'FOR EACH ROW WHEN NEW."{parent_column}" IS NOT NULL AND '
                f'NEW."organization_id" != (SELECT "organization_id" FROM "{parent}" '
                f'WHERE "id" = NEW."{parent_column}") '
                "BEGIN SELECT RAISE(ABORT, 'tenant scope mismatch'); END"
            )
    for table in _IMMUTABLE_TABLES:
        for operation in ("UPDATE", "DELETE"):
            schema_editor.execute(
                f'CREATE TRIGGER "rp_{table}_immutable_{operation.lower()}" '
                f'BEFORE {operation} ON "{table}" '
                "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
            )


def create_integrity_controls(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        _create_postgresql(schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        _create_sqlite(schema_editor)
    else:
        raise RuntimeError("ReleaseProof tenant constraints require PostgreSQL or test SQLite")


def drop_integrity_controls(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        for table in _IMMUTABLE_TABLES:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable" ON "{table}"')
        schema_editor.execute("DROP FUNCTION IF EXISTS releaseproof_reject_immutable()")
        for child, _parent_column, _parent, constraint in reversed(_RELATIONS):
            schema_editor.execute(f'ALTER TABLE "{child}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    elif schema_editor.connection.vendor == "sqlite":
        for _child, _parent_column, _parent, constraint in _RELATIONS:
            for operation in ("insert", "update"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "{constraint}_{operation}"')
        for table in _IMMUTABLE_TABLES:
            for operation in ("update", "delete"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable_{operation}"')


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0001_initial"),
        ("audit", "0001_initial"),
        ("changes", "0001_initial"),
        ("repositories", "0001_initial"),
    ]
    operations = [migrations.RunPython(create_integrity_controls, drop_integrity_controls)]
