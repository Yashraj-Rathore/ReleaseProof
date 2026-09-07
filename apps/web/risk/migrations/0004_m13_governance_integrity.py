"""Database-enforced M13 tenant consistency and append-only evidence."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_RELATIONS = (
    (
        "risk_modellifecycleevent",
        ("organization_id", "artifact_id"),
        "risk_governedmodelartifact",
        ("organization_id", "id"),
        "rp_gov_event_artifact_org_fk",
    ),
    (
        "risk_modeldeployment",
        ("organization_id", "model_name", "active_artifact_id"),
        "risk_governedmodelartifact",
        ("organization_id", "model_name", "id"),
        "rp_gov_deploy_active_org_fk",
    ),
    (
        "risk_modeldeployment",
        ("organization_id", "model_name", "rollback_artifact_id"),
        "risk_governedmodelartifact",
        ("organization_id", "model_name", "id"),
        "rp_gov_deploy_rollback_org_fk",
    ),
    (
        "risk_deploymentoutcome",
        ("organization_id", "repository_id"),
        "repositories_repository",
        ("organization_id", "id"),
        "rp_outcome_repository_org_fk",
    ),
    (
        "risk_deploymentoutcome",
        ("organization_id", "snapshot_id"),
        "changes_pullrequestsnapshot",
        ("organization_id", "id"),
        "rp_outcome_snapshot_org_fk",
    ),
    (
        "risk_deploymentoutcome",
        ("organization_id", "prediction_id"),
        "risk_riskscore",
        ("organization_id", "id"),
        "rp_outcome_prediction_org_fk",
    ),
    (
        "risk_deploymentoutcome",
        ("prediction_id", "snapshot_id"),
        "risk_riskscore",
        ("id", "snapshot_id"),
        "rp_outcome_prediction_snapshot_fk",
    ),
    (
        "risk_driftassessmentrecord",
        ("organization_id", "artifact_id"),
        "risk_governedmodelartifact",
        ("organization_id", "id"),
        "rp_drift_artifact_org_fk",
    ),
    (
        "risk_driftreview",
        ("organization_id", "assessment_id"),
        "risk_driftassessmentrecord",
        ("organization_id", "id"),
        "rp_drift_review_assessment_org_fk",
    ),
)
_IMMUTABLE_TABLES = (
    "risk_governedmodelartifact",
    "risk_modellifecycleevent",
    "risk_deploymentoutcome",
    "risk_driftassessmentrecord",
    "risk_driftreview",
)


def _create_postgresql(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for table, child_columns, parent, parent_columns, constraint in _RELATIONS:
        child_sql = ", ".join(f'"{column}"' for column in child_columns)
        parent_sql = ", ".join(f'"{column}"' for column in parent_columns)
        schema_editor.execute(
            f'ALTER TABLE "{table}" ADD CONSTRAINT "{constraint}" '
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
    for table, child_columns, parent, parent_columns, constraint in _RELATIONS:
        predicate = " AND ".join(
            f'parent."{parent_column}" = NEW."{child_column}"'
            for child_column, parent_column in zip(child_columns, parent_columns, strict=True)
        )
        nullable = " OR ".join(f'NEW."{column}" IS NULL' for column in child_columns)
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(
                f'CREATE TRIGGER "{constraint}_{operation.lower()}" '
                f'BEFORE {operation} ON "{table}" '
                f"WHEN NOT ({nullable}) AND NOT EXISTS "
                f'(SELECT 1 FROM "{parent}" AS parent WHERE {predicate}) '
                "BEGIN SELECT RAISE(ABORT, 'tenant relationship mismatch'); END"
            )
    for table in _IMMUTABLE_TABLES:
        for operation in ("UPDATE", "DELETE"):
            schema_editor.execute(
                f'CREATE TRIGGER "rp_{table}_immutable_{operation.lower()}" '
                f'BEFORE {operation} ON "{table}" '
                "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
            )


def create_governance_integrity_controls(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        _create_postgresql(schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        _create_sqlite(schema_editor)
    else:
        raise RuntimeError("ReleaseProof tenant constraints require PostgreSQL or test SQLite")


def drop_governance_integrity_controls(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        for table in _IMMUTABLE_TABLES:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable" ON "{table}"')
        for table, _child, _parent, _parent_columns, constraint in reversed(_RELATIONS):
            schema_editor.execute(f'ALTER TABLE "{table}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    elif schema_editor.connection.vendor == "sqlite":
        for _table, _child, _parent, _parent_columns, constraint in _RELATIONS:
            for operation in ("insert", "update"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "{constraint}_{operation}"')
        for table in _IMMUTABLE_TABLES:
            for operation in ("update", "delete"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable_{operation}"')


class Migration(migrations.Migration):
    dependencies = [
        ("risk", "0003_governedmodelartifact_driftassessmentrecord_and_more"),
    ]
    operations = [
        migrations.RunPython(
            create_governance_integrity_controls,
            drop_governance_integrity_controls,
        )
    ]
