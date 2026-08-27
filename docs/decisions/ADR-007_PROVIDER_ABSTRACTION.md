# ADR-007 — Provider Abstraction
**Status:** Accepted

LLMs, embeddings, rerankers, object storage, GitHub, and model serving sit behind explicit contracts with deterministic fakes. Provider-specific SDK types do not leak into core domain contracts. At least one complete path must run locally without a paid provider.
