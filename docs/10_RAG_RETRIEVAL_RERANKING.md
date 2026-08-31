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

## Implemented M6 contracts and evidence

- Ingestion accepts only explicitly approved bounded inert content. `source-aware-chunker-v1`
  splits Markdown by headings, Python with `ast` function/class boundaries and unsupported input
  with a bounded fallback; it never imports or executes repository code.
- Lexical profile `postgres-simple-code-v1` uses PostgreSQL configuration `simple` and
  `code-aware-normalizer-v1`, retaining complete lower-cased identifiers/path tokens plus
  camelCase/snake/path components. A GIN index is created by a forward PostgreSQL migration.
- The first semantic physical contract is `retrieval_knowledgeembedding384` with cosine HNSW index
  `retrieval_embedding384_cosine_hnsw_v1`. The selected embedding is
  `sentence-transformers/all-MiniLM-L6-v2` revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, 384 dimensions, Apache-2.0, safetensors SHA-256
  `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db`.
- Hybrid profile `rrf-v1-k60` combines bounded lexical and vector rankings and exposes original
  component scores/ranks. Semantic absence or incompatibility degrades explicitly to lexical
  evidence.
- The optional reranker is `cross-encoder/ms-marco-MiniLM-L6-v2` revision
  `4bebbd56fc380a66525f95b03d4ec1a4b41a4f1e`, Apache-2.0, safetensors SHA-256
  `821d1aa69520101d6e0737f78a042ae25b19e5cb9160701909d10434f4aeb0ae`. It receives at most 50
  candidates and falls back to RRF on provider failure.
- Neither real artifact is downloaded implicitly. The local adapter requires an explicitly
  provisioned checksum-verified safetensors cache and disables remote code. Offline tests/demo use
  a separately named deterministic fake.
- `m6-relevance-fixture-v1` has eight synthetic chunks and five synthetic graded queries. At K=3,
  lexical, fake-vector, hybrid and fake-reranked variants all record Recall 0.90, MRR 1.00 and nDCG
  0.950262129022. The equality provides no evidence that semantic or reranked retrieval is better,
  so the real reranker remains disabled by default. Full raw rankings and local timing evidence are
  in `artifacts/evaluation/m6_retrieval_eval_v1.json` and docs/34.
