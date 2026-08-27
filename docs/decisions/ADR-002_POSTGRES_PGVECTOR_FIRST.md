# ADR-002 — PostgreSQL + pgvector First
**Status:** Accepted

PostgreSQL is the system of record and first retrieval store. PostgreSQL full-text search provides lexical retrieval and pgvector provides semantic retrieval. Do not introduce Pinecone, Weaviate, Milvus, Elasticsearch, or another vector/search platform until the existing design has a measured limitation and a benchmark demonstrates a benefit.
