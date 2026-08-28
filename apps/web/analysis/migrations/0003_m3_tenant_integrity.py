"""Database-enforced M3 tenant consistency and append-only evidence."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_RELATIONS = (
    (
        "changes_changefeatureset",
        ("organization_id", "snapshot_id"),
        "changes_pullrequestsnapshot",
        ("organization_id", "id"),
        "rp_features_snapshot_org_fk",
    ),
    (
        "evidence_evidenceitem",
        ("organization_id", "snapshot_id"),
        "changes_pullrequestsnapshot",
        ("organization_id", "id"),
        "rp_evidence_snapshot_org_fk",
    ),
    (
        "evidence_evidenceitem",
        ("organization_id", "feature_set_id"),
        "changes_changefeatureset",
        ("organization_id", "id"),
        "rp_evidence_features_org_fk",
    ),
    (
        "evidence_evidenceitem",
        ("feature_set_id", "snapshot_id"),
        "changes_changefeatureset",
        ("id", "snapshot_id"),
        "rp_evidence_features_snapshot_fk",
    ),
)
_IMMUTABLE_TABLES = ("changes_changefeatureset", "evidence_evidenceitem")


def _create_postgresql(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, child_columns, parent, parent_columns, constraint in _RELATIONS:
        child_sql = ", ".join(f'"{column}"' for column in child_columns)
        parent_sql = ", ".join(f'"{column}"' for column in parent_columns)
        schema_editor.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT "{constraint}" '
            f'FOREIGN KEY ({child_sql}) REFERENCES "{parent}" ({parent_sql}) '
            "DEFERRABLE INITIALLY IMMEDIATE"
        )
    for table in _IMMUTABLE_TABLES:
        schema_editor.execute(
            f'CREATE TRIGGER "rp_{table}_immutable" '
            f'BEFORE UPDATE OR DELETE ON "{table}" FOR EACH ROW '
            "EXECUTE FUNCTION releaseproof_reject_immutable()"
        )


def _create_sqlite(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, child_columns, parent, parent_columns, constraint in _RELATIONS:
        predicate = " AND ".join(
            f'parent."{parent_column}" = NEW."{child_column}"'
            for child_column, parent_column in zip(child_columns, parent_columns, strict=True)
        )
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(
                f'CREATE TRIGGER "{constraint}_{operation.lower()}" '
                f'BEFORE {operation} ON "{child}" '
                f'WHEN NOT EXISTS (SELECT 1 FROM "{parent}" AS parent WHERE {predicate}) '
                "BEGIN SELECT RAISE(ABORT, 'tenant relationship mismatch'); END"
            )
    for table in _IMMUTABLE_TABLES:
        for operation in ("UPDATE", "DELETE"):
            schema_editor.execute(
                f'CREATE TRIGGER "rp_{table}_immutable_{operation.lower()}" '
                f'BEFORE {operation} ON "{table}" '
                "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
            )


def create_m3_integrity_controls(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        _create_postgresql(schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        _create_sqlite(schema_editor)
    else:
        raise RuntimeError("ReleaseProof tenant constraints require PostgreSQL or test SQLite")


def drop_m3_integrity_controls(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        for table in _IMMUTABLE_TABLES:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable" ON "{table}"')
        for child, _child_columns, _parent, _parent_columns, constraint in reversed(_RELATIONS):
            schema_editor.execute(f'ALTER TABLE "{child}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    elif schema_editor.connection.vendor == "sqlite":
        for _child, _child_columns, _parent, _parent_columns, constraint in _RELATIONS:
            for operation in ("insert", "update"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "{constraint}_{operation}"')
        for table in _IMMUTABLE_TABLES:
            for operation in ("update", "delete"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable_{operation}"')


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0002_tenant_integrity"),
        ("changes", "0002_pullrequestsnapshot_author_key_and_more"),
        ("evidence", "0001_initial"),
    ]
    operations = [migrations.RunPython(create_m3_integrity_controls, drop_m3_integrity_controls)]
