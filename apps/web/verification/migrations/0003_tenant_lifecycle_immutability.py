"""Database tenant, append-only, and M8 lifecycle enforcement."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_PROPOSAL = "verification_generatedtestproposal"
_EVENT = "verification_proposallifecycleevent"
_RELATIONS = (
    (
        _PROPOSAL,
        ("organization_id", "source_llm_evidence_id"),
        "evidence_evidenceitem",
        ("organization_id", "id"),
        "rp_proposal_source_org_fk",
        True,
    ),
    (
        _PROPOSAL,
        ("organization_id", "parent_proposal_id"),
        _PROPOSAL,
        ("organization_id", "id"),
        "rp_proposal_parent_org_fk",
        False,
    ),
    (
        _EVENT,
        ("organization_id", "proposal_id"),
        _PROPOSAL,
        ("organization_id", "id"),
        "rp_proposal_event_org_fk",
        True,
    ),
)
_LIFECYCLE_FUNCTION = "releaseproof_validate_proposal_event"
_LIFECYCLE_TRIGGER = "rp_proposal_event_lifecycle"


def _create_postgresql(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, child_columns, parent, parent_columns, constraint, _required in _RELATIONS:
        child_sql = ", ".join(f'"{column}"' for column in child_columns)
        parent_sql = ", ".join(f'"{column}"' for column in parent_columns)
        schema_editor.execute(
            f'ALTER TABLE "{child}" ADD CONSTRAINT "{constraint}" '
            f'FOREIGN KEY ({child_sql}) REFERENCES "{parent}" ({parent_sql}) '
            "DEFERRABLE INITIALLY IMMEDIATE"
        )
    for table in (_PROPOSAL, _EVENT):
        schema_editor.execute(
            f'CREATE TRIGGER "rp_{table}_immutable" '
            f'BEFORE UPDATE OR DELETE ON "{table}" FOR EACH ROW '
            "EXECUTE FUNCTION releaseproof_reject_immutable()"
        )
    schema_editor.execute(
        f"""
        CREATE FUNCTION {_LIFECYCLE_FUNCTION}() RETURNS trigger AS $$
        DECLARE
            prior_lifecycle text;
            prior_sequence integer;
            proposal_valid boolean;
        BEGIN
            SELECT to_lifecycle, sequence
              INTO prior_lifecycle, prior_sequence
              FROM {_EVENT}
             WHERE proposal_id = NEW.proposal_id
             ORDER BY sequence DESC
             LIMIT 1;

            IF prior_sequence IS NULL THEN
                IF NEW.sequence <> 0 OR NEW.from_lifecycle IS NOT NULL
                   OR NEW.to_lifecycle <> 'draft' THEN
                    RAISE EXCEPTION 'invalid initial proposal lifecycle';
                END IF;
            ELSE
                IF NEW.sequence <> prior_sequence + 1
                   OR NEW.from_lifecycle IS DISTINCT FROM prior_lifecycle THEN
                    RAISE EXCEPTION 'proposal lifecycle sequence mismatch';
                END IF;
                IF NOT (
                    (prior_lifecycle = 'draft' AND NEW.to_lifecycle IN
                        ('accepted_for_export', 'rejected', 'superseded'))
                    OR (prior_lifecycle IN ('accepted_for_export', 'rejected')
                        AND NEW.to_lifecycle = 'superseded')
                ) THEN
                    RAISE EXCEPTION 'proposal lifecycle transition is not allowed';
                END IF;
            END IF;

            IF NEW.to_lifecycle = 'accepted_for_export' THEN
                SELECT COALESCE((validation_report ->> 'valid')::boolean, false)
                  INTO proposal_valid
                  FROM {_PROPOSAL}
                 WHERE id = NEW.proposal_id;
                IF proposal_valid IS NOT TRUE THEN
                    RAISE EXCEPTION 'invalid proposal cannot be accepted';
                END IF;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    schema_editor.execute(
        f'CREATE TRIGGER "{_LIFECYCLE_TRIGGER}" BEFORE INSERT ON "{_EVENT}" '
        f"FOR EACH ROW EXECUTE FUNCTION {_LIFECYCLE_FUNCTION}()"
    )


