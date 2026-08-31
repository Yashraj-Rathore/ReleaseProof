"""Database tenant constraints, immutable rows, and M6 PostgreSQL physical indexes."""

from __future__ import annotations

from django.apps.registry import Apps
from django.db import migrations
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

_RELATIONS = (
    (
        "retrieval_knowledgedocument",
        ("organization_id", "repository_id"),
        "repositories_repository",
        ("organization_id", "id"),
        "rp_retrieval_document_repository_fk",
    ),
    (
        "retrieval_knowledgechunk",
        ("organization_id", "repository_id"),
        "repositories_repository",
        ("organization_id", "id"),
        "rp_retrieval_chunk_repository_fk",
    ),
    (
        "retrieval_knowledgechunk",
        ("organization_id", "repository_id", "document_id"),
        "retrieval_knowledgedocument",
        ("organization_id", "repository_id", "id"),
        "rp_retrieval_chunk_document_fk",
    ),
    (
        "retrieval_lexicalindexprofile",
        ("organization_id", "repository_id"),
        "repositories_repository",
        ("organization_id", "id"),
        "rp_retrieval_lexical_profile_repository_fk",
    ),
    (
        "retrieval_knowledgelexicalindex",
        ("organization_id", "repository_id"),
        "repositories_repository",
        ("organization_id", "id"),
        "rp_retrieval_lexical_repository_fk",
    ),
    (
        "retrieval_knowledgelexicalindex",
        ("organization_id", "repository_id", "chunk_id"),
        "retrieval_knowledgechunk",
        ("organization_id", "repository_id", "id"),
        "rp_retrieval_lexical_chunk_fk",
    ),
    (
        "retrieval_knowledgelexicalindex",
        ("organization_id", "repository_id", "profile_id"),
        "retrieval_lexicalindexprofile",
        ("organization_id", "repository_id", "id"),
        "rp_retrieval_lexical_profile_fk",
    ),
    (
        "retrieval_embeddingindexprofile",
        ("organization_id", "repository_id"),
        "repositories_repository",
        ("organization_id", "id"),
        "rp_retrieval_embedding_profile_repository_fk",
    ),
    (
        "retrieval_knowledgeembedding384",
        ("organization_id", "repository_id"),
        "repositories_repository",
        ("organization_id", "id"),
        "rp_retrieval_embedding_repository_fk",
    ),
    (
        "retrieval_knowledgeembedding384",
        ("organization_id", "repository_id", "chunk_id"),
        "retrieval_knowledgechunk",
        ("organization_id", "repository_id", "id"),
        "rp_retrieval_embedding_chunk_fk",
    ),
    (
        "retrieval_knowledgeembedding384",
        ("organization_id", "repository_id", "profile_id"),
        "retrieval_embeddingindexprofile",
        ("organization_id", "repository_id", "id"),
        "rp_retrieval_embedding_profile_fk",
    ),
)
_IMMUTABLE_TABLES = (
    "retrieval_knowledgedocument",
    "retrieval_knowledgechunk",
    "retrieval_knowledgelexicalindex",
    "retrieval_knowledgeembedding384",
)
_LEXICAL_INDEX = "retrieval_lexical_search_gin_v1"
_EMBEDDING_INDEX = "retrieval_embedding384_cosine_hnsw_v1"


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
    schema_editor.execute(
        f'CREATE INDEX "{_LEXICAL_INDEX}" '
        'ON "retrieval_knowledgelexicalindex" USING gin ("search_vector") '
        'WHERE "search_vector" IS NOT NULL'
    )
    schema_editor.execute(
        f'CREATE INDEX "{_EMBEDDING_INDEX}" '
        'ON "retrieval_knowledgeembedding384" USING hnsw ("vector" vector_cosine_ops) '
        "WITH (m = 16, ef_construction = 64)"
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


def create_retrieval_integrity_controls(
    apps: Apps,
    schema_editor: BaseDatabaseSchemaEditor,
) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        _create_postgresql(schema_editor)
    elif schema_editor.connection.vendor == "sqlite":
        _create_sqlite(schema_editor)
    else:
        raise RuntimeError("ReleaseProof retrieval constraints require PostgreSQL or test SQLite")


def drop_retrieval_integrity_controls(
    apps: Apps,
    schema_editor: BaseDatabaseSchemaEditor,
) -> None:
    del apps
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(f'DROP INDEX IF EXISTS "{_EMBEDDING_INDEX}"')
        schema_editor.execute(f'DROP INDEX IF EXISTS "{_LEXICAL_INDEX}"')
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
        ("analysis", "0003_m3_tenant_integrity"),
        ("retrieval", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(
            create_retrieval_integrity_controls,
            drop_retrieval_integrity_controls,
        )
    ]
