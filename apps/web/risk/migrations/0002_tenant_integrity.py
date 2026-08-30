"""Database-enforced risk-score tenant consistency and immutability."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_RELATIONS = (
    (
        ("organization_id", "snapshot_id"),
        "changes_pullrequestsnapshot",
        ("organization_id", "id"),
        "rp_risk_snapshot_org_fk",
    ),
    (
        ("organization_id", "feature_set_id"),
        "changes_changefeatureset",
        ("organization_id", "id"),
        "rp_risk_features_org_fk",
    ),
    (
        ("feature_set_id", "snapshot_id"),
        "changes_changefeatureset",
        ("id", "snapshot_id"),
        "rp_risk_features_snapshot_fk",
    ),
)
_TABLE = "risk_riskscore"


def _create_postgresql(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child_columns, parent, parent_columns, constraint in _RELATIONS:
        child_sql = ", ".join(f'"{column}"' for column in child_columns)
        parent_sql = ", ".join(f'"{column}"' for column in parent_columns)
        schema_editor.execute(
            f'ALTER TABLE "{_TABLE}" ADD CONSTRAINT "{constraint}" '
            f'FOREIGN KEY ({child_sql}) REFERENCES "{parent}" ({parent_sql}) '
            "DEFERRABLE INITIALLY IMMEDIATE"
        )
    schema_editor.execute(
        f'CREATE TRIGGER "rp_{_TABLE}_immutable" '
        f'BEFORE UPDATE OR DELETE ON "{_TABLE}" FOR EACH ROW '
        "EXECUTE FUNCTION releaseproof_reject_immutable()"
    )


def _create_sqlite(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child_columns, parent, parent_columns, constraint in _RELATIONS:
        predicate = " AND ".join(
            f'parent."{parent_column}" = NEW."{child_column}"'
            for child_column, parent_column in zip(child_columns, parent_columns, strict=True)
        )
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(
                f'CREATE TRIGGER "{constraint}_{operation.lower()}" '
                f'BEFORE {operation} ON "{_TABLE}" '
                f'WHEN NOT EXISTS (SELECT 1 FROM "{parent}" AS parent WHERE {predicate}) '
                "BEGIN SELECT RAISE(ABORT, 'tenant relationship mismatch'); END"
            )
    for operation in ("UPDATE", "DELETE"):
        schema_editor.execute(
            f'CREATE TRIGGER "rp_{_TABLE}_immutable_{operation.lower()}" '
            f'BEFORE {operation} ON "{_TABLE}" '
            "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
        )


def create_risk_integrity_controls(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        _create_postgresql(schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        _create_sqlite(schema_editor)
    else:
        raise RuntimeError("ReleaseProof tenant constraints require PostgreSQL or test SQLite")


def drop_risk_integrity_controls(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{_TABLE}_immutable" ON "{_TABLE}"')
        for _child_columns, _parent, _parent_columns, constraint in reversed(_RELATIONS):
            schema_editor.execute(
                f'ALTER TABLE "{_TABLE}" DROP CONSTRAINT IF EXISTS "{constraint}"'
            )
    elif schema_editor.connection.vendor == "sqlite":
        for _child_columns, _parent, _parent_columns, constraint in _RELATIONS:
            for operation in ("insert", "update"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "{constraint}_{operation}"')
        for operation in ("update", "delete"):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{_TABLE}_immutable_{operation}"')


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0003_m3_tenant_integrity"),
        ("risk", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(create_risk_integrity_controls, drop_risk_integrity_controls)
    ]