def _create_sqlite(schema_editor: BaseDatabaseSchemaEditor) -> None:
    for child, child_columns, parent, parent_columns, constraint, required in _RELATIONS:
        predicate = " AND ".join(
            f'parent."{parent_column}" = NEW."{child_column}"'
            for child_column, parent_column in zip(child_columns, parent_columns, strict=True)
        )
        null_guard = "" if required else 'NEW."parent_proposal_id" IS NOT NULL AND '
        for operation in ("INSERT", "UPDATE"):
            schema_editor.execute(
                f'CREATE TRIGGER "{constraint}_{operation.lower()}" '
                f'BEFORE {operation} ON "{child}" '
                f"WHEN {null_guard}NOT EXISTS ("
                f'SELECT 1 FROM "{parent}" AS parent WHERE {predicate}) '
                "BEGIN SELECT RAISE(ABORT, 'tenant relationship mismatch'); END"
            )
    for table in (_PROPOSAL, _EVENT):
        for operation in ("UPDATE", "DELETE"):
            schema_editor.execute(
                f'CREATE TRIGGER "rp_{table}_immutable_{operation.lower()}" '
                f'BEFORE {operation} ON "{table}" '
                "BEGIN SELECT RAISE(ABORT, 'immutable ReleaseProof record'); END"
            )
    schema_editor.execute(
        f"""
        CREATE TRIGGER "{_LIFECYCLE_TRIGGER}"
        BEFORE INSERT ON "{_EVENT}"
        WHEN NOT (
            (
                NEW."sequence" = 0
                AND NEW."from_lifecycle" IS NULL
                AND NEW."to_lifecycle" = 'draft'
                AND NOT EXISTS (
                    SELECT 1 FROM "{_EVENT}" AS prior
                    WHERE prior."proposal_id" = NEW."proposal_id"
                )
            )
            OR (
                NEW."sequence" > 0
                AND EXISTS (
                    SELECT 1 FROM "{_EVENT}" AS prior
                    WHERE prior."proposal_id" = NEW."proposal_id"
                      AND prior."sequence" = NEW."sequence" - 1
                      AND prior."to_lifecycle" = NEW."from_lifecycle"
                      AND (
                          (prior."to_lifecycle" = 'draft' AND NEW."to_lifecycle" IN
                              ('accepted_for_export', 'rejected', 'superseded'))
                          OR (prior."to_lifecycle" IN ('accepted_for_export', 'rejected')
                              AND NEW."to_lifecycle" = 'superseded')
                      )
                )
                AND (
                    NEW."to_lifecycle" <> 'accepted_for_export'
                    OR EXISTS (
                        SELECT 1 FROM "{_PROPOSAL}" AS proposal
                        WHERE proposal."id" = NEW."proposal_id"
                          AND json_extract(proposal."validation_report", '$.valid') = 1
                    )
                )
            )
        )
        BEGIN SELECT RAISE(ABORT, 'invalid proposal lifecycle transition'); END
        """
    )


def create_m8_integrity_controls(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        _create_postgresql(schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        _create_sqlite(schema_editor)
    else:
        raise RuntimeError("ReleaseProof proposal constraints require PostgreSQL or test SQLite")


def drop_m8_integrity_controls(apps: Apps, schema_editor: BaseDatabaseSchemaEditor) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{_LIFECYCLE_TRIGGER}" ON "{_EVENT}"')
        schema_editor.execute(f"DROP FUNCTION IF EXISTS {_LIFECYCLE_FUNCTION}()")
        for table in (_PROPOSAL, _EVENT):
            schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable" ON "{table}"')
        for child, _child_columns, _parent, _parent_columns, constraint, _required in reversed(
            _RELATIONS
        ):
            schema_editor.execute(f'ALTER TABLE "{child}" DROP CONSTRAINT IF EXISTS "{constraint}"')
    elif schema_editor.connection.vendor == "sqlite":
        schema_editor.execute(f'DROP TRIGGER IF EXISTS "{_LIFECYCLE_TRIGGER}"')
        for table in (_PROPOSAL, _EVENT):
            for operation in ("update", "delete"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "rp_{table}_immutable_{operation}"')
        for _child, _child_columns, _parent, _parent_columns, constraint, _required in _RELATIONS:
            for operation in ("insert", "update"):
                schema_editor.execute(f'DROP TRIGGER IF EXISTS "{constraint}_{operation}"')


class Migration(migrations.Migration):
    dependencies = [
        ("analysis", "0002_tenant_integrity"),
        ("verification", "0002_generatedtestproposal_verification_proposal_schema_v1_and_more"),
    ]
    operations = [
        migrations.RunPython(
            create_m8_integrity_controls,
            drop_m8_integrity_controls,
        )
    ]
