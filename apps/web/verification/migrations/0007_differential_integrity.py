"""Database tenant binding and append-only enforcement for M10 evidence."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_PLAN = "verification_differentialplan"
_RUN = "verification_differentialrun"
_RECOMMENDATION = "verification_recommendationdecision"
_EXECUTION_PLAN = "verification_executionplan"
_EXECUTION_APPROVAL = "verification_executionapproval"
_SNAPSHOT = "changes_pullrequestsnapshot"
_RELATIONS = (
    (_PLAN, "source_execution_plan_id", _EXECUTION_PLAN, "rp_diff_plan_execution_org_fk"),
    (_PLAN, "source_approval_id", _EXECUTION_APPROVAL, "rp_diff_plan_approval_org_fk"),
    (_RUN, "plan_id", _PLAN, "rp_diff_run_plan_org_fk"),
    (_RECOMMENDATION, "differential_run_id", _RUN, "rp_rec_diff_run_org_fk"),
    (_RECOMMENDATION, "snapshot_id", _SNAPSHOT, "rp_rec_snapshot_org_fk"),
)
_TABLES = (_PLAN, _RUN, _RECOMMENDATION)


def _create_postgresql(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, child_id, parent, constraint in _RELATIONS:
        schema_editor.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT "{constraint}" '
            f'FOREIGN KEY ("organization_id", "{child_id}") '
            f'REFERENCES "{parent}" ("organization_id", "id") DEFERRABLE INITIALLY IMMEDIATE'
        )
    for table in _TABLES:
        schema_editor.execute(
            f'CREATE TRIGGER "rp_{table}_immutable" BEFORE UPDATE OR DELETE ON "{table}" '
            "FOR EACH ROW EXECUTE FUNCTION releaseproof_reject_immutable()"
        )
    schema_editor.execute(
        f"""
        CREATE FUNCTION releaseproof_validate_differential_plan() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM {_EXECUTION_APPROVAL} AS approval
                WHERE approval.id = NEW.source_approval_id
                  AND approval.plan_id = NEW.source_execution_plan_id
                  AND approval.organization_id = NEW.organization_id
            ) THEN
                RAISE EXCEPTION 'differential plan approval mismatch';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    schema_editor.execute(
        f"CREATE TRIGGER rp_differential_plan_binding BEFORE INSERT ON {_PLAN} "
        "FOR EACH ROW EXECUTE FUNCTION releaseproof_validate_differential_plan()"
    )
    schema_editor.execute(
        f"""
        CREATE FUNCTION releaseproof_validate_recommendation() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM {_RUN} AS run
                JOIN {_PLAN} AS plan ON plan.id = run.plan_id
                JOIN {_EXECUTION_PLAN} AS execution_plan
                  ON execution_plan.id = plan.source_execution_plan_id
                WHERE run.id = NEW.differential_run_id
                  AND run.organization_id = NEW.organization_id
                  AND execution_plan.snapshot_id = NEW.snapshot_id
            ) THEN
                RAISE EXCEPTION 'recommendation snapshot mismatch';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    schema_editor.execute(
        f"CREATE TRIGGER rp_recommendation_binding BEFORE INSERT ON {_RECOMMENDATION} "
        "FOR EACH ROW EXECUTE FUNCTION releaseproof_validate_recommendation()"
    )


def _create_sqlite(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, child_id, parent, constraint in _RELATIONS:
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(
                f'CREATE TRIGGER "{constraint}_{operation.lower()}" BEFORE {operation} ON "{child}" '
                f'WHEN NOT EXISTS (SELECT 1 FROM "{parent}" AS parent '
                f'WHERE parent."organization_id" = NEW."organization_id" '
                f'AND parent."id" = NEW."{child_id}") '
                "BEGIN SELECT RAISE(ABORT, 'tenant relationship mismatch'); END"
            )
    for table in _TABLES:
        for operation in ("UPDATE", "DELETE"):
            schema_editor.execute(
                f'CREATE TRIGGER "rp_{table}_immutable_{operation.lower()}" '
                f'BEFORE {operation} ON "{table}" '
                "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
            )
    schema_editor.execute(
        f"""
        CREATE TRIGGER rp_differential_plan_binding BEFORE INSERT ON "{_PLAN}"
        WHEN NOT EXISTS (
            SELECT 1 FROM "{_EXECUTION_APPROVAL}" AS approval
            WHERE approval."id" = NEW."source_approval_id"
              AND approval."plan_id" = NEW."source_execution_plan_id"
              AND approval."organization_id" = NEW."organization_id"
        ) BEGIN SELECT RAISE(ABORT, 'differential plan approval mismatch'); END
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER rp_recommendation_binding BEFORE INSERT ON "{_RECOMMENDATION}"
        WHEN NOT EXISTS (
            SELECT 1 FROM "{_RUN}" AS run
            JOIN "{_PLAN}" AS plan ON plan."id" = run."plan_id"
            JOIN "{_EXECUTION_PLAN}" AS execution_plan
              ON execution_plan."id" = plan."source_execution_plan_id"
            WHERE run."id" = NEW."differential_run_id"
              AND run."organization_id" = NEW."organization_id"
              AND execution_plan."snapshot_id" = NEW."snapshot_id"
        ) BEGIN SELECT RAISE(ABORT, 'recommendation snapshot mismatch'); END
        """
    )


def create_differential_integrity(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        _create_postgresql(schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        _create_sqlite(schema_editor)
    else:
        raise RuntimeError("ReleaseProof M10 constraints require PostgreSQL or test SQLite")


def drop_differential_integrity(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(
            f'DROP TRIGGER IF EXISTS rp_recommendation_binding ON "{_RECOMMENDATION}"'
        )
        schema_editor.execute(f'DROP TRIGGER IF EXISTS rp_differential_plan_binding ON "{_PLAN}"')
        schema_editor.execute("DROP FUNCTION IF EXISTS releaseproof_validate_recommendation()")
        schema_editor.execute("DROP FUNCTION IF EXISTS releaseproof_validate_differential_plan()")
        for table in _TABLES:
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable" ON "{table}"')
        for child, _child_id, _parent, constraint in reversed(_RELATIONS):
            schema_editor.execute(f'ALTER TABLE "{child}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    elif schema_editor.connection.vendor == "sqlite":
        schema_editor.execute("DROP TRIGGER IF EXISTS rp_recommendation_binding")
        schema_editor.execute("DROP TRIGGER IF EXISTS rp_differential_plan_binding")
        for table in _TABLES:
            for operation in ("update", "delete"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable_{operation}"')
        for _child, _child_id, _parent, constraint in _RELATIONS:
            for operation in ("insert", "update"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "{constraint}_{operation}"')


class Migration(migrations.Migration):
    dependencies = [("verification", "0006_differentialplan_differentialrun_and_more")]
    operations = [migrations.RunPython(create_differential_integrity, drop_differential_integrity)]
