"""Database tenant binding and append-only enforcement for M9 evidence."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_PLAN = "verification_executionplan"
_APPROVAL = "verification_executionapproval"
_RUN = "verification_executionrun"
_RELATIONS = (
    (_PLAN, "proposal_id", "verification_generatedtestproposal", "rp_plan_proposal_org_fk"),
    (_PLAN, "snapshot_id", "changes_pullrequestsnapshot", "rp_plan_snapshot_org_fk"),
    (_APPROVAL, "plan_id", _PLAN, "rp_approval_plan_org_fk"),
    (_RUN, "plan_id", _PLAN, "rp_run_plan_org_fk"),
    (_RUN, "approval_id", _APPROVAL, "rp_run_approval_org_fk"),
)


def _create_postgresql(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, child_id, parent, constraint in _RELATIONS:
        schema_editor.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT "{constraint}" '
            f'FOREIGN KEY ("organization_id", "{child_id}") '
            f'REFERENCES "{parent}" ("organization_id", "id") DEFERRABLE INITIALLY IMMEDIATE'
        )
    for table in (_PLAN, _APPROVAL, _RUN):
        schema_editor.execute(
            f'CREATE TRIGGER "rp_{table}_immutable" BEFORE UPDATE OR DELETE ON "{table}" '
            "FOR EACH ROW EXECUTE FUNCTION releaseproof_reject_immutable()"
        )
    schema_editor.execute(
        f"""
        CREATE FUNCTION releaseproof_validate_execution_approval() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM {_PLAN} AS plan
                WHERE plan.id = NEW.plan_id
                  AND plan.organization_id = NEW.organization_id
                  AND plan.snapshot_head_sha = NEW.snapshot_head_sha
                  AND plan.proposal_hash = NEW.proposal_hash
                  AND plan.plan_hash = NEW.plan_hash
            ) THEN
                RAISE EXCEPTION 'execution approval binding mismatch';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    schema_editor.execute(
        f"CREATE TRIGGER rp_execution_approval_binding BEFORE INSERT ON {_APPROVAL} "
        "FOR EACH ROW EXECUTE FUNCTION releaseproof_validate_execution_approval()"
    )
    schema_editor.execute(
        f"""
        CREATE FUNCTION releaseproof_validate_execution_run() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM {_APPROVAL} AS approval
                WHERE approval.id = NEW.approval_id
                  AND approval.plan_id = NEW.plan_id
                  AND approval.organization_id = NEW.organization_id
            ) THEN
                RAISE EXCEPTION 'execution run approval mismatch';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    schema_editor.execute(
        f"CREATE TRIGGER rp_execution_run_binding BEFORE INSERT ON {_RUN} "
        "FOR EACH ROW EXECUTE FUNCTION releaseproof_validate_execution_run()"
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
    for table in (_PLAN, _APPROVAL, _RUN):
        for operation in ("UPDATE", "DELETE"):
            schema_editor.execute(
                f'CREATE TRIGGER "rp_{table}_immutable_{operation.lower()}" '
                f'BEFORE {operation} ON "{table}" '
                "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
            )
    schema_editor.execute(
        f"""
        CREATE TRIGGER rp_execution_approval_binding BEFORE INSERT ON "{_APPROVAL}"
        WHEN NOT EXISTS (
            SELECT 1 FROM "{_PLAN}" AS plan
            WHERE plan."id" = NEW."plan_id"
              AND plan."organization_id" = NEW."organization_id"
              AND plan."snapshot_head_sha" = NEW."snapshot_head_sha"
              AND plan."proposal_hash" = NEW."proposal_hash"
              AND plan."plan_hash" = NEW."plan_hash"
        ) BEGIN SELECT RAISE(ABORT, 'execution approval binding mismatch'); END
        """
    )
    schema_editor.execute(
        f"""
        CREATE TRIGGER rp_execution_run_binding BEFORE INSERT ON "{_RUN}"
        WHEN NOT EXISTS (
            SELECT 1 FROM "{_APPROVAL}" AS approval
            WHERE approval."id" = NEW."approval_id"
              AND approval."plan_id" = NEW."plan_id"
              AND approval."organization_id" = NEW."organization_id"
        ) BEGIN SELECT RAISE(ABORT, 'execution run approval mismatch'); END
        """
    )


def create_execution_integrity(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        _create_postgresql(schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        _create_sqlite(schema_editor)
    else:
        raise RuntimeError("ReleaseProof execution constraints require PostgreSQL or test SQLite")


def drop_execution_integrity(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f'DROP TRIGGER IF EXISTS rp_execution_run_binding ON "{_RUN}"')
        schema_editor.execute(
            f'DROP TRIGGER IF EXISTS rp_execution_approval_binding ON "{_APPROVAL}"'
        )
        schema_editor.execute("DROP FUNCTION IF EXISTS releaseproof_validate_execution_run()")
        schema_editor.execute("DROP FUNCTION IF EXISTS releaseproof_validate_execution_approval()")
        for table in (_PLAN, _APPROVAL, _RUN):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable" ON "{table}"')
        for child, _child_id, _parent, constraint in reversed(_RELATIONS):
            schema_editor.execute(f'ALTER TABLE "{child}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    elif schema_editor.connection.vendor == "sqlite":
        schema_editor.execute("DROP TRIGGER IF EXISTS rp_execution_run_binding")
        schema_editor.execute("DROP TRIGGER IF EXISTS rp_execution_approval_binding")
        for table in (_PLAN, _APPROVAL, _RUN):
            for operation in ("update", "delete"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable_{operation}"')
        for _child, _child_id, _parent, constraint in _RELATIONS:
            for operation in ("insert", "update"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "{constraint}_{operation}"')


class Migration(migrations.Migration):
    dependencies = [("verification", "0004_executionplan_executionapproval_executionrun_and_more")]
    operations = [migrations.RunPython(create_execution_integrity, drop_execution_integrity)]
