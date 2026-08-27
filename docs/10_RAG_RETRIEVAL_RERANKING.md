# 10 — RAG, Retrieval and Reranking

## Objective
Retrieve organization/repository-specific evidence: architecture docs, ADRs, runbooks, prior PR summaries, tests and selected issue/postmortem records.

## Ingestion
Fetch allowed inert content -> normalize -> source-aware chunk -> PostgreSQL FTS -> exact-version embedding -> pgvector. Every chunk has org/repo/source/version/hash/retention metadata.

Chunking:
- Markdown heading-aware
- Python code AST function/class where possible
- PR summary/changed evidence separately
- bounded fallbacks for unsupported source

## Hybrid retrieval
- lexical/FTS candidates; v1 uses PostgreSQL's `simple` text-search configuration plus versioned code-aware identifier/path normalization so stemming does not destroy source identifiers
- pgvector semantic candidates
- documented fusion such as RRF
- optional bounded cross-encoder reranker using sentence-transformers/HF

Every vector/FTS query is tenant/repository scoped.

## Evaluation
Frozen query/relevance corpus. Measure Recall@K, MRR, nDCG where graded relevance exists, latency and index size. Compare lexical-only, vector-only, hybrid and reranked variants. If reranker adds no measured value, keep it disabled.

## Grounding
LLM receives only allowed retrieved evidence and must cite source/evidence IDs. Unsupported claims become hypotheses/uncertainty.

## Versioning
FTS configuration/normalizer, embedding model/revision/dimension, chunk strategy, fusion and reranker are versioned. RP-0503 selects the first exact embedding artifact and dimension; no dimension is guessed during the foundation. Each incompatible dimension gets a separate physical vector index. New lexical/embedding versions build beside the active index and switch only after isolation, compatibility and retrieval evaluation pass.

## Why pgvector first
Transactions + relational scope filters + operational simplicity. Dedicated vector DB only after measured scale/latency need.
