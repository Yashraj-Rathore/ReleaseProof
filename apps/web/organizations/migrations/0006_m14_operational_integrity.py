"""Tenant bindings, append-only evidence, and scoped retention-delete grants."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_GRANT = "organizations_retentiondeletiongrant"
_TARGET_TABLES = (
    "changes_pullrequestsnapshot",
    "retrieval_knowledgeembedding384",
    "risk_governedmodelartifact",
    "evidence_evidenceitem",
)
_RETENTION_CLASS_BY_TABLE = {
    "changes_pullrequestsnapshot": "source_snapshot",
    "retrieval_knowledgeembedding384": "embedding",
    "risk_governedmodelartifact": "artifact",
    "evidence_evidenceitem": "analysis",
}
_NEW_IMMUTABLE_TABLES = (
    "organizations_operationalpolicy",
    "organizations_usagereservation",
    "organizations_retentiondeletionplan",
    "organizations_retentiondeletionexecution",
)
_RELATIONS = (
    (
        "organizations_retentiondeletionplan",
        "policy_id",
        "organizations_operationalpolicy",
        "rp_retention_plan_policy_org_fk",
    ),
    (
        _GRANT,
        "plan_id",
        "organizations_retentiondeletionplan",
        "rp_retention_grant_plan_org_fk",
    ),
    (
        "organizations_retentiondeletionexecution",
        "plan_id",
        "organizations_retentiondeletionplan",
        "rp_retention_execution_plan_org_fk",
    ),
    (
        "organizations_usagereservation",
        "counter_id",
        "organizations_usagecounter",
        "rp_usage_reservation_counter_org_fk",
    ),
)


def _postgresql_function(*, governed_delete: bool) -> str:
    if governed_delete:
        target_list = ", ".join(f"'{table}'" for table in _TARGET_TABLES)
        candidate_checks = "\n".join(
            f"WHEN '{table}' THEN (plan.candidate_public_ids -> '{retention_class}') "
            "? OLD.public_id::text"
            for table, retention_class in _RETENTION_CLASS_BY_TABLE.items()
        )
        allowance = f"""
            IF TG_OP = 'DELETE' AND TG_TABLE_NAME IN ({target_list}) AND EXISTS (
                SELECT 1 FROM {_GRANT} AS deletion_grant
                INNER JOIN organizations_retentiondeletionplan AS plan
                  ON plan.id = deletion_grant.plan_id
                 AND plan.organization_id = deletion_grant.organization_id
                WHERE deletion_grant.organization_id = OLD.organization_id
                  AND deletion_grant.active = TRUE
                  AND deletion_grant.expires_at > CURRENT_TIMESTAMP
                  AND plan.dry_run = FALSE
                  AND CASE TG_TABLE_NAME
                    {candidate_checks}
                    ELSE FALSE
                  END
            ) THEN
                RETURN OLD;
            END IF;
        """
    else:
        allowance = ""
    return f"""
        CREATE OR REPLACE FUNCTION releaseproof_reject_immutable() RETURNS trigger AS $$
        BEGIN
            {allowance}
            RAISE EXCEPTION 'immutable ReleaseProof record';
        END;
        $$ LANGUAGE plpgsql
    """


def _create_postgresql(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, child_id, parent, constraint in _RELATIONS:
        schema_editor.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT "{constraint}" '
            f'FOREIGN KEY ("organization_id", "{child_id}") '
            f'REFERENCES "{parent}" ("organization_id", "id") '
            "DEFERRABLE INITIALLY IMMEDIATE"
        )
    schema_editor.execute(_postgresql_function(governed_delete=True))
    for table in _NEW_IMMUTABLE_TABLES:
        schema_editor.execute(
            f'CREATE TRIGGER "rp_{table}_immutable" BEFORE UPDATE OR DELETE ON "{table}" '
            "FOR EACH ROW EXECUTE FUNCTION releaseproof_reject_immutable()"
        )


def _replace_sqlite_delete_trigger(
    schema_editor: BaseDatabaseSchemaEditor,
    *,
    table: str,
    retention_class: str | None,
    governed: bool,
) -> None:
    trigger = f"rp_{table}_immutable_delete"
    schema_editor.execute(f'DROP TRIGGER IF EXISTS "{trigger}"')
    when = ""
    if governed:
        if retention_class is None:
            raise ValueError("governed retention trigger requires a content class")
        when = (
            f'WHEN NOT EXISTS (SELECT 1 FROM "{_GRANT}" AS deletion_grant '
            'INNER JOIN "organizations_retentiondeletionplan" AS plan '
            'ON plan."id" = deletion_grant."plan_id" '
            'AND plan."organization_id" = deletion_grant."organization_id", '
            f"json_each(plan.\"candidate_public_ids\", '$.{retention_class}') AS candidate "
            'WHERE deletion_grant."organization_id" = OLD."organization_id" '
            'AND deletion_grant."active" = 1 '
            'AND deletion_grant."expires_at" > CURRENT_TIMESTAMP '
            'AND plan."dry_run" = 0 '
            "AND replace(CAST(candidate.value AS TEXT), '-', '') = "
            "replace(CAST(OLD.\"public_id\" AS TEXT), '-', '')) "
        )
    schema_editor.execute(
        f'CREATE TRIGGER "{trigger}" BEFORE DELETE ON "{table}" {when}'
        "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
    )


def _create_sqlite(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, child_id, parent, constraint in _RELATIONS:
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(
                f'CREATE TRIGGER "{constraint}_{operation.lower()}" '
                f'BEFORE {operation} ON "{child}" '
                f'WHEN NOT EXISTS (SELECT 1 FROM "{parent}" AS parent '
                'WHERE parent."organization_id" = NEW."organization_id" '
                f'AND parent."id" = NEW."{child_id}") '
                "BEGIN SELECT RAISE(ABORT, 'tenant relationship mismatch'); END"
            )
    for table, retention_class in _RETENTION_CLASS_BY_TABLE.items():
        _replace_sqlite_delete_trigger(
            schema_editor,
            table=table,
            retention_class=retention_class,
            governed=True,
        )
    for table in _NEW_IMMUTABLE_TABLES:
        for operation in ("UPDATE", "DELETE"):
            schema_editor.execute(
                f'CREATE TRIGGER "rp_{table}_immutable_{operation.lower()}" '
                f'BEFORE {operation} ON "{table}" '
                "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
            )


def create_m14_integrity(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        _create_postgresql(schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        _create_sqlite(schema_editor)
    else:
        raise RuntimeError("ReleaseProof operational controls require PostgreSQL or test SQLite")


def drop_m14_integrity(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        for table in _NEW_IMMUTABLE_TABLES:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable" ON "{table}"')
        schema_editor.execute(_postgresql_function(governed_delete=False))
        for child, _child_id, _parent, constraint in reversed(_RELATIONS):
            schema_editor.execute(f'ALTER TABLE "{child}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    elif schema_editor.connection.vendor == "sqlite":
        for table in _NEW_IMMUTABLE_TABLES:
            for operation in ("update", "delete"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable_{operation}"')
        for table in _TARGET_TABLES:
            _replace_sqlite_delete_trigger(
                schema_editor,
                table=table,
                retention_class=None,
                governed=False,
            )
        for _child, _child_id, _parent, constraint in _RELATIONS:
            for operation in ("insert", "update"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "{constraint}_{operation}"')


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0003_m3_tenant_integrity"),
        ("organizations", "0005_operationalpolicy_organizations_ops_policy_org_id_unique_and_more"),
        ("retrieval", "0002_tenant_integrity_and_indexes"),
        ("risk", "0004_m13_governance_integrity"),
        ("verification", "0007_differential_integrity"),
    ]
    operations = [migrations.RunPython(create_m14_integrity, drop_m14_integrity)]
