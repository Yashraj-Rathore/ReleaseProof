# 34 — M6 Retrieval Evaluation

## Scope and artifact identity

- Issues: `RP-0501..RP-0506`
- Evaluation schema: `m6-retrieval-eval-v1`
- Frozen fixture: `tests/fixtures/retrieval/m6_relevance_v1.json`
- Fixture SHA-256: `c6ec6c4473b264a027ca7ab9482a31ed0b2d9ea1f0d76a3247d76fc694ac9976`
- Raw artifact: `artifacts/evaluation/m6_retrieval_eval_v1.json`
- Artifact root SHA-256 contract:
  `f7e9009bdc7547b3fb677013b0f7752d5a28ea1071f92a17754d36af3d107b70`

The fixture contains eight CC0-1.0 synthetic evidence chunks and five synthetic graded queries.
It is designed to validate ingestion/ranking/evaluation mechanics. It is not customer or public
repository data and cannot support a product-quality claim.

## Exact retrieval configuration

- FTS: PostgreSQL `simple`, profile `postgres-simple-code-v1`
- Normalizer: `code-aware-normalizer-v1`
- Fusion: reciprocal-rank fusion `rrf-v1-k60`
- Evaluation embedding: `deterministic-hash-embedding-v1`, 384 dimensions, synthetic fake
- Selected real embedding: `sentence-transformers/all-MiniLM-L6-v2`, revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, 384 dimensions, Apache-2.0
- Selected real reranker: `cross-encoder/ms-marco-MiniLM-L6-v2`, revision
  `4bebbd56fc380a66525f95b03d4ec1a4b41a4f1e`, Apache-2.0

## Frozen synthetic measurements at K=3

| Variant | Recall@3 | MRR@3 | nDCG@3 |
|---|---:|---:|---:|
| Lexical | 0.90 | 1.00 | 0.950262129022 |
| Deterministic fake vector | 0.90 | 1.00 | 0.950262129022 |
| Hybrid RRF | 0.90 | 1.00 | 0.950262129022 |
| Deterministic fake reranked | 0.90 | 1.00 | 0.950262129022 |

The raw artifact contains every query ranking and relevance-derived metric. Equal aggregate results
mean this fixture provides no evidence that semantic search or reranking is superior to lexical
retrieval. The real reranker therefore stays disabled by default.

## Latency and size evidence

On the recorded Windows/Python 3.13.15 environment, 100 in-memory executions of the complete
five-query/four-variant synthetic suite recorded median 6.930450 ms, p95 7.680900 ms and minimum
6.620100 ms. This explicitly excludes PostgreSQL/network time and real transformer inference.
The fixture contains 1,123 text bytes and 3,072 fake-vector floats. Representative PostgreSQL
on-disk index size, end-to-end latency and real-model latency are **not yet measured**.

## Failure and privacy behavior

- Missing lexical/embedding profiles return explicit unavailable status.
- Missing/mismatched embedding provider keeps scoped lexical evidence.
- Reranker failure preserves deterministic hybrid ordering.
- Expired documents are filtered before ranking.
- Cross-tenant/repository service requests and database relationships fail closed.
- Repository text remains untrusted inert data; no query/source content is logged.
- Real adapters require checksum-verified local safetensors and never fetch weights implicitly.

## Reproduction

```text
uv run python -m eng.evaluate_m6_retrieval --check
uv run pytest tests/unit/test_retrieval_core.py tests/integration/test_retrieval_persistence.py tests/security/test_retrieval_tenancy.py
```

`--check` verifies the frozen configuration, rankings, metrics and artifact root hash, then reports
a fresh local timing sample without pretending timing is byte-deterministic.
