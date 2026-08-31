# 35 — M6 Owner Learning Note

## 1. Concept implemented

M6 implements repository-scoped retrieval-augmented evidence: approved source ingestion,
source-aware chunking, PostgreSQL lexical search, pgvector semantic candidates, reciprocal-rank
fusion, optional cross-encoder reranking, side-by-side index activation and frozen retrieval
evaluation.

## 2. Why it is used here

Risk scores explain current change properties but do not surface prior architectural decisions,
runbooks or similar historical evidence. Lexical search is strong for exact code identifiers;
embeddings can retrieve related wording; RRF combines ranks without pretending incomparable raw
scores share a calibrated scale. A cross-encoder can inspect query/document pairs more deeply, but
its latency and value must be measured before activation.

## 3. Algorithm and data assumptions

- Approved source content and relevance judgments are trustworthy metadata even though document
  text itself remains hostile/untrusted content.
- PostgreSQL `simple` tokenization plus code-aware identifier/path expansion preserves exact source
  names better than language stemming for the first corpus.
- Cosine similarity is meaningful only for vectors from the exact same model/revision/dimension.
- RRF uses ranks rather than raw lexical/vector scores and therefore avoids unsafe score scaling;
  K=60 is a fixed versioned hyperparameter, not a learned probability.
- Synthetic fake embeddings validate contracts and degradation behavior, not real semantic quality.
- Retrieval quality from eight fictional chunks cannot generalize to customer repositories.

## 4. Key code paths

- `packages/retrieval_core/`: validation, normalization, chunking, RRF, reranking and metrics.
- `apps/web/retrieval/models.py`: scoped immutable evidence and versioned index profiles.
- `apps/web/retrieval/services.py`: ingestion, build/switch, scoped FTS/vector retrieval and fallback.
- `adapters/retrieval/`: deterministic fakes and offline checksum-verified sentence-transformers.
- `eng/evaluate_m6_retrieval.py`: frozen ablations, metrics, latency evidence and artifact check.
- `artifacts/evaluation/m6_retrieval_eval_v1.json`: raw rankings and limitations.

## 5. Exact experiment/test to rerun

```text
uv run python -m eng.evaluate_m6_retrieval --check
uv run pytest tests/unit/test_retrieval_core.py tests/integration/test_retrieval_persistence.py tests/security/test_retrieval_tenancy.py
```

Inspect per-query rankings and confirm every source reference retains type, source ID/version and
chunk ID. Then inspect active/candidate profile rows to verify switching did not delete old vectors.

## 6. Likely interview question and answer

**Question:** Why combine PostgreSQL FTS and vectors with RRF instead of using vector similarity
alone?

**Answer:** Code retrieval needs exact identifiers and paths, where lexical search is often best,
while embeddings may help with paraphrases. Their raw scores are not directly comparable, so I use
a deterministic versioned reciprocal-rank fusion over tenant-filtered candidate lists and preserve
both component ranks/scores. The frozen synthetic fixture showed no aggregate improvement from the
fake semantic/reranked variants, so I did not claim superiority or enable the real reranker without
representative evidence.
