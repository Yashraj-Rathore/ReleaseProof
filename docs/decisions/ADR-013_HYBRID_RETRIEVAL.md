# ADR-013 — Hybrid Retrieval
**Status:** Accepted

Historical/context retrieval combines lexical and semantic candidates, followed by optional bounded cross-encoder reranking. Every result retains source/chunk/version provenance. RAG quality is evaluated on frozen fixtures; vector similarity alone is not treated as sufficient evidence.
